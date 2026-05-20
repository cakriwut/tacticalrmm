FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx

COPY server.py /app/server.py

RUN mkdir -p /data/agents

EXPOSE 8000

CMD ["python", "server.py"]
