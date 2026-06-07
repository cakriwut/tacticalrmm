#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "rich"]
# ///

import json
import subprocess
import sys
from pathlib import Path

import httpx
from rich.console import Console

console = Console()

CF_API = "https://api.cloudflare.com/client/v4"
ZONE_ID = "e50ecbf134b09c530f282a4570dc5b74"
DOMAIN = "s2t.ai"
SUBDOMAINS = ["rmm", "api", "mesh"]


def get_secret(name: str) -> str:
    result = subprocess.run(
        ["doppler", "secrets", "get", name, "--plain", "--no-check-version",
         "--project", "dev-console-personal", "--config", "dev"],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def cf_client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=CF_API,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30,
    )


def delete_existing(client: httpx.Client, name: str) -> None:
    resp = client.get(f"/zones/{ZONE_ID}/dns_records", params={"name": f"{name}.{DOMAIN}", "type": "A"})
    resp.raise_for_status()
    for record in resp.json().get("result", []):
        client.delete(f"/zones/{ZONE_ID}/dns_records/{record['id']}")


def create_record(client: httpx.Client, subdomain: str, ip: str) -> str:
    payload = {
        "type": "A",
        "name": f"{subdomain}.{DOMAIN}",
        "content": ip,
        "ttl": 120,
        "proxied": False,
    }
    resp = client.post(f"/zones/{ZONE_ID}/dns_records", json=payload)
    resp.raise_for_status()
    return resp.json()["result"]["id"]


def main() -> None:
    state = json.loads(Path("state.json").read_text())
    public_ip = state["public_ip"]

    console.print(f"[bold blue]Cloudflare DNS Setup[/bold blue] — IP: [green]{public_ip}[/green]")

    token = get_secret("CLOUDFLARE_API_TOKEN")

    with cf_client(token) as client:
        record_ids = {}
        for sub in SUBDOMAINS:
            fqdn = f"{sub}.{DOMAIN}"
            console.print(f"  Creating {fqdn} → {public_ip} (proxy OFF)...")
            delete_existing(client, sub)
            record_id = create_record(client, sub, public_ip)
            record_ids[fqdn] = record_id
            console.print(f"    [green]✓[/green] {record_id}")

    state["dns_records"] = record_ids
    Path("state.json").write_text(json.dumps(state, indent=2))

    console.print(f"\n[bold green]DNS records created![/bold green]")
    console.print("All three records: DNS-only (grey cloud), proxied=false")
    console.print(f"\nNext: [bold]uv run install-trmm.py[/bold] to install TacticalRMM on the server")


if __name__ == "__main__":
    main()
