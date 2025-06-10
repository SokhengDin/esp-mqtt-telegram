#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "driver/gpio.h"

#include "includes/wifi_manager.h"
#include "includes/mqtt_manager.h"
#include "includes/relay_control.h"

static const char *TAG = "main";

// Status LED control
static void status_led_init(void)
{
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_DISABLE,
        .mode = GPIO_MODE_OUTPUT,
        .pin_bit_mask = (1ULL << CONFIG_STATUS_LED_GPIO),
        .pull_down_en = 0,
        .pull_up_en = 0,
    };
    gpio_config(&io_conf);
    gpio_set_level(CONFIG_STATUS_LED_GPIO, 0);
    ESP_LOGI(TAG, "Status LED initialized on GPIO %d", CONFIG_STATUS_LED_GPIO);
}

static void status_led_set(bool on)
{
    gpio_set_level(CONFIG_STATUS_LED_GPIO, on ? 1 : 0);
}

// Status LED blink patterns
static void status_led_blink_task(void *pvParameters)
{
    int blink_pattern = *(int*)pvParameters;
    
    while (1) {
        switch (blink_pattern) {
            case 0: // Solid off - disconnected
                status_led_set(false);
                vTaskDelay(pdMS_TO_TICKS(1000));
                break;
                
            case 1: // Slow blink - connecting
                status_led_set(true);
                vTaskDelay(pdMS_TO_TICKS(500));
                status_led_set(false);
                vTaskDelay(pdMS_TO_TICKS(500));
                break;
                
            case 2: // Fast blink - WiFi connected, MQTT connecting
                status_led_set(true);
                vTaskDelay(pdMS_TO_TICKS(200));
                status_led_set(false);
                vTaskDelay(pdMS_TO_TICKS(200));
                break;
                
            case 3: // Solid on - fully connected
                status_led_set(true);
                vTaskDelay(pdMS_TO_TICKS(1000));
                break;
                
            default:
                vTaskDelay(pdMS_TO_TICKS(100));
                break;
        }
    }
}

static int current_led_pattern = 0;
static TaskHandle_t led_task_handle = NULL;

static void update_status_led(int pattern)
{
    current_led_pattern = pattern;
    if (led_task_handle == NULL) {
        xTaskCreate(status_led_blink_task, "status_led", 2048, &current_led_pattern, 5, &led_task_handle);
    }
}

// WiFi event callback
static void wifi_event_callback(wifi_state_t state)
{
    switch (state) {
        case WIFI_STATE_DISCONNECTED:
            ESP_LOGI(TAG, "WiFi: Disconnected");
            update_status_led(0); // Solid off
            mqtt_client_stop();
            break;
            
        case WIFI_STATE_CONNECTING:
            ESP_LOGI(TAG, "WiFi: Connecting...");
            update_status_led(1); // Slow blink
            break;
            
        case WIFI_STATE_CONNECTED:
            ESP_LOGI(TAG, "WiFi: Connected");
            update_status_led(2); // Fast blink
            // Start MQTT client when WiFi is connected
            mqtt_client_start();
            break;
            
        case WIFI_STATE_FAILED:
            ESP_LOGI(TAG, "WiFi: Failed to connect");
            update_status_led(0); // Solid off
            break;
    }
}

// Function to update status LED based on MQTT state
void status_led_set_mqtt_state(mqtt_state_t state)
{
    switch (state) {
        case MQTT_STATE_DISCONNECTED:
            ESP_LOGI(TAG, "MQTT: Disconnected");
            if (wifi_manager_is_connected()) {
                update_status_led(2); // Fast blink - WiFi connected 
            }
            break;
            
        case MQTT_STATE_CONNECTING:
            ESP_LOGI(TAG, "MQTT: Connecting...");
            update_status_led(2); // Fast blink
            break;
            
        case MQTT_STATE_CONNECTED:
            ESP_LOGI(TAG, "MQTT: Connected");
            update_status_led(3); // Solid on - fully connected
            break;
            
        case MQTT_STATE_ERROR:
            ESP_LOGI(TAG, "MQTT: Connection error");
            update_status_led(2); // Fast blink
            break;
    }
}

static void heartbeat_task(void *pvParameters)
{
    while (1) {
        if (mqtt_client_get_state() == MQTT_STATE_CONNECTED) {
            // Send heartbeat status
            mqtt_publish_status();
            
            // Send current relay state
            relay_state_t current_state = relay_control_get_state();
            mqtt_publish_relay_state(current_state);
            
            const char *state_str = (current_state == RELAY_STATE_ON) ? "on" : "off";
            ESP_LOGI(TAG, "Heartbeat sent - Status: online, Relay: %s", state_str);
        }
        
        // Send heartbeat every 30 seconds
        vTaskDelay(pdMS_TO_TICKS(30000));
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "ESP32 Device Controller starting...");
    ESP_LOGI(TAG, "Device ID: %s", CONFIG_DEVICE_ID);
    ESP_LOGI(TAG, "Relay GPIO: %d", CONFIG_RELAY_GPIO);
    ESP_LOGI(TAG, "Status LED GPIO: %d", CONFIG_STATUS_LED_GPIO);
    
    // Initialize NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    
    // Initialize components
    ESP_LOGI(TAG, "Initializing components...");
    
    // Initialize status LED
    status_led_init();
    update_status_led(0); // Start with LED off
    
    // Initialize relay control
    ESP_ERROR_CHECK(relay_control_init());
    
    // Initialize WiFi manager
    ESP_ERROR_CHECK(wifi_manager_init(wifi_event_callback));
    
    // Initialize MQTT client
    ESP_ERROR_CHECK(mqtt_client_init());
    
    ESP_LOGI(TAG, "Starting WiFi connection...");
    
    // Create heartbeat task (it will wait for connections)
    xTaskCreate(heartbeat_task, "heartbeat", 4096, NULL, 5, NULL);
    
    ESP_LOGI(TAG, "ESP32 Device Controller initialized successfully");
    ESP_LOGI(TAG, "Ready to receive MQTT commands on topic: %s/relay/set", CONFIG_DEVICE_ID);
    
    // Start WiFi connection (non-blocking)
    esp_err_t wifi_err = wifi_manager_start();
    if (wifi_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start WiFi: %s", esp_err_to_name(wifi_err));
    }
    
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
