#include <stdio.h>
#include <string.h>
#include <sys/socket.h>

#include "cJSON.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"
#include "wifi_test.h"

typedef struct {
    char ssid[33];
    char password[65];
} credentials_t;

typedef struct {
    bool forget;
    credentials_t credentials;
} command_t;

typedef struct {
    bool enabled;
    bool configured;
    char ssid[33];
    const char *state;
    const char *error;
    esp_ip4_addr_t ip;
    uint32_t disconnects;
    uint8_t reason;
    int64_t connected_at;
    int64_t retry_at;
} status_t;

static const char *TAG = "wifi_test";
static SemaphoreHandle_t status_lock;
static QueueHandle_t commands;
static esp_netif_t *wifi_netif;
static status_t status = {.state = "disabled", .error = ""};
// Only the worker task starts/stops/configures the Wi-Fi driver and writes NVS.
static bool driver_initialized;
static bool driver_started;

static void set_error(esp_err_t err)
{
    xSemaphoreTake(status_lock, portMAX_DELAY);
    status.error = esp_err_to_name(err);
    status.state = "error";
    xSemaphoreGive(status_lock);
    ESP_LOGW(TAG, "Wi-Fi operation failed: %s", esp_err_to_name(err));
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    xSemaphoreTake(status_lock, portMAX_DELAY);
    if (status.enabled) {
        if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
            status.retry_at = esp_timer_get_time();
        } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_CONNECTED) {
            status.state = "getting_ip";
            status.retry_at = 0;
        } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
            const wifi_event_sta_disconnected_t *event = data;
            status.ip.addr = 0;
            status.connected_at = 0;
            status.state = "retrying";
            status.reason = event->reason;
            status.disconnects++;
            status.retry_at = esp_timer_get_time() + 3000000;
        } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
            const ip_event_got_ip_t *event = data;
            status.ip = event->ip_info.ip;
            status.state = "connected";
            status.error = "";
            status.connected_at = esp_timer_get_time();
            status.retry_at = 0;
            ESP_LOGI(TAG, "Wi-Fi ready: http://" IPSTR "/", IP2STR(&status.ip));
        } else if (base == IP_EVENT && id == IP_EVENT_STA_LOST_IP) {
            status.ip.addr = 0;
            status.connected_at = 0;
            status.state = "getting_ip";
        }
    }
    xSemaphoreGive(status_lock);
}

static esp_err_t save_credentials(const credentials_t *credentials)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open("wifi_test", NVS_READWRITE, &handle);
    if (err != ESP_OK) return err;
    if (credentials) {
        err = nvs_set_blob(handle, "credentials", credentials, sizeof(*credentials));
    } else {
        err = nvs_erase_key(handle, "credentials");
        if (err == ESP_ERR_NVS_NOT_FOUND) err = ESP_OK;
    }
    if (err == ESP_OK) err = nvs_commit(handle);
    nvs_close(handle);
    return err;
}

static esp_err_t stop_wifi(void)
{
    xSemaphoreTake(status_lock, portMAX_DELAY);
    status.enabled = false; // Suppress retries and late events while stopping.
    status.ip.addr = 0;
    status.connected_at = 0;
    status.retry_at = 0;
    status.state = "disabled";
    xSemaphoreGive(status_lock);
    if (driver_started) {
        esp_err_t err = esp_wifi_stop();
        if (err != ESP_OK) return err;
        driver_started = false;
    }
    if (driver_initialized) {
        esp_err_t err = esp_wifi_deinit();
        if (err != ESP_OK) return err;
        driver_initialized = false;
    }
    return ESP_OK;
}

static esp_err_t start_wifi(const credentials_t *credentials)
{
    if (!wifi_netif) {
        wifi_netif = esp_netif_create_default_wifi_sta();
        if (!wifi_netif) return ESP_ERR_NO_MEM;
        ESP_ERROR_CHECK(esp_netif_set_hostname(wifi_netif, "rjnode-wifi"));
    }
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    esp_err_t err = esp_wifi_init(&init);
    if (err != ESP_OK) return err;
    driver_initialized = true;
    // Credentials live only in our own NVS key, so Forget can remove all of them.
    err = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (err != ESP_OK) return err;
    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) return err;
    wifi_config_t config = {0};
    memcpy(config.sta.ssid, credentials->ssid, strlen(credentials->ssid));
    memcpy(config.sta.password, credentials->password, strlen(credentials->password));
    config.sta.threshold.authmode = credentials->password[0] ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    config.sta.pmf_cfg.capable = true;
    config.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    err = esp_wifi_set_config(WIFI_IF_STA, &config);
    if (err != ESP_OK) return err;
    xSemaphoreTake(status_lock, portMAX_DELAY);
    status.enabled = true;
    status.state = "connecting";
    status.error = "";
    status.reason = 0;
    status.disconnects = 0;
    strlcpy(status.ssid, credentials->ssid, sizeof(status.ssid));
    xSemaphoreGive(status_lock);
    err = esp_wifi_start();
    if (err != ESP_OK) return err;
    driver_started = true;
    // Fixed test setting, independent of whether Ethernet is plugged in.
    return esp_wifi_set_ps(WIFI_PS_NONE);
}

static void apply_command(const command_t *command)
{
    esp_err_t err = stop_wifi();
    if (err != ESP_OK) {
        set_error(err);
        return;
    }
    err = save_credentials(command->forget ? NULL : &command->credentials);
    if (err != ESP_OK) {
        set_error(err);
        return;
    }
    xSemaphoreTake(status_lock, portMAX_DELAY);
    status.configured = !command->forget;
    status.ssid[0] = 0;
    status.error = "";
    status.reason = 0;
    status.disconnects = 0;
    xSemaphoreGive(status_lock);
    if (!command->forget) {
        err = start_wifi(&command->credentials);
        if (err != ESP_OK) {
            stop_wifi();
            set_error(err);
        }
    }
}

static void wifi_worker(void *arg)
{
    // Restore credentials without rewriting flash on every boot.
    credentials_t saved = {0};
    nvs_handle_t handle;
    if (nvs_open("wifi_test", NVS_READONLY, &handle) == ESP_OK) {
        size_t length = sizeof(saved);
        esp_err_t err = nvs_get_blob(handle, "credentials", &saved, &length);
        nvs_close(handle);
        if (err == ESP_OK && length == sizeof(saved) && saved.ssid[0] &&
            saved.ssid[32] == 0 && saved.password[64] == 0) {
            xSemaphoreTake(status_lock, portMAX_DELAY);
            status.configured = true;
            xSemaphoreGive(status_lock);
            err = start_wifi(&saved);
            if (err != ESP_OK) {
                stop_wifi();
                set_error(err);
            }
        }
    }
    memset(&saved, 0, sizeof(saved));
    for (;;) {
        command_t command;
        if (xQueueReceive(commands, &command, pdMS_TO_TICKS(500)) == pdTRUE) {
            apply_command(&command);
            memset(&command, 0, sizeof(command));
        }
        xSemaphoreTake(status_lock, portMAX_DELAY);
        bool retry = status.enabled && status.retry_at && esp_timer_get_time() >= status.retry_at;
        if (retry) {
            status.retry_at = 0;
            status.state = "connecting";
        }
        xSemaphoreGive(status_lock);
        if (retry) {
            esp_err_t err = esp_wifi_connect();
            if (err != ESP_OK) {
                set_error(err);
                xSemaphoreTake(status_lock, portMAX_DELAY);
                status.retry_at = esp_timer_get_time() + 3000000;
                xSemaphoreGive(status_lock);
            }
        }
    }
}

static esp_err_t status_handler(httpd_req_t *req)
{
    xSemaphoreTake(status_lock, portMAX_DELAY);
    status_t snapshot = status;
    xSemaphoreGive(status_lock);
    wifi_ap_record_t ap;
    bool associated = snapshot.enabled && esp_wifi_sta_get_ap_info(&ap) == ESP_OK;
    struct sockaddr_storage local = {0};
    socklen_t length = sizeof(local);
    bool via_wifi = getsockname(httpd_req_to_sockfd(req), (struct sockaddr *)&local, &length) == 0 &&
                    local.ss_family == AF_INET && snapshot.ip.addr &&
                    ((struct sockaddr_in *)&local)->sin_addr.s_addr == snapshot.ip.addr;
    char ip[16];
    snprintf(ip, sizeof(ip), IPSTR, IP2STR(&snapshot.ip));
    cJSON *json = cJSON_CreateObject();
    if (!json) return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Out of memory");
    cJSON_AddBoolToObject(json, "enabled", snapshot.enabled);
    cJSON_AddBoolToObject(json, "configured", snapshot.configured);
    cJSON_AddStringToObject(json, "state", snapshot.state);
    cJSON_AddStringToObject(json, "ssid", snapshot.ssid);
    cJSON_AddStringToObject(json, "ip", snapshot.ip.addr ? ip : "");
    cJSON_AddBoolToObject(json, "via_wifi", via_wifi);
    if (associated) {
        cJSON_AddNumberToObject(json, "rssi_dbm", ap.rssi);
        cJSON_AddNumberToObject(json, "channel", ap.primary);
    } else {
        cJSON_AddNullToObject(json, "rssi_dbm");
        cJSON_AddNullToObject(json, "channel");
    }
    cJSON_AddNumberToObject(json, "disconnects", snapshot.disconnects);
    cJSON_AddNumberToObject(json, "last_disconnect_reason", snapshot.reason);
    cJSON_AddStringToObject(json, "error", snapshot.error);
    cJSON_AddNumberToObject(json, "connected_s", snapshot.connected_at ?
                           (esp_timer_get_time() - snapshot.connected_at) / 1000000 : 0);
    char *body = cJSON_PrintUnformatted(json);
    cJSON_Delete(json);
    if (!body) return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Out of memory");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t err = httpd_resp_sendstr(req, body);
    cJSON_free(body);
    return err;
}

static bool valid_password(const char *password)
{
    size_t length = strlen(password);
    if (length == 0 || (length >= 8 && length <= 63)) return true;
    if (length != 64) return false;
    return strspn(password, "0123456789abcdefABCDEF") == 64;
}

static esp_err_t config_handler(httpd_req_t *req)
{
    char header[8];
    if (httpd_req_get_hdr_value_str(req, "X-RJNode-Control", header, sizeof(header)) != ESP_OK ||
        strcmp(header, "1")) {
        return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Missing control header");
    }
    if (req->content_len < 2 || req->content_len > 512) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Expected JSON, at most 512 bytes");
    }
    char body[513];
    size_t received = 0;
    while (received < req->content_len) {
        int count = httpd_req_recv(req, body + received, req->content_len - received);
        if (count <= 0) {
            httpd_resp_send_err(req, HTTPD_408_REQ_TIMEOUT, "Incomplete request");
            memset(body, 0, sizeof(body));
            return ESP_FAIL;
        }
        received += count;
    }
    body[received] = 0;
    cJSON *json = cJSON_ParseWithOpts(body, NULL, true);
    memset(body, 0, sizeof(body));
    if (!cJSON_IsObject(json)) {
        cJSON_Delete(json);
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON object");
    }
    command_t command = {0};
    command.forget = cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "forget"));
    if (!command.forget) {
        const cJSON *ssid = cJSON_GetObjectItemCaseSensitive(json, "ssid");
        const cJSON *password = cJSON_GetObjectItemCaseSensitive(json, "password");
        if (!cJSON_IsString(ssid) || !cJSON_IsString(password) ||
            strlen(ssid->valuestring) < 1 || strlen(ssid->valuestring) > 32 ||
            !valid_password(password->valuestring)) {
            cJSON_Delete(json);
            return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST,
                "SSID: 1-32 bytes; password: 8-63 bytes, 64 hex digits, or empty for open Wi-Fi");
        }
        strlcpy(command.credentials.ssid, ssid->valuestring, sizeof(command.credentials.ssid));
        strlcpy(command.credentials.password, password->valuestring, sizeof(command.credentials.password));
    }
    cJSON_Delete(json);
    bool queued = xQueueSend(commands, &command, 0) == pdTRUE;
    memset(&command, 0, sizeof(command));
    if (!queued) {
        httpd_resp_set_status(req, "503 Service Unavailable");
        return httpd_resp_sendstr(req, "Wi-Fi busy; retry shortly");
    }
    httpd_resp_set_status(req, "202 Accepted");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, "{\"accepted\":true}");
}

void wifi_test_init(void)
{
    status_lock = xSemaphoreCreateMutex();
    commands = xQueueCreate(2, sizeof(command_t));
    ESP_ERROR_CHECK(status_lock && commands ? ESP_OK : ESP_ERR_NO_MEM);
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_LOST_IP, wifi_event, NULL));
    ESP_ERROR_CHECK(xTaskCreate(wifi_worker, "wifi_test", 6144, NULL, 5, NULL) == pdPASS ? ESP_OK : ESP_ERR_NO_MEM);
}

void wifi_test_register_routes(httpd_handle_t server)
{
    const httpd_uri_t get = {.uri = "/api/wifi", .method = HTTP_GET, .handler = status_handler};
    const httpd_uri_t post = {.uri = "/api/wifi", .method = HTTP_POST, .handler = config_handler};
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &get));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &post));
}
