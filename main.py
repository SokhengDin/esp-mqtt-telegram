import uvicorn
import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException, status, Depends, Request, Response, FastAPI
from fastapi.responses import Response, JSONResponse

from config import settings
from models import Device, DeviceControl, DevicesResponse, DeviceStatus, RelayState
from managers import ConfigManager
from mqtt_client import MQTTClient
from telegram_bot import TelegramBot
from logger import setup_logging, get_logger, log_startup_info, log_shutdown_info

setup_logging()
logger = get_logger('main')

config_manager  = ConfigManager()
mqtt_client     = MQTTClient(config_manager=config_manager)
telegram_bot    = TelegramBot(config_manager=config_manager, mqtt_client=mqtt_client)

# Background task control
background_task_running = False

def get_config_manager() -> ConfigManager:
    return config_manager

def get_mqtt_client() -> MQTTClient:
    return mqtt_client

def get_telegram_bot() -> TelegramBot:
    return telegram_bot

async def device_timeout_monitor():
    """Background task to monitor device timeouts and update status"""
    global background_task_running
    monitor_logger              = get_logger('device_monitor')
    monitor_logger.info("Device timeout monitor started")
    
    while background_task_running:
        try:
            timeout_updates     = config_manager.check_device_timeouts()
            
            if timeout_updates:
                monitor_logger.info(f"Timeout monitor: Updated {len(timeout_updates)} devices")
                for device_id, new_status in timeout_updates.items():
                    monitor_logger.warning(f"Device {device_id} marked as {new_status.value} due to timeout")
                
                    if telegram_bot.application and telegram_bot.allowed_users:
                        try:
                            message = f"⚠️ Device {device_id} has been marked as {new_status.value} due to timeout"
                            for chat_id in telegram_bot.allowed_users:
                                await telegram_bot.application.bot.send_message(chat_id=chat_id, text=message)
                        except Exception as e:
                            monitor_logger.error(f"Failed to send timeout notification: {e}")
            
            await asyncio.sleep(settings.DEVICE_MONITOR_INTERVAL_SECONDS)
            
        except Exception as e:
            monitor_logger.error(f"Error in device timeout monitor: {e}")
            await asyncio.sleep(60) 

@asynccontextmanager
async def lifespan(app: FastAPI):
    global background_task_running
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
    
    background_task_running = True
    monitor_task            = asyncio.create_task(device_timeout_monitor())
    logger.info("Device timeout monitor started")
    
    yield

    log_shutdown_info()
    background_task_running = False
    
    if not monitor_task.done():
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            logger.info("Device timeout monitor stopped")
    
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
    device_id   : str
    , config    : ConfigManager = Depends(get_config_manager)
):
    api_logger = get_logger('api')
    api_logger.info(f"Getting device: {device_id}")
    
    device = config.get_device(device_id)
    if not device:
        api_logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    return device

@app.get("/devices/{device_id}/connection", tags=["Devices", "Diagnostics"])
async def get_device_connection_info(
    device_id: str
    , config: ConfigManager = Depends(get_config_manager)
):
    """Get detailed connection information for a device including timestamps and timeout status"""
    api_logger      = get_logger('api')
    api_logger.info(f"Getting connection info for device: {device_id}")
    
    connection_info = config.get_device_connection_info(device_id)
    if "error" in connection_info:
        api_logger.warning(f"Device not found: {device_id}")
        raise HTTPException(status_code=404, detail="Device not found")
    
    return connection_info

@app.get("/devices/status/{status}", tags=["Devices"])
async def get_devices_by_status(
    status: DeviceStatus
    , config: ConfigManager = Depends(get_config_manager)
):
    """Get all devices with a specific status"""
    api_logger = get_logger('api')
    api_logger.info(f"Getting devices with status: {status.value}")
    
    devices = config.get_devices_by_status(status)
    return {
        "status": status.value,
        "count": len(devices),
        "devices": list(devices.values())
    }

@app.get("/devices/diagnostics/stale", tags=["Devices", "Diagnostics"])
async def get_stale_devices(
    threshold_seconds: int = None
    , config: ConfigManager = Depends(get_config_manager)
):
    """Get devices that haven't been seen within the threshold (default: heartbeat timeout)"""
    api_logger = get_logger('api')
    api_logger.info(f"Getting stale devices with threshold: {threshold_seconds}")
    
    stale_devices = config.get_stale_devices(threshold_seconds)
    return {
        "threshold_seconds": threshold_seconds or config.heartbeat_timeout_seconds,
        "stale_count": len(stale_devices),
        "devices": list(stale_devices.values())
    }

@app.post("/devices/diagnostics/check-timeouts", tags=["Devices", "Diagnostics"])
async def manual_timeout_check(config: ConfigManager = Depends(get_config_manager)):
    """Manually trigger a device timeout check"""
    api_logger = get_logger('api')
    api_logger.info("Manual timeout check requested")
    
    timeout_updates = config.check_device_timeouts()
    return {
        "message": "Timeout check completed",
        "updated_devices": len(timeout_updates),
        "updates": timeout_updates
    }

@app.post("/devices/{device_id}/control", tags=["Control"])
async def control_device_relay(
    device_id   : str
    , control   : DeviceControl
    , config    : ConfigManager = Depends(get_config_manager)
    , mqtt      : MQTTClient    = Depends(get_mqtt_client)
):
    api_logger  = get_logger('api')
    api_logger.info(f"Controlling device {device_id} - setting relay to {control.relay_state}")
    
    device      = config.get_device(device_id)
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