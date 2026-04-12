FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir grpcio protobuf

# Ensure python output is unbuffered so logs appear immediately
CMD ["python", "-u", "raft_server.py"]
