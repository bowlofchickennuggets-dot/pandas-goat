FROM python:3.11-slim

WORKDIR /app

# Install Node.js
RUN apt-get update && \
    apt-get install -y curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# JavaScript dependencies
COPY package*.json ./
RUN npm install

# Copy project
COPY . .

RUN mkdir -p /app/data

CMD ["python", "main.py"]