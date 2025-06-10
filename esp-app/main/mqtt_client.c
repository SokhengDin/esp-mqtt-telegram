#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <inttypes.h>
#include "esp_system.h"
#include "esp_log.h"
#include "esp_event.h"
#include "mqtt_client.h"
#include "includes/mqtt_manager.h"
#include "includes/relay_control.h"

static const char *TAG = "MQTT_CLIENT";

static esp_mqtt_client_handle_t s_mqtt_client = NULL;
static mqtt_state_t s_mqtt_state = MQTT_STATE_DISCONNECTED;

// Function prototypes
extern void status_led_set_mqtt_state(mqtt_state_t state);

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    ESP_LOGD(TAG, "Event dispatched from event loop base=%s, event_id=%" PRIi32, base, event_id);
    esp_mqtt_event_handle_t event = event_data;
    esp_mqtt_client_handle_t client = event->client;
    int msg_id;
    
    switch ((esp_mqtt_event_id_t)event_id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT_EVENT_CONNECTED");
            s_mqtt_state = MQTT_STATE_CONNECTED;
            status_led_set_mqtt_state(s_mqtt_state);
            
            // Subscribe to relay control topic
            char subscribe_topic[64];
            snprintf(subscribe_topic, sizeof(subscribe_topic), "%s/relay/set", CONFIG_DEVICE_ID);
            msg_id = esp_mqtt_client_subscribe(client, subscribe_topic, 0);
            ESP_LOGI(TAG, "sent subscribe successful, msg_id=%d to topic: %s", msg_id, subscribe_topic);
            
            // Publish online status
            char status_topic[64];
            snprintf(status_topic, sizeof(status_topic), "%s/status", CONFIG_DEVICE_ID);
            msg_id = esp_mqtt_client_publish(client, status_topic, "online", 0, 1, 1);
            ESP_LOGI(TAG, "sent publish successful, msg_id=%d", msg_id);
            break;

        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGI(TAG, "MQTT_EVENT_DISCONNECTED");
            s_mqtt_state = MQTT_STATE_DISCONNECTED;
            status_led_set_mqtt_state(s_mqtt_state);
            esp_mqtt_client_reconnect(client);
            break;

        case MQTT_EVENT_SUBSCRIBED:
            ESP_LOGI(TAG, "MQTT_EVENT_SUBSCRIBED, msg_id=%d", event->msg_id);
            break;

        case MQTT_EVENT_PUBLISHED:
            ESP_LOGI(TAG, "MQTT_EVENT_PUBLISHED, msg_id=%d", event->msg_id);
            break;

        case MQTT_EVENT_DATA:
            ESP_LOGI(TAG, "MQTT_EVENT_DATA");
            printf("TOPIC=%.*s\r\n", event->topic_len, event->topic);
            printf("DATA=%.*s\r\n", event->data_len, event->data);
            
            // Process received message - check if this is relay control
            char expected_topic[64];
            snprintf(expected_topic, sizeof(expected_topic), "%s/relay/set", CONFIG_DEVICE_ID);
            
            if (strncmp(event->topic, expected_topic, event->topic_len) == 0) {
                int newState = strncmp(event->data, "on", event->data_len) == 0 ? 1 : 0;
                relay_state_t relay_state = newState ? RELAY_STATE_ON : RELAY_STATE_OFF;
                
                if (relay_control_get_state() != relay_state) {
                    relay_control_set_state(relay_state);
                    const char *payload = newState ? "on" : "off";
                    
                    ESP_LOGI(TAG, "Relay state changed to: %s", payload);
                    
                    // Publish confirmation
                    char state_topic[64];
                    snprintf(state_topic, sizeof(state_topic), "%s/relay/state", CONFIG_DEVICE_ID);
                    esp_mqtt_client_publish(client, state_topic, payload, 0, 1, 0);
                }
            }
            break;

        case MQTT_EVENT_ERROR:
            ESP_LOGI(TAG, "MQTT_EVENT_ERROR");
            s_mqtt_state = MQTT_STATE_ERROR;
            status_led_set_mqtt_state(s_mqtt_state);
            
            if (event->error_handle->error_type == MQTT_ERROR_TYPE_TCP_TRANSPORT) {
                ESP_LOGI(TAG, "Last error code reported from esp-tls: 0x%x", event->error_handle->esp_tls_last_esp_err);
                ESP_LOGI(TAG, "Last tls stack error number: 0x%x", event->error_handle->esp_tls_stack_err);
                ESP_LOGI(TAG, "Last captured errno : %d (%s)",  event->error_handle->esp_transport_sock_errno,
                         strerror(event->error_handle->esp_transport_sock_errno));
            } else if (event->error_handle->error_type == MQTT_ERROR_TYPE_CONNECTION_REFUSED) {
                ESP_LOGI(TAG, "Connection refused error: 0x%x", event->error_handle->connect_return_code);
            } else {
                ESP_LOGW(TAG, "Unknown error type: 0x%x", event->error_handle->error_type);
            }
            break;

        default:
            ESP_LOGI(TAG, "Other event id:%d", event->event_id);
            break;
    }
}

esp_err_t mqtt_client_init(void)
{
    ESP_LOGI(TAG, "Initializing MQTT client");
    
    // Configure MQTT client using the exact working structure from user's code
    const esp_mqtt_client_config_t mqtt_cfg = {
        .broker = {
            .address.uri = CONFIG_MQTT_BROKER_URI,
        },
        .credentials = {
            .username = CONFIG_MQTT_USERNAME,
            .authentication.password = CONFIG_MQTT_PASSWORD,
        }
    };

    s_mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (s_mqtt_client == NULL) {
        ESP_LOGE(TAG, "Failed to initialize MQTT client");
        return ESP_FAIL;
    }

    esp_mqtt_client_register_event(s_mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);

    ESP_LOGI(TAG, "MQTT client initialized successfully");
    return ESP_OK;
}

esp_err_t mqtt_client_start(void)
{
    if (s_mqtt_client == NULL) {
        ESP_LOGE(TAG, "MQTT client not initialized");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Starting MQTT client");
    s_mqtt_state = MQTT_STATE_CONNECTING;
    status_led_set_mqtt_state(s_mqtt_state);

    return esp_mqtt_client_start(s_mqtt_client);
}

esp_err_t mqtt_client_stop(void)
{
    if (s_mqtt_client == NULL) {
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Stopping MQTT client");
    esp_err_t err = esp_mqtt_client_stop(s_mqtt_client);
    s_mqtt_state = MQTT_STATE_DISCONNECTED;
    status_led_set_mqtt_state(s_mqtt_state);

    return err;
}

esp_err_t mqtt_publish_message(const char *topic, const char *data, int qos, int retain)
{
    if (s_mqtt_client == NULL || s_mqtt_state != MQTT_STATE_CONNECTED) {
        ESP_LOGW(TAG, "MQTT client not connected");
        return ESP_FAIL;
    }

    int msg_id = esp_mqtt_client_publish(s_mqtt_client, topic, data, 0, qos, retain);
    if (msg_id == -1) {
        ESP_LOGE(TAG, "Failed to publish message to topic: %s", topic);
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Published message to %s: %s (msg_id=%d)", topic, data, msg_id);
    return ESP_OK;
}

esp_err_t mqtt_publish_status(void)
{
    char topic[64];
    snprintf(topic, sizeof(topic), "%s/status", CONFIG_DEVICE_ID);
    return mqtt_publish_message(topic, "online", 1, 1);
}

esp_err_t mqtt_publish_relay_state(relay_state_t state)
{
    char topic[64];
    snprintf(topic, sizeof(topic), "%s/relay/state", CONFIG_DEVICE_ID);
    const char *state_str = (state == RELAY_STATE_ON) ? "on" : "off";
    return mqtt_publish_message(topic, state_str, 1, 1);
}

mqtt_state_t mqtt_client_get_state(void)
{
    return s_mqtt_state;
} 