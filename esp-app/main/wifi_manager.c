#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "includes/wifi_manager.h"

static const char *TAG = "wifi_manager";

/* FreeRTOS event group to signal when we are connected*/
static EventGroupHandle_t s_wifi_event_group = NULL;

/* The event group allows multiple bits for each event, but we only care about two events:
 * - we are connected to the AP with an IP
 * - we failed to connect after the maximum amount of retries */
#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1

static int s_retry_num                          = 0;
static wifi_state_t s_wifi_state                = WIFI_STATE_DISCONNECTED;
static wifi_event_callback_t s_event_callback   = NULL;
static bool s_wifi_initialized                  = false;

static void wifi_state_changed(wifi_state_t new_state)
{
    s_wifi_state = new_state;
    if (s_event_callback) {
        s_event_callback(new_state);
    }
}

static void event_handler(void* arg, esp_event_base_t event_base,
                         int32_t event_id, void* event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "WiFi started, connecting...");
        
        esp_err_t tx_power_ret = esp_wifi_set_max_tx_power(34); 
        if (tx_power_ret == ESP_OK) {
            ESP_LOGI(TAG, "WiFi TX power reduced to 8.5dBm");
        } else {
            ESP_LOGW(TAG, "Failed to set WiFi TX power: %s", esp_err_to_name(tx_power_ret));
        }
        
        wifi_state_changed(WIFI_STATE_CONNECTING);
        vTaskDelay(pdMS_TO_TICKS(100)); 
        esp_wifi_connect();

    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (s_retry_num < CONFIG_ESP_MAXIMUM_RETRY) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            esp_wifi_connect();
            s_retry_num++;
            ESP_LOGI(TAG, "Retry to connect to the AP (%d/%d)", s_retry_num, CONFIG_ESP_MAXIMUM_RETRY);
            wifi_state_changed(WIFI_STATE_CONNECTING);

        } else {
            if (s_wifi_event_group != NULL) {
                xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
            } else {
                ESP_LOGW(TAG, "WiFi event group is NULL, cannot set fail bit");
            }
            ESP_LOGI(TAG, "Connect to the AP fail");
            wifi_state_changed(WIFI_STATE_FAILED);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        if (event) {
            ESP_LOGI(TAG, "Got IP:" IPSTR, IP2STR(&event->ip_info.ip));
        }
        s_retry_num = 0;
        if (s_wifi_event_group != NULL) {
            xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
        } else {
            ESP_LOGW(TAG, "WiFi event group is NULL, cannot set connected bit");
        }
        wifi_state_changed(WIFI_STATE_CONNECTED);
    }
}

esp_err_t wifi_manager_init(wifi_event_callback_t callback)
{
    if (s_wifi_initialized) {
        ESP_LOGW(TAG, "WiFi manager already initialized");
        return ESP_OK;
    }
    
    s_event_callback    = callback;
    s_wifi_event_group  = xEventGroupCreate();
    
    if (s_wifi_event_group == NULL) {
        ESP_LOGE(TAG, "Failed to create WiFi event group");
        return ESP_FAIL;
    }

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    
    // Configure WiFi with power-saving settings
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    
    // Aggressive power reduction settings
    cfg.static_rx_buf_num   = 2;      // Minimum possible
    cfg.dynamic_rx_buf_num  = 4;      // Reduced further
    cfg.tx_buf_type         = 0;      
    cfg.static_tx_buf_num   = 2;      // Minimum possible
    cfg.cache_tx_buf_num    = 2;      // Minimum possible
    
    // Additional power optimizations
    cfg.ampdu_rx_enable     = 0;      // Disable AMPDU to reduce power
    cfg.ampdu_tx_enable     = 0;      // Disable AMPDU to reduce power
    cfg.amsdu_tx_enable     = 0;      // Disable AMSDU to reduce power
    cfg.nvs_enable          = 1;      // Keep NVS for calibration data
    cfg.nano_enable         = 0;      // Disable nano formatting
    
    ESP_LOGI(TAG, "Initializing WiFi with minimal power settings...");
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &event_handler,
                                                        NULL,
                                                        &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &event_handler,
                                                        NULL,
                                                        &instance_got_ip));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid       = CONFIG_ESP_WIFI_SSID,
            .password   = CONFIG_ESP_WIFI_PASSWORD,
            .threshold.authmode = WIFI_AUTH_WPA2_PSK,
            .pmf_cfg        = {
                .capable    = true,
                .required   = false
            },
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_MIN_MODEM));
    
    ESP_LOGI(TAG, "Pre-configuring WiFi TX power to reduce startup current...");
    esp_err_t tx_power_ret = esp_wifi_set_max_tx_power(28);
    if (tx_power_ret == ESP_OK) {
        ESP_LOGI(TAG, "WiFi TX power pre-configured to 7dBm");
    } else {
        ESP_LOGW(TAG, "Failed to pre-configure WiFi TX power: %s", esp_err_to_name(tx_power_ret));
    }

    s_wifi_initialized = true;
    ESP_LOGI(TAG, "WiFi manager initialized with power optimizations");
    return ESP_OK;
}

esp_err_t wifi_manager_start(void)
{
    if (!s_wifi_initialized) {
        ESP_LOGE(TAG, "WiFi manager not initialized");
        return ESP_FAIL;
    }
    
    if (s_wifi_event_group == NULL) {
        ESP_LOGE(TAG, "WiFi event group not created");
        return ESP_FAIL;
    }
    
    ESP_LOGI(TAG, "Starting WiFi with aggressive power management...");
    
    
    ESP_LOGI(TAG, "Stage 1: Extended pre-start stabilization (5 seconds)...");
    vTaskDelay(pdMS_TO_TICKS(5000));
    
    const int max_attempts = 3;
    esp_err_t start_result = ESP_FAIL;
    
    for (int attempt = 1; attempt <= max_attempts; attempt++) {
        ESP_LOGI(TAG, "Stage 2: WiFi start attempt %d/%d", attempt, max_attempts);
        
        if (attempt > 1) {
            uint32_t delay_ms = attempt * 2000;
            vTaskDelay(pdMS_TO_TICKS(delay_ms));
        }
        
        start_result = esp_wifi_start();
        if (start_result == ESP_OK) {
            break;
        }
    }
    
    if (start_result != ESP_OK) {
        ESP_LOGE(TAG, "All WiFi start attempts failed");
        return start_result;
    }
    
    ESP_LOGI(TAG, "Stage 3: Extended WiFi stabilization (5 seconds)...");
    vTaskDelay(pdMS_TO_TICKS(5000)); 
    
    ESP_LOGI(TAG, "WiFi radio started successfully after power management staging");
    
    return ESP_OK;
}

wifi_state_t wifi_manager_get_state(void)
{
    return s_wifi_state;
}

bool wifi_manager_is_connected(void)
{
    return s_wifi_state == WIFI_STATE_CONNECTED;
}

esp_err_t wifi_manager_wait_for_connection(uint32_t timeout_ms)
{
    if (s_wifi_event_group == NULL) {
        return ESP_FAIL;
    }
    
    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group,
            WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
            pdFALSE,
            pdFALSE,
            pdMS_TO_TICKS(timeout_ms));
    
    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "Connected to AP SSID:%s", CONFIG_ESP_WIFI_SSID);
        return ESP_OK;
    } else if (bits & WIFI_FAIL_BIT) {
        ESP_LOGI(TAG, "Failed to connect to SSID:%s", CONFIG_ESP_WIFI_SSID);
        return ESP_FAIL;
    } else {
        ESP_LOGW(TAG, "WiFi connection timeout after %lu ms", timeout_ms);
        return ESP_ERR_TIMEOUT;
    }
} 