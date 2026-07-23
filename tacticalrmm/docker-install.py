#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "paramiko",
#   "rich",
# ]
# ///
"""
TacticalRMM Docker install script.
Bypasses buggy tactical-cli. Creates /opt/tactical/.env and docker-compose.yml directly.

Certs must already be on server at:
  /etc/letsencrypt/live/s2t.ai/fullchain.pem
  /etc/letsencrypt/live/s2t.ai/privkey.pem
"""

import base64
import json
import secrets
import string
import sys
import time
from pathlib import Path

import paramiko
from rich.console import Console
from rich.panel import Panel

console = Console()

STATE_FILE = Path(__file__).parent / "state.json"
SSH_KEY    = Path.home() / ".ssh" / "id_rsa"
SSH_USER   = "tactical"

API_HOST   = "api.s2t.ai"
APP_HOST   = "rmm.s2t.ai"
MESH_HOST  = "mesh.s2t.ai"
EMAIL      = "admin@s2t.ai"
CERT_PUB   = "/etc/letsencrypt/live/s2t.ai/fullchain.pem"
CERT_PRIV  = "/etc/letsencrypt/live/s2t.ai/privkey.pem"
INSTALL_DIR = "/opt/tactical"

state = json.loads(STATE_FILE.read_text())
IP = state["public_ip"]
console.print(f"[bold cyan]Server IP:[/] {IP}")


def gen_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


TACTICAL_USER = "tacticaladmin"
TACTICAL_PASS = gen_password(20)
MESH_PASS     = gen_password(20)
MONGO_USER    = "mongouser"
MONGO_PASS    = gen_password(20)
PG_USER       = "pguser"
PG_PASS       = gen_password(20)

console.print(f"[bold yellow]TRMM admin user:[/] {TACTICAL_USER}")
console.print(f"[bold yellow]TRMM admin pass:[/] {TACTICAL_PASS}")
console.print("[dim]Save these — they won't be shown again.[/dim]")


def make_client() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=IP, username=SSH_USER, key_filename=str(SSH_KEY), timeout=30)
    return client


def run(client, cmd: str, *, sudo: bool = False, check: bool = True, timeout: int = 600) -> tuple[int, str]:
    if sudo and not cmd.startswith("sudo "):
        cmd = f"sudo {cmd}"
    console.print(f"[dim]$ {cmd[:100]}{'...' if len(cmd) > 100 else ''}[/dim]")
    _, stdout_, _ = client.exec_command(cmd, timeout=timeout, get_pty=True)
    stdout_.channel.settimeout(timeout)
    out = stdout_.read().decode(errors="replace")
    rc  = stdout_.channel.recv_exit_status()
    if out.strip():
        console.print(out.strip()[:2000])
    if rc != 0 and check:
        raise RuntimeError(f"Failed (rc={rc}): {cmd}")
    return rc, out


def run_stream(client, cmd: str, *, sudo: bool = False, timeout: int = 1800) -> int:
    if sudo and not cmd.startswith("sudo "):
        cmd = f"sudo {cmd}"
    console.print(f"[dim]$ {cmd[:100]}{'...' if len(cmd) > 100 else ''}[/dim]")
    transport = client.get_transport()
    channel = transport.open_session()
    channel.get_pty()
    channel.settimeout(timeout)
    channel.exec_command(cmd)
    buf = ""
    while True:
        try:
            chunk = channel.recv(4096).decode(errors="replace")
            if not chunk:
                break
            buf += chunk
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if line.strip():
                    console.print(line)
        except Exception:
            break
    if buf.strip():
        console.print(buf.strip())
    return channel.recv_exit_status()


console.rule("[bold]Step 1: Install Docker")
client = make_client()

rc, _ = run(client, "docker --version", check=False)
if rc == 0:
    console.print("[green]Docker already installed.[/green]")
else:
    run(client, "apt-get update -qq", sudo=True, timeout=120)
    run(client, "apt-get install -y curl ca-certificates", sudo=True, timeout=120)
    rc = run_stream(client, "curl -fsSL https://get.docker.com | bash", sudo=True, timeout=300)
    if rc != 0:
        console.print("[red]Docker install failed[/red]")
        sys.exit(1)
    run(client, "systemctl enable --now docker", sudo=True)
    run(client, "usermod -aG docker tactical", sudo=True)
    console.print("[green]Docker installed.[/green]")

rc, _ = run(client, "docker compose version 2>&1 || docker-compose version 2>&1", check=False)
if rc != 0:
    run(client, "apt-get install -y docker-compose-plugin", sudo=True, timeout=120)

client.close()


console.rule("[bold]Step 2: Read certs and build .env")
client = make_client()

_, cert_pub_out = run(client, f"base64 -w 0 {CERT_PUB}", sudo=True)
_, cert_priv_out = run(client, f"base64 -w 0 {CERT_PRIV}", sudo=True)

CERT_PUB_B64  = cert_pub_out.strip()
CERT_PRIV_B64 = cert_priv_out.strip()
console.print(f"[green]Certs encoded:[/] pub={len(CERT_PUB_B64)}B priv={len(CERT_PRIV_B64)}B")

env_content = f"""IMAGE_REPO=ghcr.io/cakriwut/
VERSION=latest
TRMM_USER={TACTICAL_USER}
TRMM_PASS={TACTICAL_PASS}
APP_HOST={APP_HOST}
API_HOST={API_HOST}
MESH_HOST={MESH_HOST}
MESH_USER={TACTICAL_USER}
MESH_PASS={MESH_PASS}
MONGODB_USER={MONGO_USER}
MONGODB_PASSWORD={MONGO_PASS}
POSTGRES_USER={PG_USER}
POSTGRES_PASS={PG_PASS}
MESH_PERSISTENT_CONFIG=1
CERT_PUB_KEY={CERT_PUB_B64}
CERT_PRIV_KEY={CERT_PRIV_B64}
AGENT_BASE_URL=https://agents.s2t.ai
"""

run(client, f"mkdir -p {INSTALL_DIR}", sudo=True)
run(client, f"chmod 755 {INSTALL_DIR}", sudo=True)
run(client, f"chown tactical:tactical {INSTALL_DIR}", sudo=True)

sftp = client.open_sftp()
import tempfile, os
with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as tmp:
    tmp.write(env_content)
    tmp_path = tmp.name

sftp.put(tmp_path, f"{INSTALL_DIR}/.env")
sftp.chmod(f"{INSTALL_DIR}/.env", 0o600)
os.unlink(tmp_path)
sftp.close()
console.print(f"[green].env written to {INSTALL_DIR}/.env[/green]")

client.close()


console.rule("[bold]Step 3: Download docker-compose.yml")
client = make_client()

compose_url = "https://raw.githubusercontent.com/amidaware/tacticalrmm/master/docker/docker-compose.yml"
run(client, f"curl -fsSL {compose_url} -o {INSTALL_DIR}/docker-compose.yml", sudo=True)
console.print("[green]docker-compose.yml downloaded.[/green]")

client.close()


console.rule("[bold]Step 4: Pull images and start containers")
client = make_client()

console.print("[yellow]Pulling images (this may take 5-10 min)...[/yellow]")
rc = run_stream(client, f"bash -c 'cd {INSTALL_DIR} && docker compose pull'", sudo=True, timeout=900)
if rc != 0:
    console.print(f"[bold red]docker compose pull failed (rc={rc})[/bold red]")
    sys.exit(1)

console.print("[yellow]Starting containers...[/yellow]")
rc = run_stream(client, f"bash -c 'cd {INSTALL_DIR} && docker compose up -d'", sudo=True, timeout=300)
if rc != 0:
    console.print(f"[bold red]docker compose up failed (rc={rc})[/bold red]")
    sys.exit(1)

client.close()


console.rule("[bold]Step 5: Verify containers")
time.sleep(20)
client = make_client()

_, out = run(client, "docker ps --format 'table {{.Names}}\t{{.Status}}'", sudo=True, check=False)
console.print(out)

expected = ["trmm-nginx", "trmm-backend", "trmm-frontend", "trmm-nats", "trmm-meshcentral"]
missing  = [c for c in expected if c not in out]
if missing:
    console.print(f"[bold yellow]Containers not yet up: {missing}[/bold yellow]")
    console.print("Waiting 30s...")
    time.sleep(30)
    _, out = run(client, "docker ps --format 'table {{.Names}}\t{{.Status}}'", sudo=True, check=False)
    console.print(out)
    missing = [c for c in expected if c not in out]
    if missing:
        console.print(f"[bold red]Still missing: {missing} — check logs below[/bold red]")
        run(client, f"bash -c 'cd {INSTALL_DIR} && docker compose logs --tail=30'", sudo=True, check=False, timeout=30)

client.close()


console.print()
console.print(Panel.fit(
    f"[bold green]TacticalRMM Docker deployment complete![/bold green]\n\n"
    f"[bold]URL:[/bold]      https://rmm.s2t.ai\n"
    f"[bold]Username:[/bold] {TACTICAL_USER}\n"
    f"[bold]Password:[/bold] {TACTICAL_PASS}\n\n"
    f"[yellow]IMPORTANT:[/yellow] Enable 2FA (TOTP) on first login — mandatory.\n"
    f"Use Google Authenticator, Authy, or any TOTP app.\n\n"
    f"[dim]API:    https://api.s2t.ai\n"
    f"Mesh:   https://mesh.s2t.ai\n"
    f"Env:    {INSTALL_DIR}/.env\n"
    f"Compose:{INSTALL_DIR}/docker-compose.yml[/dim]",
    title="Access Info",
    border_style="green",
))
