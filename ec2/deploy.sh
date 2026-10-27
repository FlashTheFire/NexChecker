#!/usr/bin/env bash
# ==============================================================================
# NexChecker 1-Command Production Deployment Script for AWS EC2
# Usage: bash ec2/deploy.sh
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${APP_DIR}"

echo "========================================================"
echo "🚀 Deploying NexChecker on AWS EC2..."
echo "Directory: ${APP_DIR}"
echo "========================================================"

# 1. Check for .env file
if [ ! -f "${APP_DIR}/.env" ]; then
    if [ -f "${APP_DIR}/.env.example" ]; then
        echo "⚠️  .env not found. Copying .env.example -> .env..."
        cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
        echo "Please edit ${APP_DIR}/.env with your real BOT_TOKEN and secret keys before re-running."
    else
        echo "❌ Error: Neither .env nor .env.example found."
        exit 1
    fi
fi

# 2. Ensure data directory structure exists
mkdir -p "${APP_DIR}/NexBot/data/users"
chmod -R 775 "${APP_DIR}/NexBot/data"

# 3. Pull latest code if Git repository
if [ -d "${APP_DIR}/.git" ]; then
    echo "📥 Pulling latest git updates..."
    git fetch origin master
    git merge origin/master --ff-only || true
fi

# 4. Generate local self-signed SSL certs if none exist
CERT_DIR="${APP_DIR}/docker/certs"
mkdir -p "${CERT_DIR}"
if [ ! -f "${CERT_DIR}/cert.pem" ] || [ ! -f "${CERT_DIR}/key.pem" ]; then
    echo "🔐 Generating SSL certificates for Nginx..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "${CERT_DIR}/key.pem" \
        -out "${CERT_DIR}/cert.pem" \
        -subj "/C=IN/ST=Delhi/L=NewDelhi/O=NexChecker/CN=nexchecker.ec2.local"
fi

# 5. Build and launch Docker Compose stack
echo "🐳 Rebuilding and starting Docker services..."
docker compose down --remove-orphans || true
docker compose build --pull
docker compose up -d

# 6. Verify health
echo "⏳ Waiting for services to become healthy..."
sleep 5
docker compose ps

echo "========================================================"
echo "✅ NexChecker is now LIVE on AWS EC2!"
echo "Check logs anytime with: docker compose logs -f bot"
echo "========================================================"
