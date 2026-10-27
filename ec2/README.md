# 🚀 NexChecker — AWS EC2 Production Deployment Guide

This directory contains production-ready configuration and automated provisioning scripts to deploy **NexChecker** (Universal Platform Checker API + Telegram Bot) onto AWS EC2 instances (e.g. `t3.micro`, `t3.small`, or Ubuntu 22.04/24.04 LTS).

---

## ⚡ Option 1: Docker Compose Deployment (Recommended)

### Step 1: Clone Repository on EC2
```bash
git clone https://github.com/FlashTheFire/NexChecker.git /home/ubuntu/NexChecker
cd /home/ubuntu/NexChecker
```

### Step 2: Run Host Setup & Swap Configuration
```bash
bash ec2/setup_ec2.sh
```
*Configures 2GB swap (prevents OOM on t3.micro), installs Docker Engine, UFW firewall, and tools.*

### Step 3: Configure Environment Variables
```bash
cp .env.example .env
nano .env
```
Ensure the following variables are configured:
- `BOT_TOKEN`: Your Telegram Bot Token (`9262395268:AAHxorgmQ0rTQzdrMRkQc8XDCyVqFECA1jY`)
- `ADMIN_IDS`: Admin Telegram IDs (`1889471360`)
- `ZOMATO_SERVICE_CODE`: `dy`

### Step 4: Run 1-Click Deploy
```bash
bash ec2/deploy.sh
```
This automatically builds the containers, generates SSL certificates, and launches the entire stack:
- **`nexchecker_bot`**: Multi-platform Telegram Bot with per-order hierarchical JSON storage.
- **`nexchecker_api`**: Universal REST API with Swagger docs at `http://<EC2-IP>:8000/docs`.
- **`nexchecker_nginx`**: SSL Reverse Proxy on ports 80 & 443.
- **`nexchecker_tunnel`**: Cloudflare Tunnel for secure HTTPS worldwide.

### Manage Services
```bash
# View live bot logs
docker compose logs -f bot

# Restart services
docker compose restart

# View running containers
docker compose ps
```

---

## 🛠️ Option 2: Native Systemd Deployment (Without Docker)

If you prefer running directly on the host using Python `venv`:

```bash
# 1. Create Virtualenv & Install Requirements
python3 -m venv /home/ubuntu/NexChecker/venv
/home/ubuntu/NexChecker/venv/bin/pip install --upgrade pip
/home/ubuntu/NexChecker/venv/bin/pip install -r /home/ubuntu/NexChecker/requirements.txt
/home/ubuntu/NexChecker/venv/bin/playwright install --with-deps chromium

# 2. Copy Systemd Unit Files
sudo cp ec2/nexchecker-bot.service /etc/systemd/system/
sudo cp ec2/nexchecker-api.service /etc/systemd/system/

# 3. Reload & Enable Services
sudo systemctl daemon-reload
sudo systemctl enable --now nexchecker-api
sudo systemctl enable --now nexchecker-bot

# 4. Check Status
sudo systemctl status nexchecker-bot
sudo journalctl -u nexchecker-bot -f
```

---

## 📁 Storage Architecture (Millions of Numbers / Thousands of Users)

User and order data is isolated hierarchically in `NexBot/data/users/`:
```text
NexBot/data/users/
├── 1889471360/
│   ├── info.json                           # User profile, API key, preferences, active order pointers
│   ├── 1791210961004126002825.json         # Complete order file for purchase 1
│   └── 1791210961004126002999.json         # Complete order file for purchase 2 (e.g. Zomato)
└── 974986178/
    ├── info.json
    └── ...
```

- **Concurrency Isolation**: Active purchases across different services (Zomato, Myntra, Flipkart, BigBasket) do not overwrite each other.
- **Order-Keyed SMS Polling**: Each SMS polling worker is keyed by `order_id`, allowing simultaneous background OTP polling for multiple platforms.
