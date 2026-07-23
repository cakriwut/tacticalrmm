#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["paramiko>=3.4", "rich>=13"]
# ///
"""
Apply self-hosted customizations and upgrades to the TacticalRMM server.

Changes applied:
  1. Add AGENT_BASE_URL to .env
  2. Write AGENT_BASE_URL into local_settings.py on the tactical_data volume
     (settings.py reads AGENT_BASE_URL as a Python constant, not os.environ —
      the .env alone is insufficient; local_settings.py is the authoritative override)
  3. Patch docker-compose.yml:
     a. Change tactical services to ghcr.io/cakriwut/tactical:latest
     b. Add AGENT_BASE_URL to tactical-init and tactical-backend environments
     c. Add trmm-agent-server service
     d. Add agent-server nginx conf mount to trmm-nginx
     e. Add agent_server_data volume
     f. Add SSO callback nginx conf and HTML bind mounts to trmm-nginx
  4. Write agents.s2t.ai nginx conf into /opt/tactical/agents.conf
  5. Write 00-sso-callback.conf into /opt/tactical/
  6. Write sso-callback.html into /opt/tactical/ (and into the tactical_data volume)
  7. Pull new images and restart containers
  8. Restart backend workers to reload local_settings.py

NOTE on AGENT_BASE_URL:
  The TacticalRMM adapter (ee/sso/adapter.py) calls token_is_valid() on every SSO
  login. token_is_valid() POSTs to CHECK_TOKEN_URL = AGENT_BASE_URL + /api/v2/checktoken.
  Without the override, it hits agents.tacticalrmm.com (upstream) which rejects the
  selfhosted-bypass-token → PermissionDenied on SSO + license warning on dashboard.
  local_settings.py is written by the container entrypoint but does NOT include
  AGENT_BASE_URL — it must be appended manually and persists in the tactical_data volume.
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

SSO_CALLBACK_CONF = """\
# 00-sso-callback.conf — loaded before default.conf (alphabetical order) so this
# server block wins for rmm.s2t.ai and the location = exact-match takes priority.
# Fixes: Microsoft Entra SSO redirect → 404/expired because the Vue SPA has no
# /account/provider/callback route and the frontend missing token exchange step.
server {
    resolver 127.0.0.11 valid=30s;
    server_name rmm.s2t.ai;

    listen 4443 ssl;
    ssl_certificate /opt/tactical/certs/fullchain.pem;
    ssl_certificate_key /opt/tactical/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers EECDH+AESGCM:EDH+AESGCM;
    ssl_ecdh_curve secp384r1;
    add_header X-Content-Type-Options nosniff;

    # Exact match — intercept SSO callback BEFORE the Vue SPA proxy
    # This page exchanges the allauth Django session for a Knox token and stores it
    # in localStorage, then redirects to /
    location = /account/provider/callback {
        alias /opt/tactical/sso-callback.html;
        add_header Content-Type "text/html; charset=utf-8";
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }

    # All other requests proxied to Vue SPA
    location / {
        set $app http://tactical-frontend:8080;
        proxy_pass $app;
        proxy_http_version  1.1;
        proxy_cache_bypass  $http_upgrade;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        "upgrade";
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
        proxy_set_header X-Forwarded-Port  $server_port;
    }
}
"""

SSO_CALLBACK_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Completing SSO Login...</title>
  <script src="/env-config.js"></script>
  <style>
    body { font-family: sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; background: #1d1d1d; color: #fff; }
    .box { text-align: center; }
    .spinner { border: 3px solid rgba(255,255,255,0.2); border-top-color: #fff; border-radius: 50%; width: 40px; height: 40px; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .error { color: #f66; }
    a { color: #7ec8e3; }
  </style>
</head>
<body>
  <div class="box">
    <div id="spinner" class="spinner"></div>
    <p id="msg">Completing login...</p>
  </div>
  <script>
    (async function () {
      var spinner = document.getElementById('spinner');
      var msg = document.getElementById('msg');

      function getCookie(name) {
        var v = null;
        if (document.cookie) {
          document.cookie.split(';').forEach(function (c) {
            var t = c.trim();
            if (t.substring(0, name.length + 1) === (name + '=')) {
              v = decodeURIComponent(t.substring(name.length + 1));
            }
          });
        }
        return v;
      }

      function showError(text) {
        spinner.style.display = 'none';
        msg.className = 'error';
        msg.innerHTML = text + '<br><br><a href="/login">Go back to Login</a>';
      }

      var params = new URLSearchParams(window.location.search);
      var error = params.get('error');
      if (error) {
        showError('SSO login failed: ' + error);
        return;
      }

      try {
        // PROD_URL is set by /env-config.js (loaded in <head>)
        var apiBase = (window._env_ && window._env_.PROD_URL) ? window._env_.PROD_URL : '';

        // Exchange the allauth Django session (set by backend OIDC callback) for a Knox token
        var resp = await fetch(apiBase + '/accounts/ssoproviders/token/', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || ''
          },
          body: JSON.stringify({})
        });

        if (!resp.ok) {
          var errText = await resp.text();
          throw new Error('Token exchange failed (' + resp.status + '): ' + errText);
        }

        var data = await resp.json();

        // Store Knox token in localStorage using the same format as the Vue auth store.
        // useStorage("access_token", null) uses the "any" serializer (default null type):
        //   read:  e => e  (raw string, no JSON.parse)
        //   write: e => String(e)
        // Must store the raw string — NOT JSON.stringify() which wraps in quotes
        // and causes Authorization: Token "abc..." to be rejected by the backend.
        localStorage.setItem('access_token', data.token);
        if (data.username) localStorage.setItem('user_name', data.username);
        if (data.name) localStorage.setItem('name', data.name);
        if (data.provider) localStorage.setItem('sso_provider', data.provider);

        msg.textContent = 'Login successful! Redirecting...';

        // Honour a saved next route (e.g. deep link set before SSO was triggered)
        var next = '/';
        try {
          var savedNext = localStorage.getItem('next');
          if (savedNext) {
            var parsed = JSON.parse(savedNext);
            if (parsed && parsed !== 'null') {
              next = parsed;
              localStorage.removeItem('next');
            }
          }
        } catch (e) {}

        window.location.replace(next);

      } catch (err) {
        showError('Login error: ' + err.message);
        console.error('SSO callback error:', err);
      }
    })();
  </script>
</body>
</html>
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

    console.rule("[bold]Step 2: Patch local_settings.py with AGENT_BASE_URL[/bold]")
    # CRITICAL: settings.py hardcodes AGENT_BASE_URL = "https://agents.tacticalrmm.com"
    # local_settings.py is the override file — the .env value is NOT read by Django.
    # Without this, token_is_valid() and token_is_expired() call the upstream server
    # which rejects the selfhosted-bypass-token → SSO PermissionDenied + dashboard
    # license warning even when the token is present and the local agent server is up.
    vol_local_settings = "/var/lib/docker/volumes/tactical_tactical_data/_data/api/tacticalrmm/local_settings.py"
    ls_content = run(client, f"cat {vol_local_settings} 2>/dev/null || echo __MISSING__", check=False)
    if f"AGENT_BASE_URL = '{AGENT_BASE_URL}'" in ls_content:
        console.print(f"[yellow]local_settings.py already has AGENT_BASE_URL={AGENT_BASE_URL}[/yellow]")
    elif "AGENT_BASE_URL" in ls_content:
        run(client, f"sed -i \"s|^AGENT_BASE_URL = .*|AGENT_BASE_URL = '{AGENT_BASE_URL}'|\" {vol_local_settings}")
        console.print(f"[green]AGENT_BASE_URL updated in local_settings.py[/green]")
    else:
        run(client, f"echo \"AGENT_BASE_URL = '{AGENT_BASE_URL}'\" >> {vol_local_settings}")
        console.print(f"[green]AGENT_BASE_URL appended to local_settings.py[/green]")

    console.rule("[bold]Step 3: Write agents.s2t.ai nginx conf[/bold]")
    existing = run(client, f"cat {TACTICAL_DIR}/agents.conf 2>/dev/null || echo __MISSING__", check=False)
    if "agents.s2t.ai" in existing:
        console.print("[yellow]agents.conf already exists[/yellow]")
    else:
        run(client, f"cp {TACTICAL_DIR}/agents.conf {TACTICAL_DIR}/agents.conf.bak 2>/dev/null || true", check=False)
        write_remote_file(client, f"{TACTICAL_DIR}/agents.conf", AGENTS_NGINX_CONF)
        console.print("[green]agents.conf written to /opt/tactical/agents.conf[/green]")

    console.rule("[bold]Step 4: Patch docker-compose.yml[/bold]")
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

    # 3g. Add SSO callback nginx conf and HTML bind mounts to trmm-nginx
    sso_conf_mount = "      - /opt/tactical/00-sso-callback.conf:/etc/nginx/conf.d/00-sso-callback.conf:ro"
    sso_html_mount = "      - /opt/tactical/sso-callback.html:/opt/tactical/sso-callback.html:ro"
    if "00-sso-callback.conf" not in patched:
        # Insert after the agents.conf mount line
        patched = patched.replace(
            "      - /opt/tactical/agents.conf:/etc/nginx/conf.d/agents.conf:ro",
            f"      - /opt/tactical/agents.conf:/etc/nginx/conf.d/agents.conf:ro\n{sso_conf_mount}\n{sso_html_mount}"
        )
        console.print("[green]SSO callback conf+html bind mounts added to trmm-nginx[/green]")

    if patched != compose:
        run(client, f"sudo cp {TACTICAL_DIR}/docker-compose.yml {TACTICAL_DIR}/docker-compose.yml.bak")
        write_remote_file(client, f"{TACTICAL_DIR}/docker-compose.yml", patched, sudo=True)
        console.print("[green]docker-compose.yml patched and backed up[/green]")
    else:
        console.print("[yellow]docker-compose.yml already fully patched[/yellow]")

    console.rule("[bold]Step 5: Validate compose[/bold]")
    run(client, f"cd {TACTICAL_DIR} && docker compose config --quiet")
    console.print("[green]docker-compose.yml is valid[/green]")

    console.rule("[bold]Step 6: Write SSO callback nginx conf[/bold]")
    existing_sso_conf = run(client, f"cat {TACTICAL_DIR}/00-sso-callback.conf 2>/dev/null || echo __MISSING__", check=False)
    if "location = /account/provider/callback" in existing_sso_conf:
        console.print("[yellow]00-sso-callback.conf already exists[/yellow]")
    else:
        write_remote_file(client, f"{TACTICAL_DIR}/00-sso-callback.conf", SSO_CALLBACK_CONF)
        console.print("[green]00-sso-callback.conf written to /opt/tactical/00-sso-callback.conf[/green]")

    console.rule("[bold]Step 7: Write SSO callback HTML page[/bold]")
    existing_sso_html = run(client, f"cat {TACTICAL_DIR}/sso-callback.html 2>/dev/null || echo __MISSING__", check=False)
    if "ssoproviders/token" in existing_sso_html:
        console.print("[yellow]sso-callback.html already exists[/yellow]")
    else:
        write_remote_file(client, f"{TACTICAL_DIR}/sso-callback.html", SSO_CALLBACK_HTML)
        console.print("[green]sso-callback.html written to /opt/tactical/sso-callback.html[/green]")
    # Also write to the Docker volume so it's accessible inside containers
    vol_path = "/var/lib/docker/volumes/tactical_tactical_data/_data/sso-callback.html"
    run(client, f"cp {TACTICAL_DIR}/sso-callback.html {vol_path} && chmod 644 {vol_path}", check=False)
    console.print("[green]sso-callback.html copied to tactical_data Docker volume[/green]")

    console.rule("[bold]Step 8: Pull latest images[/bold]")
    run(client, f"cd {TACTICAL_DIR} && docker pull ghcr.io/cakriwut/tactical:latest", check=True)
    run(client, f"cd {TACTICAL_DIR} && docker pull ghcr.io/cakriwut/agent-server:latest", check=True)

    console.rule("[bold]Step 9: Restart containers[/bold]")
    run(client, f"cd {TACTICAL_DIR} && docker compose up -d")
    console.print("[green]docker compose up -d done[/green]")

    console.print("\nWaiting 20s for containers to start...")
    time.sleep(20)

    # Explicit backend restart ensures workers reload local_settings.py with the
    # correct AGENT_BASE_URL. compose up -d only recreates containers whose config
    # changed; if the compose file was already up to date the backend won't restart
    # and will keep the stale in-memory settings.AGENT_BASE_URL from its initial load.
    console.rule("[bold]Step 10: Restart backend workers (reload local_settings.py)[/bold]")
    run(client, f"cd {TACTICAL_DIR} && docker compose restart tactical-backend tactical-celery tactical-celerybeat tactical-websockets")
    console.print("[green]Backend workers restarted — local_settings.py reloaded[/green]")

    console.print("\nWaiting 10s for workers to come up...")
    time.sleep(10)

    console.rule("[bold]Step 11: Verify[/bold]")
    run(client, "docker ps --format 'table {{.Names}}\t{{.Status}}'")

    console.rule("[bold cyan]Done[/bold cyan]")
    console.print("\n[bold green]All changes applied.[/bold green]")
    console.print("\nVerification:")
    console.print("  • Login: https://rmm.s2t.ai")
    console.print("  • SSO login via Azure: https://rmm.s2t.ai/login")
    console.print("  • Agent server health: https://agents.s2t.ai/health")
    console.print("  • No license warning should appear on dashboard")

    client.close()


if __name__ == "__main__":
    main()
