from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class DeviceStatus(str, Enum):
    connected       = "connected"
    disconnected    = "disconnected"

class RelayState(str, Enum):
    on              = "on"
    off             = "off"

class Device(BaseModel):
    device          : str = Field(..., description="Device identifier")
    status          : DeviceStatus = Field(..., description="Connection status")
    relay_state     : RelayState = Field(..., description="Relay state")
    mqtt_topic      : str = Field(..., description="MQTT topic for device")
    last_seen       : Optional[datetime] = Field(default=None, description="Last heartbeat timestamp")
    last_heartbeat  : Optional[datetime] = Field(default=None, description="Last status message timestamp")

class DeviceControl(BaseModel):
    device      : str = Field(..., description="Device identifier") 
    relay_state : RelayState = Field(..., description="Desired relay state")

class DevicesResponse(BaseModel):
    devices     : List[Device] 