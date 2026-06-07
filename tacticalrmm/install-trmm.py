#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich", "paramiko"]
# ///

import json
import subprocess
import sys
import time
from pathlib import Path

import paramiko
from rich.console import Console

console = Console()

TRMM_INSTALL_URL = "https://raw.githubusercontent.com/amidaware/tacticalrmm/master/install.sh"
ROOT_DOMAIN = "s2t.ai"
API_DOMAIN = f"api.{ROOT_DOMAIN}"
RMM_DOMAIN = f"rmm.{ROOT_DOMAIN}"
MESH_DOMAIN = f"mesh.{ROOT_DOMAIN}"
ADMIN_EMAIL = "admin@s2t.ai"
CERT_DIR = f"/etc/letsencrypt/live/{ROOT_DOMAIN}"
FULLCHAIN = f"{CERT_DIR}/fullchain.pem"
PRIVKEY = f"{CERT_DIR}/privkey.pem"


def get_secret(name: str) -> str:
    result = subprocess.run(
        ["doppler", "secrets", "get", name, "--plain", "--no-check-version",
         "--project", "dev-console-personal", "--config", "dev"],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def get_ssh_key_path() -> Path:
    candidates = [
        Path.home() / ".ssh" / "riwut-do",
        Path.home() / ".ssh" / "id_rsa",
        Path.home() / ".ssh" / "id_ed25519",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError("SSH key not found. Expected ~/.ssh/riwut-do")


def wait_for_ssh(host: str, timeout: int = 300) -> None:
    deadline = time.time() + timeout
    console.print(f"Waiting for SSH on {host}...")
    while time.time() < deadline:
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(host, username="tactical", key_filename=str(get_ssh_key_path()), timeout=5)
            client.close()
            console.print("  [green]SSH ready[/green]")
            return
        except Exception:
            time.sleep(10)
    raise TimeoutError(f"SSH not available on {host} after {timeout}s")


def wait_for_cloud_init(ssh: paramiko.SSHClient) -> None:
    console.print("Waiting for cloud-init to finish...")
    for _ in range(30):
        _, stdout, _ = ssh.exec_command("test -f /tmp/cloud-init-done && echo yes || echo no")
        if stdout.read().decode().strip() == "yes":
            console.print("  [green]cloud-init complete[/green]")
            return
        time.sleep(20)
    console.print("  [yellow]cloud-init marker not found, proceeding anyway[/yellow]")


def run_remote(ssh: paramiko.SSHClient, cmd: str, stdin_data: str = "", timeout: int = 1800) -> tuple[int, str, str]:
    transport = ssh.get_transport()
    chan = transport.open_session()
    chan.set_combine_stderr(False)
    chan.get_pty(term="vt100", width=220, height=50)
    chan.exec_command(cmd)

    if stdin_data:
        chan.sendall(stdin_data.encode())
        chan.shutdown_write()

    stdout_chunks = []
    start = time.time()

    while not chan.exit_status_ready():
        if time.time() - start > timeout:
            raise TimeoutError(f"Command timed out after {timeout}s")
        if chan.recv_ready():
            chunk = chan.recv(4096).decode("utf-8", errors="replace")
            stdout_chunks.append(chunk)
            print(chunk, end="", flush=True)
        time.sleep(0.1)

    while chan.recv_ready():
        chunk = chan.recv(4096).decode("utf-8", errors="replace")
        stdout_chunks.append(chunk)
        print(chunk, end="", flush=True)

    return chan.recv_exit_status(), "".join(stdout_chunks), ""


def obtain_wildcard_cert(ssh: paramiko.SSHClient, cf_token: str) -> None:
    console.print("\n[bold]Step 1: Obtaining wildcard certificate via Cloudflare DNS-01...[/bold]")

    setup_script = f"""#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
sudo -E apt-get install -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" certbot python3-certbot-dns-cloudflare
sudo mkdir -p /etc/cloudflare
printf 'dns_cloudflare_api_token = {cf_token}\\n' | sudo tee /etc/cloudflare/cf.ini > /dev/null
sudo chmod 600 /etc/cloudflare/cf.ini
sudo certbot certonly \\
  --dns-cloudflare \\
  --dns-cloudflare-credentials /etc/cloudflare/cf.ini \\
  --dns-cloudflare-propagation-seconds 60 \\
  -d "*.{ROOT_DOMAIN}" \\
  -d "{ROOT_DOMAIN}" \\
  --agree-tos \\
  --no-eff-email \\
  -m {ADMIN_EMAIL} \\
  --non-interactive
sudo chown -R tactical:tactical /etc/letsencrypt
"""
    stdin_chan = ssh.get_transport().open_session()
    stdin_chan.exec_command("cat > /tmp/getcert.sh")
    stdin_chan.sendall(setup_script.encode())
    stdin_chan.shutdown_write()
    stdin_chan.recv_exit_status()

    rc, out, _ = run_remote(ssh, "bash /tmp/getcert.sh", timeout=600)
    if rc != 0:
        console.print(f"[red]Certificate acquisition failed (exit {rc})[/red]")
        console.print(out[-3000:])
        sys.exit(1)
    console.print("  [green]Wildcard cert obtained[/green]")


def run_trmm_install(ssh: paramiko.SSHClient) -> None:
    console.print("\n[bold]Step 2: Running TacticalRMM install script...[/bold]")

    rc, _, _ = run_remote(ssh, f"curl -fsSL {TRMM_INSTALL_URL} -o /tmp/install.sh")
    if rc != 0:
        console.print("[red]Failed to download install script[/red]")
        sys.exit(1)

    stdin_answers = "\n".join([
        API_DOMAIN,
        RMM_DOMAIN,
        MESH_DOMAIN,
        ROOT_DOMAIN,
        ADMIN_EMAIL,
        FULLCHAIN,
        PRIVKEY,
        "",
    ])

    console.print("[yellow]Install takes 20-40 minutes — streaming output...[/yellow]\n")
    rc, out, _ = run_remote(
        ssh,
        "bash /tmp/install.sh --use-own-cert",
        stdin_data=stdin_answers,
        timeout=3600,
    )

    if rc != 0:
        console.print(f"\n[red]Install failed (exit {rc})[/red]")
        console.print(out[-3000:])
        sys.exit(1)


def verify_services(ssh: paramiko.SSHClient) -> None:
    console.print("\n[bold]Step 3: Verifying services...[/bold]")
    services = ["nginx", "rmm", "daphne", "celery", "celerybeat", "nats", "meshcentral"]
    all_ok = True
    for svc in services:
        _, stdout, _ = ssh.exec_command(f"systemctl is-active {svc} 2>/dev/null || echo inactive")
        status = stdout.read().decode().strip()
        color = "green" if status == "active" else "red"
        console.print(f"  {svc}: [{color}]{status}[/{color}]")
        if status != "active":
            all_ok = False

    if not all_ok:
        console.print("\n[yellow]Some services not yet active — may still be starting up[/yellow]")


def main() -> None:
    state = json.loads(Path("state.json").read_text())
    public_ip = state["public_ip"]

    console.print(f"[bold blue]TacticalRMM Installer[/bold blue] — {public_ip}")

    cf_token = get_secret("CLOUDFLARE_API_TOKEN")
    key_path = get_ssh_key_path()

    wait_for_ssh(public_ip)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(public_ip, username="tactical", key_filename=str(key_path))

    try:
        wait_for_cloud_init(ssh)
        obtain_wildcard_cert(ssh, cf_token)
        run_trmm_install(ssh)
        verify_services(ssh)

        state["trmm_installed"] = True
        Path("state.json").write_text(json.dumps(state, indent=2))

        console.print(f"\n[bold green]TacticalRMM is ready![/bold green]")
        console.print(f"  URL:   [cyan]https://rmm.{ROOT_DOMAIN}[/cyan]")
        console.print(f"  [yellow]First login requires TOTP setup — scan QR with authenticator app[/yellow]")

    finally:
        ssh.close()


if __name__ == "__main__":
    main()
