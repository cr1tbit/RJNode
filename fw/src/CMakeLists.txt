idf_component_register(
    SRCS "main.c" "wifi_test.c"
    INCLUDE_DIRS "."
    EMBED_TXTFILES "index.html"
    REQUIRES esp_driver_gpio esp_driver_spi esp_eth esp_netif esp_event
             esp_http_server esp_timer nvs_flash espressif__ch390 esp_wifi json
)
