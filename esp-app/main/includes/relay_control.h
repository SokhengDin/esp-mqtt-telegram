#ifndef RELAY_CONTROL_H
#define RELAY_CONTROL_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Relay states
 */
typedef enum {
    RELAY_STATE_OFF = 0,
    RELAY_STATE_ON = 1
} relay_state_t;

/**
 * @brief Initialize relay control
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t relay_control_init(void);

/**
 * @brief Set relay state
 * 
 * @param state Desired relay state
 * @return esp_err_t ESP_OK on success
 */
esp_err_t relay_control_set_state(relay_state_t state);

/**
 * @brief Get current relay state
 * 
 * @return relay_state_t Current relay state
 */
relay_state_t relay_control_get_state(void);

/**
 * @brief Turn relay on
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t relay_control_turn_on(void);

/**
 * @brief Turn relay off
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t relay_control_turn_off(void);

/**
 * @brief Toggle relay state
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t relay_control_toggle(void);

#ifdef __cplusplus
}
#endif

#endif // RELAY_CONTROL_H 