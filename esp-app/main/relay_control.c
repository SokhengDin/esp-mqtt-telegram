#include "includes/relay_control.h"
#include "driver/gpio.h"
#include "esp_log.h"

static const char *TAG = "relay_control";

static relay_state_t s_relay_state = RELAY_STATE_OFF;

esp_err_t relay_control_init(void)
{
    gpio_config_t io_conf = {
        .intr_type = GPIO_INTR_DISABLE,
        .mode = GPIO_MODE_OUTPUT,
        .pin_bit_mask = (1ULL << CONFIG_RELAY_GPIO),
        .pull_down_en = 0,
        .pull_up_en = 0,
    };
    
    esp_err_t ret = gpio_config(&io_conf);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure relay GPIO");
        return ret;
    }
    
    // Initialize relay to OFF state
    gpio_set_level(CONFIG_RELAY_GPIO, 0);
    s_relay_state = RELAY_STATE_OFF;
    
    ESP_LOGI(TAG, "Relay control initialized on GPIO %d", CONFIG_RELAY_GPIO);
    return ESP_OK;
}

esp_err_t relay_control_set_state(relay_state_t state)
{
    esp_err_t ret = gpio_set_level(CONFIG_RELAY_GPIO, state);
    if (ret == ESP_OK) {
        s_relay_state = state;
        ESP_LOGI(TAG, "Relay state set to: %s", state == RELAY_STATE_ON ? "ON" : "OFF");
    } else {
        ESP_LOGE(TAG, "Failed to set relay state");
    }
    
    return ret;
}

relay_state_t relay_control_get_state(void)
{
    return s_relay_state;
}

esp_err_t relay_control_turn_on(void)
{
    return relay_control_set_state(RELAY_STATE_ON);
}

esp_err_t relay_control_turn_off(void)
{
    return relay_control_set_state(RELAY_STATE_OFF);
}

esp_err_t relay_control_toggle(void)
{
    relay_state_t new_state = (s_relay_state == RELAY_STATE_ON) ? RELAY_STATE_OFF : RELAY_STATE_ON;
    return relay_control_set_state(new_state);
} 