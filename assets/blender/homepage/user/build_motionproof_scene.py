"""Procedural Blender 5.3 scene builder for the MotionProof cinematic engineering brief.
All dimensions are illustrative reference design dimensions, not certified hardware data.
Run: blender-launcher.exe --background --python build_motionproof_scene.py
"""
import bpy, math, os, sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG = open(os.path.join(ROOT, 'build.log'), 'w', buffering=1)
sys.stdout = LOG
sys.stderr = LOG
BLEND_PATH = os.path.join(ROOT, 'MotionProof_Cinematic_Engineering.blend')
PREVIEW_PATH = os.path.join(ROOT, 'preview_reveal.png')
M = 0.0015                    # illustrative module in metres
SUN_Z, PLANET_Z, RING_Z = 20, 20, 60
STAGE1_Z, STAGE2_Z = -0.018, 0.040
FPS, END = 24, 1440

# Reset and organise.
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
for c in list(bpy.data.collections):
    if c.name != 'Collection': bpy.data.collections.remove(c)
root=bpy.context.scene.collection

def collection(name):
    c=bpy.data.collections.new(name); root.children.link(c); return c
COL={n:collection(n) for n in ['01 Motor','02 Gearbox Housing','03 Stage 1','04 Stage 2','05 Bearings','06 Shafts','07 Structure','08 Fasteners','09 Cinematography','10 Studio','11 Technical Labels','12 Variant Illustration']}
CURRENT=COL['07 Structure']

def link_obj(obj, coll=None):
    coll=coll or CURRENT
    for c in list(obj.users_collection): c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj

def mat(name, color, metallic=0.0, rough=0.35):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(*color,1); bs.inputs['Metallic'].default_value=metallic; bs.inputs['Roughness'].default_value=rough
    return m
AL=mat('Titanium | satin bead-blast',(.34,.39,.42),.82,.29)
STEEL=mat('Steel | ground and hardened',(.18,.22,.25),.9,.22)
DARK=mat('Graphite | hard anodised',(.035,.048,.055),.72,.28)
BLACK=mat('Motor | satin black',(.012,.017,.02),.35,.36)
COPPER=mat('Copper | winding enamel',(.48,.17,.055),.78,.25)
BRASS=mat('Bronze | bearing cage',(.42,.25,.09),.78,.25)
VERM=mat('MotionProof | vermilion',(.78,.095,.035),.55,.24)
CERAMIC=mat('Ceramic | bearing balls',(.72,.77,.78),.1,.15)
WHITE=mat('Type | warm white',(.86,.88,.87),.15,.42)
FLOOR=mat('Studio | graphite',(.018,.022,.026),.25,.32)

def assign(obj, material):
    if material: obj.data.materials.append(material)
    return obj

def bevel(obj, width=.001, segments=3):
    mod=obj.modifiers.new('Machined edge | controlled radius','BEVEL'); mod.width=width; mod.segments=segments
    mod2=obj.modifiers.new('Corner normals','WEIGHTED_NORMAL'); mod2.keep_sharp=True
    return obj

def cube(name, loc, scale, material, coll=None, bevel_w=.001):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o=bpy.context.object; o.name=name; o.dimensions=scale; bpy.ops.object.transform_apply(location=False, rotation=False, scale=True); assign(o,material); bevel(o,bevel_w); return link_obj(o,coll)

def cyl(name, radius, depth, loc, material, coll=None, vertices=96, bevel_w=.0006):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc); o=bpy.context.object; o.name=name; assign(o,material); bevel(o,bevel_w); return link_obj(o,coll)

def torus(name, major, minor, loc, material, coll=None):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=96, minor_segments=12, location=loc); o=bpy.context.object; o.name=name; assign(o,material); return link_obj(o,coll)

def uv_sphere(name, radius, loc, material, coll=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=radius, location=loc); o=bpy.context.object; o.name=name; assign(o,material); bpy.ops.object.shade_smooth(); return link_obj(o,coll)

def annulus(name, outer, inner, depth, z, material, coll, seg=128):
    verts=[]; faces=[]
    for zz in (z-depth/2,z+depth/2):
        for r in (outer,inner):
            for i in range(seg):
                a=2*math.pi*i/seg; verts.append((r*math.cos(a),r*math.sin(a),zz))
    # layers: bottom outer, bottom inner, top outer, top inner
    for i in range(seg):
        j=(i+1)%seg
        faces += [(i,j,seg+j,seg+i),(2*seg+i,3*seg+i,3*seg+j,2*seg+j),(i,2*seg+i,2*seg+j,j),(seg+i,seg+j,3*seg+j,3*seg+i)]
    mesh=bpy.data.meshes.new(name+' | mesh'); mesh.from_pydata(verts,[],faces); mesh.update(); o=bpy.data.objects.new(name,mesh); coll.objects.link(o); assign(o,material); bevel(o,.00035,2); return o

def arc_shell(name, outer, inner, depth, z, material, coll, start_deg=20, end_deg=220, seg=96):
    """Open-backed annular housing sector. The front-facing sector is deliberately cut away for inspection."""
    a0,a1=math.radians(start_deg),math.radians(end_deg)
    verts=[]
    for radius,zz in [(outer,z-depth/2),(outer,z+depth/2),(inner,z-depth/2),(inner,z+depth/2)]:
        for i in range(seg+1):
            a=a0+(a1-a0)*i/seg; verts.append((radius*math.cos(a),radius*math.sin(a),zz))
    stride=seg+1; bo,to,bi,ti=0,stride,2*stride,3*stride; faces=[]
    for i in range(seg):
        j=i+1
        faces += [(bo+i,bo+j,to+j,to+i),(bi+j,bi+i,ti+i,ti+j),(to+i,to+j,ti+j,ti+i),(bo+j,bo+i,bi+i,bi+j)]
    faces += [(bo,to,ti,bi),(bo+seg,bi+seg,ti+seg,to+seg)]
    me=bpy.data.meshes.new(name+' | open cutaway mesh'); me.from_pydata(verts,[],faces); me.update(); o=bpy.data.objects.new(name,me); coll.objects.link(o); assign(o,material); return o
def external_gear(name, teeth, module, z, depth, loc, material, coll):
    # Analytic involute flank sampling with the illustrative 20 degree pressure angle.
    rp=module*teeth/2; rb=rp*math.cos(math.radians(20)); ra=rp+module; rr=rp-1.25*module
    half0=math.pi/(2*teeth)+(math.tan(math.radians(20))-math.radians(20))
    outline=[]; samples=6
    for k in range(teeth):
        center=2*math.pi*k/teeth
        # root arc to left flank start
        aL=center-half0
        outline.append((rr*math.cos(aL),rr*math.sin(aL)))
        for j in range(samples+1):
            r=rr+(ra-rr)*j/samples
            if r <= rb: half=half0
            else:
                alpha=math.acos(max(-1,min(1,rb/r)))
                inv=math.tan(alpha)-alpha
                invp=math.tan(math.radians(20))-math.radians(20)
                half=math.pi/(2*teeth)+invp-inv
            a=center-half; outline.append((r*math.cos(a),r*math.sin(a)))
        # tip arc
        for j in range(1,4):
            r=ra; a=center-half0+(2*half0)*j/4; outline.append((r*math.cos(a),r*math.sin(a)))
        for j in range(samples,-1,-1):
            r=rr+(ra-rr)*j/samples
            if r <= rb: half=half0
            else:
                alpha=math.acos(max(-1,min(1,rb/r))); inv=math.tan(alpha)-alpha; invp=math.tan(math.radians(20))-math.radians(20); half=math.pi/(2*teeth)+invp-inv
            a=center+half; outline.append((r*math.cos(a),r*math.sin(a)))
        outline.append((rr*math.cos(center+half0),rr*math.sin(center+half0)))
        # root gap midpoint
        nxt=center+2*math.pi/teeth-half0
        outline.append((rr*math.cos(nxt),rr*math.sin(nxt)))
    n=len(outline); verts=[(x,y,z-depth/2) for x,y in outline]+[(x,y,z+depth/2) for x,y in outline]
    faces=[tuple(range(n-1,-1,-1)),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    me=bpy.data.meshes.new(name+' | involute profile'); me.from_pydata(verts,[],faces); me.update(); o=bpy.data.objects.new(name,me); coll.objects.link(o); o.location=(loc[0],loc[1],0); assign(o,material); bevel(o,.00018,2); o['teeth']=teeth; o['module_m']=module; o['pressure_angle_deg']=20; return o

def ring_gear(name, teeth, module, z, depth, loc, coll):
    rp=module*teeth/2; root=rp+1.25*module; tip=rp-module; outer=rp+7*module
    body=annulus(name+' | ring body',outer,root,depth,z,STEEL,coll)
    body['teeth']=teeth; body['module_m']=module; body['role']='Fixed internal ring gear; illustrative involute tooth inserts'
    # Separate internal tooth sectors, evenly indexed; tooth profiles are stylised inserts at root diameter.
    for k in range(teeth):
        a=2*math.pi*k/teeth
        # tapered inward tooth with rounded tip; sector overlaps the annulus at the root.
        half=math.pi/(2*teeth)*.72
        pts=[(root*math.cos(a-half),root*math.sin(a-half)),(tip*math.cos(a-half*.63),tip*math.sin(a-half*.63)),(tip*math.cos(a+half*.63),tip*math.sin(a+half*.63)),(root*math.cos(a+half),root*math.sin(a+half))]
        verts=[(x+loc[0],y+loc[1],z-depth*.44) for x,y in pts]+[(x+loc[0],y+loc[1],z+depth*.44) for x,y in pts]
        faces=[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        me=bpy.data.meshes.new(name+f' tooth {k+1:02d}'); me.from_pydata(verts,[],faces); me.update(); o=bpy.data.objects.new(name+f' | internal tooth {k+1:02d}',me); coll.objects.link(o); assign(o,STEEL); o['tooth_index']=k+1
    return body

def parent_at_origin(obj, parent, origin):
    obj.parent=parent; obj.matrix_parent_inverse=parent.matrix_world.inverted(); obj.location=obj.location

def add_bearing(label,z,coll):
    annulus(label+' outer race',.027,.021,.008,z,STEEL,coll)
    annulus(label+' inner race',.019,.011,.008,z,AL,coll)
    for i in range(10):
        a=2*math.pi*i/10; uv_sphere(label+f' ceramic ball {i+1:02d}',.003,(.020*math.cos(a),.020*math.sin(a),z),CERAMIC,COL['05 Bearings'])

def radial_fasteners(prefix,radius,count,z,coll=COL['08 Fasteners']):
    for i in range(count):
        a=2*math.pi*i/count; x=radius*math.cos(a); y=radius*math.sin(a)
        cyl(prefix+f' | socket cap {i+1:02d}',.0038,.003,(x,y,z),STEEL,coll,24,.00045)
        # socket recess cue, dark inset disk
        cyl(prefix+f' | hex socket {i+1:02d}',.00125,.0005,(x,y,z+.0017),BLACK,coll,6,.0001)

# NEMA 17 envelope, connector, motor end plates and restrained exposed copper detail.
CURRENT=COL['01 Motor']
motor=cube('NEMA 17 | stator can',(0,0,-.145),(.0423,.0423,.064),BLACK,CURRENT,.003)
motor['designation']='NEMA 17 envelope'; motor['provenance']='Illustrative dimensions; not tied to a specific vendor drawing'
cube('Motor | front plate',(0,0,-.108),(.0423,.0423,.006),AL,CURRENT,.0015)
cube('Motor | rear plate',(0,0,-.181),(.0423,.0423,.005),DARK,CURRENT,.0015)
cyl('Motor | pilot boss',.011,.006,(0,0,-.102),STEEL,CURRENT)
# visible shaft projects into stage 1
cyl('Input shaft | 5 mm nominal illustrative',.0025,.055,(0,0,-.066),STEEL,COL['06 Shafts'],48,.0003)
cyl('Input shaft | shoulder',.004,.004,(0,0,-.091),AL,COL['06 Shafts'])
for ix in [-1,1]:
 for iy in [-1,1]:
  x,y=ix*.0155,iy*.0155
  cyl(f'Motor flange | M3 clearance seat {ix},{iy}',.0022,.006,(x,y,-.104),DARK,COL['08 Fasteners'],24,.0002)
  cyl(f'Motor flange | cap screw {ix},{iy}',.0017,.002,(x,y,-.100),STEEL,COL['08 Fasteners'],24,.0002)
# connector shell and pins
cube('Motor | connector shell',(0,.024,-.153),(.014,.014,.018),DARK,CURRENT,.002)
for i in range(4): cyl(f'Motor | connector pin {i+1}',.0008,.012,(-.0045+i*.003,.024,-.154),COPPER,CURRENT,16,.0001)

# Gearbox mount plate and housing shell, cutaway side opening represented by a partial arc shell.
CURRENT=COL['02 Gearbox Housing']
annulus('Housing | rear mounting flange',.078,.029,.008,-.060,AL,CURRENT)
arc_shell('Housing | barrel | front cutaway',.076,.061,.105,-.005,DARK,CURRENT,20,220,112)
annulus('Housing | front lip',.078,.043,.009,.050,AL,CURRENT)
# Cutaway service window inset panel gives inspectable but still assembled industrial housing.
cube('Housing | cutaway service window',(0,.108,-.004),(.105,.008,.066),BLACK,CURRENT,.004)
for i in range(3): cube(f'Housing | window rib {i+1}',(0,.102,-.026+i*.022),(.083,.003,.002),AL,CURRENT,.0004)
torus('Housing | machined perimeter bead',.074,.0012,(0,0,.048),STEEL,CURRENT)
radial_fasteners('Housing | front flange',.073,12,.056)
radial_fasteners('Housing | rear flange',.073,8,-.054)

# Two-stage fixed-ring epicyclic assembly. Mesh tooth form is involute for external gears;
# ring teeth are clearly identified illustrative internal inserts and are not a validated contact model.
for stage,z,coll in [(1,STAGE1_Z,COL['03 Stage 1']),(2,STAGE2_Z,COL['04 Stage 2'])]:
    rg=ring_gear(f'Stage {stage} | fixed 60T ring gear',RING_Z,M,z,.014,(0,0),coll); rg['stage']=stage
    sun=external_gear(f'Stage {stage} | 20T sun gear',SUN_Z,M,z,.012,(0,0),AL,coll); sun['stage']=stage
    rp_s=M*SUN_Z/2; rp_p=M*PLANET_Z/2; orbit=rp_s+rp_p
    # Carrier body and three arms.
    carrier=cyl(f'Stage {stage} | planet carrier',.031,.006,(0,0,z+.010),DARK,coll)
    carrier['stage']=stage; carrier['planet_count']=3
    for k in range(3):
        a=2*math.pi*k/3; px,py=orbit*math.cos(a),orbit*math.sin(a)
        cube(f'Stage {stage} | carrier spoke {k+1}',(px*.52,py*.52,z+.010),(.038,.009,.004),AL,coll,.001).rotation_euler[2]=a
        cyl(f'Stage {stage} | planet pin {k+1}',.003,.010,(px,py,z+.012),STEEL,coll,32,.0003)
        pg=external_gear(f'Stage {stage} | planet {k+1} | 20T',PLANET_Z,M,z,.010,(px,py),AL,coll); pg['stage']=stage; pg['planet_index']=k+1
    if stage==1:
        # Stage 1 carrier doubles as the coaxial input sun shaft support for stage 2.
        cyl('Interstage shaft | stage 1 carrier to stage 2 sun',.004,.052,(0,0,.010),STEEL,COL['06 Shafts'])
    add_bearing(f'Stage {stage} | output support bearing A',z+.025,COL['05 Bearings'])
    add_bearing(f'Stage {stage} | output support bearing B',z-.023,COL['05 Bearings'])
    radial_fasteners(f'Stage {stage} | carrier pins',orbit,3,z+.014,coll)
# Output shaft, cross flange, robotic elbow fork and structural link.
CURRENT=COL['06 Shafts']
cyl('Output shaft | stepped',.008,.075,(0,0,.081),STEEL,CURRENT,64,.0006)
cyl('Output shaft | shoulder',.014,.009,(0,0,.113),AL,CURRENT)
cyl('Output flange | hub',.032,.012,(0,0,.122),AL,COL['07 Structure'])
radial_fasteners('Output flange | fasteners',.025,6,.129)
CURRENT=COL['07 Structure']
# Clevis cheeks rise from a cross-axis link. Rounded edges and cut-through bores are represented by cylinders/rings.
for side in [-1,1]:
    cheek=cube(f'Elbow clevis | cheek {side:+}',(.043,side*.022,.158),(.060,.008,.065),AL,CURRENT,.005); cheek.rotation_euler[1]=-.18
    annulus(f'Elbow clevis | pivot bushing {side:+}',.013,.006,.009,.158,BRASS,CURRENT)
    # Reposition pivot rings to side plates with explicit y offsets.
    ring=bpy.data.objects[f'Elbow clevis | pivot bushing {side:+}']; ring.location.y=side*.027
    cyl(f'Elbow clevis | shoulder bolt {side:+}',.005,.060,(.043,0,.158),STEEL,COL['08 Fasteners'],32,.0004)
link=cube('Robotic link | box section',(.154,0,.158),(.205,.044,.038),DARK,CURRENT,.006)
link.rotation_euler[1]=-.10
cube('Robotic link | machined top insert',(.154,0,.178),(.166,.030,.003),AL,CURRENT,.001)
for i in range(4):
 x=.085+i*.045
 cyl(f'Robotic link | socket fastener {i+1}',.0027,.003,(x,0,.181),STEEL,COL['08 Fasteners'],24,.0002)
# End joint for visual completion.
cyl('Link | distal pivot housing',.025,.047,(.265,0,.158),AL,CURRENT)
annulus('Link | distal bearing seat',.020,.010,.009,.158,STEEL,CURRENT)

# Illustrative nominal / variant counterpart with a transparent vermilion overlay, no random distortion.
CURRENT=COL['12 Variant Illustration']
# Smaller duplicate is parked to the right of the main unit; explicit fixed delta is illustrative only.
# Use linked meshes where possible, keep prototype light, and annotate as non-simulation.
variant_root=bpy.data.objects.new('Illustrative variant | display root',None); CURRENT.objects.link(variant_root); variant_root.location=(.38,0,.06); variant_root['status']='Illustrative visual comparison only; no generated MotionProof assembly data'
for src in list(COL['03 Stage 1'].objects)+list(COL['04 Stage 2'].objects):
    dup=src.copy(); dup.data=src.data.copy() if src.data else None; CURRENT.objects.link(dup); dup.name='Variant display | '+src.name; dup.parent=variant_root; dup.location=src.location.copy(); dup.location.x+=.38
    if dup.data and hasattr(dup.data,'materials'):
        for i in range(len(dup.data.materials)): dup.data.materials[i]=VERM
    dup.hide_render=True
# Create transparent comparison annulus cue only; not a physical deviation.

# Studio plinth and floor.
CURRENT=COL['10 Studio']
cyl('Product plinth | upper',.205,.016,(.025,0,-.221),DARK,CURRENT,128,.004)
torus('Product plinth | vermilion reveal',.187,.0012,(.025,0,-.212),VERM,CURRENT)
cube('Studio floor',(0,0,-.237),(200,200,.01),FLOOR,CURRENT,.001)

# Technical labels: sparse, editorial, clearly marked as illustrative.
CURRENT=COL['11 Technical Labels']
def text_obj(name, body, loc, size=.010, material=WHITE):
    cu=bpy.data.curves.new(name,'FONT'); cu.body=body; cu.size=size; cu.extrude=.00004; ob=bpy.data.objects.new(name,cu); CURRENT.objects.link(ob); ob.location=loc; ob.rotation_euler=(math.radians(90),0,0); assign(ob,material); return ob
text_obj('Provenance | illustrative label','ILLUSTRATIVE REFERENCE ASSEMBLY  /  NOT MEASURED HARDWARE',(-.19,-.145,-.18),.006)
text_obj('Gear ratio | stage note','20T / 60T   •   4:1 PER STAGE   •   16:1 TOTAL',(-.18,-.146,-.193),.006,VERM)
text_obj('Tolerance | note','DIMENSIONS SHOWN ARE ILLUSTRATIVE ONLY',(-.17,-.146,-.206),.0055,WHITE)

# Camera target, choreographed nine-chapter path, lens changes and DOF cues.
CURRENT=COL['09 Cinematography']
cam_data=bpy.data.cameras.new('MotionProof | master camera'); cam=bpy.data.objects.new('MotionProof | master camera',cam_data); CURRENT.objects.link(cam); bpy.context.scene.camera=cam
cam_data.lens=55; cam_data.dof.use_dof=True; cam_data.dof.aperture_fstop=4.0
focus=bpy.data.objects.new('Camera focus | animated target',None); CURRENT.objects.link(focus); focus.location=(.05,0,.02); focus.hide_render=True; cam_data.dof.focus_object=focus
shots=[
 (1,(-.018,-.22,-.075),(.0,0,-.07),100),
 (145,(.115,-.23,-.035),(.02,0,-.01),72),
 (300,(.55,-.92,.42),(.05,0,.02),42),
 (445,(.08,-.48,.22),(.03,0,.02),50),
 (530,(.16,-1.15,.42),(.06,0,.03),36),
 (590,(-.20,-.33,.07),(0,0,.02),58),
 (735,(.06,-.38,.13),(.02,0,.03),70),
 (880,(.48,-.49,.16),(.27,0,.10),58),
 (1050,(.04,-.50,.20),(.03,0,.04),55),
 (1200,(.10,-.48,.25),(.12,0,.04),48),
 (1300,(.20,-.88,.42),(.08,0,.02),36),
 (1440,(.32,-.70,.31),(.10,0,.02),48),
]
for frame,loc,target,lens in shots:
    cam.location=loc; direction=Vector(target)-cam.location; cam.rotation_euler=direction.to_track_quat('-Z','Y').to_euler(); cam_data.lens=lens; cam.keyframe_insert(data_path='location',frame=frame); cam.keyframe_insert(data_path='rotation_euler',frame=frame); cam_data.keyframe_insert(data_path='lens',frame=frame)
    focus.location=target; focus.keyframe_insert(data_path='location',frame=frame)
# smooth camera travel
# Blender defaults camera keys to eased Bezier interpolation.
# Chapter markers, exact editorial beats.
scene=bpy.context.scene
chapters=[(1,'01 | THE FIRST DETAIL'),(145,'02 | THE MACHINE REVEAL'),(300,'03 | THE EXPLODED ASSEMBLY'),(445,'04 | INSIDE THE GEARBOX'),(590,'05 | PRECISION & MANUFACTURING'),(735,'06 | NOMINAL VS VARIATION'),(880,'07 | THE MECHANISM IN MOTION'),(1050,'08 | A POPULATION OF POSSIBLE ASSEMBLIES'),(1200,'09 | THE FINAL PRODUCT FILM')]
for f,n in chapters: scene.timeline_markers.new(n,frame=f)

# Gear motion follows fixed-ring kinematics: sun -> carrier at 1/4 speed; planet absolute speed -1/2 sun.
# Stage 2 input is stage-1 carrier, giving 1/16 output speed. Mesh contact is illustrative, not solved.
turns=6*2*math.pi
motion_end=END
animated=[]
for ob in bpy.data.objects:
    nm=ob.name
    if nm.startswith('Stage 1 | 20T sun gear'):
        ob.rotation_euler[2]=0; ob.keyframe_insert(data_path='rotation_euler',frame=1,index=2); ob.rotation_euler[2]=turns; ob.keyframe_insert(data_path='rotation_euler',frame=motion_end,index=2); animated.append(ob)
    elif nm.startswith('Stage 1 | planet ') and ' | 20T' in nm:
        ob.rotation_euler[2]=0; ob.keyframe_insert(data_path='rotation_euler',frame=1,index=2); ob.rotation_euler[2]=-.5*turns; ob.keyframe_insert(data_path='rotation_euler',frame=motion_end,index=2); animated.append(ob)
    elif nm.startswith('Stage 1 | planet carrier'):
        ob.rotation_euler[2]=0; ob.keyframe_insert(data_path='rotation_euler',frame=1,index=2); ob.rotation_euler[2]=.25*turns; ob.keyframe_insert(data_path='rotation_euler',frame=motion_end,index=2); animated.append(ob)
    elif nm.startswith('Stage 2 | 20T sun gear'):
        ob.rotation_euler[2]=0; ob.keyframe_insert(data_path='rotation_euler',frame=1,index=2); ob.rotation_euler[2]=.25*turns; ob.keyframe_insert(data_path='rotation_euler',frame=motion_end,index=2); animated.append(ob)
    elif nm.startswith('Stage 2 | planet ') and ' | 20T' in nm:
        ob.rotation_euler[2]=0; ob.keyframe_insert(data_path='rotation_euler',frame=1,index=2); ob.rotation_euler[2]=-.125*turns; ob.keyframe_insert(data_path='rotation_euler',frame=motion_end,index=2); animated.append(ob)
    elif nm.startswith('Stage 2 | planet carrier') or nm.startswith('Output shaft | stepped') or nm.startswith('Robotic link | box section'):
        ob.rotation_euler[2]=0; ob.keyframe_insert(data_path='rotation_euler',frame=1,index=2); ob.rotation_euler[2]=.0625*turns; ob.keyframe_insert(data_path='rotation_euler',frame=motion_end,index=2); animated.append(ob)
# Identically keyed motions preserve their 1:4:16 kinematic ratios under the same eased interpolation.
# Explode / reassemble staged groups by direct keyframed component offsets, preserving identity and orientation.
for coll in [COL['01 Motor'],COL['03 Stage 1'],COL['04 Stage 2'],COL['05 Bearings'],COL['06 Shafts'],COL['07 Structure'],COL['08 Fasteners']]:
    for ob in list(coll.objects):
        if ob.type not in {'MESH','CURVE'}: continue
        base=ob.location.copy(); delta=Vector((0,0,0))
        if coll==COL['01 Motor']: delta=Vector((0,0,-.085))
        elif coll==COL['03 Stage 1']: delta=Vector((0,0,-.035))
        elif coll==COL['04 Stage 2']: delta=Vector((0,0,.035))
        elif coll==COL['05 Bearings']: delta=Vector((0,0,.065 if base.z>0 else -.065))
        elif coll==COL['06 Shafts']: delta=Vector((0,0,.085))
        elif coll==COL['07 Structure']: delta=Vector((.055,0,.11))
        elif coll==COL['08 Fasteners']: delta=Vector((.06,0,0))
        ob.location=base; ob.keyframe_insert(data_path='location',frame=300); ob.location=base+delta; ob.keyframe_insert(data_path='location',frame=530); ob.keyframe_insert(data_path='location',frame=625); ob.location=base; ob.keyframe_insert(data_path='location',frame=720)
# Note: simultaneous local rotations and exploded location keys remain editable; chapter cameras frame the mechanism.

# Scene settings and premium studio lighting.
scene.render.engine='CYCLES'
scene.cycles.samples=32; scene.cycles.use_denoising=True
scene.render.resolution_x=1280; scene.render.resolution_y=720; scene.render.resolution_percentage=100
scene.render.fps=FPS; scene.frame_start=1; scene.frame_end=END
scene.world.color=(.018,.022,.028)

def area(name, loc, power, color, shape, size, target, size_y=None):
    d=bpy.data.lights.new(name,'AREA'); d.energy=power; d.color=color; d.shape=shape; d.size=size
    if size_y and shape=='RECTANGLE': d.size_y=size_y
    o=bpy.data.objects.new(name,d); COL['10 Studio'].objects.link(o); o.location=loc; o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler(); return o
area('Key | broad cool softbox',(.30,-.28,.42),75,(.78,.86,1),'RECTANGLE',.42,(0,0,0),.18)
area('Rim | warm strip',(-.24,.08,.30),95,(1,.48,.25),'RECTANGLE',.28,(0,0,0),.05)
area('Fill | overhead',(.02,.24,.35),65,(.68,.78,1),'DISK',.28,(0,0,.02))
area('Edge | low silver',(-.30,-.12,-.02),40,(.92,.96,1),'RECTANGLE',.22,(0,0,0),.04)
area('Link | warm kicker',(.34,-.05,.28),55,(1,.72,.48),'RECTANGLE',.20,(.12,0,.08),.04)
# Camera clipping and color management.
cam.data.clip_start=.004; cam.data.clip_end=20
scene.view_settings.view_transform='AgX'; scene.view_settings.exposure=-0.8
scene.render.image_settings.file_format='PNG'; scene.render.filepath=PREVIEW_PATH
scene['design_provenance']='Procedural illustrative reference assembly. No MotionProof CAD, tolerance, variant, or simulation data was supplied.'
scene['gear_note']='20T sun / 20T planet / 60T fixed ring; 4:1 per stage; kinematic keyframes are explanatory, not contact dynamics.'
scene['variant_note']='Red display variant is a labelled illustration only; not a sampled or simulated as-manufactured assembly.'
# Start at hero reveal frame for the opening state.
scene.frame_set(300)
bpy.context.view_layer.objects.active=cam
bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
# Optional interactive-geometry GLB; excludes the presentation-only duplicate and studio.
if '--render-preview' in __import__('sys').argv:
    scene.render.engine='CYCLES'; scene.cycles.samples=12; scene.render.resolution_x=960; scene.render.resolution_y=540; scene.render.resolution_percentage=100; scene.frame_set(300); bpy.ops.render.render(write_still=True)
if '--export-glb' in __import__('sys').argv:
    import addon_utils
    addon_utils.enable('io_scene_gltf2', default_set=True)
    exportable=[]
    for coll_name in ['01 Motor','02 Gearbox Housing','03 Stage 1','04 Stage 2','05 Bearings','06 Shafts','07 Structure','08 Fasteners']:
        exportable.extend([o for o in COL[coll_name].objects if o.type=='MESH'])
    bpy.ops.object.select_all(action='DESELECT')
    for ob in exportable: ob.select_set(True)
    if exportable: bpy.context.view_layer.objects.active=exportable[0]
    glb_path=os.path.join(ROOT,'MotionProof_Illustrative_Assembly.glb')
    bpy.ops.export_scene.gltf(filepath=glb_path, export_format='GLB', use_selection=True, export_animations=True)
    print('Exported GLB:',glb_path,'Meshes:',len(exportable))
print('Saved:', BLEND_PATH)
print('Objects:',len(bpy.data.objects),'Frames:',END,'Chapters:',len(chapters))










