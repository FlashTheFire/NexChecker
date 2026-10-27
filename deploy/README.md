# 🚀 NexChecker — Universal Deployment & Operations Guide

NexChecker includes a fully universal, single-command deployment engine designed to run seamlessly on **any Linux server, VPS, cloud provider (AWS, GCP, Azure, DigitalOcean, Hetzner, Linode, Oracle Cloud), or bare-metal environment**.

---

## ⚡ Quick Start (1-Command Universal Deploy)

### 1. Clone & Enter Repository
```bash
git clone https://github.com/FlashTheFire/NexChecker.git
cd NexChecker
```

### 2. Configure Credentials
```bash
cp .env.example .env
nano .env
```
Ensure your `BOT_TOKEN` (`9262395268:AAHxorgmQ0rTQzdrMRkQc8XDCyVqFECA1jY`), `ADMIN_IDS` (`1889471360`), and API keys are set.

### 3. Launch
```bash
bash deploy.sh
```
*That's it!* The universal engine will automatically:
1. Detect your Linux distribution (Ubuntu, Debian, CentOS, RHEL, Fedora, Rocky, Alma, Arch, Alpine).
2. Configure a 2GB swap partition if running on low-memory servers (<2GB RAM).
3. Ensure Docker and Docker Compose plugin are installed and active.
4. Generate local SSL certificates for secure HTTPS reverse proxying.
5. Create and permission the hierarchical storage directories (`NexBot/data/users/`).
6. Build and start all microservices:
   - **`nexchecker_bot`**: Multi-platform Telegram Bot.
   - **`nexchecker_api`**: Universal REST API with Swagger documentation at `http://localhost:8000/docs`.
   - **`nexchecker_nginx`**: SSL Reverse Proxy on ports 80 and 443.
   - **`nexchecker_tunnel`**: Cloudflare Tunnel for trusted public HTTPS anywhere.

---

## 🛠️ Management CLI Commands

```bash
# View live container / service status
bash deploy.sh --status

# Tail live application and bot logs
bash deploy.sh --logs

# Restart all services
bash deploy.sh --restart

# Stop all services
bash deploy.sh --stop
```

---

## 💻 Alternative: Native Host Mode (Without Docker)

To run natively on the host using Python virtual environment and native Linux systemd services:

```bash
bash deploy.sh --native
```
This automatically:
- Creates `venv/` and installs all dependencies from `requirements.txt`.
- Installs Playwright Chromium browsers with all OS library dependencies.
- Generates tailored systemd service files dynamically bound to the current user and repository path:
  - `/etc/systemd/system/nexchecker-bot.service`
  - `/etc/systemd/system/nexchecker-api.service`
- Enables and starts the services via `systemctl`.

---

## 📁 Storage Architecture (High Volume / Multi-User)

User profiles and orders are stored hierarchically:
```text
NexBot/data/users/
├── <user_id>/
│   ├── info.json                 # User profile, API key, preferences, active order pointers
│   ├── <order_id_1>.json         # Complete purchase & check state for order 1
│   └── <order_id_2>.json         # Complete purchase & check state for order 2
```
- **Independent Concurrent Loops**: A user can run checks across different services (Zomato, Myntra, Flipkart, BigBasket) simultaneously without state collisions.
- **Order-Keyed SMS Polling**: Background OTP polling is isolated per order ID.
