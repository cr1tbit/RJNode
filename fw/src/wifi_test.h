#pragma once

#include "esp_http_server.h"

// Call after NVS, esp_netif and the default event loop have been initialized.
void wifi_test_init(void);
void wifi_test_register_routes(httpd_handle_t server);
