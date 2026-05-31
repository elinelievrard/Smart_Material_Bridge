import json
import os
import shutil
import bpy
from ..mesh_pairs import find_mesh_pairs, export_pair
from ..functions.launch_substance_painter import launch_substance_painter
from ..vertex_colors import get_unique_vertex_colors, clear_materials
from ..ui import RESOLUTION_TO_LOG2
from ...handle_sp_files import install_sp_files

from ...config import SP_STARTUP, SP_EXE


def get_next_bake_folder(base_folder):
    i = 1
    while True:
        path = os.path.join(base_folder, f"bake_{i}")
        if not os.path.exists(path):
            return path
        i += 1

def sanitize_folder_name(name: str) -> str:
    name = name.strip()
    name = "_".join(name.split())
    name = "".join(c for c in name if c.isalnum() or c in "_-")
    return name

SAFE_SUBFOLDERS = {"fbx", "textures", "projects"}

def safe_overwrite_bake_folder(bake_folder):
    for sub in SAFE_SUBFOLDERS:
        sub_path = os.path.join(bake_folder, sub)
        if os.path.normpath(os.path.dirname(sub_path)) != os.path.normpath(bake_folder):
            print(f"[SMB] Safety check failed for {sub_path}, skipping.")
            continue
        if os.path.isdir(sub_path):
            shutil.rmtree(sub_path)
            print(f"[SMB] Removed: {sub_path}")
        elif os.path.isfile(sub_path):
            print(f"[SMB] Unexpected file at {sub_path}, skipping.")

class OBJECT_OT_bake_preview(bpy.types.Operator):
    bl_idname = "object.bake_preview"
    bl_label = "Bake Preview"

    def execute(self, context):
        scene = context.scene

        # Require a selected low poly mesh
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a low poly mesh first")
            return {'CANCELLED'}
        if not obj.name.endswith("_low"):
            self.report({'ERROR'}, f"'{obj.name}' is not a _low mesh — select a _low object first")
            return {'CANCELLED'}
        if not SP_EXE or not SP_STARTUP:
            self.report({'ERROR'}, "Substance Painter not found")
            return {'CANCELLED'}

        base_folder = getattr(scene, "bake_base_folder",
                              os.path.join(os.path.expanduser("~"), "MyBakeFolder"))
        resolution = getattr(scene, "smb_resolution", "2048")
        size_log2 = RESOLUTION_TO_LOG2.get(resolution, 11)
        export_fbx = scene.smb_export_fbx
        export_project = scene.smb_export_project and export_fbx
        export_textures = scene.smb_export_textures
        overwrite = scene.smb_overwrite_bake
        raw_overwrite = scene.smb_overwrite_folder.strip()
        use_low_as_high = scene.smb_use_low_as_high

        raw_name = getattr(scene, "smb_bake_folder_name", "").strip()
        clean_name = sanitize_folder_name(raw_name) if raw_name else ""

        bake_folder = None

        if overwrite and raw_overwrite:
            norm_overwrite = os.path.normpath(raw_overwrite)
            norm_base = os.path.normpath(base_folder.strip())

            if not os.path.exists(norm_overwrite):
                self.report({'ERROR'}, "Overwrite folder no longer exists — pick a new one.")
                return {'CANCELLED'}
            if norm_overwrite == norm_base:
                self.report({'ERROR'}, "Cannot overwrite the root Bake Folder.")
                return {'CANCELLED'}
            if not norm_overwrite.startswith(norm_base + os.sep):
                self.report({'ERROR'}, "Overwrite folder must be inside the Bake Folder.")
                return {'CANCELLED'}

            bake_folder = norm_overwrite
            safe_overwrite_bake_folder(bake_folder)

        if bake_folder is None:
            if clean_name:
                bake_folder = os.path.join(base_folder, clean_name)
                if os.path.exists(bake_folder):
                    # Auto-increment: cube_1, cube_2, etc.
                    i = 1
                    while True:
                        candidate = os.path.join(base_folder, f"{clean_name}_{i}")
                        if not os.path.exists(candidate):
                            bake_folder = candidate
                            break
                        i += 1
                    self.report({'INFO'}, f"Folder already exists — '{os.path.basename(bake_folder)}' will be created")
            else:
                bake_folder = get_next_bake_folder(base_folder)

        fbx_folder = os.path.join(bake_folder, "fbx")
        textures_folder = os.path.join(bake_folder, "textures")
        projects_folder = os.path.join(bake_folder, "projects")

        os.makedirs(fbx_folder, exist_ok=True)
        if export_textures:
            os.makedirs(textures_folder, exist_ok=True)
        if export_project:
            os.makedirs(projects_folder, exist_ok=True)

        pairs = find_mesh_pairs(use_low_as_high=use_low_as_high)
        if not pairs:
            if use_low_as_high:
                self.report({'WARNING'}, "No _low meshes found in scene")
            else:
                self.report({'WARNING'},
                            "No valid _low/_high pairs found — enable 'Use Low as High' if you have no high poly")
            return {'CANCELLED'}

        # After finding all pairs, filter to just the selected one
        pair_low_names = [low.name for low, high in pairs]
        if obj.name not in pair_low_names:
            self.report({'ERROR'}, f"'{obj.name}' was not matched — check scene for a corresponding _high mesh")
            return {'CANCELLED'}

        # Only bake the selected pair
        selected_pair = [(low, high) for low, high in pairs if low.name == obj.name]
        pairs = selected_pair  # ← overwrite with just the one pair

        # Clear materials from all low meshes before baking
        for low, high in pairs:
            clear_materials(low)

        colors = get_unique_vertex_colors(pairs[0][0])
        print(f"Found {len(colors)} vertex colors:", colors)

        for low, high in pairs:
            print(f"Exporting pair: {low.name} <- {high.name}")
            export_pair(low, high, fbx_folder)

        color_mapping = {}
        if scene.smb_use_vertex_colors:
            for item in scene.smb_vertex_colors:
                if item.smart_material and item.smart_material != 'NONE':
                    color_mapping[item.hex_name] = item.smart_material
        else:
            single_mat = scene.smb_single_smart_material
            if single_mat and single_mat != 'NONE':
                colors = get_unique_vertex_colors(pairs[0][0])
                for color in colors:
                    hex_name = '#{:02X}{:02X}{:02X}'.format(
                        int(color[0] * 255),
                        int(color[1] * 255),
                        int(color[2] * 255)
                    )
                    color_mapping[hex_name] = single_mat

        print(f"[SMB] Color mapping: {color_mapping}")

        preset_name = ""
        if export_textures:
            preset_name = scene.smb_export_preset
            if not preset_name:
                self.report({'ERROR'}, "No export preset selected")
                return {'CANCELLED'}

        config_json_path = os.path.join(SP_STARTUP, "bake_config.json")
        with open(config_json_path, "w", encoding="utf-8") as file:
            json.dump({
                "bake_folder": str(fbx_folder),
                "texture_out": str(textures_folder) if export_textures else "",
                "projects_folder": str(projects_folder) if export_project else "",
                "color_mapping": color_mapping,
                "size_log2": size_log2,
                "export_preset": preset_name,
                "delete_fbx_after": not export_fbx,
            }, file, indent=4)

        install_sp_files()
        sp_process = launch_substance_painter(SP_EXE)

        if export_textures:
            from .bake_watcher import OBJECT_OT_bake_watcher
            OBJECT_OT_bake_watcher._sp_process = sp_process
            bpy.ops.object.bake_watcher(
                'INVOKE_DEFAULT',
                bake_folder=textures_folder,
                low_mesh_name=pairs[0][0].name
            )
        else:
            self._start_exit_watcher(context, sp_process)
            self.report({'INFO'}, "Done - textures export skipped.")

        self.report({'INFO'}, f"Exported {len(pairs)} pair(s) -> {bake_folder}")
        return {'FINISHED'}

    def _start_exit_watcher(self, context, sp_process):
        if sp_process is None:
            return
        from .bake_watcher import OBJECT_OT_bake_watcher
        OBJECT_OT_bake_watcher._sp_process = sp_process
        bpy.ops.object.bake_watcher(
            'INVOKE_DEFAULT',
            bake_folder="",
            low_mesh_name=""
        )