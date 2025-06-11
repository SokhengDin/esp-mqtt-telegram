#include "includes/rgb_led_manager.h"
#include "led_strip.h"
#include "esp_log.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <math.h>

static const char *TAG = "RGB_LED";

// LED Strip handle
static led_strip_handle_t led_strip     = NULL;

// Effect task handle and control
static TaskHandle_t effect_task_handle = NULL;
static SemaphoreHandle_t effect_mutex   = NULL;
static volatile bool effect_running     = false;
static rgb_effect_config_t current_effect_config = {0};
static uint8_t global_brightness        = 255;

// Predefined Colors
const rgb_color_t RGB_COLOR_OFF     = {0, 0, 0};
const rgb_color_t RGB_COLOR_RED     = {255, 0, 0};
const rgb_color_t RGB_COLOR_GREEN   = {0, 255, 0};
const rgb_color_t RGB_COLOR_BLUE    = {0, 0, 255};
const rgb_color_t RGB_COLOR_YELLOW  = {255, 255, 0};
const rgb_color_t RGB_COLOR_CYAN    = {0, 255, 255};
const rgb_color_t RGB_COLOR_MAGENTA = {255, 0, 255};
const rgb_color_t RGB_COLOR_WHITE   = {255, 255, 255};
const rgb_color_t RGB_COLOR_ORANGE  = {255, 165, 0};
const rgb_color_t RGB_COLOR_PURPLE  = {128, 0, 128};
const rgb_color_t RGB_COLOR_PINK    = {255, 192, 203};
const rgb_color_t RGB_COLOR_LIME    = {50, 205, 50};

// Forward declarations
static void effect_task(void *pvParameters);
static void apply_brightness(rgb_color_t *color, uint8_t brightness);

esp_err_t rgb_led_manager_init(void)
{
    ESP_LOGI(TAG, "Initializing RGB LED Manager for ESP32-C6");
    
    // Create mutex for thread safety
    effect_mutex = xSemaphoreCreateMutex();
    if (effect_mutex == NULL) {
        ESP_LOGE(TAG, "Failed to create effect mutex");
        return ESP_ERR_NO_MEM;
    }
    
    // LED strip configuration
    led_strip_config_t strip_config = {
        .strip_gpio_num     = RGB_LED_GPIO,
        .max_leds           = RGB_LED_COUNT,
        .led_pixel_format   = LED_PIXEL_FORMAT_GRB,
        .led_model          = LED_MODEL_WS2812,
        .flags.invert_out   = false,
    };
    
    // RMT configuration
    led_strip_rmt_config_t rmt_config = {
        .clk_src        = RMT_CLK_SRC_DEFAULT,
        .resolution_hz  = RGB_LED_RMT_RES_HZ,
        .flags.with_dma = false,
    };
    
    // Create LED strip
    esp_err_t ret = led_strip_new_rmt_device(&strip_config, &rmt_config, &led_strip);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create LED strip: %s", esp_err_to_name(ret));
        vSemaphoreDelete(effect_mutex);
        return ret;
    }
    
    // Clear LED
    led_strip_clear(led_strip);
    
    ESP_LOGI(TAG, "RGB LED Manager initialized successfully");
    return ESP_OK;
}

esp_err_t rgb_led_manager_deinit(void)
{
    // Stop any running effects
    rgb_led_stop_effect();
    
    // Delete LED strip
    if (led_strip) {
        led_strip_del(led_strip);
        led_strip = NULL;
    }
    
    // Delete mutex
    if (effect_mutex) {
        vSemaphoreDelete(effect_mutex);
        effect_mutex = NULL;
    }
    
    ESP_LOGI(TAG, "RGB LED Manager deinitialized");
    return ESP_OK;
}

esp_err_t rgb_led_set_color(rgb_color_t color)
{
    if (!led_strip) {
        return ESP_ERR_INVALID_STATE;
    }
    
    xSemaphoreTake(effect_mutex, portMAX_DELAY);
    
    apply_brightness(&color, global_brightness);
    esp_err_t ret = led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
    if (ret == ESP_OK) {
        ret = led_strip_refresh(led_strip);
    }
    
    xSemaphoreGive(effect_mutex);
    return ret;
}

esp_err_t rgb_led_set_color_brightness(rgb_color_t color, uint8_t brightness)
{
    if (!led_strip) {
        return ESP_ERR_INVALID_STATE;
    }
    
    xSemaphoreTake(effect_mutex, portMAX_DELAY);
    
    apply_brightness(&color, brightness);
    esp_err_t ret = led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
    if (ret == ESP_OK) {
        ret = led_strip_refresh(led_strip);
    }
    
    xSemaphoreGive(effect_mutex);
    return ret;
}

esp_err_t rgb_led_off(void)
{
    return rgb_led_set_color(RGB_COLOR_OFF);
}

esp_err_t rgb_led_start_effect(rgb_effect_config_t *config)
{
    if (!config || !led_strip) {
        return ESP_ERR_INVALID_ARG;
    }
    
    // Stop current effect
    rgb_led_stop_effect();
    
    xSemaphoreTake(effect_mutex, portMAX_DELAY);
    
    // Copy configuration
    current_effect_config = *config;
    effect_running = true;
    
    // Create effect task
    BaseType_t result = xTaskCreate(
        effect_task,
        "rgb_effect",
        4096,
        NULL,
        5,
        &effect_task_handle
    );
    
    xSemaphoreGive(effect_mutex);
    
    if (result != pdPASS) {
        effect_running = false;
        ESP_LOGE(TAG, "Failed to create effect task");
        return ESP_ERR_NO_MEM;
    }
    
    ESP_LOGI(TAG, "Started effect: %d", config->effect);
    return ESP_OK;
}

esp_err_t rgb_led_stop_effect(void)
{
    if (effect_task_handle) {
        effect_running = false;
        
        // Wait for task to finish naturally
        int retry_count = 0;
        while (effect_task_handle != NULL && retry_count < 50) {
            vTaskDelay(pdMS_TO_TICKS(10));
            retry_count++;
        }
        
        // Force delete if still running
        if (effect_task_handle != NULL) {
            vTaskDelete(effect_task_handle);
            effect_task_handle = NULL;
        }
        
        if (led_strip) {
            led_strip_clear(led_strip);
        }
        
        ESP_LOGI(TAG, "Effect stopped");
    }
    return ESP_OK;
}

esp_err_t rgb_led_set_status(rgb_status_t status)
{
    rgb_effect_config_t config = {0};
    
    switch (status) {
        case RGB_STATUS_DISCONNECTED:
            config.effect           = RGB_EFFECT_SOLID;
            config.primary_color    = RGB_COLOR_OFF;
            config.speed_ms         = 1000;
            config.brightness       = 0;
            break;
            
        case RGB_STATUS_CONNECTING:
            config.effect           = RGB_EFFECT_BREATHE;
            config.primary_color    = RGB_COLOR_BLUE;
            config.speed_ms         = 1000;
            config.brightness       = 128;
            config.repeat           = true;
            break;
            
        case RGB_STATUS_WIFI_CONNECTED:
            config.effect           = RGB_EFFECT_BLINK;
            config.primary_color    = RGB_COLOR_CYAN;
            config.speed_ms         = 500;
            config.brightness       = 200;
            config.repeat           = true;
            break;
            
        case RGB_STATUS_MQTT_CONNECTED:
            config.effect           = RGB_EFFECT_SOLID;
            config.primary_color    = RGB_COLOR_GREEN;
            config.speed_ms         = 5000;  // Update less frequently for solid colors
            config.brightness       = 255;
            break;
            
        case RGB_STATUS_MQTT_RELAY_ON:
            config.effect           = RGB_EFFECT_SOLID;
            config.primary_color    = RGB_COLOR_GREEN;
            config.speed_ms         = 5000;
            config.brightness       = 255;
            break;
            
        case RGB_STATUS_MQTT_RELAY_OFF:
            config.effect           = RGB_EFFECT_SOLID;
            config.primary_color    = RGB_COLOR_YELLOW;
            config.speed_ms         = 5000;
            config.brightness       = 255;
            break;
            
        case RGB_STATUS_ERROR:
            config.effect           = RGB_EFFECT_STROBE;
            config.primary_color    = RGB_COLOR_RED;
            config.speed_ms         = 200;
            config.brightness       = 255;
            config.repeat           = true;
            break;
            
        default:
            return ESP_ERR_INVALID_ARG;
    }
    
    return rgb_led_start_effect(&config);
}

esp_err_t rgb_led_set_mqtt_relay_status(bool mqtt_connected, bool relay_on)
{
    rgb_status_t status;
    
    if (!mqtt_connected) {
        return ESP_ERR_INVALID_STATE;
    }
    
    if (relay_on) {
        status = RGB_STATUS_MQTT_RELAY_ON;  // Green
    } else {
        status = RGB_STATUS_MQTT_RELAY_OFF; // Yellow
    }
    
    return rgb_led_set_status(status);
}

rgb_effect_config_t* rgb_led_get_current_effect(void)
{
    return effect_running ? &current_effect_config : NULL;
}

bool rgb_led_is_effect_running(void)
{
    return effect_running;
}

rgb_color_t rgb_led_hsv_to_rgb(uint16_t hue, uint8_t saturation, uint8_t value)
{
    rgb_color_t rgb = {0};
    
    if (saturation == 0) {
        rgb.red = rgb.green = rgb.blue = value;
        return rgb;
    }
    
    uint8_t region = hue / 43;
    uint8_t remainder = (hue - (region * 43)) * 6;
    
    uint8_t p = (value * (255 - saturation)) >> 8;
    uint8_t q = (value * (255 - ((saturation * remainder) >> 8))) >> 8;
    uint8_t t = (value * (255 - ((saturation * (255 - remainder)) >> 8))) >> 8;
    
    switch (region) {
        case 0:
            rgb.red = value; rgb.green = t; rgb.blue = p;
            break;
        case 1:
            rgb.red = q; rgb.green = value; rgb.blue = p;
            break;
        case 2:
            rgb.red = p; rgb.green = value; rgb.blue = t;
            break;
        case 3:
            rgb.red = p; rgb.green = q; rgb.blue = value;
            break;
        case 4:
            rgb.red = t; rgb.green = p; rgb.blue = value;
            break;
        default:
            rgb.red = value; rgb.green = p; rgb.blue = q;
            break;
    }
    
    return rgb;
}

rgb_color_t rgb_led_blend_colors(rgb_color_t color1, rgb_color_t color2, uint8_t blend_factor)
{
    rgb_color_t result;
    result.red = ((uint16_t)color1.red * (255 - blend_factor) + (uint16_t)color2.red * blend_factor) / 255;
    result.green = ((uint16_t)color1.green * (255 - blend_factor) + (uint16_t)color2.green * blend_factor) / 255;
    result.blue = ((uint16_t)color1.blue * (255 - blend_factor) + (uint16_t)color2.blue * blend_factor) / 255;
    return result;
}

esp_err_t rgb_led_set_brightness(uint8_t brightness)
{
    global_brightness = brightness;
    return ESP_OK;
}

uint8_t rgb_led_get_brightness(void)
{
    return global_brightness;
}

// Private functions
static void apply_brightness(rgb_color_t *color, uint8_t brightness)
{
    if (brightness == 255) return;
    
    color->red = ((uint16_t)color->red * brightness) / 255;
    color->green = ((uint16_t)color->green * brightness) / 255;
    color->blue = ((uint16_t)color->blue * brightness) / 255;
}

static void effect_task(void *pvParameters)
{
    uint32_t step = 0;
    TickType_t last_wake_time = xTaskGetTickCount();
    
    ESP_LOGI(TAG, "Effect task started: %d", current_effect_config.effect);
    
    while (effect_running && led_strip) {
        rgb_color_t color = {0};
        esp_err_t ret = ESP_OK;
        
        switch (current_effect_config.effect) {
            case RGB_EFFECT_SOLID:
                
                if (step == 0) {
                    color = current_effect_config.primary_color;
                    apply_brightness(&color, current_effect_config.brightness);
                    ret = led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                    if (ret == ESP_OK) {
                        ret = led_strip_refresh(led_strip);
                    }
                    if (ret != ESP_OK) {
                        ESP_LOGW(TAG, "LED strip solid set failed: %s", esp_err_to_name(ret));
                    }
                }
                vTaskDelay(pdMS_TO_TICKS(1000)); 
                break;
                
            case RGB_EFFECT_BLINK:
                if (step % 2 == 0) {
                    color = current_effect_config.primary_color;
                } else {
                    color = RGB_COLOR_OFF;
                }
                apply_brightness(&color, current_effect_config.brightness);
                ret = led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                if (ret == ESP_OK) {
                    ret = led_strip_refresh(led_strip);
                }
                if (ret != ESP_OK) {
                    ESP_LOGW(TAG, "LED strip blink failed: %s", esp_err_to_name(ret));
                }
                break;
                
            case RGB_EFFECT_BREATHE: {
                float breath        = (sin(step * 0.1) + 1.0) / 2.0; // 0 to 1
                uint8_t brightness  = (uint8_t)(breath * current_effect_config.brightness);
                color               = current_effect_config.primary_color;
                apply_brightness(&color, brightness);
                led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                led_strip_refresh(led_strip);
                break;
            }
            
            case RGB_EFFECT_RAINBOW: {
                uint16_t hue        = (step * 10) % 360;
                color               = rgb_led_hsv_to_rgb(hue, 100, current_effect_config.brightness);
                led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                led_strip_refresh(led_strip);
                break;
            }
            
            case RGB_EFFECT_PULSE: {
                float pulse         = fabs(sin(step * 0.2));
                uint8_t brightness  = (uint8_t)(pulse * current_effect_config.brightness);
                color               = current_effect_config.primary_color;
                apply_brightness(&color, brightness);
                led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                led_strip_refresh(led_strip);
                break;
            }
            
            case RGB_EFFECT_STROBE:
                if (step % 10 < 2) { 
                    color = current_effect_config.primary_color;
                    apply_brightness(&color, current_effect_config.brightness);
                } else {
                    color = RGB_COLOR_OFF;
                }
                led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                led_strip_refresh(led_strip);
                break;
                
            case RGB_EFFECT_FADE_IN_OUT: {
                uint8_t fade_step   = step % 200;
                uint8_t brightness;
                if (fade_step < 100) {
                    brightness      = (fade_step * current_effect_config.brightness) / 100;
                } else {
                    brightness      = ((200 - fade_step) * current_effect_config.brightness) / 100;
                }
                color   = current_effect_config.primary_color;
                apply_brightness(&color, brightness);
                led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                led_strip_refresh(led_strip);
                break;
            }
            
            case RGB_EFFECT_FIRE: {
                // Simulate fire with random red/orange colors
                uint8_t red = 255;
                uint8_t green   = esp_random() % 100 + 50; // 50-150
                uint8_t blue    = esp_random() % 20; // 0-20
                color.red       = red;
                color.green     = green;
                color.blue      = blue;
                apply_brightness(&color, current_effect_config.brightness);
                led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                led_strip_refresh(led_strip);
                break;
            }
            
            case RGB_EFFECT_SPARKLE:
                if (esp_random() % 10 == 0) { // Random sparkle
                    color = current_effect_config.primary_color;
                    apply_brightness(&color, current_effect_config.brightness);
                } else {
                    color = RGB_COLOR_OFF;
                }
                led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                led_strip_refresh(led_strip);
                break;
                
            default:
                color = RGB_COLOR_OFF;
                led_strip_set_pixel(led_strip, 0, color.red, color.green, color.blue);
                led_strip_refresh(led_strip);
                break;
        }
        
        step++;
        
        if (!current_effect_config.repeat && step > 100) {
            effect_running = false;
            break;
        }
        
        // Ensure minimum delay to prevent assertion failure
        uint32_t delay_ms = current_effect_config.speed_ms / 10;
        if (delay_ms == 0) {
            delay_ms = 1; // Minimum 1ms delay
        }
        vTaskDelayUntil(&last_wake_time, pdMS_TO_TICKS(delay_ms));
    }
    
    // Turn off
    led_strip_clear(led_strip);
    effect_task_handle = NULL;
    ESP_LOGI(TAG, "Effect task ended");
    vTaskDelete(NULL);
} 