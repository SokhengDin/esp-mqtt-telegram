import uvicorn
from contextlib import asynccontextmanager

from fastapi import HTTPException, status, Depends, Request, Response, FastAPI
from fastapi.responses import Response, JSONResponse

from config import settings
from models import Device, DeviceControl, DevicesResponse, DeviceStatus, RelayState
from managers import ConfigManager
from mqtt_client import MQTTClient
from telegram_bot import TelegramBot
from logger import setup_logging, get_logger, log_startup_info, log_shutdown_info

# Setup centralized logging
setup_logging()
logger = get_logger('main')

config_manager  = ConfigManager()
mqtt_client     = MQTTClient(config_manager=config_manager)
telegram_bot    = TelegramBot(config_manager=config_manager, mqtt_client=mqtt_client)

def get_config_manager() -> ConfigManager:
    return config_manager

def get_mqtt_client() -> MQTTClient:
    return mqtt_client

def get_telegram_bot() -> TelegramBot:
    return telegram_bot

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_startup_info()

    try:
        await mqtt_client.connect()
        logger.info("MQTT client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize MQTT: {e}")
    
    try:
        await telegram_bot.start()
        logger.info("Telegram bot started successfully")
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")
    
    yield

    log_shutdown_info()
    await mqtt_client.disconnect()
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
    api_logger = get_logger('api')
    api_logger.info("Root endpoint accessed")
    return {"message": "ESP32 Device Controller API", "status": "running"}

@app.get("/devices", response_model=DevicesResponse, tags=["Devices"])
async def get_devices(config: ConfigManager = Depends(get_config_manager)):
    api_logger = get_logger('api')
    api_logger.info("Getting all devices")
    return DevicesResponse(devices=list(config.devices_db.values()))

@app.get("/devices/{device_id}", response_model=Device, tags=["Devices"])
async def get_device(
    device_id: str
    , config: ConfigManager = Depends(get_config_manager)
):
    api_logger = get_logger('api')
    api_logger.info(f"Getting device: {device_id}")
    
    device = config.get_device(device_id)
    if not device:
        api_logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    return device

@app.post("/devices/{device_id}/control", tags=["Control"])
async def control_device_relay(
    device_id: str
    , control: DeviceControl
    , config: ConfigManager = Depends(get_config_manager)
    , mqtt: MQTTClient = Depends(get_mqtt_client)
):
    api_logger = get_logger('api')
    api_logger.info(f"Controlling device {device_id} - setting relay to {control.relay_state}")
    
    device = config.get_device(device_id)
    if not device:
        api_logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    if device.status == DeviceStatus.disconnected:
        api_logger.warning(f"Device {device_id} is disconnected")
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
        api_logger.error(f"Failed to control device {device_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to send command to device")

@app.post("/devices", response_model=Device, tags=["Devices"])
async def add_device(
    device  : Device
    , config: ConfigManager = Depends(get_config_manager)
    , mqtt  : MQTTClient = Depends(get_mqtt_client)
):
    logger.info(f"Adding new device: {device.device}")
    
    if config.get_device(device.device):
        logger.warning(f"Device already exists: {device.device}")
        raise HTTPException(status_code=400, detail="Device already exists")
    
    config.add_device(device)
    
    if mqtt.is_connected:
        mqtt.subscribe_device(device.device)
    
    return device

@app.delete("/devices/{device_id}", tags=["Devices"])
async def remove_device(
    device_id   : str
    , config    : ConfigManager = Depends(get_config_manager)
    , mqtt      : MQTTClient = Depends(get_mqtt_client)
):
    logger.info(f"Removing device: {device_id}")
    
    if not config.get_device(device_id):
        logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    if mqtt.is_connected:
        mqtt.unsubscribe_device(device_id)
    
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
    device_id   : str
    , config    : ConfigManager = Depends(get_config_manager)
    , mqtt      : MQTTClient    = Depends(get_mqtt_client)
):
    logger.info(f"Subscribing to MQTT topics for device: {device_id}")
    
    device = config.get_device(device_id)
    if not device:
        logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    if not mqtt.is_connected:
        logger.error("MQTT client not connected")
        raise HTTPException(status_code=500, detail="MQTT client not connected")
    
    try:
        success = mqtt.subscribe_device(device_id)
        if success:
            return {
                "message"   : f"Subscribed to MQTT topics for {device_id}"
                , "topics"  : [f"{device_id}/status", f"{device_id}/relay/state"]
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to subscribe to some topics")
        
    except Exception as e:
        logger.error(f"Failed to subscribe to MQTT topics: {e}")
        raise HTTPException(status_code=500, detail="Failed to subscribe to MQTT topics")

@app.get("/mqtt/status", tags=["MQTT"])
async def get_mqtt_status(mqtt: MQTTClient = Depends(get_mqtt_client)):
    return mqtt.get_connection_status()

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