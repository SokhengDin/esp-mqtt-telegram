#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "nvs_flash.h"
#include "driver/gpio.h"

#include "includes/wifi_manager.h"
#include "includes/mqtt_manager.h"
#include "includes/relay_control.h"
#include "includes/rgb_led_manager.h"
#include "esp_pm.h"

static const char *TAG = "main";

// RGB LED status indication 
static void update_rgb_status_led(rgb_status_t status)
{
    esp_err_t ret = rgb_led_set_status(status);
    if (ret != ESP_OK) {
        ESP_LOGW(TAG, "Failed to set RGB LED status: %s", esp_err_to_name(ret));
    }
}

// WiFi event callback
static void wifi_event_callback(wifi_state_t state)
{
    switch (state) {
        case WIFI_STATE_DISCONNECTED:
            ESP_LOGI(TAG, "WiFi: Disconnected");
            update_rgb_status_led(RGB_STATUS_DISCONNECTED);
            mqtt_client_stop();
            break;
            
        case WIFI_STATE_CONNECTING:
            ESP_LOGI(TAG, "WiFi: Connecting...");
            update_rgb_status_led(RGB_STATUS_CONNECTING);
            break;
            
        case WIFI_STATE_CONNECTED:
            ESP_LOGI(TAG, "WiFi: Connected");
            update_rgb_status_led(RGB_STATUS_WIFI_CONNECTED);
            // Start MQTT client when WiFi is connected
            mqtt_client_start();
            break;
            
        case WIFI_STATE_FAILED:
            ESP_LOGI(TAG, "WiFi: Failed to connect");
            update_rgb_status_led(RGB_STATUS_ERROR);
            break;
    }
}

void update_system_status_led(void)
{
    if (mqtt_client_get_state() == MQTT_STATE_CONNECTED) {

        relay_state_t relay_state = relay_control_get_state();
        bool relay_on = (relay_state == RELAY_STATE_ON);
        
        esp_err_t ret = rgb_led_set_mqtt_relay_status(true, relay_on);
        if (ret != ESP_OK) {
            ESP_LOGW(TAG, "Failed to set MQTT relay status LED: %s", esp_err_to_name(ret));
        }
        
        const char *color_str = relay_on ? "green (relay on)" : "yellow (relay off)";
        ESP_LOGI(TAG, "RGB LED status: %s", color_str);
    } else if (wifi_manager_is_connected()) {
        update_rgb_status_led(RGB_STATUS_WIFI_CONNECTED);
    } else {
        update_rgb_status_led(RGB_STATUS_DISCONNECTED);
    }
}

// Function to update RGB LED based on MQTT state
void status_led_set_mqtt_state(mqtt_state_t state)
{
    switch (state) {
        case MQTT_STATE_DISCONNECTED:
            ESP_LOGI(TAG, "MQTT: Disconnected");
            if (wifi_manager_is_connected()) {
                update_rgb_status_led(RGB_STATUS_WIFI_CONNECTED);
            }
            break;
            
        case MQTT_STATE_CONNECTING:
            ESP_LOGI(TAG, "MQTT: Connecting...");
            update_rgb_status_led(RGB_STATUS_WIFI_CONNECTED);
            break;
            
        case MQTT_STATE_CONNECTED:
            ESP_LOGI(TAG, "MQTT: Connected - RGB LED will show relay state (green=on, yellow=off)!");
            update_system_status_led();
            break;
            
        case MQTT_STATE_ERROR:
            ESP_LOGI(TAG, "MQTT: Connection error");
            update_rgb_status_led(RGB_STATUS_ERROR);
            break;
    }
}

static void heartbeat_task(void *pvParameters)
{
    ESP_LOGI(TAG, "Heartbeat task started");
    
    while (1) {
        if (mqtt_client_get_state() == MQTT_STATE_CONNECTED) {
            // Send heartbeat status
            mqtt_publish_status();
            
            // Send current relay state
            relay_state_t current_state = relay_control_get_state();
            mqtt_publish_relay_state(current_state);
            
            update_system_status_led();
            
            const char *state_str       = (current_state == RELAY_STATE_ON) ? "on" : "off";
            ESP_LOGI(TAG, "Heartbeat sent - Status: online, Relay: %s", state_str);
        }
        
        // Check heap integrity every heartbeat
        if (!heap_caps_check_integrity_all(true)) {
            ESP_LOGE(TAG, "Heap corruption detected!");
        }
        
        // Send heartbeat every 30 seconds
        vTaskDelay(pdMS_TO_TICKS(30000));
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "ESP32 Device Controller starting...");
    ESP_LOGI(TAG, "Device ID: %s", CONFIG_DEVICE_ID);


    int max_gpio            = 39;  // Default for ESP32
    const char* chip_name   = "ESP32";
    
#ifdef CONFIG_ESP32_CHIP_ESP32C3
    max_gpio = 21;
    chip_name = "ESP32-C3";
#elif defined(CONFIG_ESP32_CHIP_ESP32C6)
    max_gpio = 23;
    chip_name = "ESP32-C6";
#elif defined(CONFIG_ESP32_CHIP_ESP32S2)
    max_gpio = 45;
    chip_name = "ESP32-S2";
#elif defined(CONFIG_ESP32_CHIP_ESP32S3)
    max_gpio = 47;
    chip_name = "ESP32-S3";
#endif

    ESP_LOGI(TAG, "Chip type: %s", chip_name);
    
    if (CONFIG_RELAY_GPIO > max_gpio || CONFIG_STATUS_LED_GPIO > max_gpio) {
        ESP_LOGE(TAG, "Invalid GPIO configuration for %s!", chip_name);
        ESP_LOGE(TAG, "Relay GPIO: %d (max: %d), LED GPIO: %d (max: %d)", 
                 CONFIG_RELAY_GPIO, max_gpio, CONFIG_STATUS_LED_GPIO, max_gpio);
        ESP_LOGE(TAG, "Please update sdkconfig with valid GPIO pins");
        return;
    }
    
    ESP_LOGI(TAG, "Relay GPIO: %d", CONFIG_RELAY_GPIO);
    ESP_LOGI(TAG, "Status LED GPIO: %d", CONFIG_STATUS_LED_GPIO);
    
    ESP_LOGI(TAG, "Initial free heap size: %lu bytes", (unsigned long)esp_get_free_heap_size());
    ESP_LOGI(TAG, "Minimum free heap size: %lu bytes", (unsigned long)esp_get_minimum_free_heap_size());
    
    ESP_LOGI(TAG, "Allowing system to stabilize...");
    vTaskDelay(pdMS_TO_TICKS(1000)); // Longer stabilization time
    
    ESP_LOGI(TAG, "Initializing NVS...");
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition needs to be erased");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    ESP_LOGI(TAG, "NVS initialized successfully");
    ESP_LOGI(TAG, "Free heap after NVS: %lu bytes", (unsigned long)esp_get_free_heap_size());
    
    ESP_LOGI(TAG, "Configuring power management...");
    esp_pm_config_t pm_config = {
        .max_freq_mhz = 80, 
        .min_freq_mhz = 10,  
        .light_sleep_enable = false 
    };
    esp_err_t pm_ret = esp_pm_configure(&pm_config);
    if (pm_ret == ESP_OK) {
        ESP_LOGI(TAG, "Power management configured: Max 80MHz, Min 10MHz");
    } else {
        ESP_LOGW(TAG, "Power management not available on this build: %s", esp_err_to_name(pm_ret));
        ESP_LOGI(TAG, "Continuing without dynamic frequency scaling");
    }
    
    ESP_LOGI(TAG, "Initializing GPIO components...");
    
    ESP_LOGI(TAG, "Initializing RGB LED Manager...");
    esp_err_t rgb_err = rgb_led_manager_init();
    if (rgb_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize RGB LED Manager: %s", esp_err_to_name(rgb_err));
        ESP_LOGE(TAG, "System will continue without RGB LED functionality");
    } else {
        ESP_LOGI(TAG, "RGB LED Manager initialized - ESP32-C6 RGB LED ready!");
        
        rgb_effect_config_t startup_effect = {
            .effect     = RGB_EFFECT_SOLID, 
            .primary_color = RGB_COLOR_BLUE,
            .speed_ms   = 100, 
            .brightness = 20,  
            .repeat     = false
        };
        rgb_led_start_effect(&startup_effect);
        vTaskDelay(pdMS_TO_TICKS(500)); 
        rgb_led_stop_effect();
        
        rgb_led_set_status(RGB_STATUS_DISCONNECTED);
    }
    ESP_LOGI(TAG, "Free heap after RGB LED init: %lu bytes", (unsigned long)esp_get_free_heap_size());
    
    // Longer delay to allow power to stabilize after RGB LED
    vTaskDelay(pdMS_TO_TICKS(1000));
    
    update_rgb_status_led(RGB_STATUS_DISCONNECTED);
    ESP_LOGI(TAG, "RGB LED status setup complete");
    ESP_LOGI(TAG, "Free heap after RGB LED setup: %lu bytes", (unsigned long)esp_get_free_heap_size());
    
    ESP_LOGI(TAG, "Initializing relay control...");
    esp_err_t relay_err = relay_control_init();
    if (relay_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize relay control: %s", esp_err_to_name(relay_err));
        ESP_LOGE(TAG, "System will continue without relay functionality");
    } else {
        ESP_LOGI(TAG, "Relay control initialized");
    }
    ESP_LOGI(TAG, "Free heap after relay init: %lu bytes", (unsigned long)esp_get_free_heap_size());
    
    vTaskDelay(pdMS_TO_TICKS(500));


    ESP_LOGI(TAG, "Turning off RGB LED to minimize power during WiFi initialization...");
    rgb_led_off();
    
    vTaskDelay(pdMS_TO_TICKS(2000)); 
    
    ESP_LOGI(TAG, "Reducing CPU frequency to minimize power consumption during WiFi init...");
    esp_pm_config_t low_power_config = {
        .max_freq_mhz = 40,  
        .min_freq_mhz = 10,  
        .light_sleep_enable = false 
    };
    esp_err_t low_pm_ret = esp_pm_configure(&low_power_config);
    if (low_pm_ret == ESP_OK) {
        ESP_LOGI(TAG, "CPU frequency reduced to 40MHz for WiFi initialization");
    } else {
        ESP_LOGI(TAG, "Using extended delays for power management instead");
        vTaskDelay(pdMS_TO_TICKS(3000)); 
    }

    vTaskDelay(pdMS_TO_TICKS(1000));
    
    ESP_LOGI(TAG, "Initializing WiFi manager...");

    nvs_handle_t phy_handle;
    esp_err_t nvs_ret = nvs_open("phy", NVS_READWRITE, &phy_handle);
    if (nvs_ret == ESP_OK) {
        nvs_close(phy_handle);
        ESP_LOGI(TAG, "PHY calibration NVS namespace ready");
    } else {
        ESP_LOGW(TAG, "PHY calibration NVS not available: %s", esp_err_to_name(nvs_ret));
        // Try to create the namespace
        nvs_ret = nvs_open("phy", NVS_READWRITE, &phy_handle);
        if (nvs_ret == ESP_OK) {
            nvs_close(phy_handle);
            ESP_LOGI(TAG, "PHY calibration NVS namespace created");
        }
    }
    
    esp_err_t wifi_err = wifi_manager_init(wifi_event_callback);
    if (wifi_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize WiFi manager: %s", esp_err_to_name(wifi_err));
        ESP_LOGE(TAG, "System will continue without WiFi functionality");
    } else {
        ESP_LOGI(TAG, "WiFi manager initialized");
    }
    ESP_LOGI(TAG, "Free heap after WiFi init: %lu bytes", (unsigned long)esp_get_free_heap_size());


    ESP_LOGI(TAG, "WiFi initialized - waiting before starting connection...");
    vTaskDelay(pdMS_TO_TICKS(3000)); 
    
    ESP_LOGI(TAG, "Initializing MQTT client...");
    esp_err_t mqtt_err = mqtt_client_init();
    if (mqtt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client: %s", esp_err_to_name(mqtt_err));
        ESP_LOGE(TAG, "System will continue without MQTT functionality");
    } else {
        ESP_LOGI(TAG, "MQTT client initialized");
    }
    ESP_LOGI(TAG, "Free heap after MQTT init: %lu bytes", (unsigned long)esp_get_free_heap_size());
    
    ESP_LOGI(TAG, "Creating heartbeat task...");
    BaseType_t heartbeat_result = xTaskCreate(
        heartbeat_task, 
        "heartbeat", 
        8192,  
        NULL, 
        5, 
        NULL
    );
    
    if (heartbeat_result != pdPASS) {
        ESP_LOGE(TAG, "Failed to create heartbeat task");
    } else {
        ESP_LOGI(TAG, "Heartbeat task created successfully");
    }
    ESP_LOGI(TAG, "Free heap after heartbeat task: %lu bytes", (unsigned long)esp_get_free_heap_size());
    
    ESP_LOGI(TAG, "%s Device Controller initialized successfully", chip_name);
    ESP_LOGI(TAG, "Ready to receive MQTT commands on topic: %s/relay/set", CONFIG_DEVICE_ID);
    ESP_LOGI(TAG, "RGB LED will show system status: Blue=Connecting, Cyan=WiFi, Green=Relay ON, Yellow=Relay OFF");
    
    if (wifi_err == ESP_OK) {
        ESP_LOGI(TAG, "Starting WiFi connection with power management...");
        
        ESP_LOGI(TAG, "Final power stabilization before WiFi start...");
        vTaskDelay(pdMS_TO_TICKS(2000));
        
        ESP_LOGI(TAG, "Starting WiFi at reduced CPU frequency...");
        esp_err_t wifi_start_err = wifi_manager_start();
        if (wifi_start_err != ESP_OK) {
            ESP_LOGE(TAG, "Failed to start WiFi: %s", esp_err_to_name(wifi_start_err));
        } else {
            ESP_LOGI(TAG, "WiFi started successfully at low power");
            
            vTaskDelay(pdMS_TO_TICKS(3000));
            
            ESP_LOGI(TAG, "Restoring normal CPU frequency...");
            esp_pm_config_t normal_config = {
                .max_freq_mhz = 80,
                .min_freq_mhz = 10,  
                .light_sleep_enable = false 
            };
            esp_err_t restore_pm_ret = esp_pm_configure(&normal_config);
            if (restore_pm_ret == ESP_OK) {
                ESP_LOGI(TAG, "CPU frequency restored to 80MHz");
            } else {
                ESP_LOGI(TAG, "Power management not available - continuing with default frequency");
            }
            
            ESP_LOGI(TAG, "Restoring RGB LED status...");
            update_rgb_status_led(RGB_STATUS_CONNECTING);
            
            ESP_LOGI(TAG, "WiFi connection started, waiting for result...");
            esp_err_t wait_result = wifi_manager_wait_for_connection(30000);
            if (wait_result == ESP_OK) {
                ESP_LOGI(TAG, "WiFi connected successfully");
            } else if (wait_result == ESP_ERR_TIMEOUT) {
                ESP_LOGW(TAG, "WiFi connection timeout, will retry in background");
            } else {
                ESP_LOGW(TAG, "WiFi connection failed, will retry in background");
            }
        }
    }
    
    vTaskDelay(pdMS_TO_TICKS(500));
    ESP_LOGI(TAG, "Entering main loop");
    
    while (1) {
        static int loop_count = 0;
        if (loop_count % 10 == 0) {  
            ESP_LOGI(TAG, "Free heap size: %lu bytes", (unsigned long)esp_get_free_heap_size());
            ESP_LOGI(TAG, "Minimum free heap: %lu bytes", (unsigned long)esp_get_minimum_free_heap_size());
            ESP_LOGI(TAG, "WiFi state: %d, MQTT state: %d", 
                    wifi_manager_get_state(), 
                    mqtt_client_get_state());
        }
        loop_count++;
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
}
