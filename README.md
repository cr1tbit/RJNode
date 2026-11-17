# RJNode

ESP32-C3 Ethernet relay node (2 relays, CH390D Ethernet).

> [!WARNING]
> **This board runs on 230 V AC mains, which can kill.** Mains voltage is present on the
> input terminal, both fuses, the MOV, the AC/DC module primary, the relays and all output
> terminals whenever the board is connected, even with both relays OFF.
>
> - Only a qualified electrician, or someone competent to work on mains, should build, install or service it.
> - Disconnect and isolate the supply, and verify it is dead, before touching the board or the wiring.
> - Never operate it on mains without the enclosure fitted. Do not touch the PCB, USB-C or
>   programming header while mains is connected. For firmware work, power it from USB only, with mains disconnected.
> - This design has **not been certified or safety-tested**. Its AC/DC module
>   (HLK-5M05) gives only about basic insulation; the RJ45 magnetics are an informal second barrier.
>   It is meant for internal or trial use, inside a closed enclosure, behind a circuit breaker.
>
> You build and use this design at your own risk.

## Power rating

**Proposed rating (not yet validated on hardware): 230 V~ 50 Hz, max 250 W per channel, 500 W total.**

| Parameter | Value |
| --- | --- |
| Supply | 230 V AC, 50 Hz (the AC/DC module accepts 85–264 V AC) |
| Load per channel | ≤ 250 W (≈ 1.2 A at PF 0.9) |
| Total input current | ≤ 2.4 A (main fuse: T4A, 1500 A breaking) |
| LED drivers | ≤ 4 per channel, cold-start inrush ≤ 50 A / 250 µs each |
| Outputs | 2 × changeover (NO/NC), neutral passes through. No PE on the PCB; join PE outside the board |
| Insulation class | Class II (no protective earth) |
| Device consumption | ≤ 5 W (5 V / 1 A AC/DC module) |

Notes:

- **The limit is set by the fuse and the inrush, not by the relays or terminals.** The SRD relays are
  10 A parts derated to about 5 A resistive, and the terminals are rated 16 A / 300 V. The main
  fuse sizing and the inrush budget only cover the figures above. Do not fit a larger fuse to
  get more power.
- **Inrush depends on the number of drivers, not on wattage.** Check each LED driver's datasheet
  against the inrush limit. Cheap drivers without an NTC can exceed it.
- **The firmware never switches both relays at the same instant** (≥ 100 ms apart), so the main fuse sees only one channel's inrush at a time.
- **Large motors, compressors and capacitive loads are not covered** by this rating.
- **Still to verify:** a full-load thermal run (terminal, trace and fuse temperatures inside the
  closed enclosure) and an inrush measurement with the real load.

## Repository layout

| Path | Contents |
| --- | --- |
| `RJNode.kicad_*` | KiCad project: schematic, PCB, custom design rules (`.kicad_dru`) |
| `RJNode-schematic.pdf` | Schematic export |
| `tools/` | KiCad helper scripts (net classes + DRU rules, 3D model assignment) |
| `jlcpcb/` | Fabrication output (gerbers, BOM, CPL) |
| `fw/` | PlatformIO / ESP-IDF firmware — see [fw/README.md](fw/README.md) |
| `3d/` | Enclosure CAD, exports and generators — see [3d/README.md](3d/README.md) |

Regenerate the schematic PDF:

```sh
kicad-cli sch export pdf -o RJNode-schematic.pdf RJNode.kicad_sch
```
