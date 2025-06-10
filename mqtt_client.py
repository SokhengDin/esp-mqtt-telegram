from typing import Dict

import paho.mqtt.client as mqtt

from config import settings
from models import DeviceStatus, RelayState
from logger import get_logger

logger = get_logger('mqtt')

class MQTTClient:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.client         = None
        self.broker_host    = settings.MQTT_BROKER_HOST
        self.broker_port    = settings.MQTT_BROKER_PORT
        self.username       = settings.MQTT_USERNAME
        self.password       = settings.MQTT_PASSWORD
        self.is_connected   = False

    async def connect(self):
        """Connect to MQTT broker"""
        try:
            self.client = mqtt.Client()

            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            # Set callback functions
            self.client.on_connect      = self._on_connect
            self.client.on_message      = self._on_message
            self.client.on_disconnect   = self._on_disconnect
            self.client.on_subscribe    = self._on_subscribe
            self.client.on_publish      = self._on_publish

            # Connect to broker
            self.client.connect(self.broker_host, self.broker_port, 60)
            self.client.loop_start()

            logger.info(f"MQTT: Connecting to {self.broker_host}:{self.broker_port}")

        except Exception as e:
            logger.error(f"MQTT: Failed to connect - {e}")
            raise

    async def disconnect(self):
        """Disconnect from MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.is_connected = False
            logger.info("MQTT: Disconnected")

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when client connects to broker"""
        if rc == 0:
            self.is_connected = True
            logger.info("MQTT: Connected successfully")
            
            # Subscribe to all device status topics
            self._subscribe_to_device_topics()
            
        else:
            self.is_connected = False
            logger.error(f"MQTT: Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback for when client disconnects from broker"""
        self.is_connected = False
        if rc != 0:
            logger.warning(f"MQTT: Unexpected disconnection (code: {rc})")
        else:
            logger.info("MQTT: Disconnected cleanly")

    def _on_subscribe(self, client, userdata, mid, granted_qos):
        """Callback for when subscription is confirmed"""
        logger.debug(f"MQTT: Subscription confirmed (mid: {mid}, qos: {granted_qos})")

    def _on_publish(self, client, userdata, mid):
        """Callback for when message is published"""
        logger.debug(f"MQTT: Message published (mid: {mid})")

    def _on_message(self, client, userdata, msg):
        """Callback for when message is received"""
        try:
            topic   = msg.topic
            payload = msg.payload.decode('utf-8')
            
            logger.info(f"MQTT: Received - Topic: {topic}, Payload: {payload}")
            
            # Handle different message types
            if "/status" in topic:
                self._handle_status_message(topic, payload)
            elif "/relay/state" in topic:
                self._handle_relay_state_message(topic, payload)
            else:
                logger.debug(f"MQTT: Unhandled topic: {topic}")

        except Exception as e:
            logger.error(f"MQTT: Error processing message - {e}")

    def _handle_status_message(self, topic: str, payload: str):
        """Handle device status messages"""
        device_id = topic.replace("/status", "")
        
        if device_id in self.config_manager.devices_db:
            # Determine device status from payload
            if payload.lower() in ["online", "connected", "1", "true"]:
                new_status = DeviceStatus.connected
            else:
                new_status = DeviceStatus.disconnected
            
            # Update device status
            current_status = self.config_manager.devices_db[device_id].status
            if current_status != new_status:
                self.config_manager.update_device_status(device_id, new_status)
                logger.info(f"MQTT: Device {device_id} status changed: {current_status.value} → {new_status.value}")
        else:
            logger.warning(f"MQTT: Received status for unknown device: {device_id}")

    def _handle_relay_state_message(self, topic: str, payload: str):
        """Handle relay state feedback messages"""
        device_id = topic.replace("/relay/state", "")
        
        if device_id in self.config_manager.devices_db:
            
            if payload.lower() in ["on", "1", "true", "high"]:
                new_state = RelayState.on
            else:
                new_state = RelayState.off
            
            current_state = self.config_manager.devices_db[device_id].relay_state
            if current_state != new_state:
                self.config_manager.update_device_relay(device_id, new_state)
                logger.info(f"MQTT: Device {device_id} relay state changed: {current_state.value} → {new_state.value}")
        else:
            logger.warning(f"MQTT: Received relay state for unknown device: {device_id}")

    def _subscribe_to_device_topics(self):
        """Subscribe to all device-related topics"""
        if not self.is_connected:
            logger.warning("MQTT: Cannot subscribe - not connected")
            return

        for device_id in self.config_manager.devices_db.keys():
            topics = [
                f"{device_id}/status",
                f"{device_id}/relay/state"
            ]
            
            for topic in topics:
                result, mid = self.client.subscribe(topic)
                if result == mqtt.MQTT_ERR_SUCCESS:
                    logger.info(f"MQTT: Subscribed to {topic}")
                else:
                    logger.error(f"MQTT: Failed to subscribe to {topic}")

    def subscribe_device(self, device_id: str):
        """Subscribe to topics for a specific device"""
        if not self.is_connected:
            logger.warning("MQTT: Cannot subscribe - not connected")
            return False

        topics = [
            f"{device_id}/status",
            f"{device_id}/relay/state"
        ]
        
        success = True
        for topic in topics:
            result, mid = self.client.subscribe(topic)
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"MQTT: Subscribed to {topic}")
            else:
                logger.error(f"MQTT: Failed to subscribe to {topic}")
                success = False
        
        return success

    def unsubscribe_device(self, device_id: str):
        """Unsubscribe from topics for a specific device"""
        if not self.is_connected:
            logger.warning("MQTT: Cannot unsubscribe - not connected")
            return False

        topics = [
            f"{device_id}/status",
            f"{device_id}/relay/state"
        ]
        
        success = True
        for topic in topics:
            result, mid = self.client.unsubscribe(topic)
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"MQTT: Unsubscribed from {topic}")
            else:
                logger.error(f"MQTT: Failed to unsubscribe from {topic}")
                success = False
        
        return success

    def publish_relay_control(self, device_id: str, state: RelayState):
        """Publish relay control command"""
        if not self.is_connected:
            raise Exception("MQTT client not connected")
        
        topic   = f"{device_id}/relay/set"
        payload = state.value
        
        # Publish with QoS 1 (at least once delivery)
        result  = self.client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"MQTT: Published relay command - Topic: {topic}, Payload: {payload}")
            # Update local state immediately for responsive UI
            self.config_manager.update_device_relay(device_id, state)
            return True
        else:
            logger.error(f"MQTT: Failed to publish to {topic} (error: {result.rc})")
            raise Exception(f"Failed to publish MQTT message (error: {result.rc})")

    def publish_custom_message(self, topic: str, payload: str, qos: int = 0):
        """Publish a custom message to any topic"""
        if not self.is_connected:
            raise Exception("MQTT client not connected")
        
        result = self.client.publish(topic, payload, qos=qos)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"MQTT: Published custom message - Topic: {topic}, Payload: {payload}")
            return True
        else:
            logger.error(f"MQTT: Failed to publish custom message to {topic}")
            raise Exception(f"Failed to publish MQTT message (error: {result.rc})")

    def get_connection_status(self) -> Dict[str, any]:
        """Get current MQTT connection status"""
        return {
            "connected": self.is_connected,
            "broker_host": self.broker_host,
            "broker_port": self.broker_port,
            "client_id": self.client._client_id.decode() if self.client and self.client._client_id else None,
            "subscribed_topics": len(self.config_manager.devices_db) * 2 if self.is_connected else 0
        } 