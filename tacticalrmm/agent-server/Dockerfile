FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends p7zip-full wget && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx

COPY server.py /app/server.py

RUN mkdir -p /data/agents

RUN wget -qO /tmp/7z-win.exe https://downloads.sourceforge.net/sevenzip/7z2409.exe && \
    7z e /tmp/7z-win.exe 7z.sfx -o/app/ && \
    rm /tmp/7z-win.exe && \
    ls -la /app/7z.sfx

EXPOSE 8000

CMD ["python", "server.py"]
