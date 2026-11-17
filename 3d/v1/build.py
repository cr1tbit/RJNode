#!/usr/bin/env python3
"""RJNode bring-up enclosure v1. Run with system Python + FreeCAD libraries.
All coordinates in mm, matching KiCad XY. Z=0 is outside bottom.
Only 3d/v1 is written. No PCB or firmware modifications.
"""
import sys, math, json, hashlib
from pathlib import Path
sys.path.append('/usr/lib/freecad/lib')
import FreeCAD as A
import Part, Mesh

OUT = Path(__file__).resolve().parent
WALL = 2.8
FLOOR = 2.8
PCB_BOTTOM = 8.8
PCB_THICKNESS = 1.6
SEAM = 38.0
ROOF = 2.8
COVER = 2.4
GLAND_D = 16.2  # M16 clearance; confirm selected gland's actual mounting spec
PILOT_D = 2.7  # tune to filament/printer using coupon; M3 thread-forming
PCB_HOLES = [(78,95),(170,95),(78,147),(170,147)]
LID_SCREWS = [(71.5,85.5),(176.5,85.5),(71.5,152),(176.5,173.5)]
OUTLINE = [(68,65),(180,65),(180,177),(143,177),(143,156),(68,156)]
# Cover openings include vertical screwdriver paths and room to reach gland nuts.
HATCHES = {
 'outputs': dict(hole=(119,70,48,33), plate=(114,68.5,58,39),
                 screws=[(116.5,71.5),(169.5,71.5),(116.5,105),(169.5,105)]),
 'input': dict(hole=(153,140,16,31), plate=(145.5,136,30,38.5),
               screws=[(149.2,138),(173,138),(149.2,166),(173,166)]),
}

def box(x,y,z,dx,dy,dz): return Part.makeBox(dx,dy,dz,A.Vector(x,y,z))
def cyl(x,y,z,d,h,axis=(0,0,1)):
 return Part.makeCylinder(d/2,h,A.Vector(x,y,z),A.Vector(*axis))
def prism(points,z,h):
 vs=[A.Vector(x,y,z) for x,y in points]
 return Part.Face(Part.makePolygon(vs+[vs[0]])).extrude(A.Vector(0,0,h))
def footprint(): return prism(OUTLINE,0,1)
def inset(distance):
 # OCC planar face offset retains the concave rear step.
 wire=footprint().Faces[0].OuterWire
 # Select bottom XY face explicitly (face ordering depends on OCC).
 wire=next(f for f in footprint().Faces if abs(f.CenterOfMass.z)<1e-6).OuterWire
 return wire.makeOffset2D(-distance,0,False,False,True)
def inset_prism(distance,z,h):
 s=Part.Face(inset(distance)).extrude(A.Vector(0,0,h))
 s.translate(A.Vector(0,0,z))
 return s

def base():
 s=prism(OUTLINE,0,SEAM).cut(inset_prism(WALL,FLOOR,SEAM))
 for x,y in PCB_HOLES:
  s=s.fuse(cyl(x,y,FLOOR,6.8,PCB_BOTTOM-FLOOR))
 for x,y in LID_SCREWS:
  s=s.fuse(cyl(x,y,FLOOR,7,SEAM-FLOOR))
 # Rear bay separator: encloses input wiring away from Ethernet access.
 # The step begins beyond PCB rear edge and does not cross isolation slots.
 s=s.fuse(box(143,151.6,FLOOR,WALL,22.6,SEAM-FLOOR))
 for x,y in PCB_HOLES:
  s=s.cut(cyl(x,y,FLOOR+1,PILOT_D,PCB_BOTTOM-FLOOR))
 for x,y in LID_SCREWS:
  s=s.cut(cyl(x,y,SEAM-10,PILOT_D,11))
 # Outputs on north face; mains input south, all in cable bays outside PCB.
 for x in [128,152]: s=s.cut(cyl(x,64,21,GLAND_D,6,(0,1,0)))
 s=s.cut(cyl(159,173,21,GLAND_D,6,(0,1,0)))
 # USB-C plug-body clearance; recessed receptacle face is x=73.35.
 s=s.cut(box(67,113.15,9.6,7,14,9))
 # Ethernet opening with upper clearance for boot/latch, rear wall at y=156.
 s=s.cut(box(82.2,150.8,9.8,24,7,21))
 return s.removeSplitter()

def lid():
 s=prism(OUTLINE,SEAM,ROOF)
 # 0.35 mm radial clearance to inside of base; lip descends 2.5 mm.
 lip=inset_prism(WALL+0.35,SEAM-2.5,2.6).cut(inset_prism(WALL+1.75,SEAM-2.6,2.8))
 # Avoid case fastening columns and connector aperture / wire bay divider.
 for x,y in LID_SCREWS: lip=lip.cut(cyl(x,y,SEAM-3,8,4))
 lip=lip.cut(box(142.5,150.8,SEAM-3,4,24,4))
 s=s.fuse(lip)
 for x,y in LID_SCREWS:
  s=s.cut(cyl(x,y,SEAM-1,3.4,ROOF+2))
 for h in HATCHES.values():
  x,y,w,d=h['hole']
  s=s.cut(box(x,y,SEAM-4,w,d,ROOF+6))
  for sx,sy in h['screws']:
   s=s.fuse(cyl(sx,sy,SEAM-3,6.6,3.1))
   s=s.cut(cyl(sx,sy,SEAM-2.4,PILOT_D,ROOF+3))
 return s.removeSplitter()

def cover(which):
 h=HATCHES[which]; x,y,w,d=h['plate']
 s=box(x,y,SEAM+ROOF,w,d,COVER)
 for sx,sy in h['screws']:
  s=s.cut(cyl(sx,sy,SEAM+ROOF-0.1,3.4,COVER+0.2))
 # Clearance for the adjacent main-lid screw head at the rear corner.
 if which=='input':s=s.cut(cyl(176.5,173.5,SEAM+ROOF-0.1,8,COVER+0.2))
 return s.removeSplitter()

def coupon():
 s=box(0,0,0,42,16,6)
 for i,d in enumerate([2.5,2.6,2.7,2.8]):s=s.cut(cyl(6+10*i,8,1,d,6))
 return s

def pcb_envelope():
 # Board outline: 100x60, R4, four holes. Slots omitted in display model.
 s=box(78,91,PCB_BOTTOM,92,60,PCB_THICKNESS).fuse(box(74,95,PCB_BOTTOM,100,52,PCB_THICKNESS))
 for x,y in PCB_HOLES:s=s.fuse(cyl(x,y,PCB_BOTTOM,8,PCB_THICKNESS))
 for x,y in PCB_HOLES:s=s.cut(cyl(x,y,PCB_BOTTOM-.1,3.2,2))
 return s.removeSplitter()

def components():
 z=PCB_BOTTOM+PCB_THICKNESS
 return {
 'J501_OUT1':box(119.9,89.9,z,15.0,10.2,14.6),
 'J502_OUT2':box(135.5,89.9,z,15.0,10.2,14.6),
 'J503_NEUTRALS':box(151.1,89.9,z,15.0,10.2,14.6),
 'J101_MAINS':box(151.28,140.9,z,15,10.2,14.6),
 'K501_RELAY':box(123.2,101.4,z,15.6,19.2,16.5),
 'K511_RELAY':box(143.2,101.4,z,15.6,19.2,16.5),
 'PS101_HLK':box(106.5,127.2,z,39,23.5,20),
 'J401_ETHERNET':box(86.18,129.43,z,16.04,21.3,14.2),
 'J6_USB':box(73.35,115.68,z,7.3,8.94,3.4),
 'U1_ESP32':box(89.49,90.8,z,18,20,3.5),
 'F102':box(166.4,109.75,z+1.5,6.2,22.5,6.2),
 'F101':box(146,141.25,z,4,8.5,9),
 'RV101':box(157.5,126,z,6,11,14),
 'C201':cyl(117.3,121.8,z,7,13),
 }

def feature(doc,name,shape,color):
 o=doc.addObject('PartDesign::Feature',name);o.Shape=shape
 # Headless FreeCAD has no ViewObject. Color is applied in GUI when available.
 if o.ViewObject:o.ViewObject.ShapeColor=color
 return o

def main():
 doc=A.newDocument('RJNode_enclosure_v1')
 parts={'base':base(),'lid':lid(),'outputs_cover':cover('outputs'),'input_cover':cover('input'),'fit_coupon':coupon()}
 checks=[]
 for name,s in parts.items():
  assert s.isValid() and len(s.Solids)==1, (name,'invalid or disconnected',len(s.Solids))
  feature(doc,name,s,(.27,.34,.43))
  Part.export([doc.getObject(name)],str(OUT/(name+'.step')))
  # STLs individually oriented on the print bed. Lid: exterior roof down.
  printshape=s.copy()
  if name=='lid': printshape.rotate(A.Vector(0,0,0),A.Vector(1,0,0),180)
  bb=printshape.BoundBox;printshape.translate(A.Vector(-bb.XMin,-bb.YMin,-bb.ZMin))
  mesh=Mesh.Mesh(printshape.tessellate(0.06))
  assert mesh.isSolid(), (name, 'STL is not closed')
  mesh.write(str(OUT/(name+'.stl')))
  checks.append({'part':name,'solid_count':len(s.Solids),'valid':s.isValid(),'stl_closed':mesh.isSolid(),'stl_facets':mesh.CountFacets,'volume_mm3':round(s.Volume,2),
    'print_size_mm':[round(printshape.BoundBox.XLength,2),round(printshape.BoundBox.YLength,2),round(printshape.BoundBox.ZLength,2)]})
 board=pcb_envelope();feature(doc,'PCB_reference',board,(.1,.5,.2))
 comps=components()
 for name,s in comps.items():feature(doc,name,s,(.16,.23,.28))
 # Enclosure parts must not overlap each other, PCB, or conservative bodies.
 collisions=[]
 for name,s in parts.items():
  if name=='fit_coupon':continue
  for other,t in [('PCB',board)]+list(comps.items()):
   v=s.common(t).Volume
   if v>0.001:collisions.append((name,other,round(v,3)))
 names=[n for n in parts if n!='fit_coupon']
 for i,n in enumerate(names):
  for m in names[i+1:]:
   v=parts[n].common(parts[m]).Volume
   if v>0.001:collisions.append((n,m,round(v,3)))
 doc.recompute();doc.saveAs(str(OUT/'RJNode_enclosure_v1.FCStd'))
 Part.export([doc.getObject(n) for n in names],str(OUT/'enclosure_assembly.step'))
 report={'pcb_sha256':hashlib.sha256((OUT.parent.parent/'RJNode.kicad_pcb').read_bytes()).hexdigest(),
  'parts':checks,'collisions':collisions,'component_model':'Conservative envelopes, not exact imported supplier models',
  'parameters':{'wall_mm':WALL,'floor_mm':FLOOR,'pcb_bottom_z_mm':PCB_BOTTOM,'roof_z_mm':SEAM+ROOF,'overall_height_mm':SEAM+ROOF+COVER,'gland_hole_mm':GLAND_D}}
 (OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
 assert not collisions,collisions
if __name__=='__main__':main()
