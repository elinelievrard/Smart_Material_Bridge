# 🔹 Export function
import os
import bpy


def export_pair(low_obj, high_obj, folder):
    os.makedirs(folder, exist_ok=True)  # ensure folder exists

    bpy.ops.object.select_all(action='DESELECT')

    # Export Low Poly
    low_obj.select_set(True)
    low_path = os.path.join(folder, low_obj.name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=str(low_path), use_selection=True)
    low_obj.select_set(False)

    # Export High Poly
    high_obj.select_set(True)
    high_path = os.path.join(folder, high_obj.name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=str(high_path), use_selection=True)
    high_obj.select_set(False)

    print(f"Exported: {low_path} and {high_path}")