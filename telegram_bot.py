import datetime
import zoneinfo
from typing import List

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

from config import settings
from models import DeviceStatus, RelayState
from managers import ConfigManager
from mqtt_client import MQTTClient
from logger import get_logger

logger  = get_logger('telegram')

class TelegramBot:
    def __init__(self, config_manager: ConfigManager, mqtt_client: MQTTClient):
        self.config_manager = config_manager
        self.mqtt_client    = mqtt_client
        self.bot_token      = settings.TELEGRAM_BOT_TOKEN
        self.allowed_users  = settings.get_telegram_allowed_users()
        self.application    = None
        
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not found in environment variables")
    
    def _get_device_display_name(self, device_id: str) -> str:
    
        devices     = list(self.config_manager.devices_db.keys())
        if device_id in devices:
            index   = devices.index(device_id) + 1
            return f"Device {index}"
        return f"Device {device_id}"
    
    def _get_actual_power_state(self, relay_state: RelayState) -> str:
        return "ON" if relay_state == RelayState.off else "OFF"
    
    def _get_power_emoji(self, relay_state: RelayState) -> str:
        return "🔌" if relay_state == RelayState.off else "⚫"
    
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
            
            self.application.add_handler(CallbackQueryHandler(self.button_callback))
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            bot_info = await self.application.bot.get_me()
            logger.info(f"TELEGRAM: Bot started - @{bot_info.username} ({bot_info.id})")
            logger.info(f"TELEGRAM: Allowed users: {self.allowed_users}")
            logger.info("TELEGRAM: Polling started - bot is now listening for messages")
            logger.info("Telegram bot started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            raise
    
    async def stop(self):
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot stopped")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

Welcome! I can help you control your ESP32 devices with an interactive interface.

Available commands:
• `/get_devices` - List all devices
• `/status <device_id>` - Check device power status
• `/control <device_id>` - Open interactive power control panel
• `/help` - Show detailed help

Example:
`/status esp-device-1`
`/control esp-device-1`

The control command opens an interactive panel with buttons for easy power control!
        """
        
        await update.effective_message.reply_text(welcome_message, parse_mode="Markdown")
        logger.info(f"TELEGRAM: Sent welcome message to {username} ({user_id})")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
   Shows connection status and power state
   Example: `/status esp-device-1`

🎛️ `/control <device_id>`
   Opens interactive control panel with buttons
   Example: `/control esp-device-1`
   
   *Interactive Features:*
   • Real-time device status display
   • ON/OFF buttons for power control
   • Refresh button to update status
   • Close button to exit control panel

❓ `/help`
   Shows this help message
        """
        
        await update.effective_message.reply_text(help_message, parse_mode="Markdown")
    
    async def get_devices_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                status_emoji        = "🟢" if device.status == DeviceStatus.connected else "🔴"
                power_emoji         = self._get_power_emoji(device.relay_state)
                actual_power_state  = self._get_actual_power_state(device.relay_state)
                device_display_name = self._get_device_display_name(device.device)
                
                message += f"{status_emoji} *{device_display_name}*\n"
                message += f"   Status: {device.status.value}\n"
                message += f"   Power: {power_emoji} {actual_power_state}\n"
                message += f"   ID: `{device.device}`\n\n"
            
            await update.effective_message.reply_text(message, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error in get_devices_command: {e}")
            try:
                await update.effective_message.reply_text("❌ Error retrieving device list.")
            except Exception as reply_error:
                logger.error(f"Failed to send error message: {reply_error}")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_message:
            logger.error("No effective message in update")
            return
            
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        if not self._is_authorized(user_id):
            await update.effective_message.reply_text("❌ Unauthorized access.")
            return
        
        if not context.args:
            await update.effective_message.reply_text("❌ Usage: `/status <device_id>`\nExample: `/status esp-device-1`", parse_mode="Markdown")
            return
        
        device_id = context.args[0]
        logger.info(f"User {username} ({user_id}) requested status for {device_id}")
        
        try:
            device = self.config_manager.get_device(device_id)
            
            if not device:
                await update.effective_message.reply_text(f"❌ Device `{device_id}` not found.")
                return
            
            status_emoji        = "🟢" if device.status == DeviceStatus.connected else "🔴"
            power_emoji         = self._get_power_emoji(device.relay_state)
            actual_power_state  = self._get_actual_power_state(device.relay_state)
            device_display_name = self._get_device_display_name(device.device)
            
            message = f"""
📊 *Device Status: {device_display_name}*

{status_emoji} **Connection:** {device.status.value}
{power_emoji} **Power State:** {actual_power_state}
🏷️ **Device ID:** `{device.device}`
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
        
        if not context.args:
            await update.effective_message.reply_text(
                "❌ Usage: `/control <device_id>`\n"
                "Example: `/control esp-device-1`",
                parse_mode="Markdown"
            )
            return
        
        device_id = context.args[0]
        
        logger.info(f"User {username} ({user_id}) opening control panel for {device_id}")
        
        try:
            device = self.config_manager.get_device(device_id)
            
            if not device:
                await update.effective_message.reply_text(f"❌ Device `{device_id}` not found.")
                return
            
            # Show interactive control panel
            await self._show_control_panel(update.effective_message, device_id)
            
        except Exception as e:
            logger.error(f"Error in control_command: {e}")
            try:
                await update.effective_message.reply_text(f"❌ Failed to open control panel: {str(e)}")
            except Exception as reply_error:
                logger.error(f"Failed to send error message: {reply_error}")
    
    async def _show_control_panel(self, message, device_id: str):
        """Show interactive control panel for a device"""
        try:
            device = self.config_manager.get_device(device_id)
            
            if not device:
                await message.reply_text(f"❌ Device `{device_id}` not found.")
                return
            
            status_emoji        = "🟢" if device.status == DeviceStatus.connected else "🔴"
            power_emoji         = self._get_power_emoji(device.relay_state)
            actual_power_state  = self._get_actual_power_state(device.relay_state)
            mqtt_emoji          = "📡" if device.status == DeviceStatus.connected else "📵"
            device_display_name = self._get_device_display_name(device.device)
            
            status_message = f"""
🎛️ *Device Control Panel*

📱 **Device:** {device_display_name}
{mqtt_emoji} **MQTT Status:** {device.status.value}
{power_emoji} **Power State:** {actual_power_state}

Use the buttons below to control the power:
            """
            
            keyboard = []
            
            if device.status == DeviceStatus.connected:

                keyboard.append([
                    InlineKeyboardButton("🔌 Turn ON", callback_data=f"power_on_{device_id}"),
                    InlineKeyboardButton("⚫ Turn OFF", callback_data=f"power_off_{device_id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("❌ Device Disconnected", callback_data="device_disconnected")
                ])
            
            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{device_id}"),
                InlineKeyboardButton("❌ Close", callback_data=f"close_{device_id}")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await message.reply_text(
                status_message,
                parse_mode      ="Markdown",
                reply_markup    =reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error showing control panel: {e}")
            await message.reply_text(f"❌ Error showing control panel: {str(e)}")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks from inline keyboards"""
        query = update.callback_query
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"
        
        if not self._is_authorized(user_id):
            await query.answer("❌ Unauthorized access.", show_alert=True)
            return
        
        await query.answer()  
        
        try:
            callback_data   = query.data
            logger.info(f"User {username} ({user_id}) pressed button: {callback_data}")
            
            if callback_data == "device_disconnected":
                await query.answer("❌ Device is disconnected. Cannot control power.", show_alert=True)
                return
            
            if callback_data.startswith("power_on_"):
                device_id   = callback_data.replace("power_on_", "")
                
                await self._handle_power_control(query, device_id, "ON", RelayState.off)
                
            elif callback_data.startswith("power_off_"):
                device_id   = callback_data.replace("power_off_", "")
                
                await self._handle_power_control(query, device_id, "OFF", RelayState.on)
                
            elif callback_data.startswith("refresh_"):
                device_id   = callback_data.replace("refresh_", "")
                await self._handle_refresh(query, device_id)
                
            elif callback_data.startswith("close_"):
                device_id   = callback_data.replace("close_", "")
                await self._handle_close(query, device_id)
                
        except Exception as e:
            logger.error(f"Error in button_callback: {e}")
            await query.edit_message_text(f"❌ Error processing button press: {str(e)}")
    
    async def _handle_power_control(self, query, device_id: str, power_action: str, relay_state: RelayState):
        try:
            device = self.config_manager.get_device(device_id)
            
            if not device:
                await query.edit_message_text(f"❌ Device `{device_id}` not found.")
                return
            
            if device.status == DeviceStatus.disconnected:
                await query.answer("❌ Device is disconnected. Cannot control power.", show_alert=True)
                return
            
            # Send MQTT command and update local state immediately
            self.mqtt_client.publish_relay_control(device_id, relay_state)
            
            action_emoji = "🔌" if power_action == "ON" else "⚫"
            await self._update_control_panel(
                query, 
                device_id, 
                f"✅ {action_emoji} Power command sent: {power_action}"
            )
            
        except Exception as e:
            logger.error(f"Error controlling power: {e}")
            try:
                await query.edit_message_text(f"❌ Failed to control power: {str(e)}")
            except Exception as edit_error:
                logger.error(f"Failed to edit message with error: {edit_error}")
                await query.answer(f"❌ Failed to control power: {str(e)}", show_alert=True)
    
    async def _handle_refresh(self, query, device_id: str):
        try:
            
            cambodia_tz = zoneinfo.ZoneInfo("Asia/Phnom_Penh")
            timestamp   = datetime.datetime.now(cambodia_tz).strftime("%H:%M:%S")
            await self._update_control_panel(query, device_id, f"🔄 Status refreshed at {timestamp}")
        except Exception as e:
            logger.error(f"Error refreshing status: {e}")
            try:
                await query.edit_message_text(f"❌ Error refreshing status: {str(e)}")
            except Exception as edit_error:
                logger.error(f"Failed to edit message with error: {edit_error}")
                await query.answer(f"❌ Error refreshing: {str(e)}", show_alert=True)
    
    async def _handle_close(self, query, device_id: str):
        try:
            device_display_name = self._get_device_display_name(device_id)
            await query.edit_message_text(
                f"🎛️ Control panel for {device_display_name} closed.\n"
                f"Use `/control {device_id}` to open it again.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error closing control panel: {e}")
            await query.edit_message_text(f"❌ Error closing control panel: {str(e)}")
    
    async def _update_control_panel(self, query, device_id: str, action_message: str = None):
        try:
            device = self.config_manager.get_device(device_id)
            
            if not device:
                await query.edit_message_text(f"❌ Device `{device_id}` not found.")
                return
            
            status_emoji        = "🟢" if device.status == DeviceStatus.connected else "🔴"
            power_emoji         = self._get_power_emoji(device.relay_state)
            actual_power_state  = self._get_actual_power_state(device.relay_state)
            mqtt_emoji          = "📡" if device.status == DeviceStatus.connected else "📵"
            device_display_name = self._get_device_display_name(device.device)
            
            status_message = f"""
🎛️ *Device Control Panel*

📱 **Device:** {device_display_name}
{mqtt_emoji} **MQTT Status:** {device.status.value}
{power_emoji} **Power State:** {actual_power_state}
"""
            
            if action_message:
                status_message += f"\n{action_message}\n"
            
            status_message += "\nUse the buttons below to control the power:"
            
            keyboard        = []
            
            if device.status == DeviceStatus.connected:
                
                keyboard.append([
                    InlineKeyboardButton("🔌 Turn ON", callback_data=f"power_on_{device_id}"),
                    InlineKeyboardButton("⚫ Turn OFF", callback_data=f"power_off_{device_id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("❌ Device Disconnected", callback_data="device_disconnected")
                ])
            
            keyboard.append([
                InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{device_id}"),
                InlineKeyboardButton("❌ Close", callback_data=f"close_{device_id}")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                status_message,
                parse_mode      = "Markdown",
                reply_markup    = reply_markup
            )
            
        except Exception as e:
            error_msg = str(e)
            if "Message is not modified" in error_msg:
                logger.info(f"Control panel content unchanged for {device_id}, skipping update")
                
                await query.answer("Status unchanged", show_alert=False)
            else:
                logger.error(f"Error updating control panel: {e}")
                try:
                    await query.edit_message_text(f"❌ Error updating control panel: {str(e)}")
                except Exception as edit_error:
                    logger.error(f"Failed to edit message with error: {edit_error}")
                    await query.answer(f"❌ Error: {str(e)}", show_alert=True) 