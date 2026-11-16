"""Render the user-supplied illustrative scene (user/MotionProof_Cinematic_Engineering.blend) as a scroll sequence.
The scene is NOT the MotionProof reference design (20T/60T, 16:1) and is labelled illustrative on the page.

    blender -b assets/blender/homepage/user/MotionProof_Cinematic_Engineering.blend -P assets/blender/homepage/render_user_scene.py -- <out-dir> [step] [samples] [WxH] [start] [end]
"""
import sys, bpy
a = sys.argv[sys.argv.index("--") + 1:]
out, step, samples = a[0], int(a[1]) if len(a) > 1 else 8, int(a[2]) if len(a) > 2 else 32
W, H = (int(v) for v in (a[3] if len(a) > 3 else "1280x720").split("x"))
s = bpy.context.scene
s.render.resolution_x, s.render.resolution_y, s.render.resolution_percentage = W, H, 100
s.cycles.samples = samples; s.cycles.use_denoising = True
p = bpy.context.preferences.addons["cycles"].preferences
try:
    p.compute_device_type = "OPTIX"; p.get_devices()
    for d in p.devices: d.use = d.type in ("OPTIX", "CUDA")
    s.cycles.device = "GPU"
except Exception as e: print("CPU render:", e)
s.view_settings.exposure = -1.3
s.frame_start = int(a[4]) if len(a) > 4 else 1; s.frame_end = int(a[5]) if len(a) > 5 else 1440; s.frame_step = step
s.render.image_settings.file_format = "PNG"; s.render.filepath = out.rstrip("/") + "/f_"
bpy.ops.render.render(animation=True)
