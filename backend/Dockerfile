FROM python:3.12-slim

WORKDIR /app

# System deps: libpq (Postgres), gcc (compile extensions), git (Kronos clone)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-kronos.txt ./
# Install CPU-only torch first (much smaller than default CUDA build, fits in 512 MB free tier)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
# Optional Kronos extras. torch is already satisfied by the CPU wheel above.
RUN pip install --no-cache-dir -r requirements-kronos.txt

# Clone Kronos AI forecasting library
RUN git clone --depth 1 https://github.com/shiyu-coder/Kronos.git /app/kronos_lib

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
