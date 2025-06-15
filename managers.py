import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timedelta

from config import settings
from models import Device, DeviceStatus, RelayState
from logger import get_logger

logger = get_logger('config')

class ConfigManager:
    def __init__(self, config_file: str = None):
        self.config_file    = Path(config_file or settings.CONFIG_FILE_PATH)
        self.devices_db     : Dict[str, Device] = {}
        # Device status timeout configuration from settings
        self.heartbeat_timeout_seconds = settings.DEVICE_HEARTBEAT_TIMEOUT_SECONDS
        self.status_timeout_seconds = settings.DEVICE_STATUS_TIMEOUT_SECONDS
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
                    
                    if 'last_seen' not in device_data:
                        device_data['last_seen'] = None
                    if 'last_heartbeat' not in device_data:
                        device_data['last_heartbeat'] = None
                    
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
        default_devices = [
            {
                "device": "esp-cdc-hrm-1"
                , "status": "disconnected"
                , "relay_state": "off"
                , "mqtt_topic": "esp-cdc-hrm-1"
                , "last_seen": None
                , "last_heartbeat": None
            },
            {
                "device": "esp-cdc-hrm-2"
                , "status": "disconnected"
                , "relay_state": "off"
                , "mqtt_topic": "esp-cdc-hrm-2"
                , "last_seen": None
                , "last_heartbeat": None
            },
            {
                "device": "esp-cdc-hrm-3"
                , "status": "disconnected"
                , "relay_state": "off"
                , "mqtt_topic": "esp-cdc-hrm-3"
                , "last_seen": None
                , "last_heartbeat": None
            }
        ]

        default_config = {"devices": default_devices}

        with open(self.config_file, 'w') as f:
            json.dump(default_config, f, indent=4, default=str)

        for device_data in default_devices:
            device = Device(**device_data)
            self.devices_db[device.device] = device

    def save_config(self):
        try:
            devices_list = [device.model_dump() for device in self.devices_db.values()]
            config_data = {"devices": devices_list}

            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=4, default=str)

            logger.info(f"Configuration saved to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def get_device(self, device_id: str) -> Optional[Device]:
        return self.devices_db.get(device_id)
    
    def get_all_devices(self) -> Dict[str, Device]:
        return self.devices_db.copy()
    
    def update_device_status(self, device_id: str, status: DeviceStatus, update_heartbeat: bool = True):
        """Update device status with optional heartbeat timestamp update"""
        if device_id in self.devices_db:
            current_time = datetime.now()
            self.devices_db[device_id].status = status
            
            if update_heartbeat:
                self.devices_db[device_id].last_heartbeat = current_time
                
            # Always update last_seen when we receive any status update
            self.devices_db[device_id].last_seen = current_time
            
            self.save_config()
            logger.info(f"Updated {device_id} status to {status.value} at {current_time}")
    
    def update_device_relay(self, device_id: str, relay_state: RelayState):
        if device_id in self.devices_db:
            current_time = datetime.now()
            self.devices_db[device_id].relay_state = relay_state
            self.devices_db[device_id].last_seen = current_time
            self.save_config()
            logger.info(f"Updated {device_id} relay to {relay_state.value} at {current_time}")
    
    def check_device_timeouts(self) -> Dict[str, DeviceStatus]:

        current_time    = datetime.now()
        timeout_updates = {}
        
        for device_id, device in self.devices_db.items():
            if device.status == DeviceStatus.connected:
                
                if device.last_heartbeat:
                    time_since_heartbeat = current_time - device.last_heartbeat
                    if time_since_heartbeat.total_seconds() > self.heartbeat_timeout_seconds:
                        logger.warning(f"Device {device_id} heartbeat timeout: {time_since_heartbeat.total_seconds()}s > {self.heartbeat_timeout_seconds}s")
                        self.devices_db[device_id].status   = DeviceStatus.disconnected
                        timeout_updates[device_id]          = DeviceStatus.disconnected
                        continue
                
                if device.last_seen:
                    time_since_seen = current_time - device.last_seen
                    if time_since_seen.total_seconds() > self.status_timeout_seconds:
                        logger.warning(f"Device {device_id} status timeout: {time_since_seen.total_seconds()}s > {self.status_timeout_seconds}s")
                        self.devices_db[device_id].status = DeviceStatus.disconnected
                        timeout_updates[device_id] = DeviceStatus.disconnected
                        continue
                
                if not device.last_seen and not device.last_heartbeat:
                    logger.warning(f"Device {device_id} marked connected but has no timestamp data")
                    self.devices_db[device_id].status = DeviceStatus.disconnected
                    timeout_updates[device_id] = DeviceStatus.disconnected
        
        if timeout_updates:
            self.save_config()
            logger.info(f"Updated {len(timeout_updates)} devices due to timeout")
        
        return timeout_updates
    
    def get_device_connection_info(self, device_id: str) -> Dict[str, any]:

        device          = self.get_device(device_id)
        if not device:
            return {"error": "Device not found"}
        
        current_time    = datetime.now()
        info = {
            "device_id" : device_id,
            "status"    : device.status.value,
            "last_seen"     : device.last_seen,
            "last_heartbeat": device.last_heartbeat,
            "relay_state"   : device.relay_state.value
        }
        
        if device.last_seen:
            info["seconds_since_last_seen"]     = (current_time - device.last_seen).total_seconds()
        
        if device.last_heartbeat:
            info["seconds_since_heartbeat"]     = (current_time - device.last_heartbeat).total_seconds()
            info["heartbeat_timeout_threshold"] = self.heartbeat_timeout_seconds
            info["is_heartbeat_overdue"]        = (current_time - device.last_heartbeat).total_seconds() > self.heartbeat_timeout_seconds
        
        return info
    
    def add_device(self, device: Device):
        if not device.last_seen:
            device.last_seen = None
        if not device.last_heartbeat:
            device.last_heartbeat = None
            
        self.devices_db[device.device] = device
        self.save_config()
        logger.info(f"Added new device: {device.device}")
    
    def remove_device(self, device_id: str):
        if device_id in self.devices_db:
            del self.devices_db[device_id]
            self.save_config()
            logger.info(f"Removed device: {device_id}")
    
    def device_exists(self, device_id: str) -> bool:
        return device_id in self.devices_db
    
    def get_devices_count(self) -> int:
        return len(self.devices_db)
    
    def get_connected_devices_count(self) -> int:
        return sum(1 for device in self.devices_db.values() 
                  if device.status == DeviceStatus.connected)
    
    def get_devices_by_status(self, status: DeviceStatus) -> Dict[str, Device]:
        return {device_id: device for device_id, device in self.devices_db.items()
                if device.status == status}
    
    def get_stale_devices(self, threshold_seconds: int = None) -> Dict[str, Device]:
        """Get devices that haven't been seen within the threshold"""
        if threshold_seconds is None:
            threshold_seconds = self.heartbeat_timeout_seconds
            
        current_time    = datetime.now()
        stale_devices   = {}
        
        for device_id, device in self.devices_db.items():
            if device.last_seen:
                time_since_seen = current_time - device.last_seen
                if time_since_seen.total_seconds() > threshold_seconds:
                    stale_devices[device_id]    = device
            elif device.status == DeviceStatus.connected:
            
                stale_devices[device_id]        = device
        
        return stale_devices 