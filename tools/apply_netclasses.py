#!/usr/bin/env python3
"""Set RJNode net classes (.kicad_pro) and isolation rules (.kicad_dru).

Usage: python3 tools/apply_netclasses.py [--dru-only] [project_dir]
       (project_dir defaults to the parent of tools/)

Re-runnable; backs up what it writes. KiCad keeps net classes in memory and
rewrites .kicad_pro on save, so close the project before a full run. The
.kicad_dru is not rewritten by KiCad, so --dru-only is safe while it is open.
"""
import json, shutil, sys, time
from pathlib import Path

args = [a for a in sys.argv[1:] if not a.startswith("--")]
dru_only = "--dru-only" in sys.argv
d = Path(args[0]) if args else Path(__file__).resolve().parent.parent
pro, dru = d / "RJNode.kicad_pro", d / "RJNode.kicad_dru"
stamp = time.strftime("%Y%m%d-%H%M%S")
for f in ((dru,) if dru_only else (pro, dru)):
    shutil.copy2(f, f.with_name(f.name + f".bak-{stamp}"))


def cls(default, name, prio, track, clear, via=(0.6, 0.3), dp=(0.2, 0.25)):
    c = dict(default)
    c.update(name=name, priority=prio, track_width=track, clearance=clear,
             via_diameter=via[0], via_drill=via[1],
             diff_pair_width=dp[0], diff_pair_gap=dp[1])
    return c


if not dru_only:
    p = json.loads(pro.read_text())
    ns = p["net_settings"]
    default = next(c for c in ns["classes"] if c["name"] == "Default")
    # Lower priority number wins when a net matches several patterns.
    ns["classes"] = [
        default,
        # Load path: input L/N trunk, relay COM, NO/NC outputs, pass-through N.
        # Rated 2 x 1.2 A, 2.4 A trunk, T4A main fuse (handover 13.8).
        cls(default, "MAINS_LOAD", 0, 2.0, 2.0, via=(1.2, 0.6)),
        # PSU branch after the 0.5 A fuse, and any relay contact pad left unconnected.
        cls(default, "MAINS", 1, 1.0, 2.0, via=(1.2, 0.6)),
        cls(default, "ETH", 2, 0.25, 0.2, dp=(0.25, 0.2)),
        cls(default, "USB", 3, 0.25, 0.2, dp=(0.25, 0.2)),
        cls(default, "PWR", 4, 0.5, 0.2),
        cls(default, "GND", 5, 0.4, 0.15),
        cls(default, "EARTH", 6, 0.4, 1.0),
    ]
    ns["netclass_patterns"] = [
        {"netclass": "MAINS_LOAD", "pattern": "/AC_L_IN"},
        {"netclass": "MAINS_LOAD", "pattern": "/AC_L_RELAY"},
        {"netclass": "MAINS_LOAD", "pattern": "/AC_L"},
        {"netclass": "MAINS_LOAD", "pattern": "/AC_N"},
        {"netclass": "MAINS_LOAD", "pattern": "/OUT?"},
        {"netclass": "MAINS_LOAD", "pattern": "/OUT?_N?"},
        {"netclass": "MAINS", "pattern": "/AC_L_F"},
        {"netclass": "MAINS", "pattern": "unconnected-?K5*"},
        {"netclass": "ETH", "pattern": "/ETH_TX?"},
        {"netclass": "ETH", "pattern": "/ETH_RX?"},
        {"netclass": "USB", "pattern": "/DP"},
        {"netclass": "USB", "pattern": "/DM"},
        {"netclass": "USB", "pattern": "/USBDP"},
        {"netclass": "USB", "pattern": "/USBDM"},
        {"netclass": "PWR", "pattern": "+5V"},
        {"netclass": "PWR", "pattern": "+3.3V"},
        {"netclass": "PWR", "pattern": "VBUS"},
        {"netclass": "PWR", "pattern": "/RL?_COIL"},
        {"netclass": "GND", "pattern": "GND"},
        {"netclass": "EARTH", "pattern": "Earth_Protective"},
    ]
    pro.write_text(json.dumps(p, indent=2) + "\n")

# A net is mains if its class says so OR its name does. The name test keeps the
# isolation rules correct even when KiCad has overwritten the class patterns.
MAINS = ("(X.NetClass == 'MAINS*' || X.NetName == '/AC_*' || X.NetName == '/OUT1*'"
         " || X.NetName == '/OUT2*' || X.NetName == 'unconnected-?K5*')")
A, B = MAINS.replace("X.", "A."), MAINS.replace("X.", "B.")

dru.write_text(f"""(version 1)

# --- Mains isolation (handover 5.1) ---------------------------------------
# Mains <-> mains (L/N, open relay contacts): functional insulation,
# IEC 60664-1 250 V, pollution degree 2, FR4 (IIIb): creepage 2.5 mm.
(rule "mains_to_mains"
  (constraint clearance (min 2.5mm))
  (constraint creepage (min 2.5mm))
  (condition "{A} && {B}"))

# Mains <-> everything else (SELV, unconnected pads, holes): 5 mm creepage
# target, 3 mm clearance. Slots in Edge.Cuts count toward creepage.
(rule "mains_to_selv"
  (constraint clearance (min 3.0mm))
  (constraint creepage (min 5.0mm))
  (condition "{A} && !{B}"))

(rule "mains_to_hole"
  (constraint hole_clearance (min 3.0mm))
  (condition "{A} && !{B}"))

# --- JLC 2-layer limits not covered by the board setup ---------------------
(rule "pth_annular"
  (constraint annular_width (min 0.18mm))
  (condition "A.Type == 'Pad' && A.isPlated()"))

(rule "pth_hole_to_hole"
  (constraint hole_to_hole (min 0.45mm))
  (condition "A.Type == 'Pad' && B.Type == 'Pad'"))
""")
print("written", dru if dru_only else f"{pro} {dru}", "backups *.bak-" + stamp)
