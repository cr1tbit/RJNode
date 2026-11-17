#!/usr/bin/env python3
"""Render actual CAD solids to an offline PNG; no GUI or graphics server needed."""
import os
os.environ['MPLCONFIGDIR']='/tmp/rjnode-mpl'
import build as b
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb

def draw(ax,s,color,shift=(0,0,0)):
 s=b.to_cad(s)
 pts,faces=s.tessellate(.3)
 pts=np.array([[p.x,p.y,p.z] for p in pts])+np.array(shift)
 tris=pts[np.array(faces)]
 normals=np.cross(tris[:,1]-tris[:,0],tris[:,2]-tris[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-10)
 brightness=.66+.34*np.abs(normals@np.array([-.3,-.5,.81]))
 colors=np.clip(np.array(to_rgb(color))[None,:]*brightness[:,None],0,1)
 if not hasattr(ax,'cad_triangles'):ax.cad_triangles=[];ax.cad_colors=[]
 ax.cad_triangles.extend(tris);ax.cad_colors.extend(colors)

def raster(ax,az):
 tris=np.array(ax.cad_triangles);colors=np.array(ax.cad_colors)
 az=np.deg2rad(az);el=np.deg2rad(28)
 view=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
 right=np.array([-np.sin(az),np.cos(az),0]);up=np.cross(view,right)
 q=tris@np.stack([right,up,view],axis=1)
 lo=q[:,:,:2].min(axis=(0,1));hi=q[:,:,:2].max(axis=(0,1));scale=690/max(hi-lo)
 q[:,:,0]=(q[:,:,0]-(lo[0]+hi[0])/2)*scale+400
 q[:,:,1]=400-(q[:,:,1]-(lo[1]+hi[1])/2)*scale
 rgb=np.full((800,800,3),[240,242,245],dtype=np.uint8);depth=np.full((800,800),-np.inf)
 for t,c in zip(q,colors):
  x0=max(0,int(np.floor(t[:,0].min())));x1=min(799,int(np.ceil(t[:,0].max())))
  y0=max(0,int(np.floor(t[:,1].min())));y1=min(799,int(np.ceil(t[:,1].max())))
  if x0>x1 or y0>y1:continue
  X,Y=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
  den=(t[1,1]-t[2,1])*(t[0,0]-t[2,0])+(t[2,0]-t[1,0])*(t[0,1]-t[2,1])
  if abs(den)<1e-9:continue
  u=((t[1,1]-t[2,1])*(X-t[2,0])+(t[2,0]-t[1,0])*(Y-t[2,1]))/den
  v=((t[2,1]-t[0,1])*(X-t[2,0])+(t[0,0]-t[2,0])*(Y-t[2,1]))/den
  w=1-u-v;d=u*t[0,2]+v*t[1,2]+w*t[2,2]
  patch=depth[y0:y1+1,x0:x1+1];mask=(u>=-1e-8)&(v>=-1e-8)&(w>=-1e-8)&(d>patch)
  patch[mask]=d[mask];rgb[y0:y1+1,x0:x1+1][mask]=(c*255).astype(np.uint8)
 ax.imshow(rgb);ax.axis('off')

fig=plt.figure(figsize=(16,9),facecolor='#f0f2f5')
fig.text(.04,.95,'RJNode / inner protective enclosure',fontsize=25,weight='bold',color='#172737')
fig.text(.04,.905,'Iteration 02   •   112 × 74 × 36.8 mm   •   rectangular base + screw-on lid',fontsize=12,color='#536371')
base=b.base();lid=b.lid()
for i,(title,az,exploded) in enumerate([('Outputs + USB-C',125,False),('Mains input + Ethernet',-55,False),('Lid + screwdriver guides',115,True)]):
 ax=fig.add_subplot(1,3,i+1);ax.set_facecolor('#f0f2f5')
 draw(ax,base,'#637a90')
 if exploded:
  draw(ax,b.pcb_envelope(),'#258458')
  for name,s in b.components().items():draw(ax,s,'#267aae' if 'RELAY' in name else '#283139')
 draw(ax,lid,'#cbd4de',shift=(0,0,28 if exploded else 0))
 raster(ax,az)
 ax.set_title(title,fontsize=13,color='#172737',pad=20)
fig.text(.04,.16,'8 narrow screwdriver guides • 8 individual wire entries • 2 LED viewing holes',fontsize=12,color='#344d60')
fig.text(.04,.12,'Wiring access with lid fitted. Outer waterproof enclosure provides cable restraint and weather protection.',fontsize=11,color='#344d60')
fig.text(.04,.065,'Isolate before wiring. First fit prototype; contact protection and temperature rise require physical verification.',fontsize=11,color='#80551a')
plt.subplots_adjust(left=.01,right=.99,bottom=.21,top=.85,wspace=0)
fig.savefig(b.OUT/'preview.png',dpi=160,facecolor=fig.get_facecolor())
