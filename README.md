# NexChecker 🔍

**NexChecker** is a Telegram bot that checks if a mobile number is registered on Myntra and auto-receives OTPs via NexNum virtual numbers.

## Features
- 🔍 Myntra account registration check
- 📱 Auto-buy virtual number + OTP polling
- 📋 Native copy buttons (OTP + Full SMS)
- 🔄 Session restore on bot restart
- ☁️ Runs on AWS with systemd auto-restart

## Setup

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/NexChecker.git
cd NexChecker/NexBot

# 2. Create venv
python3 -m venv .venv
source .venv/bin/activate   # Linux
.venv\Scripts\activate      # Windows

# 3. Install deps
pip install -r requirements.txt
playwright install chromium

# 4. Configure
cp .env.example .env
# Edit .env with your BOT_TOKEN and NEXNUM_API_KEY

# 5. Warmup browser profile (first time only)
python warmup.py

# 6. Run
python bot.py
```

## Environment Variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `NEXNUM_API_KEY` | NexNum API key |

## Deploy (AWS / Linux)

```bash
sudo systemctl start nexchecker
sudo systemctl status nexchecker
sudo journalctl -u nexchecker -f   # live logs
```
