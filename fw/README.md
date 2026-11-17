# RJNode firmware

PlatformIO + ESP-IDF firmware for the **ESP32-C3-WROOM-02-N4** on
`RJNode.kicad_pcb`. The ESP hosts a self-contained page for controlling the two
relays over the board's **CH390D Ethernet** interface, with optional Wi-Fi for
range testing. No external web assets, filesystem upload, or cloud service are
needed. Wi-Fi stays off until configured; BLE is not initialized.

## Build and flash

Install PlatformIO Core or the PlatformIO extension for VS Code, then run from
this directory:

```sh
pio run
pio run -t upload --upload-port /dev/ttyACM0
pio device monitor --port /dev/ttyACM0
```

Use the serial port reported on your machine. The first build needs internet
access to download the pinned pioarduino platform, ESP-IDF, toolchain, and
[Espressif CH390 driver](https://components.espressif.com/components/espressif/ch390/versions/0.4.1/readme).
The DevKitM PlatformIO board profile supplies the ESP32-C3/4 MB flash settings;
all application GPIOs are assigned explicitly for this custom PCB in
[`src/board.h`](src/board.h).

Programming and logs use the native USB-C interface (GPIO18/19). If the device
does not initially enumerate, hold BOOT while powering it up, release BOOT, and
flash. Power-cycle after the first flash if it stays in download mode.

Connect Ethernet to a network with a DHCP server. The USB serial log prints:

```text
Open http://192.168.x.x/
```

Open that address in a browser. The DHCP hostname is `rjnode`; the router's lease
table is another way to find it. This firmware does not provide mDNS or a Wi-Fi
access point. The active-low status LED lights when Ethernet obtains an IP and
turns off on disconnection or IP loss.

## Wi-Fi range testing

Open the page over Ethernet and use **Wi-Fi range test** to enter a 2.4 GHz
SSID and password, then choose **Save & connect**. WPA2/WPA3 Personal and open
networks are supported; enterprise credentials and captive portal login are
not provided. Passwords are never returned by the API or printed by the
application. They are stored in the board's unencrypted NVS flash and sent
over local HTTP, so configure it on a trusted network.

The page shows the assigned Wi-Fi IP, RSSI in dBm, channel, connected duration,
and disconnection count. Click the Wi-Fi IP to open a new page, confirm
**This page uses: Wi-Fi**, and unplug Ethernet while leaving USB power
connected. Move the board through the test locations. Watch signal strength,
HTTP round-trip time, and failed polls, and optionally ping the Wi-Fi IP from
a computer on the same network. These round trips measure small HTTP requests,
not maximum throughput; browser background throttling can affect polling.

Wi-Fi reconnects after a lost link and restores saved credentials after a
power cycle. Power saving is disabled consistently for this test firmware.
The disconnect counter resets on reboot or reconfiguration; failed status
polls count only in the current browser tab. The status LED still indicates
Ethernet, so use the page for Wi-Fi status.

**Disable Wi-Fi & forget** stops and deinitializes the radio and removes the
saved credential key. Access through Wi-Fi will drop when this completes;
reconnect Ethernet to confirm it. Removing the NVS key is logical deletion,
not a forensic erase of flash. With no saved credentials, subsequent boots
leave the radio uninitialized.

`GET /api/wifi` returns status without the password. `POST /api/wifi` accepts
JSON `{"ssid":"...","password":"..."}` or `{"forget":true}`, with the same
`X-RJNode-Control: 1` header as relay commands. Configuration is asynchronous:
HTTP 202 means queued; poll GET for the resulting state or error.

## Relay behavior

| Output | GPIO | Energized level |
| --- | --- | --- |
| Relay 1 | 4 | HIGH |
| Relay 2 | 5 | HIGH |

Both relays initialize **OFF** before networking starts and always return OFF
after reset or power loss. The PCB's driver base pull-downs hold them OFF while
the MCU resets. No relay state is saved to flash. All OFF-to-ON transitions are
separated by at least **100 ms**, including requests from different browsers,
to meet the main fuse inrush constraint (one channel's inrush at a time). The server serializes
relay commands and responds after applying the requested state.

The UI polls every two seconds and reports the commanded GPIO states; there is
no contact feedback. Relays retain their last commanded state when Ethernet or
the browser disconnects. BOOT remains a programming button and does not toggle
either relay.

## HTTP API

```sh
# Read both states: {"relays":[false,false]}
curl http://192.168.x.x/api/relays

# Turn relay 1 on (use /2 for relay 2 and body 0 for off)
curl -X POST http://192.168.x.x/api/relays/1 \
  -H 'X-RJNode-Control: 1' -H 'Content-Type: text/plain' --data-binary '1'
```

Only POST requests with a one-byte `0` or `1` body and the control header change
outputs. This also prevents ordinary cross-origin web forms from switching
relays. The bootstrap server uses HTTP without authentication and is intended
for a trusted local network.

## Hardware bring-up

Initially power from USB with the mains input and relay loads disconnected.
Verify that both relays stay OFF during startup/reset, that each web control
switches the corresponding relay, and that state updates appear in a second
browser. Check Ethernet disconnect/reconnect and confirm that reboot returns
both relays OFF. Verify the 100 ms activation spacing with a logic analyzer on
GPIO4/5 while issuing consecutive ON commands.

Firmware builds and physical bring-up are separate checks: a successful compile
does not verify the PCB, relay contacts, or Ethernet link.

Browser behavior tests (requires Node.js):

```sh
node --test test/ui.test.cjs
```
