idf_component_register(SRCS "esp-app.c"
                           "wifi_manager.c"
                           "mqtt_client.c"
                           "relay_control.c"
                    INCLUDE_DIRS "." "includes"
                    REQUIRES esp_wifi esp_netif nvs_flash
                    PRIV_REQUIRES mqtt esp_driver_gpio)
