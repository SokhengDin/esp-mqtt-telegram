#ifndef WIFI_MANAGER_H
#define WIFI_MANAGER_H

#include "esp_err.h"
#include "esp_event.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief WiFi connection states
 */
typedef enum {
    WIFI_STATE_DISCONNECTED,
    WIFI_STATE_CONNECTING,
    WIFI_STATE_CONNECTED,
    WIFI_STATE_FAILED
} wifi_state_t;

/**
 * @brief WiFi event callback function type
 */
typedef void (*wifi_event_callback_t)(wifi_state_t state);

/**
 * @brief Initialize WiFi manager
 * 
 * @param callback Callback function for WiFi events
 * @return esp_err_t ESP_OK on success
 */
esp_err_t wifi_manager_init(wifi_event_callback_t callback);

/**
 * @brief Start WiFi connection
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t wifi_manager_start(void);

/**
 * @brief Wait for WiFi connection with timeout
 * @param timeout_ms Timeout in milliseconds
 * @return ESP_OK if connected, ESP_FAIL if failed, ESP_ERR_TIMEOUT if timeout
 */
esp_err_t wifi_manager_wait_for_connection(uint32_t timeout_ms);

/**
 * @brief Get current WiFi state
 * 
 * @return wifi_state_t Current WiFi state
 */
wifi_state_t wifi_manager_get_state(void);

/**
 * @brief Check if WiFi is connected
 * 
 * @return true if connected, false otherwise
 */
bool wifi_manager_is_connected(void);

#ifdef __cplusplus
}
#endif

#endif // WIFI_MANAGER_H 