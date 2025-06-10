# ESP32 Device Controller

ESP-IDF project for ESP32-based IoT device controller with WiFi, MQTT, and relay control.

## Features

- 🔌 Single relay control via GPIO
- 📡 WiFi connectivity with auto-reconnection
- 🔄 MQTT client with auto-reconnection
- 💡 Status LED indicating connection state
- ❤️ Periodic heartbeat and status reporting
- 🔧 Configurable via menuconfig

## Hardware Connections

| Component | GPIO Pin | Description |
|-----------|----------|-------------|
| Relay | GPIO 2 (configurable) | Controls relay module |
| Status LED | GPIO 25 (configurable) | Connection status indicator |

### Status LED Patterns

- **Off**: Disconnected from WiFi
- **Slow Blink (500ms)**: Connecting to WiFi
- **Fast Blink (200ms)**: WiFi connected, connecting to MQTT
- **Solid On**: Fully connected (WiFi + MQTT)

## Configuration

Configure the project using ESP-IDF menuconfig:

```bash
idf.py menuconfig
```

Navigate to **ESP32 Device Controller Configuration** and set:

- **WiFi SSID**: Your WiFi network name
- **WiFi Password**: Your WiFi password
- **MQTT Broker URI**: e.g., `mqtt://192.168.1.100:1883`
- **MQTT Username**: (optional)
- **MQTT Password**: (optional)
- **Device ID**: Unique identifier (e.g., `esp-cdc-hrm-1`)
- **Relay GPIO Pin**: GPIO pin for relay control
- **Status LED GPIO Pin**: GPIO pin for status LED

## Build and Flash

```bash
# Configure the project
idf.py menuconfig

# Build the project
idf.py build

# Flash to ESP32
idf.py -p /dev/ttyUSB0 flash

# Monitor serial output
idf.py -p /dev/ttyUSB0 monitor
```

## MQTT Topics

The device uses the following MQTT topics (where `{device_id}` is your configured Device ID):

### Subscribed Topics (Incoming Commands)
- `{device_id}/relay/set` - Relay control commands (`on` or `off`)

### Published Topics (Status Updates)
- `{device_id}/status` - Device online status (`online` or `offline`)
- `{device_id}/relay/state` - Current relay state (`on` or `off`)

### Example Commands

To control the relay via MQTT:
```bash
# Turn relay ON
mosquitto_pub -h your-mqtt-broker -t "esp-cdc-hrm-1/relay/set" -m "on"

# Turn relay OFF
mosquitto_pub -h your-mqtt-broker -t "esp-cdc-hrm-1/relay/set" -m "off"
```

## Project Structure

```
esp-app/
├── main/
│   ├── includes/           # Header files
│   │   ├── wifi_manager.h
│   │   ├── mqtt_client.h
│   │   └── relay_control.h
│   ├── esp-app.c          # Main application
│   ├── wifi_manager.c     # WiFi connectivity
│   ├── mqtt_client.c      # MQTT client
│   ├── relay_control.c    # Relay control
│   ├── CMakeLists.txt     # Component build config
│   └── Kconfig.projbuild  # Project configuration
├── CMakeLists.txt         # Main build config
├── sdkconfig.defaults     # Default configuration
└── README.md              # This file
```

## Integration with Python Controller

This ESP32 firmware is designed to work with the Python FastAPI controller. The device will:

1. Connect to your WiFi network
2. Connect to the MQTT broker
3. Subscribe to relay control commands
4. Publish status updates and heartbeats
5. Respond to commands from the Telegram bot or REST API

## Troubleshooting

### WiFi Connection Issues
- Check SSID and password in menuconfig
- Verify WiFi network is 2.4GHz (ESP32 doesn't support 5GHz)
- Check signal strength

### MQTT Connection Issues
- Verify MQTT broker URI is correct
- Check if broker requires authentication
- Ensure firewall allows MQTT traffic (port 1883)

### Build Issues
- Ensure ESP-IDF is properly installed and sourced
- Check ESP-IDF version compatibility
- Clean build: `idf.py fullclean`

### Serial Monitor
To see debug output:
```bash
idf.py -p /dev/ttyUSB0 monitor
```

Press `Ctrl+]` to exit monitor.

## Default Pin Configuration

- **Relay**: GPIO 2
- **Status LED**: GPIO 25

These can be changed in menuconfig under "ESP32 Device Controller Configuration". 