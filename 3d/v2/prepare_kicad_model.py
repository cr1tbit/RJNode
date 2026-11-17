#!/usr/bin/env python3
"""Create a KiCad model in H5's local frame from the assembled v2 STEP.
The board attaches it with unit scale, zero model rotation and zero offset.
Run from any directory with system Python, FreeCAD and pcbnew installed.
"""
import sys
from pathlib import Path
sys.path.append('/usr/lib/freecad/lib')
import FreeCAD as A
import Part, pcbnew
ROOT=Path(__file__).resolve().parent
BOARD=ROOT.parent.parent/'RJNode.kicad_pcb'
PCB_TOP=10.4  # v2 assembly's PCB top height, measured from enclosure bottom

def main():
 board=pcbnew.LoadBoard(str(BOARD))
 hole=next(f for f in board.GetFootprints() if f.GetReference()=='H5')
 x,y=pcbnew.ToMM(hole.GetPosition());angle=hole.GetOrientationDegrees()
 shape=Part.read(str(ROOT/'enclosure_assembly.step'))
 # Assembled STEP already uses CAD Y = -KiCad Y. Place its origin on the
 # footprint at PCB top, then undo the footprint's own placement rotation.
 shape.translate(A.Vector(-x,y,-PCB_TOP))
 shape.rotate(A.Vector(),A.Vector(0,0,1),-angle)
 assert shape.isValid() and len(shape.Solids)==2
 doc=A.newDocument('RJNode_case_H5')
 obj=doc.addObject('PartDesign::Feature','Enclosure_v2');obj.Shape=shape
 Part.export([obj],str(ROOT/'kicad_case_H5.step'))
 print('Created kicad_case_H5.step, anchored to H5 at',x,y,'angle',angle)

if __name__=='__main__':main()
