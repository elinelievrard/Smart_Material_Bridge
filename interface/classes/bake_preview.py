import json
import os
import bpy
from ..functions.find_mesh_pairs import find_mesh_pairs
from ..functions.export_mesh_pairs import export_pair
from ..functions.launch_substance_painter import launch_substance_painter
from ..functions.detect_vertex_colors import get_unique_vertex_colors

def get_sp_startup_folder():
    return r"C:\Program Files\Adobe\Adobe Substance 3D Painter\resources\python\startup"

def get_sp_exe_path():
    return r"C:\Program Files\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe"

class OBJECT_OT_bake_preview(bpy.types.Operator):
    bl_idname = "object.bake_preview"
    bl_label = "Bake Preview"

    def execute(self, context):
        base_folder = getattr(context.scene, "bake_base_folder", os.path.join(os.path.expanduser("~"), "MyBakeFolder"))
        bake_folder = os.path.join(base_folder, "bake_queue")
        os.makedirs(bake_folder, exist_ok=True)

        self.report({'INFO'}, f"Bake Preview started → {bake_folder}")

        # Find pairs
        pairs = find_mesh_pairs()
        if not pairs:
            self.report({'WARNING'}, "No valid _low/_high pairs found")
            return {'CANCELLED'}

        # Vertex colors debug
        obj = pairs[0][0]
        colors = get_unique_vertex_colors(obj)
        print(f"Found {len(colors)} vertex colors:", colors)
        self.report({'INFO'}, f"{len(colors)} vertex colors detected")

        # Export all pairs
        for low, high in pairs:
            print(f"Exporting pair: {low.name} ↔ {high.name}")
            export_pair(low, high, bake_folder)

        # Write config for SP to pick up
        config_json_path = os.path.join(get_sp_startup_folder(), "bake_config.json")
        with open(config_json_path, "w", encoding="utf-8") as file:
            json.dump({"bake_folder": str(bake_folder)}, file, indent=4)

        # Launch SP
        launch_substance_painter(get_sp_exe_path())

        # Start watcher
        bpy.ops.object.bake_watcher(
            'INVOKE_DEFAULT',
            bake_folder=bake_folder,
            low_mesh_name=pairs[0][0].name
        )

        self.report({'INFO'}, f"Exported {len(pairs)} pair(s) to {bake_folder}")
        return {'FINISHED'}