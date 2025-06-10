"""
Configuration module for ESP32 Device Controller
Handles environment variables with proper formatting using python-decouple
"""

from decouple import config
from typing import List, Optional


class Settings:
    """Application settings loaded from environment variables"""
    
    # MQTT Configuration with proper alignment
    MQTT_BROKER_HOST        : str = config("MQTT_BROKER_HOST", default="localhost")
    MQTT_BROKER_PORT        : int = config("MQTT_BROKER_PORT", default=1883, cast=int)
    MQTT_USERNAME           : Optional[str] = config("MQTT_USERNAME", default=None)
    MQTT_PASSWORD           : Optional[str] = config("MQTT_PASSWORD", default=None)
    
    # Connection Pool Settings
    MQTT_POOL_SIZE          : int = config("MQTT_POOL_SIZE", default=10, cast=int)
    MQTT_MAX_OVERFLOW       : int = config("MQTT_MAX_OVERFLOW", default=5, cast=int)
    MQTT_POOL_TIMEOUT       : int = config("MQTT_POOL_TIMEOUT", default=10, cast=int)
    MQTT_POOL_RECYCLE       : int = config("MQTT_POOL_RECYCLE", default=1800, cast=int)
    
    # Telegram Bot Configuration
    TELEGRAM_BOT_TOKEN      : Optional[str] = config("TELEGRAM_BOT_TOKEN", default=None)
    TELEGRAM_ALLOWED_USERS  : str = config("TELEGRAM_ALLOWED_USERS", default="")
    
    # Application Settings
    APP_HOST                : str = config("APP_HOST", default="0.0.0.0")
    APP_PORT                : int = config("APP_PORT", default=8000, cast=int)
    APP_RELOAD              : bool = config("APP_RELOAD", default=True, cast=bool)
    
    # Logging Configuration
    LOG_LEVEL               : str = config("LOG_LEVEL", default="INFO")
    LOG_FORMAT              : str = config(
        "LOG_FORMAT"
        , default="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Device Configuration
    CONFIG_FILE_PATH        : str = config("CONFIG_FILE_PATH", default="esp_config.json")
    
    @classmethod
    def get_telegram_allowed_users(cls) -> List[int]:
        """
        Parse comma-separated user IDs from environment variable
        Maintains proper formatting and error handling
        """
        users_str = cls.TELEGRAM_ALLOWED_USERS
        if users_str:
            try:
                return [
                    int(user_id.strip()) 
                    for user_id in users_str.split(",")
                    if user_id.strip()
                ]
            except ValueError as e:
                raise ValueError(f"Invalid TELEGRAM_ALLOWED_USERS format: {e}")
        return []
    
    @classmethod
    def validate_required_settings(cls) -> bool:
        """
        Validate that required environment variables are set
        Returns True if all required settings are valid
        """
        required_settings = []
        
        # Add validation for critical settings
        if not cls.MQTT_BROKER_HOST:
            required_settings.append("MQTT_BROKER_HOST")
        
        if cls.TELEGRAM_BOT_TOKEN and not cls.get_telegram_allowed_users():
            required_settings.append("TELEGRAM_ALLOWED_USERS (when bot token is set)")
        
        if required_settings:
            raise ValueError(
                f"Missing required environment variables: {', '.join(required_settings)}"
            )
        
        return True


# Global settings instance
settings = Settings() 