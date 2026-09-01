FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for ICMP (raw sockets)
RUN apt-get update && apt-get install -y \
    iputils-ping \
    libcap2-bin \
    libpq-dev \
    unixodbc-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Allow ICMP raw sockets
RUN setcap cap_net_raw+ep /usr/bin/ping

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
