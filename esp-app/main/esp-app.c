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

// Make the LED pattern variable static to avoid race conditions
static volatile int current_led_pattern = 0;
static TaskHandle_t led_task_handle = NULL;

// Status LED blink patterns
static void status_led_blink_task(void *pvParameters)
{
    ESP_LOGI(TAG, "Status LED task started");
    
    while (1) {
        // Read the current pattern safely
        int pattern = current_led_pattern;
        
        switch (pattern) {
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

static void update_status_led(int pattern)
{
    current_led_pattern = pattern;
    

    if (led_task_handle == NULL) {
        // Check available heap before creating task
        size_t free_heap = esp_get_free_heap_size();
        if (free_heap < 8192) { 
            ESP_LOGW(TAG, "Insufficient heap for LED task: %zu bytes", free_heap);
            return;
        }
        
        BaseType_t result = xTaskCreate(
            status_led_blink_task, 
            "status_led", 
            4096,  // Increased stack size
            NULL,  // No parameter needed now
            3,     // Lower priority than critical tasks
            &led_task_handle
        );
        
        if (result != pdPASS) {
            ESP_LOGE(TAG, "Failed to create status LED task");
            led_task_handle = NULL;
        } else {
            ESP_LOGI(TAG, "Status LED task created successfully");
            // Small delay to let task start
            vTaskDelay(pdMS_TO_TICKS(10));
        }
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
    ESP_LOGI(TAG, "Heartbeat task started");
    
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
    ESP_LOGI(TAG, "ESP32-C6 Device Controller starting...");
    ESP_LOGI(TAG, "Device ID: %s", CONFIG_DEVICE_ID);
    
    if (CONFIG_RELAY_GPIO > 23 || CONFIG_STATUS_LED_GPIO > 23) {
        ESP_LOGE(TAG, "Invalid GPIO configuration for ESP32-C6!");
        ESP_LOGE(TAG, "Relay GPIO: %d (max: 23), LED GPIO: %d (max: 23)", 
                 CONFIG_RELAY_GPIO, CONFIG_STATUS_LED_GPIO);
        ESP_LOGE(TAG, "Please update sdkconfig with valid GPIO pins");
        return;
    }
    
    ESP_LOGI(TAG, "Relay GPIO: %d", CONFIG_RELAY_GPIO);
    ESP_LOGI(TAG, "Status LED GPIO: %d", CONFIG_STATUS_LED_GPIO);
    
    ESP_LOGI(TAG, "Initial free heap size: %lu bytes", esp_get_free_heap_size());
    ESP_LOGI(TAG, "Minimum free heap size: %lu bytes", esp_get_minimum_free_heap_size());
    
    ESP_LOGI(TAG, "Allowing system to stabilize...");
    vTaskDelay(pdMS_TO_TICKS(500));
    
    ESP_LOGI(TAG, "Initializing NVS...");
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition needs to be erased");
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    ESP_LOGI(TAG, "NVS initialized successfully");
    ESP_LOGI(TAG, "Free heap after NVS: %lu bytes", esp_get_free_heap_size());
    
    // Initialize components
    ESP_LOGI(TAG, "Initializing GPIO components...");
    
    ESP_LOGI(TAG, "Initializing status LED...");
    status_led_init();
    ESP_LOGI(TAG, "Status LED initialized");
    ESP_LOGI(TAG, "Free heap after LED init: %lu bytes", esp_get_free_heap_size());
    
    // Delay before creating tasks
    vTaskDelay(pdMS_TO_TICKS(100));
    
    // Set initial LED state
    update_status_led(0); // Start with LED off
    ESP_LOGI(TAG, "Status LED task setup complete");
    ESP_LOGI(TAG, "Free heap after LED task: %lu bytes", esp_get_free_heap_size());
    
    // Initialize relay control
    ESP_LOGI(TAG, "Initializing relay control...");
    esp_err_t relay_err = relay_control_init();
    if (relay_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize relay control: %s", esp_err_to_name(relay_err));
        return;
    }
    ESP_LOGI(TAG, "Relay control initialized");
    ESP_LOGI(TAG, "Free heap after relay init: %lu bytes", esp_get_free_heap_size());
    
    vTaskDelay(pdMS_TO_TICKS(200));
    
    // Initialize WiFi manager
    ESP_LOGI(TAG, "Initializing WiFi manager...");
    esp_err_t wifi_err = wifi_manager_init(wifi_event_callback);
    if (wifi_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize WiFi manager: %s", esp_err_to_name(wifi_err));
        return;
    }
    ESP_LOGI(TAG, "WiFi manager initialized");
    ESP_LOGI(TAG, "Free heap after WiFi init: %lu bytes", esp_get_free_heap_size());
    

    vTaskDelay(pdMS_TO_TICKS(200));
    
    // Initialize MQTT client
    ESP_LOGI(TAG, "Initializing MQTT client...");
    esp_err_t mqtt_err = mqtt_client_init();
    if (mqtt_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client: %s", esp_err_to_name(mqtt_err));
        return;
    }
    ESP_LOGI(TAG, "MQTT client initialized");
    ESP_LOGI(TAG, "Free heap after MQTT init: %lu bytes", esp_get_free_heap_size());
    
    ESP_LOGI(TAG, "Starting WiFi connection...");
    
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
    ESP_LOGI(TAG, "Free heap after heartbeat task: %lu bytes", esp_get_free_heap_size());
    
    ESP_LOGI(TAG, "ESP32-C6 Device Controller initialized successfully");
    ESP_LOGI(TAG, "Ready to receive MQTT commands on topic: %s/relay/set", CONFIG_DEVICE_ID);
    
    // Start WiFi connection 
    ESP_LOGI(TAG, "Starting WiFi connection process...");
    esp_err_t wifi_start_err = wifi_manager_start();
    if (wifi_start_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start WiFi: %s", esp_err_to_name(wifi_start_err));
    }
    
    vTaskDelay(pdMS_TO_TICKS(500));
    ESP_LOGI(TAG, "Entering main loop");
    
    while (1) {
        
        static int loop_count = 0;
        if (loop_count % 10 == 0) {  
            ESP_LOGI(TAG, "Free heap size: %lu bytes", esp_get_free_heap_size());
            ESP_LOGI(TAG, "Minimum free heap: %lu bytes", esp_get_minimum_free_heap_size());
        }
        loop_count++;
        vTaskDelay(pdMS_TO_TICKS(10000)); 
    }
}
