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
  GET  /api/v2/webtar/     — proxies web tar from GitHub releases (optional)
  GET  /health             — health check

Binaries are fetched from cakriwut/rmmagent GitHub Releases on first request
and cached in BINARY_CACHE_DIR.
"""
import asyncio
import logging
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="TRMM Agent Server", docs_url=None, redoc_url=None)

GITHUB_REPO = os.environ.get("GITHUB_REPO", "cakriwut/rmmagent")
BINARY_CACHE_DIR = Path(os.environ.get("BINARY_CACHE_DIR", "/data/agents"))
BINARY_CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
