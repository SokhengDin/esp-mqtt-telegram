# ESP32 Device Controller

A FastAPI-based MQTT controller for ESP32 devices with Telegram bot integration.

## Features

- 🔌 Control ESP32 device relays via MQTT
- 🤖 Telegram bot for remote control
- 📊 Real-time device status monitoring
- 🌐 REST API for device management
- ⚙️ Environment-based configuration

## Quick Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp environment_template.env .env
   # Edit .env with your settings
   ```

3. **Run the application:**
   ```bash
   python main.py
   ```

The API will be available at `http://localhost:8000`

## Configuration

Edit your `.env` file with these settings:

```env
# MQTT Settings
MQTT_BROKER_HOST        = your_mqtt_broker
MQTT_BROKER_PORT        = 1883
MQTT_USERNAME           = username
MQTT_PASSWORD           = password

# Telegram Bot
TELEGRAM_BOT_TOKEN      = your_bot_token
TELEGRAM_ALLOWED_USERS  = user_id1,user_id2
```

## Telegram Commands

- `/start` - Get started
- `/get_devices` - List all devices
- `/status <device_id>` - Check device status
- `/control <device_id> <on/off>` - Control relay

## API Endpoints

- `GET /devices` - List all devices
- `GET /devices/{device_id}` - Get device info
- `POST /devices/{device_id}/control` - Control device relay
- `GET /telegram/status` - Check bot status

## Device Configuration

Devices are stored in `esp_config.json` (auto-created):

```json
{
  "devices": [
    {
      "device": "esp-cdc-hrm-1",
      "status": "connected",
      "relay_state": "off",
      "mqtt_topic": "esp-cdc-hrm-1"
    }
  ]
}
```

## MQTT Topics

- Device status: `{device_id}/status`
- Relay control: `{device_id}/relay/set`

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run with auto-reload
python main.py
```

Visit `http://localhost:8000/docs` for the interactive API documentation. 