import json
from pathlib import Path
from typing import Dict, Optional

from config import settings
from models import Device, DeviceStatus, RelayState
from logger import get_logger

logger = get_logger('config')

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
        default_devices = [
            {
                "device": "esp-cdc-hrm-1"
                , "status": "disconnected"
                , "relay_state": "off"
                , "mqtt_topic": "esp-cdc-hrm-1"
            },
            {
                "device": "esp-cdc-hrm-2"
                , "status": "disconnected"
                , "relay_state": "off"
                , "mqtt_topic": "esp-cdc-hrm-2"
            },
            {
                "device": "esp-cdc-hrm-3"
                , "status": "disconnected"
                , "relay_state": "off"
                , "mqtt_topic": "esp-cdc-hrm-3"
            }
        ]

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
    
    def get_all_devices(self) -> Dict[str, Device]:
        return self.devices_db.copy()
    
    def update_device_status(self, device_id: str, status: DeviceStatus):
        if device_id in self.devices_db:
            self.devices_db[device_id].status = status
            self.save_config()
            logger.info(f"Updated {device_id} status to {status.value}")
    
    def update_device_relay(self, device_id: str, relay_state: RelayState):
        if device_id in self.devices_db:
            self.devices_db[device_id].relay_state = relay_state
            self.save_config()
            logger.info(f"Updated {device_id} relay to {relay_state.value}")
    
    def add_device(self, device: Device):
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