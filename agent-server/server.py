#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "fastapi>=0.110",
#   "uvicorn[standard]>=0.29",
#   "httpx>=0.27",
# ]
# ///
"""
Self-hosted TacticalRMM agent distribution server.

Endpoints:
  POST /api/v2/checktoken  — always returns 200 (any token accepted)
  GET  /api/v2/agents/     — serves pre-built agent binary by version/arch/plat
  POST /api/v2/exe         — generates Windows EXE installer (7-Zip SFX wrapping PS1)
  GET  /api/v2/webtar/     — proxies web tar from GitHub releases (optional)
  GET  /health             — health check

Binaries are fetched from cakriwut/rmmagent GitHub Releases on first request
and cached in BINARY_CACHE_DIR.
"""
import asyncio
import logging
import os
import subprocess
import tempfile
import urllib.parse as _urlparse
from pathlib import Path
from typing import Any, Dict

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="TRMM Agent Server", docs_url=None, redoc_url=None)

GITHUB_REPO = os.environ.get("GITHUB_REPO", "cakriwut/rmmagent")
BINARY_CACHE_DIR = Path(os.environ.get("BINARY_CACHE_DIR", "/data/agents"))
BINARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MESH_HOST = os.environ.get("MESH_HOST", "")

SFX_MODULE = os.environ.get("SFX_MODULE", "/app/7z.sfx")

PLATFORM_MAP = {
    ("linux", "amd64"): "tacticalagent-linux-amd64",
    ("linux", "386"): "tacticalagent-linux-386",
    ("linux", "arm64"): "tacticalagent-linux-arm64",
    ("linux", "arm"): "tacticalagent-linux-arm",
    ("windows", "amd64"): "tacticalagent-windows-amd64.exe",
    ("windows", "386"): "tacticalagent-windows-386.exe",
    ("darwin", "amd64"): "tacticalagent-darwin-amd64",
    ("darwin", "arm64"): "tacticalagent-darwin-arm64",
}

# PS1 installer template — mirrors installer.ps1 placeholders but embeds content directly
# The EXE wraps this PS1 script in a 7-Zip SFX that auto-runs it on extraction.
PS1_TEMPLATE = r"""
$api = '"__APIHOST__"'
$clientid = '__CLIENT__'
$siteid = '__SITE__'
$agenttype = '"__AGENTTYPE__"'
$power = __POWER__
$rdp = __RDP__
$ping = __PING__
$auth = '"__TOKEN__"'
$downloadlink = '__DLURL__'
$meshDownloadLink = '__MESHURL__'
$apilink = $downloadlink.split('/')

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$serviceName = 'tacticalrmm'
If (Get-Service $serviceName -ErrorAction SilentlyContinue) {
    Write-Host 'Tactical RMM Is Already Installed'
    exit 0
}

$OutPath = $env:TMP
$agentExe = 'tacticalrmm.exe'
$meshExe = 'meshagent.exe'
$installDir = 'C:\Program Files\TacticalAgent'
$meshDir = 'C:\Program Files\Mesh Agent'

Try {
    $DefenderStatus = Get-MpComputerStatus | select AntivirusEnabled
    if ($DefenderStatus -match 'True') {
        Add-MpPreference -ExclusionPath 'C:\Program Files\TacticalAgent\*'
        Add-MpPreference -ExclusionPath 'C:\Program Files\Mesh Agent\*'
        Add-MpPreference -ExclusionPath 'C:\ProgramData\TacticalRMM\*'
    }
} Catch { }

$X = 0
do {
    Write-Output 'Waiting for network'
    Start-Sleep -s 5
    $X += 1
} until(($connectresult = Test-NetConnection $apilink[2] -Port 443 | ? { $_.TcpTestSucceeded }) -or $X -eq 3)

if ($connectresult.TcpTestSucceeded -ne $true) {
    Write-Output 'Unable to connect to server'
    exit 1
}

Try {
    Write-Output "Downloading MeshAgent..."
    Invoke-WebRequest -Uri $meshDownloadLink -OutFile "$OutPath\$meshExe"
    Write-Output "Installing MeshAgent..."
    Start-Process -FilePath "$OutPath\$meshExe" -ArgumentList '-fullinstall' -Wait -NoNewWindow
    Start-Sleep -s 5

    $meshNodeId = & "$meshDir\MeshAgent.exe" -nodeid 2>&1
    $meshNodeId = $meshNodeId.Trim()
    Write-Output "Mesh Node ID: $meshNodeId"

    Write-Output "Downloading TacticalAgent..."
    Invoke-WebRequest -Uri $downloadlink -OutFile "$OutPath\$agentExe"
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
    Copy-Item -Path "$OutPath\$agentExe" -Destination "$installDir\$agentExe" -Force

    $installArgs = @('-m', 'install', '--api', "$api", '--client-id', $clientid, '--site-id', $siteid, '--agent-type', "$agenttype", '--auth', "$auth", '--meshnodeid', $meshNodeId)

    if ($power) { $installArgs += '--power' }
    if ($rdp)   { $installArgs += '--rdp' }
    if ($ping)  { $installArgs += '--ping' }

    Write-Output "Installing TacticalAgent..."
    & "$installDir\$agentExe" @installArgs
    Write-Output "Done."
    exit 0
} Catch {
    $ErrorMessage = $_.Exception.Message
    Write-Error -Message $ErrorMessage
    exit 1
} Finally {
    Remove-Item -Path "$OutPath\$agentExe" -ErrorAction SilentlyContinue
    Remove-Item -Path "$OutPath\$meshExe" -ErrorAction SilentlyContinue
}
""".strip()

# 7-Zip SFX config — runs PS1 silently after extraction to %TEMP%\trmm-install
SFX_CONFIG_TEMPLATE = """;!@Install@!UTF-8!
Title="TacticalRMM Agent Installer"
BeginPrompt="Install TacticalRMM Agent?"
RunProgram="cmd.exe /c start /min \"\" powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File trmm-install.ps1"
;!@InstallEnd@!
"""


async def fetch_binary(version: str, plat: str, arch: str) -> Path:
    filename = PLATFORM_MAP.get((plat, arch))
    if not filename:
        raise HTTPException(status_code=404, detail=f"No binary for {plat}/{arch}")

    cached = BINARY_CACHE_DIR / version / filename
    if cached.exists():
        log.info("Cache hit: %s", cached)
        return cached

    cached.parent.mkdir(parents=True, exist_ok=True)

    tag = version if version.startswith("v") else f"v{version}"
    url = f"https://github.com/{GITHUB_REPO}/releases/download/{tag}/{filename}"
    log.info("Downloading: %s", url)

    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        r = await client.get(url)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Binary not found at {url}")
        r.raise_for_status()
        cached.write_bytes(r.content)

    cached.chmod(0o755)
    log.info("Cached %s (%d bytes)", cached, cached.stat().st_size)
    return cached


async def get_latest_release_tag() -> str:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url, headers={"Accept": "application/vnd.github+json"})
        if r.status_code != 200:
            raise HTTPException(status_code=503, detail="Cannot fetch latest release from GitHub")
        return r.json()["tag_name"]


def _to_int(val, default=0) -> int:
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.lower() in ("true", "1", "yes"):
            return 1
        if val.lower() in ("false", "0", "no", ""):
            return 0
        try:
            return int(val)
        except ValueError:
            return default
    return default


def build_ps1(data: Dict[str, Any]) -> str:
    rdp_val = _to_int(data.get("rdp", 0))
    ping_val = _to_int(data.get("ping", 0))
    power_val = _to_int(data.get("power", 0))

    ps1 = PS1_TEMPLATE
    ps1 = ps1.replace("__APIHOST__", str(data.get("api", "")))
    ps1 = ps1.replace("__CLIENT__", str(data.get("client", "")))
    ps1 = ps1.replace("__SITE__", str(data.get("site", "")))
    ps1 = ps1.replace("__AGENTTYPE__", str(data.get("agenttype", "workstation")))
    ps1 = ps1.replace("__POWER__", str(power_val))
    ps1 = ps1.replace("__RDP__", str(rdp_val))
    ps1 = ps1.replace("__PING__", str(ping_val))
    ps1 = ps1.replace("__TOKEN__", str(data.get("token", "")))
    ps1 = ps1.replace("__DLURL__", str(data.get("url", "")))
    mesh_host = MESH_HOST or str(data.get("api", "")).replace("api.", "mesh.")
    raw_meshid = "sIeMDawdszrt6Gdofxx2qVLikdjaGgFY@UWeb8VrV@XaJQnoZm9K" + chr(36) + "cZHRPAYfJ" + chr(36) + "w"
    encoded_meshid = _urlparse.quote(raw_meshid, safe="")
    mesh_url = f"https://{mesh_host}/meshagents?id=4&meshid={encoded_meshid}&installflags=0"
    ps1 = ps1.replace("__MESHURL__", mesh_url)
    return ps1


def build_sfx_exe(ps1_content: str) -> bytes:
    """
    Build a Windows self-extracting EXE using 7-Zip SFX module.

    Structure: [sfx_module] + [sfx_config] + [7z archive]
    The archive contains trmm-install.ps1.
    On Windows double-click: extracts to %TEMP%\\trmm-install\\ then runs the PS1.
    """
    if not Path(SFX_MODULE).exists():
        raise HTTPException(
            status_code=500,
            detail="7-Zip SFX module not found. Ensure p7zip-full is installed.",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        ps1_path = tmpdir / "trmm-install.ps1"
        ps1_path.write_text(ps1_content, encoding="utf-8")

        sfx_config_path = tmpdir / "sfx_config.txt"
        sfx_config_path.write_text(SFX_CONFIG_TEMPLATE, encoding="utf-8")

        archive_path = tmpdir / "trmm-install.7z"
        result = subprocess.run(
            ["7z", "a", "-mx=5", str(archive_path), str(ps1_path)],
            capture_output=True,
            cwd=str(tmpdir),
        )
        if result.returncode != 0:
            log.error("7z failed: %s", result.stderr.decode())
            raise HTTPException(status_code=500, detail="Failed to create 7z archive")

        sfx_bytes = Path(SFX_MODULE).read_bytes()
        config_bytes = sfx_config_path.read_bytes()
        archive_bytes = archive_path.read_bytes()

        exe_bytes = sfx_bytes + config_bytes + archive_bytes
        log.info(
            "Built SFX EXE: sfx=%d config=%d archive=%d total=%d bytes",
            len(sfx_bytes),
            len(config_bytes),
            len(archive_bytes),
            len(exe_bytes),
        )
        return exe_bytes


@app.post("/api/v2/checktoken")
async def check_token(request: Request):
    body = await request.json()
    log.info("checktoken: token=%s api=%s", body.get("token", "")[:8] + "...", body.get("api", ""))
    return JSONResponse({"status": "ok"}, status_code=200)


@app.get("/api/v2/agents/")
async def get_agent(
    version: str = Query(...),
    arch: str = Query(...),
    plat: str = Query(...),
    token: str = Query(default=""),
    api: str = Query(default=""),
):
    log.info("agent download: version=%s arch=%s plat=%s", version, arch, plat)
    binary_path = await fetch_binary(version, arch=arch, plat=plat)
    filename = binary_path.name
    return FileResponse(
        path=binary_path,
        media_type="application/octet-stream",
        filename=filename,
    )


@app.post("/api/v2/exe")
async def generate_exe(request: Request):
    """
    Generate a Windows EXE installer using 7-Zip SFX.

    Expects JSON payload matching what tacticalrmm/utils.py generate_winagent_exe() sends:
      client, site, agenttype, rdp, ping, power, goarch, token, inno, url, api, codesigntoken
    Returns: application/octet-stream EXE file
    """
    data = await request.json()
    log.info(
        "exe gen: client=%s site=%s agenttype=%s goarch=%s api=%s",
        data.get("client"),
        data.get("site"),
        data.get("agenttype"),
        data.get("goarch"),
        data.get("api"),
    )

    ps1_content = build_ps1(data)

    try:
        exe_bytes = await asyncio.get_event_loop().run_in_executor(
            None, build_sfx_exe, ps1_content
        )
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to build EXE: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    return Response(
        content=exe_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="trmm-installer.exe"'},
    )


@app.get("/api/v2/webtar/")
async def get_webtar(version: str = Query(...), token: str = Query(default="")):
    url = f"https://github.com/{GITHUB_REPO}/releases/download/{version}/webtar-{version}.tar.gz"
    return JSONResponse({"url": url})


@app.get("/health")
async def health():
    return {"status": "ok", "repo": GITHUB_REPO, "cache": str(BINARY_CACHE_DIR)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
