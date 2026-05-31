import bpy
import os

def find_mesh_pairs(use_low_as_high=False):
    # [
    #     (Cube_low, Cube_high),
    #     (Chair_low, Chair_high),
    # ]

    pairs = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        if obj.name.endswith("_low"):
            if use_low_as_high:
                pairs.append((obj, obj))
            else:
                base_name = obj.name[:-4]
                high_name = base_name + "_high"
                high_obj = bpy.data.objects.get(high_name)
                if high_obj and high_obj.type == 'MESH':
                    pairs.append((obj, high_obj))
    return pairs

def export_pair(low_obj, high_obj, fbx_folder):
    os.makedirs(fbx_folder, exist_ok=True)

    bpy.ops.object.select_all(action='DESELECT')

    # Store and force visibility so hidden objects export correctly
    low_hide_viewport = low_obj.hide_viewport
    low_hide_render = low_obj.hide_render
    # more broad visibility check
    low_hide_get = low_obj.hide_get()
    low_obj.hide_viewport = False
    low_obj.hide_render = False
    low_obj.hide_set(False)

    low_obj.select_set(True)
    low_path = os.path.join(fbx_folder, low_obj.name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=str(low_path), use_selection=True)
    low_obj.select_set(False)

    # Restore low visibility
    low_obj.hide_viewport = low_hide_viewport
    low_obj.hide_render = low_hide_render
    low_obj.hide_set(low_hide_get)

    # If low and high are the same object, just copy the file instead of re-exporting
    high_path = os.path.join(fbx_folder, high_obj.name + ".fbx")
    if low_obj == high_obj:
        import shutil
        # Derive the expected high name: replace _low with _high in the filename
        base_name = low_obj.name[:-4]  # strip "_low"
        high_filename = base_name + "_high.fbx"
        high_path = os.path.join(fbx_folder, high_filename)
        shutil.copy2(low_path, high_path)
        print(f"[SMB] Copied low as high: {high_path}")
    else:
        # Store ALL visibility states including view layer exclusion
        high_hide_viewport = high_obj.hide_viewport
        high_hide_render = high_obj.hide_render
        high_hide_get = high_obj.hide_get()

        high_obj.hide_viewport = False
        high_obj.hide_render = False
        high_obj.hide_set(False)  # unhides from view layer

        high_obj.select_set(True)
        bpy.ops.export_scene.fbx(filepath=str(high_path), use_selection=True)
        high_obj.select_set(False)

        # Restore all visibility states
        high_obj.hide_viewport = high_hide_viewport
        high_obj.hide_render = high_hide_render
        high_obj.hide_set(high_hide_get)

    print(f"[SMB] Exported: {low_path}, {high_path}")