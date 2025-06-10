import os
import json
import logging
import uvicorn

import paho.mqtt.client as mqtt
from pathlib import Path
from decouple import config

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

from config import settings

from contextlib import asynccontextmanager
from telegram import Bot, Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes

from fastapi import HTTPException, status, Depends, Request, Response, FastAPI
from fastapi.responses import Response, JSONResponse

logging.basicConfig(
    level   = getattr(logging, settings.LOG_LEVEL.upper())
    , format= settings.LOG_FORMAT
    , handlers = [
        logging.StreamHandler()
        , logging.FileHandler("app.log")
    ]
)

logger = logging.getLogger(__name__)

class DeviceStatus(str, Enum):
    connected       = "connected"
    disconnected    = "disconnected"

class RelayState(str, Enum):
    on              = "on"
    off             = "off"

class Device(BaseModel):
    device      : str = Field(..., description="Device identifier")
    status      : DeviceStatus = Field(..., description="Connection status")
    relay_state : RelayState = Field(..., description="Relay state")
    mqtt_topic  : str = Field(..., description="MQTT topic for device")

class DeviceControl(BaseModel):
    device      : str = Field(..., description="Device identifier") 
    relay_state : RelayState = Field(..., description="Desired relay state")

class DevicesResponse(BaseModel):
    devices     : List[Device]

class ConfigManager:
    def __init__(self, config_file: str = None):
        self.config_file    = Path(config_file or settings.CONFIG_FILE_PATH)
        self.devices_db     : Dict[str, Device] = {}
        self.load_config()

    def load_config(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)

                if "devices" in config_data:
                    devices_list = config_data["devices"]
                elif isinstance(config_data, list):
                    devices_list = config_data
                else:
                    devices_list = [config_data]
                
                for device_data in devices_list:
                    device = Device(**device_data)
                    self.devices_db[device.device] = device

                logger.info(f"Loaded {len(self.devices_db)} devices from {self.config_file}")
            else:
                self.create_default_config()
                logger.info("Created default config")

        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.create_default_config()

    def create_default_config(self):
        default_devices = [{
            "device": "esp-cdc-hrm-1"
            , "status": "disconnected"
            , "relay_state": "off"
            , "mqtt_topic": "esp-cdc-hrm-1"
        }]

        default_config = {"devices": default_devices}

        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=4)

        for device_data in default_devices:
            device = Device(**device_data)
            self.devices_db[device.device] = device

    def save_config(self):
        try:
            devices_list = [device.model_dump() for device in self.devices_db.values()]
            config_data = {"devices": devices_list}

            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=4)

            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get_device(self, device_id: str) -> Optional[Device]:
        return self.devices_db.get(device_id)
    
    def update_device_status(self, device_id: str, status: DeviceStatus):
        if device_id in self.devices_db:
            self.devices_db[device_id].status = status
            self.save_config()
            logger.info(f"Updated {device_id} status to {status}")
    
    def update_device_relay(self, device_id: str, relay_state: RelayState):
        if device_id in self.devices_db:
            self.devices_db[device_id].relay_state = relay_state
            self.save_config()
            logger.info(f"Updated {device_id} relay to {relay_state}")
    
    def add_device(self, device: Device):
        self.devices_db[device.device] = device
        self.save_config()
        logger.info(f"Added new device: {device.device}")
    
    def remove_device(self, device_id: str):
        if device_id in self.devices_db:
            del self.devices_db[device_id]
            self.save_config()
            logger.info(f"Removed device: {device_id}")

class MQTTManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.client         = None
        self.broker_host    = settings.MQTT_BROKER_HOST
        self.broker_port    = settings.MQTT_BROKER_PORT
        self.username       = settings.MQTT_USERNAME
        self.password       = settings.MQTT_PASSWORD

    async def connect_mqtt(self):
        try:
            self.client = mqtt.Client()

            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            self.client.on_connect      = self.on_connect
            self.client.on_message      = self.on_message
            self.client.on_disconnect   = self.on_disconnect

            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()

            logger.info(f"MQTT client connecting to {self.broker_host}:{self.broker_port}")

        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            raise

    async def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("MQTT disconnected")

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logger.info("Connected to MQTT broker")
            for device_id in self.config_manager.devices_db.keys():
                status_topic = f"{device_id}/status"
                client.subscribe(status_topic)
                logger.info(f"Subscribed to {status_topic}")
        else:
            logger.error(f"Failed to connect to MQTT broker, return code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            topic   = msg.topic
            payload = msg.payload.decode()
            logger.info(f"Received MQTT message - Topic: {topic}, Payload: {payload}")

            if "/status" in topic:
                device_id = topic.replace("/status", "")
                if device_id in self.config_manager.devices_db:
                    if payload.lower() in ["online", "connected"]:
                        self.config_manager.update_device_status(device_id, DeviceStatus.connected)
                    else:
                        self.config_manager.update_device_status(device_id, DeviceStatus.disconnected)

        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def on_disconnect(self, client, userdata, rc):
        logger.warning(f"MQTT client disconnected with result code {rc}")

    def publish_relay_control(self, device_id: str, state: RelayState):
        if not self.client:
            raise Exception("MQTT client not connected")
        
        topic   = f"{device_id}/relay/set"
        payload = state.value
        result  = self.client.publish(topic, payload)

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Published relay command to {topic}: {payload}")
            self.config_manager.update_device_relay(device_id, state)
        else:
            logger.error(f"Failed to publish to {topic}")
            raise Exception("Failed to publish MQTT message")

class TelegramBot:
    def __init__(self, config_manager: ConfigManager, mqtt_manager: MQTTManager):
        self.config_manager = config_manager
        self.mqtt_manager   = mqtt_manager
        self.bot_token      = settings.TELEGRAM_BOT_TOKEN
        self.allowed_users  = settings.get_telegram_allowed_users()
        self.application    = None
        
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not found in environment variables")
    

    
    def _is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized to use the bot"""
        if not self.allowed_users:
            logger.warning("No allowed users configured - allowing all users")
            return True
        return user_id in self.allowed_users
    
    async def start(self):
        """Initialize and start the Telegram bot"""
        if not self.bot_token:
            logger.error("Cannot start Telegram bot: No token provided")
            return
        
        try:
            self.application = ApplicationBuilder().token(self.bot_token).build()
            
            # Add command handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("get_devices", self.get_devices_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("control", self.control_command))
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            # Log bot info for debugging
            bot_info = await self.application.bot.get_me()
            logger.info(f"TELEGRAM: Bot started - @{bot_info.username} ({bot_info.id})")
            logger.info(f"TELEGRAM: Allowed users: {self.allowed_users}")
            logger.info("TELEGRAM: Polling started - bot is now listening for messages")
            logger.info("Telegram bot started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            raise
    
    async def stop(self):
        """Stop the Telegram bot"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot stopped")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        # Check if update has a message to reply to
        if not update.effective_message:
            logger.error("No effective message in update")
            return
            
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        logger.info(f"TELEGRAM: User {username} ({user_id}) started the bot")
        
        if not self._is_authorized(user_id):
            logger.warning(f"TELEGRAM: Unauthorized access attempt by {username} ({user_id})")
            await update.effective_message.reply_text("❌ Unauthorized access. Contact administrator.")
            return
        
        welcome_message = """
🤖 *ESP32 Device Controller Bot*

Welcome! I can help you control your ESP32 devices.

Available commands:
• `/get_devices` - List all devices
• `/status <device_id>` - Check device status
• `/control <device_id> <on/off>` - Control device relay
• `/help` - Show this help message

Example:
`/status esp-cdc-hrm-1`
`/control esp-cdc-hrm-1 on`
        """
        
        await update.effective_message.reply_text(welcome_message, parse_mode="Markdown")
        logger.info(f"TELEGRAM: Sent welcome message to {username} ({user_id})")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        # Check if update has a message to reply to
        if not update.effective_message:
            logger.error("No effective message in update")
            return
            
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            await update.effective_message.reply_text("❌ Unauthorized access.")
            return
        
        help_message = """
🔧 *ESP32 Controller Commands*

📱 `/get_devices`
   Lists all available ESP32 devices

📊 `/status <device_id>`
   Shows connection status and relay state
   Example: `/status esp-cdc-hrm-1`

🎛️ `/control <device_id> <on/off>`
   Controls device relay state
   Examples: 
   • `/control esp-cdc-hrm-1 on`
   • `/control esp-cdc-hrm-1 off`

❓ `/help`
   Shows this help message
        """
        
        await update.effective_message.reply_text(help_message, parse_mode="Markdown")
    
    async def get_devices_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /get_devices command"""
        if not update.effective_message:
            logger.error("No effective message in update")
            return
            
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        logger.info(f"User {username} ({user_id}) requested device list")
        
        if not self._is_authorized(user_id):
            await update.effective_message.reply_text("❌ Unauthorized access.")
            return
        
        try:
            devices = list(self.config_manager.devices_db.values())
            
            if not devices:
                await update.effective_message.reply_text("📭 No devices found.")
                return
            
            message = "📱 *ESP32 Devices:*\n\n"
            
            for device in devices:
                status_emoji = "🟢" if device.status == DeviceStatus.connected else "🔴"
                relay_emoji = "🔌" if device.relay_state == RelayState.on else "⚫"
                
                message += f"{status_emoji} *{device.device}*\n"
                message += f"   Status: {device.status}\n"
                message += f"   Relay: {relay_emoji} {device.relay_state}\n"
                message += f"   Topic: `{device.mqtt_topic}`\n\n"
            
            await update.effective_message.reply_text(message, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error in get_devices_command: {e}")
            try:
                await update.effective_message.reply_text("❌ Error retrieving device list.")
            except Exception as reply_error:
                logger.error(f"Failed to send error message: {reply_error}")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status <device_id> command"""
        
        if not update.effective_message:
            logger.error("No effective message in update")
            return
            
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        if not self._is_authorized(user_id):
            await update.effective_message.reply_text("❌ Unauthorized access.")
            return
        
        if not context.args:
            await update.effective_message.reply_text("❌ Usage: `/status <device_id>`\nExample: `/status esp-cdc-hrm-1`", parse_mode="Markdown")
            return
        
        device_id = context.args[0]
        logger.info(f"User {username} ({user_id}) requested status for {device_id}")
        
        try:
            device = self.config_manager.get_device(device_id)
            
            if not device:
                await update.effective_message.reply_text(f"❌ Device `{device_id}` not found.")
                return
            
            status_emoji = "🟢" if device.status == DeviceStatus.connected.value else "🔴"
            relay_emoji = "🔌" if device.relay_state == RelayState.on.value else "⚫"
            
            message = f"""
📊 *Device Status: {device.device}*

{status_emoji} **Connection:** {device.status}
{relay_emoji} **Relay State:** {device.relay_state}
🏷️ **MQTT Topic:** `{device.mqtt_topic}`
            """
            
            await update.effective_message.reply_text(message, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error in status_command: {e}")
            try:
                await update.effective_message.reply_text("❌ Error retrieving device status.")
            except Exception as reply_error:
                logger.error(f"Failed to send error message: {reply_error}")
    
    async def control_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        
        if not update.effective_message:
            logger.error("No effective message in update")
            return
            
        user_id     = update.effective_user.id
        username    = update.effective_user.username or "Unknown"
        
        if not self._is_authorized(user_id):
            await update.effective_message.reply_text("❌ Unauthorized access.")
            return
        
        if len(context.args) != 2:
            await update.effective_message.reply_text(
                "❌ Usage: `/control <device_id> <on/off>`\n"
                "Examples:\n"
                "• `/control esp-cdc-hrm-1 on`\n"
                "• `/control esp-cdc-hrm-1 off`",
                parse_mode="Markdown"
            )
            return
        
        device_id = context.args[0]
        relay_command = context.args[1].lower()
        
        if relay_command not in ["on", "off"]:
            await update.effective_message.reply_text("❌ Relay state must be 'on' or 'off'")
            return
        
        logger.info(f"User {username} ({user_id}) controlling {device_id}: {relay_command}")
        
        try:
            device = self.config_manager.get_device(device_id)
            
            if not device:
                await update.effective_message.reply_text(f"❌ Device `{device_id}` not found.")
                return
            
            if device.status == DeviceStatus.disconnected:
                await update.effective_message.reply_text(f"❌ Device `{device_id}` is disconnected. Cannot control relay.")
                return
            
            relay_state = RelayState.on if relay_command == "on" else RelayState.off
            
            # Send MQTT command
            self.mqtt_manager.publish_relay_control(device_id, relay_state)
            
            relay_emoji = "🔌" if relay_state == RelayState.on else "⚫"
            await update.effective_message.reply_text(
                f"✅ Relay command sent successfully!\n"
                f"{relay_emoji} Device `{device_id}` relay set to **{relay_state.value}**",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Error in control_command: {e}")
            try:
                await update.effective_message.reply_text(f"❌ Failed to control device: {str(e)}")
            except Exception as reply_error:
                logger.error(f"Failed to send error message: {reply_error}")

config_manager  = ConfigManager()
mqtt_manager    = MQTTManager(config_manager=config_manager)
telegram_bot    = TelegramBot(config_manager=config_manager, mqtt_manager=mqtt_manager)

# Dependency injection functions
def get_config_manager() -> ConfigManager:
    return config_manager

def get_mqtt_manager() -> MQTTManager:
    return mqtt_manager

def get_telegram_bot() -> TelegramBot:
    return telegram_bot

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI application starting up")
    logger.info("Logging system initialized successfully")

    try:
        await mqtt_manager.connect_mqtt()
        logger.info("MQTT manager initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MQTT: {e}")
    
    try:
        await telegram_bot.start()
        logger.info("Telegram bot started successfully")
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")
    
    yield

    logger.info("FastAPI application shutting down")
    await mqtt_manager.disconnect()
    await telegram_bot.stop()

app = FastAPI(
    title           = "ESP32 Device Controller"
    , description   = "FastAPI MQTT publisher for controlling ESP32 devices"
    , version       = "1.0.0"
    , lifespan      = lifespan
    , docs_url      = None
    , redoc_url     = None
)

@app.get("/", tags=["Health"])
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "ESP32 Device Controller API", "status": "running"}

@app.get("/devices", response_model=DevicesResponse, tags=["Devices"])
async def get_devices(config: ConfigManager = Depends(get_config_manager)):
    logger.info("Getting all devices")
    return DevicesResponse(devices=list(config.devices_db.values()))

@app.get("/devices/{device_id}", response_model=Device, tags=["Devices"])
async def get_device(
    device_id: str
    , config: ConfigManager = Depends(get_config_manager)
):
    logger.info(f"Getting device: {device_id}")
    
    device = config.get_device(device_id)
    if not device:
        logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    return device

@app.post("/devices/{device_id}/control", tags=["Control"])
async def control_device_relay(
    device_id: str
    , control: DeviceControl
    , config: ConfigManager = Depends(get_config_manager)
    , mqtt: MQTTManager = Depends(get_mqtt_manager)
):
    logger.info(f"Controlling device {device_id} - setting relay to {control.relay_state}")
    
    device = config.get_device(device_id)
    if not device:
        logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device.status == DeviceStatus.disconnected:
        logger.warning(f"Device {device_id} is disconnected")
        raise HTTPException(status_code=400, detail="Device is disconnected")
    
    try:
        mqtt.publish_relay_control(device_id, control.relay_state)
        
        return {
            "message": f"Relay command sent to {device_id}"
            , "device": device_id
            , "relay_state": control.relay_state
            , "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Failed to control device {device_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to send command to device")

@app.post("/devices", response_model=Device, tags=["Devices"])
async def add_device(
    device: Device
    , config: ConfigManager = Depends(get_config_manager)
    , mqtt: MQTTManager = Depends(get_mqtt_manager)
):
    logger.info(f"Adding new device: {device.device}")
    
    if config.get_device(device.device):
        logger.warning(f"Device already exists: {device.device}")
        raise HTTPException(status_code=400, detail="Device already exists")
    
    config.add_device(device)
    
    if mqtt.client:
        status_topic = f"{device.device}/status"
        mqtt.client.subscribe(status_topic)
        logger.info(f"Subscribed to {status_topic}")
    
    return device

@app.delete("/devices/{device_id}", tags=["Devices"])
async def remove_device(
    device_id: str
    , config: ConfigManager = Depends(get_config_manager)
    , mqtt: MQTTManager = Depends(get_mqtt_manager)
):
    logger.info(f"Removing device: {device_id}")
    
    if not config.get_device(device_id):
        logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    if mqtt.client:
        status_topic = f"{device_id}/status"
        mqtt.client.unsubscribe(status_topic)
        logger.info(f"Unsubscribed from {status_topic}")
    
    config.remove_device(device_id)
    
    return {"message": f"Device {device_id} removed successfully"}

@app.get("/config/reload", tags=["Configuration"])
async def reload_config(config: ConfigManager = Depends(get_config_manager)):
    logger.info("Reloading configuration from file")
    
    try:
        config.load_config()
        return {
            "message": "Configuration reloaded successfully"
            , "devices_count": len(config.devices_db)
        }
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        raise HTTPException(status_code=500, detail="Failed to reload configuration")

@app.post("/subscribe/{device_id}", tags=["MQTT"])
async def subscribe_to_device(
    device_id: str
    , config: ConfigManager = Depends(get_config_manager)
    , mqtt: MQTTManager = Depends(get_mqtt_manager)
):
    logger.info(f"Subscribing to MQTT topics for device: {device_id}")
    
    device = config.get_device(device_id)
    if not device:
        logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not mqtt.client:
        logger.error("MQTT client not connected")
        raise HTTPException(status_code=500, detail="MQTT client not connected")
    
    try:
        status_topic = f"{device_id}/status"
        mqtt.client.subscribe(status_topic)
        logger.info(f"Subscribed to {status_topic}")
        
        return {
            "message": f"Subscribed to MQTT topics for {device_id}"
            , "topics": [status_topic]
        }
        
    except Exception as e:
        logger.error(f"Failed to subscribe to MQTT topics: {e}")
        raise HTTPException(status_code=500, detail="Failed to subscribe to MQTT topics")

@app.post("/telegram/test_send", tags=["Telegram"])
async def test_telegram_send(
    message: str = "Test message from ESP32 Controller"
    , bot: TelegramBot = Depends(get_telegram_bot)
):
    if not bot.application:
        raise HTTPException(status_code=500, detail="Telegram bot not running")
    
    if not bot.allowed_users:
        raise HTTPException(status_code=400, detail="No allowed users configured")
    
    try:
        chat_id = bot.allowed_users[0]
        await bot.application.bot.send_message(chat_id=chat_id, text=f"🤖 {message}")
        return {"message": f"Test message sent to user {chat_id}"}
    except Exception as e:
        logger.error(f"Failed to send test message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

@app.get("/telegram/status", tags=["Telegram"])
async def telegram_status(bot: TelegramBot = Depends(get_telegram_bot)):
    is_running = bot.application is not None
    return {
        "telegram_bot_running": is_running
        , "bot_token_configured": bot.bot_token is not None
        , "allowed_users_count": len(bot.allowed_users)
    }

@app.post("/telegram/send_message", tags=["Telegram"])
async def send_telegram_message(
    chat_id     : int
    , message   : str
    , bot       : TelegramBot = Depends(get_telegram_bot)
):
    if not bot.application:
        raise HTTPException(status_code=500, detail="Telegram bot not running")
    
    try:
        await bot.application.bot.send_message(chat_id=chat_id, text=message)
        return {"message": "Message sent successfully"}
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        raise HTTPException(status_code=500, detail="Failed to send message")

if __name__ == "__main__":
    uvicorn.run(
        "main:app"
        , reload    = settings.APP_RELOAD
        , host      = settings.APP_HOST
        , port      = settings.APP_PORT
    )