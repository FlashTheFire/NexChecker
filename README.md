# NexChecker 🔍

**NexChecker** is a multi-platform registration checker and automated virtual number acquisition bot. It verifies whether mobile numbers are registered across major Indian consumer platforms and auto-receives OTPs via NexNum.

## Supported Platforms
- 🍽 **Zomato** (`/zomato` / `zomato_check.py`): Silent contact-sync recommendation verification (zero OTP to target)
- 🛍 **Flipkart** (`/flipkart` / `flipkart_check.py`): Direct HTTP status verification
- 🛒 **BigBasket** (`/bigbasket` / `bigbasket_check.py`): Reverse engineered member status checking
- 📦 **Myntra** (`/myntra` / `myntra_check.py`): Browser-accelerated challenge auto-healing
- ⚡ **Meesho / Swiggy / Zepto / Amazon**: Direct standalone CLI inspection modules

## Features
- 🔍 Multi-platform silent account registration checks
- 📱 Auto-buy virtual number + OTP polling via NexNum
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
| `API_ACCESS_KEY` | Dedicated security key for API consumers (`X-API-Key`) |

## Targeted Virtual Number Purchase API

Endpoint for purchasing numbers filtered by silent registration status:
- **`POST /api/v1/purchase`** (or `/api/purchase`)

### Request Headers
- `X-API-Key`: Dedicated API access key (if configured on server)
- `X-NexNum-Key`: Caller's NexNum API key (or pass in request JSON as `api_key`)

### Request Body
```json
{
  "platform": "zomato",
  "target_status": "NOT_REGISTERED",
  "service_code": "dy",
  "country_code": "22",
  "max_attempts": 5,
  "api_key": "YOUR_NEXNUM_KEY"
}
```

### Successful Response (`200 OK`)
```json
{
  "success": true,
  "order_id": "1791225496122425077082",
  "phone_number": "919876543210",
  "clean_mobile": "9876543210",
  "platform": "zomato",
  "status": "NOT_REGISTERED",
  "cost": 9.0,
  "attempts_taken": 2,
  "discarded_orders": [
    {
      "order_id": "1791225496122425077081",
      "phone_number": "919876543211",
      "status": "REGISTERED",
      "cancellation": "QUEUED_DEFERRED"
    }
  ],
  "nexnum_direct_usage": {
    "get_status_url": "https://nexnum.in/stubs/handler_api.php?action=getStatus&id=1791225496122425077082&api_key=YOUR_NEXNUM_KEY",
    "cancel_url": "https://nexnum.in/stubs/handler_api.php?action=setStatus&id=1791225496122425077082&status=8&api_key=YOUR_NEXNUM_KEY"
  }
}
```

Caller uses the returned `order_id` directly with [NexNum API Documentation](https://nexnum.in/en/api-docs) to poll SMS/OTP (`action=getStatus`) or complete activations (`action=setStatus&status=6`).

## Deploy (AWS / Linux)

```bash
sudo systemctl start nexchecker
sudo systemctl status nexchecker
sudo journalctl -u nexchecker -f   # live logs
```
