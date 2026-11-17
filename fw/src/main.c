#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "board.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_eth.h"
#include "esp_eth_mac_ch390.h"
#include "esp_eth_phy_ch390.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "wifi_test.h"

static const char *TAG = "rjnode";
static const gpio_num_t relay_pins[] = {RELAY1_GPIO, RELAY2_GPIO};
// Only the HTTP server task reads/writes relay state after startup.
static bool relay_on[2];
static int64_t last_energized_us = -RELAY_ON_GAP_US;
extern const char index_html_start[] asm("_binary_index_html_start");

static void init_outputs(void)
{
    // Preload LOW before enabling outputs; board base pull-downs hold OFF at reset.
    for (size_t i = 0; i < 2; ++i) {
        ESP_ERROR_CHECK(gpio_set_level(relay_pins[i], 0));
        ESP_ERROR_CHECK(gpio_set_direction(relay_pins[i], GPIO_MODE_OUTPUT));
    }
    ESP_ERROR_CHECK(gpio_set_level(STATUS_LED_GPIO, 1));
    ESP_ERROR_CHECK(gpio_set_direction(STATUS_LED_GPIO, GPIO_MODE_OUTPUT));
}

static void set_relay(unsigned index, bool on)
{
    if (relay_on[index] == on) {
        return;
    }
    if (on) {
        // Global gap covers different channels and rapid OFF/ON requests alike.
        int64_t remaining;
        while ((remaining = RELAY_ON_GAP_US -
                            (esp_timer_get_time() - last_energized_us)) > 0) {
            vTaskDelay(pdMS_TO_TICKS((remaining + 999) / 1000) + 1);
        }
    }
    ESP_ERROR_CHECK(gpio_set_level(relay_pins[index], on ? 1 : 0));
    relay_on[index] = on;
    if (on) {
        last_energized_us = esp_timer_get_time();
    }
    ESP_LOGI(TAG, "Relay %u %s", index + 1, on ? "ON" : "OFF");
}

static esp_err_t send_state(httpd_req_t *req)
{
    char body[64];
    snprintf(body, sizeof(body), "{\"relays\":[%s,%s]}",
             relay_on[0] ? "true" : "false", relay_on[1] ? "true" : "false");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, body);
}

static esp_err_t index_handler(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, index_html_start);
}

static esp_err_t relay_handler(httpd_req_t *req)
{
    // Explicit state rather than a toggle: repeating a request is harmless.
    // A custom header blocks cross-origin HTML forms; CORS is not enabled.
    char header[8];
    if (httpd_req_get_hdr_value_str(req, "X-RJNode-Control", header, sizeof(header)) != ESP_OK ||
        strcmp(header, "1") != 0) {
        return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Missing control header");
    }
    if (req->content_len != 1) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Body must be 0 or 1");
    }
    char state;
    int received = httpd_req_recv(req, &state, 1);
    if (received <= 0) {
        if (received == HTTPD_SOCK_ERR_TIMEOUT) {
            httpd_resp_send_err(req, HTTPD_408_REQ_TIMEOUT, "Request timed out");
        }
        return ESP_FAIL;
    }
    if (state != '0' && state != '1') {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Body must be 0 or 1");
    }
    unsigned index = (unsigned)(uintptr_t)req->user_ctx;
    set_relay(index, state == '1');
    return send_state(req);
}

static void start_web_server(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.lru_purge_enable = true;
    httpd_handle_t server = NULL;
    ESP_ERROR_CHECK(httpd_start(&server, &config));
    const httpd_uri_t routes[] = {
        {.uri = "/", .method = HTTP_GET, .handler = index_handler},
        {.uri = "/api/relays", .method = HTTP_GET, .handler = send_state},
        {.uri = "/api/relays/1", .method = HTTP_POST, .handler = relay_handler, .user_ctx = (void *)0},
        {.uri = "/api/relays/2", .method = HTTP_POST, .handler = relay_handler, .user_ctx = (void *)1},
    };
    for (size_t i = 0; i < sizeof(routes) / sizeof(routes[0]); ++i) {
        ESP_ERROR_CHECK(httpd_register_uri_handler(server, &routes[i]));
    }
    wifi_test_register_routes(server);
}

static void network_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == IP_EVENT && id == IP_EVENT_ETH_GOT_IP) {
        const ip_event_got_ip_t *event = data;
        ESP_LOGI(TAG, "Open http://" IPSTR "/", IP2STR(&event->ip_info.ip));
        gpio_set_level(STATUS_LED_GPIO, 0);
    } else if (base == ETH_EVENT && id == ETHERNET_EVENT_DISCONNECTED) {
        ESP_LOGI(TAG, "Ethernet disconnected");
        gpio_set_level(STATUS_LED_GPIO, 1);
    } else if (base == IP_EVENT && id == IP_EVENT_ETH_LOST_IP) {
        gpio_set_level(STATUS_LED_GPIO, 1);
    }
}

static void start_ethernet(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_config_t netif_config = ESP_NETIF_DEFAULT_ETH();
    esp_netif_t *netif = esp_netif_new(&netif_config);
    ESP_ERROR_CHECK(netif ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_ERROR_CHECK(esp_netif_set_hostname(netif, "rjnode"));

    ESP_ERROR_CHECK(gpio_install_isr_service(0));
    spi_bus_config_t bus = {
        .mosi_io_num = ETH_MOSI_GPIO,
        .miso_io_num = ETH_MISO_GPIO,
        .sclk_io_num = ETH_SCK_GPIO,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));
    // Explicit reset meets CH390D timing even with older PHY driver defaults.
    ESP_ERROR_CHECK(gpio_set_level(ETH_RST_GPIO, 0));
    ESP_ERROR_CHECK(gpio_set_direction(ETH_RST_GPIO, GPIO_MODE_OUTPUT));
    vTaskDelay(pdMS_TO_TICKS(10) + 1);
    ESP_ERROR_CHECK(gpio_set_level(ETH_RST_GPIO, 1));
    vTaskDelay(pdMS_TO_TICKS(30) + 1);

    spi_device_interface_config_t device = {
        .mode = 0,
        .clock_speed_hz = ETH_SPI_CLOCK_HZ,
        .spics_io_num = ETH_CS_GPIO,
        .queue_size = 16,
    };
    eth_ch390_config_t ch390 = ETH_CH390_DEFAULT_CONFIG(SPI2_HOST, &device);
    ch390.int_gpio_num = ETH_INT_GPIO;
    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    mac_config.rx_task_stack_size = 4096;
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    phy_config.phy_addr = 1;
    phy_config.reset_gpio_num = -1; // Reset already performed above.
    esp_eth_mac_t *mac = esp_eth_mac_new_ch390(&ch390, &mac_config);
    esp_eth_phy_t *phy = esp_eth_phy_new_ch390(&phy_config);
    ESP_ERROR_CHECK(mac && phy ? ESP_OK : ESP_ERR_NO_MEM);
    esp_eth_config_t eth_config = ETH_DEFAULT_CONFIG(mac, phy);
    esp_eth_handle_t handle = NULL;
    ESP_ERROR_CHECK(esp_eth_driver_install(&eth_config, &handle));
    esp_eth_netif_glue_handle_t glue = esp_eth_new_netif_glue(handle);
    ESP_ERROR_CHECK(glue ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_ERROR_CHECK(esp_netif_attach(netif, glue));
    ESP_ERROR_CHECK(esp_event_handler_register(ETH_EVENT, ESP_EVENT_ANY_ID, network_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_GOT_IP, network_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_LOST_IP, network_event, NULL));
    ESP_ERROR_CHECK(esp_eth_start(handle));
}

void app_main(void)
{
    init_outputs();
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    start_ethernet();
    wifi_test_init();
    start_web_server();
    ESP_LOGI(TAG, "Ready; relays OFF. Waiting for Ethernet DHCP.");
}
