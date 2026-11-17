#!/usr/bin/env python3
"""RJNode v2 inner guard. System Python + FreeCAD. Dimensions in mm.
Design XY follows KiCad; exported CAD negates Y to preserve PCB handedness. Z=0 outside bottom. Outputs only 3d/v2.
"""
import sys, math, json, hashlib
from pathlib import Path
sys.path.append('/usr/lib/freecad/lib')
import FreeCAD as A
import Part, Mesh
OUT=Path(__file__).resolve().parent
WALL=2.8
FLOOR=2.8
PCB_BOTTOM=8.8
PCB_THICKNESS=1.6
SEAM=34.0
ROOF=2.8
PILOT_D=2.7
DRIVER_D=4.4   # insulated tool shaft <=4.0 mm, verify actual tool
DRIVER_OD=7.2
DRIVER_BOTTOM=25.4
WIRE_D=4.8     # individual insulated conductors <=4.2 mm OD, no cable glands
WIRE_Z=14.6    # PCB top +4.2 mm; terminal model mouth spans +1.4 .. +7.0 mm
LED_D=2.4
LED_POSITIONS=[('D601',76.5,101.4),('LED3',76.5,105.8)]
PCB_HOLES=[(78,95),(170,95),(78,147),(170,147)]
LID_SCREWS=[(71.5,87.5),(176.5,87.5),(71.5,154.5),(176.5,154.5)]
OUTLINE=[(68,84),(180,84),(180,158),(68,158)]
# Corrected supplier geometry: screw axes offset 0.551 mm toward wire face
# from pad row; x follows pad center after correcting supplier model origin.
TERMINALS=[
 ('J501','NC1',123.59,95.0,-1),('J501','NO1',131.21,95.0,-1),
 ('J502','NC2',139.19,95.0,-1),('J502','NO2',146.81,95.0,-1),
 ('J503','N1',154.79,95.0,-1),('J503','N2',162.41,95.0,-1),
 ('J101','L',154.97,146.0,1),('J101','N',162.59,146.0,1),
]
SCREW_OFFSET=0.551
FONT=Path('/usr/share/texmf-dist/fonts/truetype/public/dejavu/DejaVuSans.ttf')

def screw_y(row,direction):return row+direction*SCREW_OFFSET

def box(x,y,z,dx,dy,dz): return Part.makeBox(dx,dy,dz,A.Vector(x,y,z))
def cyl(x,y,z,d,h,axis=(0,0,1)):
 return Part.makeCylinder(d/2,h,A.Vector(x,y,z),A.Vector(*axis))
def prism(points,z,h):
 vs=[A.Vector(x,y,z) for x,y in points]
 return Part.Face(Part.makePolygon(vs+[vs[0]])).extrude(A.Vector(0,0,h))
def footprint(): return prism(OUTLINE,0,1)
def inset(distance):
 # Offset the rectangular outline to form the inner wall.
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
 for x,y in PCB_HOLES:s=s.fuse(cyl(x,y,FLOOR,6.8,PCB_BOTTOM-FLOOR))
 for x,y in LID_SCREWS:s=s.fuse(cyl(x,y,FLOOR,7,SEAM-FLOOR))
 # Narrow individual wire guides terminate 0.65 mm ahead of nominal terminals.
 for ref,label,x,row,direction in TERMINALS:
  if direction<0:
   s=s.fuse(cyl(x,86.6,WIRE_Z,7.6,2.4,(0,1,0)))
  else:
   s=s.fuse(cyl(x,152.0,WIRE_Z,7.6,3.4,(0,1,0)))
 for x,y in PCB_HOLES:s=s.cut(cyl(x,y,FLOOR+1,PILOT_D,PCB_BOTTOM-FLOOR))
 for x,y in LID_SCREWS:s=s.cut(cyl(x,y,SEAM-9,PILOT_D,10))
 for ref,label,x,row,direction in TERMINALS:
  s=s.cut(cyl(x,83 if direction<0 else 151.5,WIRE_Z,WIRE_D,7,(0,1,0)))
 # USB and Ethernet plug openings retained; no mains cable bays or glands.
 s=s.cut(box(67,113.15,9.6,7,14,9))
 # Short shroud behind rear wall limits reach around the Ethernet opening.
 shroud=box(80.8,151.2,8.4,26.8,4.3,23.8).cut(box(82.2,151.1,9.8,24,4.5,21))
 s=s.fuse(shroud)
 s=s.cut(box(82.2,151.1,9.8,24,8,21))
 return s.removeSplitter()

def text_cut(text,x,y,height=2.0):
 # Font outlines become shallow pockets; no extra printable pieces.
 chars=Part.makeWireString(text,str(FONT.parent)+'/',FONT.name,height)
 solids=[]
 for wires in chars:
  if not wires:continue
  face=Part.makeFace(wires,'Part::FaceMakerBullseye')
  # Flip font Y to make the label readable in KiCad top view (north up).
  transform=A.Matrix();transform.A22=-1
  face=face.transformGeometry(transform)
  face.translate(A.Vector(x,y,SEAM+ROOF-0.45))
  solids.append(face.extrude(A.Vector(0,0,.65)))
 return Part.makeCompound(solids)

def lid():
 s=prism(OUTLINE,SEAM,ROOF)
 lip=inset_prism(WALL+.35,SEAM-2.5,2.6).cut(inset_prism(WALL+1.75,SEAM-2.6,2.8))
 for x,y in LID_SCREWS:lip=lip.cut(cyl(x,y,SEAM-3,8,4))
 # Relieve the lip above the Ethernet shroud.
 lip=lip.cut(box(80.6,151.0,SEAM-3,27.2,6,4))
 s=s.fuse(lip)
 for x,y in LID_SCREWS:s=s.cut(cyl(x,y,SEAM-1,3.4,ROOF+2))
 for ref,label,x,row,direction in TERMINALS:
  y=screw_y(row,direction)
  s=s.fuse(cyl(x,y,DRIVER_BOTTOM,DRIVER_OD,SEAM-DRIVER_BOTTOM+.1))
  s=s.cut(cyl(x,y,DRIVER_BOTTOM-.1,DRIVER_D,SEAM+ROOF-DRIVER_BOTTOM+.2))
  # Lead-in on outside. The long guide bore remains only 4.4 mm diameter.
  s=s.cut(Part.makeCone(DRIVER_D/2,2.8,.8,A.Vector(x,y,SEAM+ROOF-.7)))
  if FONT.exists():s=s.cut(text_cut(label,x-2.1,row-4.0 if direction<0 else row-4.5,1.6))
 for ref,x,y in LED_POSITIONS:
  s=s.cut(cyl(x,y,SEAM-.1,LED_D,ROOF+.2))
  s=s.cut(Part.makeCone(2.1,LED_D/2,1.5,A.Vector(x,y,SEAM-.1)))
 if FONT.exists():
  s=s.cut(text_cut('RJNode v2',84,115,3.5))
  s=s.cut(text_cut('230 V~',84,123,2.4))
  s=s.cut(text_cut('ISOLATE BEFORE WIRING',84,129,2.0))
  s=s.cut(text_cut('D601',79,102,1.4));s=s.cut(text_cut('LED3',79,106.4,1.4))
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

def to_cad(shape):
 # KiCad screen coordinates have Y downward. In a right-handed CAD model
 # viewed from above, Y points upward. Reflect the COMPLETE assembly in Y;
 # otherwise the connector layout would print as a mirror of the real PCB.
 transform=A.Matrix();transform.A22=-1
 return shape.transformGeometry(transform)

def feature(doc,name,shape,color):
 o=doc.addObject('PartDesign::Feature',name);o.Shape=to_cad(shape)
 # Headless FreeCAD has no ViewObject. Color is applied in GUI when available.
 if o.ViewObject:o.ViewObject.ShapeColor=color
 return o

def check_pcb_alignment():
 import pcbnew as p
 board=p.LoadBoard(str(OUT.parent.parent/'RJNode.kicad_pcb'))
 fps={f.GetReference():f for f in board.GetFootprints()}
 for ref,label,x,y,direction in TERMINALS:
  assert any(abs(p.ToMM(pad.GetPosition().x)-x)<.01 and abs(p.ToMM(pad.GetPosition().y)-y)<.01 for pad in fps[ref].Pads()), (ref,label,'pad moved')
 for ref,x,y in LED_POSITIONS:
  pos=p.ToMM(fps[ref].GetPosition());assert abs(pos[0]-x)<.01 and abs(pos[1]-y)<.01,(ref,'LED moved')
 for ref,expected in zip(['H5','H6','H7','H8'],PCB_HOLES):
  pos=p.ToMM(fps[ref].GetPosition());assert all(abs(a-b)<.01 for a,b in zip(pos,expected)),ref
 return 'Terminal pads, LEDs and four mounting holes match current PCB'

def access_checks(parts):
 result=[]
 for ref,label,x,row,direction in TERMINALS:
  y=screw_y(row,direction)
  tool=cyl(x,y,25.1,4.0,20)
  wire=cyl(x,83 if direction<0 else 151.5,WIRE_Z,4.2,7,(0,1,0))
  for name,probe in [('screwdriver',tool),('wire',wire)]:
   overlap=sum(probe.common(parts[n]).Volume for n in ['base','lid'])
   result.append({'terminal':ref+' '+label,'access':name,'clear':overlap<.001})
 for ref,x,y in LED_POSITIONS:
  probe=cyl(x,y,SEAM-.2,2.2,ROOF+.4)
  result.append({'LED':ref,'clear':probe.common(parts['lid']).Volume<.001})
 return result

def main():
 doc=A.newDocument('RJNode_enclosure_v2')
 parts={'base':base(),'lid':lid(),'fit_coupon':coupon()}
 checks=[]
 for name,s in parts.items():
  assert s.isValid() and len(s.Solids)==1, (name,'invalid or disconnected',len(s.Solids))
  exported=feature(doc,name,s,(.27,.34,.43))
  assert exported.Shape.isValid() and exported.Shape.Volume>0, (name,'invalid export transform')
  Part.export([doc.getObject(name)],str(OUT/(name+'.step')))
  # STLs individually oriented on the print bed. Lid: exterior roof down.
  printshape=to_cad(s)
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
 doc.recompute();doc.saveAs(str(OUT/'RJNode_enclosure_v2.FCStd'))
 Part.export([doc.getObject(n) for n in names],str(OUT/'enclosure_assembly.step'))
 report={'pcb_sha256':hashlib.sha256((OUT.parent.parent/'RJNode.kicad_pcb').read_bytes()).hexdigest(),
  'parts':checks,'collisions':collisions,'access_checks':access_checks(parts),'pcb_alignment':check_pcb_alignment(),'export_coordinate_system':'CAD X = KiCad X; CAD Y = -KiCad Y; CAD Z upward','component_model':'Conservative envelopes, not exact imported supplier models',
  'parameters':{'wall_mm':WALL,'floor_mm':FLOOR,'pcb_bottom_z_mm':PCB_BOTTOM,'roof_z_mm':SEAM+ROOF,'overall_height_mm':SEAM+ROOF,'screwdriver_bore_mm':DRIVER_D,'wire_hole_mm':WIRE_D,'wire_center_z_mm':WIRE_Z,'led_hole_mm':LED_D}}
 (OUT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
 assert not collisions,collisions
 assert all(c['clear'] for c in report['access_checks']), report['access_checks']
if __name__=='__main__':main()
