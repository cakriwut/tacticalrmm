#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["paramiko>=3.4", "rich>=13"]
# ///
"""
Apply self-hosted agent server changes to the TacticalRMM server.

Changes:
  1. Add AGENT_BASE_URL to .env
  2. Patch docker-compose.yml:
     a. Change tactical services to ghcr.io/cakriwut/tactical:latest
     b. Add AGENT_BASE_URL to tactical-init and tactical-backend environments
     c. Add trmm-agent-server service
     d. Add agent-server nginx conf mount to trmm-nginx
     e. Add agent_server_data volume
  3. Write agents.s2t.ai nginx conf into /opt/tactical/agents.conf
  4. Pull new images and restart containers
"""
import base64
import os
import sys
import time

import paramiko
from rich.console import Console

console = Console()

HOST = "45.159.220.200"
USER = "tactical"
KEY = "~/.ssh/id_rsa"
TACTICAL_DIR = "/opt/tactical"

AGENT_BASE_URL = "https://agents.s2t.ai"

AGENT_SERVER_SERVICE = """\
  # self-hosted agent distribution server
  tactical-agent-server:
    container_name: trmm-agent-server
    image: ghcr.io/cakriwut/agent-server:latest
    restart: always
    environment:
      GITHUB_REPO: cakriwut/rmmagent
      BINARY_CACHE_DIR: /data/agents
    volumes:
      - agent_server_data:/data/agents
    networks:
      - proxy
"""

AGENTS_NGINX_CONF = """\
# agents.s2t.ai — self-hosted TRMM agent distribution server
server {
    resolver 127.0.0.11 valid=30s;

    listen 4443 ssl;
    server_name agents.s2t.ai;

    ssl_certificate /opt/tactical/certs/fullchain.pem;
    ssl_certificate_key /opt/tactical/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers EECDH+AESGCM:EDH+AESGCM;

    location / {
        set $agentserver http://trmm-agent-server:8000;
        proxy_pass $agentserver;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}

server {
    listen 8080;
    server_name agents.s2t.ai;
    return 301 https://$server_name$request_uri;
}
"""


def run(client: paramiko.SSHClient, cmd: str, check: bool = True) -> str:
    console.print(f"[dim]$ {cmd}[/dim]")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    rc = stdout.channel.recv_exit_status()
    if out.strip():
        console.print(out.strip())
    if err.strip():
        console.print(f"[yellow]{err.strip()}[/yellow]")
    if check and rc != 0:
        console.print(f"[red]Command failed (rc={rc})[/red]")
        sys.exit(1)
    return out


def write_remote_file(client: paramiko.SSHClient, path: str, content: str, sudo: bool = False) -> None:
    encoded = base64.b64encode(content.encode()).decode()
    # Split into 60KB chunks: base64-encoded content passed via `echo '...'` is
    # subject to ARG_MAX (~2MB on Linux), but some SSH implementations are tighter.
    chunk_size = 60000
    if len(encoded) <= chunk_size:
        if sudo:
            run(client, f"echo '{encoded}' | base64 -d | sudo tee {path} > /dev/null")
        else:
            run(client, f"echo '{encoded}' | base64 -d > {path}")
    else:
        first = True
        for i in range(0, len(encoded), chunk_size):
            chunk = encoded[i:i + chunk_size]
            if sudo:
                append_flag = "" if first else "-a"
                run(client, f"echo '{chunk}' | base64 -d | sudo tee {append_flag} {path} > /dev/null")
            else:
                redirect = ">" if first else ">>"
                run(client, f"echo '{chunk}' | base64 -d {redirect} {path}")
            first = False


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, key_filename=os.path.expanduser(KEY))
    console.print(f"[green]Connected to {HOST}[/green]")
    return client


def main():
    client = connect()

    console.rule("[bold]Step 1: Update .env[/bold]")
    env_content = run(client, f"cat {TACTICAL_DIR}/.env")
    if "AGENT_BASE_URL" not in env_content:
        run(client, f"echo 'AGENT_BASE_URL={AGENT_BASE_URL}' >> {TACTICAL_DIR}/.env")
        console.print("[green]AGENT_BASE_URL added to .env[/green]")
    else:
        current_url = [
            line.split("=", 1)[1].strip()
            for line in env_content.splitlines()
            if line.startswith("AGENT_BASE_URL=")
        ]
        if current_url and current_url[0] != AGENT_BASE_URL:
            run(client, f"sed -i 's|^AGENT_BASE_URL=.*|AGENT_BASE_URL={AGENT_BASE_URL}|' {TACTICAL_DIR}/.env")
            console.print(f"[green]AGENT_BASE_URL updated to {AGENT_BASE_URL}[/green]")
        else:
            console.print(f"[yellow]AGENT_BASE_URL already set to {AGENT_BASE_URL}[/yellow]")

    console.rule("[bold]Step 2: Write agents.s2t.ai nginx conf[/bold]")
    existing = run(client, f"cat {TACTICAL_DIR}/agents.conf 2>/dev/null || echo __MISSING__", check=False)
    if "agents.s2t.ai" in existing:
        console.print("[yellow]agents.conf already exists[/yellow]")
    else:
        run(client, f"cp {TACTICAL_DIR}/agents.conf {TACTICAL_DIR}/agents.conf.bak 2>/dev/null || true", check=False)
        write_remote_file(client, f"{TACTICAL_DIR}/agents.conf", AGENTS_NGINX_CONF)
        console.print("[green]agents.conf written to /opt/tactical/agents.conf[/green]")

    console.rule("[bold]Step 3: Patch docker-compose.yml[/bold]")
    compose = run(client, f"cat {TACTICAL_DIR}/docker-compose.yml")
    patched = compose

    # 3a. Change tactical image to ghcr.io/cakriwut for all tactical services
    if "ghcr.io/cakriwut/tactical" not in patched:
        patched = patched.replace(
            "image: ${IMAGE_REPO}tactical:${VERSION}",
            "image: ghcr.io/cakriwut/tactical:latest"
        )
        console.print("[green]Tactical image → ghcr.io/cakriwut/tactical:latest[/green]")

    # 3b. Add AGENT_BASE_URL to tactical-init environment
    if "AGENT_BASE_URL" not in patched:
        patched = patched.replace(
            "      TRMM_DISABLE_SSO: ${TRMM_DISABLE_SSO}",
            "      TRMM_DISABLE_SSO: ${TRMM_DISABLE_SSO}\n      AGENT_BASE_URL: ${AGENT_BASE_URL}"
        )
        console.print("[green]AGENT_BASE_URL added to tactical-init environment[/green]")

    # 3c. Add AGENT_BASE_URL to tactical-backend (no env block yet, add one)
    #     Insert environment block before `depends_on` in tactical-backend section
    if "tactical-backend:" in patched and "AGENT_BASE_URL" not in patched.split("tactical-backend:")[1].split("tactical-websockets:")[0]:
        patched = patched.replace(
            "  # container for django backend\n  tactical-backend:\n    container_name: trmm-backend\n    image: ghcr.io/cakriwut/tactical:latest\n    user: 1000:1000\n    command: [\"tactical-backend\"]\n    restart: always\n    networks:",
            "  # container for django backend\n  tactical-backend:\n    container_name: trmm-backend\n    image: ghcr.io/cakriwut/tactical:latest\n    user: 1000:1000\n    command: [\"tactical-backend\"]\n    restart: always\n    environment:\n      AGENT_BASE_URL: ${AGENT_BASE_URL}\n    networks:"
        )
        console.print("[green]AGENT_BASE_URL added to tactical-backend environment[/green]")

    # 3d. Add nginx bind mount for agents.conf
    nginx_mount = "      - /opt/tactical/agents.conf:/etc/nginx/conf.d/agents.conf:ro"
    if "agents.conf" not in patched:
        patched = patched.replace(
            "      - tactical_data:/opt/tactical\n\n  # container for celery worker service",
            f"      - tactical_data:/opt/tactical\n{nginx_mount}\n\n  # container for celery worker service"
        )
        console.print("[green]agents.conf bind mount added to trmm-nginx[/green]")

    # 3e. Add agent_server_data volume
    if "agent_server_data" not in patched:
        patched = patched.replace(
            "  redis_data: null",
            "  redis_data: null\n  agent_server_data: null"
        )
        console.print("[green]agent_server_data volume declared[/green]")

    # 3f. Add trmm-agent-server service
    if "tactical-agent-server" not in patched:
        patched = patched.rstrip() + "\n\n" + AGENT_SERVER_SERVICE
        console.print("[green]trmm-agent-server service added[/green]")

    if patched != compose:
        run(client, f"sudo cp {TACTICAL_DIR}/docker-compose.yml {TACTICAL_DIR}/docker-compose.yml.bak")
        write_remote_file(client, f"{TACTICAL_DIR}/docker-compose.yml", patched, sudo=True)
        console.print("[green]docker-compose.yml patched and backed up[/green]")
    else:
        console.print("[yellow]docker-compose.yml already fully patched[/yellow]")

    console.rule("[bold]Step 4: Validate compose[/bold]")
    run(client, f"cd {TACTICAL_DIR} && docker compose config --quiet")
    console.print("[green]docker-compose.yml is valid[/green]")

    console.rule("[bold]Step 5: Pull images from ghcr.io[/bold]")
    run(client, f"cd {TACTICAL_DIR} && docker pull ghcr.io/cakriwut/tactical:latest", check=True)
    run(client, f"cd {TACTICAL_DIR} && docker pull ghcr.io/cakriwut/agent-server:latest", check=True)

    console.rule("[bold]Step 6: Restart containers[/bold]")
    run(client, f"cd {TACTICAL_DIR} && docker compose up -d")
    console.print("[green]docker compose up -d done[/green]")

    console.print("\nWaiting 15s for containers to settle...")
    time.sleep(15)

    console.rule("[bold]Step 7: Verify[/bold]")
    run(client, "docker ps --format 'table {{.Names}}\t{{.Status}}'")

    console.rule("[bold cyan]Done[/bold cyan]")
    console.print("\n[bold green]All changes applied.[/bold green]")
    console.print("\nVerification:")
    console.print("  • Login: https://rmm.s2t.ai")
    console.print("  • Agent server health: https://agents.s2t.ai/health")
    console.print("  • Set code signing token in TRMM → Settings → Code Signing (any value)")

    client.close()


if __name__ == "__main__":
    main()
