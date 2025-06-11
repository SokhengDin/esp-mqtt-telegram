idf_component_register(SRCS "esp-app.c"
                           "wifi_manager.c"
                           "mqtt_client.c"
                           "relay_control.c"
                           "rgb_led_manager.c"
                    INCLUDE_DIRS "." "includes"
                    REQUIRES esp_wifi esp_netif nvs_flash led_strip
                    PRIV_REQUIRES mqtt esp_driver_gpio)
