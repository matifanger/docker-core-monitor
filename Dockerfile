# Frontend build stage
FROM node:20-alpine as frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Backend stage
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY app.py .

# Copy frontend build
COPY --from=frontend-builder /frontend/build ./static

# Expose the port
EXPOSE 5000

# Start the server
CMD ["python", "app.py"] 