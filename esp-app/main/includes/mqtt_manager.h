#ifndef MQTT_MANAGER_H
#define MQTT_MANAGER_H

#include "esp_err.h"

// MQTT connection states
typedef enum {
    MQTT_STATE_DISCONNECTED = 0,
    MQTT_STATE_CONNECTING,
    MQTT_STATE_CONNECTED,
    MQTT_STATE_ERROR
} mqtt_state_t;

#include "relay_control.h"

/**
 * @brief Initialize MQTT client
 * @return ESP_OK on success, ESP_FAIL on failure
 */
esp_err_t mqtt_client_init(void);

/**
 * @brief Start MQTT client connection
 * @return ESP_OK on success, ESP_FAIL on failure
 */
esp_err_t mqtt_client_start(void);

/**
 * @brief Stop MQTT client
 * @return ESP_OK on success, ESP_FAIL on failure
 */
esp_err_t mqtt_client_stop(void);

/**
 * @brief Publish message to MQTT topic
 * @param topic MQTT topic
 * @param data Message data
 * @param qos Quality of service (0, 1, or 2)
 * @param retain Retain flag
 * @return ESP_OK on success, ESP_FAIL on failure
 */
esp_err_t mqtt_publish_message(const char *topic, const char *data, int qos, int retain);

/**
 * @brief Subscribe to MQTT topic
 * @param topic MQTT topic
 * @param qos Quality of service (0, 1, or 2)
 * @return ESP_OK on success, ESP_FAIL on failure
 */
esp_err_t mqtt_client_subscribe(const char *topic, int qos);

/**
 * @brief Get current MQTT client state
 * @return Current MQTT state
 */
mqtt_state_t mqtt_client_get_state(void);

/**
 * @brief Publish device status
 * @return ESP_OK on success, ESP_FAIL on failure
 */
esp_err_t mqtt_publish_status(void);

/**
 * @brief Publish relay state
 * @param state Relay state to publish
 * @return ESP_OK on success, ESP_FAIL on failure
 */
esp_err_t mqtt_publish_relay_state(relay_state_t state);

#endif // MQTT_MANAGER_H 