#pragma once

// RJNode U1, ESP32-C3-WROOM-02-N4; handover.md section 13.2.
#define RELAY1_GPIO 4
#define RELAY2_GPIO 5
#define STATUS_LED_GPIO 8  // Active low; do not drive until after boot straps.
#define ETH_SCK_GPIO 6
#define ETH_MOSI_GPIO 7
#define ETH_MISO_GPIO 3
#define ETH_CS_GPIO 10
#define ETH_INT_GPIO 1
#define ETH_RST_GPIO 0
#define ETH_SPI_CLOCK_HZ (8 * 1000 * 1000)
#define RELAY_ON_GAP_US 100000
