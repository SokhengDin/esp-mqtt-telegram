# ESP32 Device Controller

An IoT solution with FastAPI-based MQTT controller and ESP32 firmware for remote device control via interactive Telegram bot.

## 🏗️ Architecture

```
┌─────────────────┐    MQTT     ┌─────────────────┐    GPIO    ┌─────────────┐
│  FastAPI Server │◄──────────►│   ESP32 Device  │──────────►│    Relay      │
│   + Telegram    │             │    (Firmware)   │            │             │
│   Interactive   │             └─────────────────┘            └─────────────┘
│   Control Panel │                     ▲
└─────────────────┘                     │
         ▲                         WiFi Network
         │                               │
    HTTP/REST                            ▼
         │                     ┌─────────────────┐
         ▼                     │  MQTT Broker    │
┌─────────────────┐            │   (Mosquitto)   │
│   Web Client    │            └─────────────────┘
│   Mobile App    │
└─────────────────┘
```


---

## 🚀 Quick Setup

### 1. Python FastAPI Controller

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp environment_template.env .env
# Edit .env with your settings

# Run the application
python main.py
```

### 2. ESP32 Firmware

```bash
cd esp-app

# Configure device settings
idf.py menuconfig
# Navigate to "ESP32 Device Controller Configuration"

# Build and flash
idf.py build
idf.py flash monitor
```

---

## ⚙️ Configuration Guide

### 🐍 Python Controller Configuration

Create a `.env` file with your settings:

```env
# Application Settings
APP_HOST                = 0.0.0.0
APP_PORT                = 8000
APP_RELOAD              = true

# MQTT Broker Settings
MQTT_BROKER_HOST        = 192.168.1.100
MQTT_BROKER_PORT        = 1883
MQTT_USERNAME           = your_mqtt_username
MQTT_PASSWORD           = your_mqtt_password

# Telegram Bot Settings
TELEGRAM_BOT_TOKEN      = 123456789:AAEhBOweik6ad6PsUpxgfgdH6gfsfgsdfgSDF
TELEGRAM_ALLOWED_USERS  = 123456789,987654321

# Configuration
CONFIG_FILE_PATH        = esp_config.json
LOG_LEVEL              = INFO
```

### 🔧 ESP32 Firmware Configuration

#### Method 1: Using `idf.py menuconfig` (Recommended)

```bash
cd esp-app
idf.py menuconfig
```

Navigate to **"ESP32 Device Controller Configuration"** and set:

| Setting | Example Value | Description |
|---------|---------------|-------------|
| **WiFi SSID** | `"MyWiFiNetwork"` | Your WiFi network name |
| **WiFi Password** | `"MyWiFiPassword"` | Your WiFi password |
| **Maximum Retry** | `5` | WiFi connection retry attempts |
| **MQTT Broker URI** | `"mqtt://192.168.1.100:1883"` | MQTT broker address |
| **MQTT Username** | `"esp_user"` | MQTT authentication username |
| **MQTT Password** | `"esp_password"` | MQTT authentication password |
| **Device ID** | `"esp-device-1"` | Unique device identifier |
| **Relay GPIO Pin** | `2` | GPIO pin for relay control |
| **Status LED GPIO Pin** | `25` | GPIO pin for status LED |

#### Method 2: Direct Configuration Files

1. **Edit `esp-app/sdkconfig.defaults`:**
```ini
# WiFi Configuration
CONFIG_ESP_WIFI_SSID="MyWiFiNetwork"
CONFIG_ESP_WIFI_PASSWORD="MyWiFiPassword"
CONFIG_ESP_MAXIMUM_RETRY=5

# MQTT Configuration
CONFIG_MQTT_BROKER_URI="mqtt://192.168.1.100:1883"
CONFIG_MQTT_USERNAME="esp_user"
CONFIG_MQTT_PASSWORD="esp_password"

# Device Configuration
CONFIG_DEVICE_ID="esp-device-1"
CONFIG_RELAY_GPIO=2
CONFIG_STATUS_LED_GPIO=25
```

2. **Clean and rebuild:**
```bash
idf.py clean
idf.py build
```

---

## 🔌 Hardware Connections

### ESP32 Pin Configuration

```
ESP32 Board          Component
├─ GPIO 2  ────────► Relay Control (IN)
├─ GPIO 25 ────────► Status LED (Anode)
├─ GND     ────────► LED Cathode, Relay GND
└─ VCC     ────────► Relay VCC (if needed)
```

### Status LED Indicators

| Pattern | Status |
|---------|--------|
| 🔴 **Solid OFF** | WiFi Disconnected |
| 🟡 **Slow Blink** | WiFi Connecting... |
| 🟠 **Fast Blink** | WiFi Connected, MQTT Connecting |
| 🟢 **Solid ON** | Fully Connected (WiFi + MQTT) |

---

## 🤖 Interactive Telegram Bot


#### Command Interface
```
/control esp-device-1
```
Opens an interactive control panel with:
- 🔌 **Turn ON** button
- ⚫ **Turn OFF** button  
- 🔄 **Refresh** status
- ❌ **Close** panel

### Available Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Initialize bot and show welcome | `/start` |
| `/help` | Show all available commands | `/help` |
| `/get_devices` | List all connected devices | `/get_devices` |
| `/status <device_id>` | Get device status and relay state | `/status esp-device-1` |
| `/control <device_id>` | Open interactive control panel | `/control esp-device-1` |

### Setting up Telegram Bot

1. **Create bot with @BotFather:**
   - Send `/newbot` to @BotFather
   - Choose a name and username
   - Copy the bot token

2. **Get your user ID:**
   - Send a message to your bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your `chat.id` in the response

3. **Add to `.env` file:**
```env
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_ALLOWED_USERS=YOUR_USER_ID
```

---

## 📡 MQTT Topics & Protocol

### Topic Structure
```
{device_id}/status          # Device online/offline status
{device_id}/relay/set       # Command topic (subscribe)
{device_id}/relay/state     # Current relay state (publish)
```

### Message Examples
```json
// Relay Control Command (QoS 1)
Topic: esp-device-1/relay/set
Payload: "on" | "off"

// Status Updates
Topic: esp-device-1/status
Payload: "online" | "offline"

// Relay State Confirmation
Topic: esp-device-1/relay/state
Payload: "on" | "off"
```

### Enhanced MQTT Features
- **QoS 1 Support**: Reliable relay command delivery
- **Dual Topic Handling**: Separate status and relay feedback
- **Connection Tracking**: Real-time MQTT connection status
- **Auto-subscription**: Automatic topic management

---

## 🌐 REST API Endpoints

### Device Management
```http
GET    /devices                    # List all devices
GET    /devices/{device_id}        # Get specific device info
POST   /devices/{device_id}/control # Control device relay
POST   /devices                    # Add new device
DELETE /devices/{device_id}        # Remove device
```

### System Management
```http
GET    /config/reload              # Reload configuration
GET    /mqtt/status                # Check MQTT connection status
GET    /telegram/status            # Check Telegram bot status
POST   /telegram/test_send         # Send test message
POST   /subscribe/{device_id}      # Subscribe to device topics
```

### Example API Usage
```bash
# Get all devices
curl http://localhost:8000/devices

# Control relay
curl -X POST http://localhost:8000/devices/esp-device-1/control \
  -H "Content-Type: application/json" \
  -d '{"device": "esp-device-1", "relay_state": "on"}'

# Check device status
curl http://localhost:8000/devices/esp-device-1

# Check system status
curl http://localhost:8000/mqtt/status
curl http://localhost:8000/telegram/status
```

---

## 🛠️ Development & Deployment

### Python Development
```bash
# Install development dependencies
pip install -r requirements.txt

# Run with auto-reload
python main.py

# Check logs
tail -f logs/app.log

# API documentation available at:
# http://localhost:8000/docs (disabled by default)
# http://localhost:8000/redoc (disabled by default)
```

### ESP32 Development
```bash
cd esp-app

# Configure build
idf.py set-target esp32c6  # or esp32, esp32s3, etc.

# Build firmware
idf.py build

# Flash and monitor
idf.py flash monitor

# Just monitor serial output
idf.py monitor
```

### 🐳 Docker Deployment
```dockerfile
# Dockerfile included - build with:
docker build -t esp32-controller .
docker run -p 8000:8000 --env-file .env esp32-controller
```

---

## 📁 Project Structure

```
esp-hrm-manager/
├── README.md                      # This documentation
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container deployment
├── environment_template.env       # Environment template
├── main.py                       # FastAPI application entry point
├── config.py                     # Settings and configuration
├── models.py                     # Data models and enums
├── managers.py                   # Device configuration management
├── mqtt_client.py                # MQTT client implementation
├── telegram_bot.py               # Interactive Telegram bot
├── logger.py                     # Centralized logging system
├── logs/
│   └── app.log                   # Application logs (auto-created)
└── esp-app/                      # ESP32 firmware
    ├── main/
    │   ├── esp-app.c             # Main firmware code
    │   ├── mqtt_client.c         # MQTT functionality
    │   ├── wifi_manager.c        # WiFi management
    │   ├── relay_control.c       # Relay control
    │   ├── includes/             # Header files
    │   ├── CMakeLists.txt        # Build configuration
    │   └── Kconfig.projbuild     # Menu configuration
    ├── sdkconfig.defaults        # Default ESP-IDF config
    └── CMakeLists.txt           # Project build file
```

### Module Responsibilities

| Module | Purpose |
|--------|---------|
| `main.py` | FastAPI application and routing |
| `models.py` | Data structures, enums, and Pydantic models |
| `managers.py` | Device configuration and persistence |
| `mqtt_client.py` | MQTT communication and message handling |
| `telegram_bot.py` | Interactive bot interface and commands |
| `logger.py` | Centralized logging with color-coded output |

---

## 📝 Logging System

### Centralized Logging Features
- **Color-coded Console Output**: Different colors for log levels
- **Unified Log File**: All logs in `logs/app.log`
- **Log Rotation**: Automatic log rotation (10MB main file, 5 backups)
- **Module-specific Loggers**: Organized logger hierarchy
- **Third-party Logger Suppression**: Reduced noise from dependencies

### Log File Location
```bash
# Main application log
logs/app.log

# Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
# Configurable via LOG_LEVEL environment variable
```

### Startup Banner Example
```
============================================================
ESP32 Device Controller Starting Up
============================================================
Log Level: INFO
App Host: 0.0.0.0:8000
MQTT Broker: 192.168.1.100:1883
Config File: esp_config.json
Reload Mode: True
============================================================
```

---

## 🐛 Troubleshooting

### Common ESP32 Issues

**WiFi Connection Failed:**
```bash
# Check configuration
idf.py menuconfig
# Verify SSID/password in "ESP32 Device Controller Configuration"

# Check serial monitor for error messages
idf.py monitor
```

**MQTT Connection Failed:**
```bash
# Verify broker URI format: mqtt://IP:PORT
# Check network connectivity: ping your MQTT broker
# Verify credentials if authentication is enabled
```

**Build Errors:**
```bash
# Clean and rebuild
idf.py clean
idf.py build

# Check ESP-IDF version compatibility
idf.py --version
```

### Common Python Issues

**MQTT Connection Failed:**
- Verify broker is running: `mosquitto -v`
- Check firewall settings
- Verify credentials in `.env` file
- Check logs: `tail -f logs/app.log`

**Telegram Bot Not Responding:**
- Verify bot token is correct
- Check allowed users list
- Test bot with `/start` command
- Check bot status: `curl http://localhost:8000/telegram/status`

**Interactive Panel Issues:**
- "Message is not modified" errors are handled automatically
- Check device connection status in control panel
- Use refresh button to update status

### Device Configuration Reset

**Reset ESP32 to defaults:**
```bash
cd esp-app
idf.py erase-flash
idf.py flash
```

**Reset Python configuration:**
```bash
rm esp_config.json
python main.py  # Will create default config
```

**Check System Status:**
```bash
# MQTT status
curl http://localhost:8000/mqtt/status

# Telegram status  
curl http://localhost:8000/telegram/status

# Device list
curl http://localhost:8000/devices
```

---

## 📚 Additional Resources

- **ESP-IDF Documentation**: https://docs.espressif.com/projects/esp-idf/
- **FastAPI Documentation**: https://fastapi.tiangolo.com/
- **Telegram Bot API**: https://core.telegram.org/bots/api
- **MQTT Protocol**: https://mqtt.org/
- **Docker Documentation**: https://docs.docker.com/
