import logging
import logging.handlers
import sys
from pathlib import Path
from datetime import datetime

from config import settings

class CustomFormatter(logging.Formatter):
    COLORS = {
        'DEBUG'     : '\033[36m',
        'INFO'      : '\033[32m',
        'WARNING'   : '\033[33m',
        'ERROR'     : '\033[31m',
        'CRITICAL'  : '\033[35m',
    }
    RESET = '\033[0m'
    
    def format(self, record):
        if hasattr(record, 'color') and record.color:
            log_color           = self.COLORS.get(record.levelname, '')
            record.levelname    = f"{log_color}{record.levelname}{self.RESET}"
            record.name         = f"{log_color}{record.name}{self.RESET}"
        
        return super().format(record)

def setup_logging():
    log_dir     = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    log_level   = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    logger      = logging.getLogger()
    logger.setLevel(log_level)
    
    logger.handlers.clear()
    
    console_handler     = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter   = CustomFormatter(
        fmt     = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt = '%Y-%m-%d %H:%M:%S'
    )
    
    class ColoredStreamHandler(logging.StreamHandler):
        def emit(self, record):
            record.color = True
            super().emit(record)
    
    console_handler = ColoredStreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    file_handler = logging.handlers.RotatingFileHandler(
        filename    = log_dir / "app.log",
        maxBytes    = 10 * 1024 * 1024,
        backupCount = 5,
        encoding    = 'utf-8'
    )
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(
        fmt     = '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt = '%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('paho').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    
    loggers = {
        'main'      : logging.getLogger('esp.main'),
        'config'    : logging.getLogger('esp.config'),
        'mqtt'      : logging.getLogger('esp.mqtt'),
        'telegram'  : logging.getLogger('esp.telegram'),
        'api'       : logging.getLogger('esp.api'),
    }
    
    return loggers

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f'esp.{name}')

def log_startup_info():
    logger = get_logger('main')
    
    logger.info("=" * 60)
    logger.info("ESP32 Device Controller Starting Up")
    logger.info("=" * 60)
    logger.info(f"Log Level: {settings.LOG_LEVEL}")
    logger.info(f"App Host: {settings.APP_HOST}:{settings.APP_PORT}")
    logger.info(f"MQTT Broker: {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}")
    logger.info(f"Config File: {settings.CONFIG_FILE_PATH}")
    logger.info(f"Reload Mode: {settings.APP_RELOAD}")
    logger.info("=" * 60)

def log_shutdown_info():
    logger = get_logger('main')
    
    logger.info("=" * 60)
    logger.info("ESP32 Device Controller Shutting Down")
    logger.info(f"Shutdown Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60) 