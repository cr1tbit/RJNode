#!/usr/bin/env python3
"""Point board footprints at the JLC/EasyEDA 3D models in claude-lcsc.

Usage: python3 tools/apply_3d_models.py [board.kicad_pcb]   (default: ../RJNode.kicad_pcb)

KiCad's TerminalBlock_MaiXu_MX126 footprints reference a model that the official
3D library never shipped. The EasyEDA model (C5188434) is centred between the
pins; KiCad's footprint origin is pin 1, hence the +2.5 mm X offset.
Re-runnable. Close the board in KiCad first (or File > Revert afterwards).
"""
import re, shutil, sys, time
from pathlib import Path

pcb = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "RJNode.kicad_pcb"

MODELS = {
    # footprint lib_id: (model path, offset xyz in mm)
    "TerminalBlock:TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm":
        ("${CBIT_ROOT}/claude-lcsc/claude-lcsc.3dshapes/CONN-TH_2P-P5.00_MX126-5.0-GN01-02P-CU-S-A.wrl", (2.5, 0, 0)),
}


def model_block(path, off, indent):
    t = indent
    return (f'{t}(model "{path}"\n'
            f'{t}\t(offset\n{t}\t\t(xyz {off[0]:g} {off[1]:g} {off[2]:g})\n{t}\t)\n'
            f'{t}\t(scale\n{t}\t\t(xyz 1 1 1)\n{t}\t)\n'
            f'{t}\t(rotate\n{t}\t\t(xyz 0 0 0)\n{t}\t)\n'
            f'{t})')


def end_of(s, i):
    d = 0
    while True:
        c = s[i]
        if c == '"':
            i = s.index('"', i + 1)
        elif c == "(":
            d += 1
        elif c == ")":
            d -= 1
            if d == 0:
                return i + 1
        i += 1


s = pcb.read_text()
out, pos, changed = [], 0, []
for m in re.finditer(r'\n\t\(footprint "([^"]+)"', s):
    lib_id = m.group(1)
    if lib_id not in MODELS or m.start() < pos:
        continue
    start, end = m.start() + 1, end_of(s, m.start() + 1)
    fp = s[start:end]
    path, off = MODELS[lib_id]
    ref = re.search(r'\(property "Reference" "([^"]+)"', fp).group(1)
    mm = re.search(r'\n(\t+)\(model ', fp)
    if mm:  # replace the existing model block
        a = mm.start() + 1
        fp = fp[:a] + model_block(path, off, mm.group(1)) + fp[end_of(fp, a + len(mm.group(1))):]
    else:   # append before the footprint's closing paren
        fp = fp[:-1].rstrip("\t") + model_block(path, off, "\t\t") + "\n\t)"
    out.append(s[pos:start] + fp)
    pos = end
    changed.append(ref)
out.append(s[pos:])

if changed:
    shutil.copy2(pcb, pcb.with_name(pcb.name + time.strftime(".bak-%Y%m%d-%H%M%S")))
    pcb.write_text("".join(out))
print("updated:", ", ".join(sorted(changed)) or "nothing")
