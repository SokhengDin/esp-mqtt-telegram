#ifndef RGB_LED_MANAGER_H
#define RGB_LED_MANAGER_H

#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#ifdef __cplusplus
extern "C" {
#endif

// RGB LED Configuration
#define RGB_LED_GPIO                8
#define RGB_LED_COUNT              1
#define RGB_LED_RMT_RES_HZ         (10 * 1000 * 1000) // 10MHz resolution

// RGB Color Structure
typedef struct {
    uint8_t red;
    uint8_t green;
    uint8_t blue;
} rgb_color_t;

// Predefined Colors
extern const rgb_color_t RGB_COLOR_OFF;
extern const rgb_color_t RGB_COLOR_RED;
extern const rgb_color_t RGB_COLOR_GREEN;
extern const rgb_color_t RGB_COLOR_BLUE;
extern const rgb_color_t RGB_COLOR_YELLOW;
extern const rgb_color_t RGB_COLOR_CYAN;
extern const rgb_color_t RGB_COLOR_MAGENTA;
extern const rgb_color_t RGB_COLOR_WHITE;
extern const rgb_color_t RGB_COLOR_ORANGE;
extern const rgb_color_t RGB_COLOR_PURPLE;
extern const rgb_color_t RGB_COLOR_PINK;
extern const rgb_color_t RGB_COLOR_LIME;

// LED Effect Types
typedef enum {
    RGB_EFFECT_SOLID = 0,           // Solid color
    RGB_EFFECT_BLINK,               // Simple blink
    RGB_EFFECT_BREATHE,             // Breathing effect
    RGB_EFFECT_RAINBOW,             // Rainbow cycle
    RGB_EFFECT_RAINBOW_CHASE,       // Rainbow with chase effect
    RGB_EFFECT_PULSE,               // Pulse effect
    RGB_EFFECT_STROBE,              // Strobe effect
    RGB_EFFECT_FADE_IN_OUT,         // Fade in and out
    RGB_EFFECT_COLOR_WIPE,          // Color wipe effect
    RGB_EFFECT_THEATER_CHASE,       // Theater chase effect
    RGB_EFFECT_FIRE,                // Fire simulation
    RGB_EFFECT_SPARKLE,             // Random sparkle
    RGB_EFFECT_MAX
} rgb_effect_t;

// LED Status Types (for system status indication)
typedef enum {
    RGB_STATUS_DISCONNECTED = 0,    // System disconnected
    RGB_STATUS_CONNECTING,          // System connecting
    RGB_STATUS_WIFI_CONNECTED,      // WiFi connected
    RGB_STATUS_MQTT_CONNECTED,      // MQTT connected (relay state unknown)
    RGB_STATUS_MQTT_RELAY_ON,       // MQTT connected + Relay ON
    RGB_STATUS_MQTT_RELAY_OFF,      // MQTT connected + Relay OFF
    RGB_STATUS_ERROR,               // System error
    RGB_STATUS_CUSTOM,              // Custom effect
    RGB_STATUS_MAX
} rgb_status_t;

// Effect Configuration
typedef struct {
    rgb_effect_t effect;
    rgb_color_t primary_color;
    rgb_color_t secondary_color;
    uint32_t speed_ms;              // Effect speed in milliseconds
    uint8_t brightness;             // Brightness 0-255
    bool repeat;                    // Whether to repeat the effect
} rgb_effect_config_t;

/**
 * @brief Initialize RGB LED manager
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_manager_init(void);

/**
 * @brief Deinitialize RGB LED manager
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_manager_deinit(void);

/**
 * @brief Set solid color
 * 
 * @param color RGB color to set
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_set_color(rgb_color_t color);

/**
 * @brief Set color with brightness
 * 
 * @param color RGB color to set
 * @param brightness Brightness level (0-255)
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_set_color_brightness(rgb_color_t color, uint8_t brightness);

/**
 * @brief Turn off RGB LED
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_off(void);

/**
 * @brief Start an effect
 * 
 * @param config Effect configuration
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_start_effect(rgb_effect_config_t *config);

/**
 * @brief Stop current effect
 * 
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_stop_effect(void);

/**
 * @brief Set system status indication
 * 
 * @param status System status to indicate
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_set_status(rgb_status_t status);

/**
 * @brief Set status indication based on MQTT and relay state
 * 
 * @param mqtt_connected Whether MQTT is connected
 * @param relay_on Whether relay is on (true) or off (false)
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_set_mqtt_relay_status(bool mqtt_connected, bool relay_on);

/**
 * @brief Get current effect configuration
 * 
 * @return rgb_effect_config_t* Current effect config or NULL
 */
rgb_effect_config_t* rgb_led_get_current_effect(void);

/**
 * @brief Check if effect is running
 * 
 * @return true if effect is running
 */
bool rgb_led_is_effect_running(void);

/**
 * @brief Create RGB color from HSV
 * 
 * @param hue Hue (0-360)
 * @param saturation Saturation (0-100)
 * @param value Value/Brightness (0-100)
 * @return rgb_color_t RGB color
 */
rgb_color_t rgb_led_hsv_to_rgb(uint16_t hue, uint8_t saturation, uint8_t value);

/**
 * @brief Blend two colors
 * 
 * @param color1 First color
 * @param color2 Second color
 * @param blend_factor Blend factor (0-255, 0=color1, 255=color2)
 * @return rgb_color_t Blended color
 */
rgb_color_t rgb_led_blend_colors(rgb_color_t color1, rgb_color_t color2, uint8_t blend_factor);

/**
 * @brief Set global brightness
 * 
 * @param brightness Global brightness (0-255)
 * @return esp_err_t ESP_OK on success
 */
esp_err_t rgb_led_set_brightness(uint8_t brightness);

/**
 * @brief Get current brightness
 * 
 * @return uint8_t Current brightness (0-255)
 */
uint8_t rgb_led_get_brightness(void);

#ifdef __cplusplus
}
#endif

#endif // RGB_LED_MANAGER_H 