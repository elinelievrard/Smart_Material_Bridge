import json
import os
import shutil
import stat
import time

import bpy
from ..mesh_pairs import find_mesh_pairs, export_pair
from ..functions.launch_substance_painter import launch_substance_painter
from ..vertex_colors import get_unique_vertex_colors, clear_materials
from ..ui import RESOLUTION_TO_LOG2
from ...handle_sp_files import install_sp_files
from ...config import SP_STARTUP, SP_EXE



# ─── HELPERS ────────────────────────────────────────────────────────────────

def get_next_bake_folder(base_folder):
    # When no bake name is given, auto-increment: bake_1, bake_2, bake_3 ...
    # base_folder = "C:\Users\eline\MyBakeFolder"
    # If bake_1 and bake_2 already exist, returns: "C:\Users\eline\MyBakeFolder\bake_3"
    i = 1
    while True:
        path = os.path.join(base_folder, f"bake_{i}")
        if not os.path.exists(path):
            return path
        i += 1

def sanitize_folder_name(name: str) -> str:
    # Cleans raw user input into a safe folder name
    # "  My Bake!! " -> "My_Bake"
    # "chair low-poly v2" -> "chair_low-poly_v2"
    # "test@folder/name" -> "testfoldername"  (@ and / are stripped)
    name = name.strip()
    name = "_".join(name.split())
    name = "".join(c for c in name if c.isalnum() or c in "_-")
    return name

# Only these three subfolders are ever deleted during an overwrite — nothing else is touched
SAFE_SUBFOLDERS = {"fbx", "textures", "projects"}

def _force_remove(func, path, exc_info):
    # Fallback handler for shutil.rmtree when it hits a PermissionError
    # OneDrive marks synced folders as read-only at the folder level
    # which causes rmtree to fail on os.rmdir even if the files inside are writable
    # os.chmod with S_IWRITE forces the write bit on before retrying the delete
    os.chmod(path, stat.S_IWRITE)
    func(path)

def ensure_vertex_color_layer(obj):
    """
    Checks whether the mesh has any real vertex color data.
    If not, injects a temporary all-white FLOAT_COLOR layer so SP
    always gets valid vertex color data for ID map baking.
    Returns the injected layer name, or None if one already existed.
    """
    mesh = obj.data
    for attr in mesh.color_attributes:
        if attr.data_type in ('BYTE_COLOR', 'FLOAT_COLOR'):
            print(f"[SMB] Mesh already has color layer: {attr.name}")
            return None  # already has one, nothing injected

    print("[SMB] No vertex color data found — injecting fallback white layer")
    layer = mesh.color_attributes.new(
        name="SMB_fallback",
        type='FLOAT_COLOR',
        domain='CORNER'
    )
    # Set every loop's color to white (1, 1, 1, 1)
    for item in layer.data:
        item.color = (1.0, 1.0, 1.0, 1.0)

    return layer.name  # caller uses this to remove it after export

def safe_overwrite_bake_folder(bake_folder):
    # Deletes only fbx/, textures/, projects/ inside the given bake folder
    # bake_folder = "C:\Users\eline\MyBakeFolder\chair_1"
    # After running:
    #   "C:\Users\eline\MyBakeFolder\chair_1\fbx"       <- deleted
    #   "C:\Users\eline\MyBakeFolder\chair_1\textures"  <- deleted
    #   "C:\Users\eline\MyBakeFolder\chair_1\projects"  <- deleted
    #   "C:\Users\eline\MyBakeFolder\chair_1\notes.txt" <- left alone (not in SAFE_SUBFOLDERS)
    for sub in SAFE_SUBFOLDERS:
        sub_path = os.path.join(bake_folder, sub)
        # Safety check: make sure sub_path is actually a direct child of bake_folder
        # os.path.normpath("C:\Users\eline\MyBakeFolder\chair_1\fbx") == "C:\Users\eline\MyBakeFolder\chair_1"
        # Prevents path traversal like "../../SomeOtherFolder"
        # os.path.dirname(sub_path) gets the parent folder
        if os.path.normpath(os.path.dirname(sub_path)) != os.path.normpath(bake_folder):
            print(f"[SMB] Safety check failed for {sub_path}, skipping.")
            continue
        if os.path.isdir(sub_path):
            # onerror=_force_remove handles OneDrive read-only folders
            # without it, rmtree raises PermissionError: [WinError 5] Access is denied
            shutil.rmtree(sub_path, onerror=_force_remove)
            print(f"[SMB] Removed: {sub_path}")
        elif os.path.isfile(sub_path):
            # Unexpected — a file where a folder should be, leave it alone
            print(f"[SMB] Unexpected file at {sub_path}, skipping.")


# ─── OPERATOR ───────────────────────────────────────────────────────────────

class OBJECT_OT_bake_preview(bpy.types.Operator):
    bl_idname = "object.bake_preview"
    bl_label = "Bake Preview"

    def execute(self, context):
        # grabs the current active scene
        scene = context.scene

        # ── Validate selection ───────────────────────────────────────────────

        # context.object = the currently active object in the Blender viewport
        # e.g. <bpy_struct, Object("Cube_low")>  or  None if nothing is selected
        obj = context.object
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a low poly mesh first")
            return {'CANCELLED'}

        # obj.name = "Cube_low"   <- valid
        # obj.name = "Cube"       <- fails, no _low suffix
        if not obj.name.endswith("_low"):
            self.report({'ERROR'}, f"'{obj.name}' is not a _low mesh — select a _low object first")
            return {'CANCELLED'}

        from .bake_watcher import OBJECT_OT_bake_watcher
        if (
                # OBJECT_OT_bake_watcher._sp_process is storing Substance Painter.exe
                # poll checks if this is still running (None still running, 0 finish succesfull, 1 error)
                OBJECT_OT_bake_watcher._sp_process is not None and
                OBJECT_OT_bake_watcher._sp_process.poll() is None
        ):
            self.report({'ERROR'}, "Substance Painter is still running — wait for it to finish")
            return {'CANCELLED'}

        # SP_EXE     = "C:\Program Files\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe"
        # SP_STARTUP = "C:\Program Files\Adobe\Adobe Substance 3D Painter\resources\python\startup"
        # Both are None if Substance Painter is not installed
        if not SP_EXE or not SP_STARTUP:
            self.report({'ERROR'}, "Substance Painter not found")
            return {'CANCELLED'}

        # ── Read panel settings ──────────────────────────────────────────────

        # os.path.expanduser("~") = "C:\Users\eline"
        # full default = "C:\Users\eline\MyBakeFolder"
        # getattr is used here as a safe fallback in case the property doesn't exist yet
        base_folder = getattr(scene, "bake_base_folder",
                              os.path.join(os.path.expanduser("~"), "MyBakeFolder"))

        # resolution = "2048"  (string, from the EnumProperty in the panel)
        resolution = getattr(scene, "smb_resolution", "2048")

        # RESOLUTION_TO_LOG2 maps resolution string -> log2 int
        # "2048" -> 11,  "4096" -> 12,  "512" -> 9
        # SP uses log2 internally: 2^11 = 2048
        size_log2 = RESOLUTION_TO_LOG2.get(resolution, 11)

        # export_fbx = True / False  (BoolProperty)
        export_fbx = scene.smb_export_fbx

        # export_project is only True when BOTH checkboxes are enabled
        # If export_fbx = False, export_project is forced False even if checked
        # True and True = True,  False and True = False
        export_project = scene.smb_export_project and export_fbx

        export_textures = scene.smb_export_textures

        # overwrite = True / False
        overwrite = scene.smb_overwrite_bake

        # raw_overwrite = "C:\Users\eline\MyBakeFolder\chair_1"  or  ""  if not set
        raw_overwrite = scene.smb_overwrite_folder.strip()

        use_low_as_high = scene.smb_use_low_as_high

        # raw_name = "  My Chair  "  <- what the user typed (may have spaces/padding)
        # clean_name = "My_Chair"    <- after sanitize_folder_name
        # clean_name = ""            <- if the user left the field empty
        raw_name = getattr(scene, "smb_bake_folder_name", "").strip()
        clean_name = sanitize_folder_name(raw_name) if raw_name else ""

        # ── Resolve bake folder ──────────────────────────────────────────────
        bake_folder = None

        if overwrite and raw_overwrite:
            # os.path.normpath cleans up slashes and redundant separators
            # "C:\Users\eline\MyBakeFolder\chair_1\" -> "C:\Users\eline\MyBakeFolder\chair_1"
            norm_overwrite = os.path.normpath(raw_overwrite)
            norm_base = os.path.normpath(base_folder.strip())

            # Guard: overwrite folder must still exist on disk
            if not os.path.exists(norm_overwrite):
                self.report({'ERROR'}, "Overwrite folder no longer exists — pick a new one.")
                return {'CANCELLED'}

            # Guard: don't let the user nuke the root bake folder itself
            # e.g. norm_overwrite == norm_base == "C:\Users\eline\MyBakeFolder"
            if norm_overwrite == norm_base:
                self.report({'ERROR'}, "Cannot overwrite the root Bake Folder.")
                return {'CANCELLED'}

            # Guard: overwrite folder must be a child of base, not some random path
            # norm_base + os.sep = "C:\Users\eline\MyBakeFolder\"
            # norm_overwrite must start with that prefix to confirm it lives inside base
            if not norm_overwrite.startswith(norm_base + os.sep):
                self.report({'ERROR'}, "Overwrite folder must be inside the Bake Folder.")
                return {'CANCELLED'}

            bake_folder = norm_overwrite
            # Wipes only fbx/, textures/, projects/ — leaves anything else untouched
            safe_overwrite_bake_folder(bake_folder)

        if bake_folder is None:
            if clean_name:
                # e.g. clean_name = "chair"
                # bake_folder = "C:\Users\eline\MyBakeFolder\chair"
                bake_folder = os.path.join(base_folder, clean_name)
                if os.path.exists(bake_folder):
                    # "chair" exists -> try "chair_1", "chair_2", etc.
                    i = 1
                    while True:
                        candidate = os.path.join(base_folder, f"{clean_name}_{i}")
                        if not os.path.exists(candidate):
                            bake_folder = candidate
                            break
                        i += 1
                    self.report({'INFO'}, f"Folder already exists — '{os.path.basename(bake_folder)}' will be created")
            else:
                # No name given — auto-increment: bake_1, bake_2, bake_3 ...
                # Returns e.g. "C:\Users\eline\MyBakeFolder\bake_3"
                bake_folder = get_next_bake_folder(base_folder)

        # ── Create output subfolders ─────────────────────────────────────────
        # bake_folder     = "C:\Users\eline\MyBakeFolder\chair"
        # fbx_folder      = "C:\Users\eline\MyBakeFolder\chair\fbx"
        # textures_folder = "C:\Users\eline\MyBakeFolder\chair\textures"
        # projects_folder = "C:\Users\eline\MyBakeFolder\chair\projects"
        fbx_folder = os.path.join(bake_folder, "fbx")
        textures_folder = os.path.join(bake_folder, "textures")
        projects_folder = os.path.join(bake_folder, "projects")

        # exist_ok=True means no error if the folder already exists
        os.makedirs(fbx_folder, exist_ok=True)
        if export_textures:
            os.makedirs(textures_folder, exist_ok=True)
        if export_project:
            os.makedirs(projects_folder, exist_ok=True)

        if scene.smb_save_blend:
            blend_folder = os.path.join(bake_folder, "blender")
            os.makedirs(blend_folder, exist_ok=True)
            current_blend = bpy.data.filepath
            if current_blend:
                blend_name = os.path.splitext(os.path.basename(current_blend))[0] + ".blend"
                bpy.ops.wm.save_as_mainfile(
                    filepath=os.path.join(blend_folder, blend_name),
                    copy=True  # copy=True saves a copy without changing the current file path
                )
                print(f"[SMB] Saved blend copy to: {blend_folder}")
            else:
                self.report({'WARNING'}, "Blend file has never been saved — skipping blend copy")

        # ── Find and filter mesh pairs ───────────────────────────────────────
        # find_mesh_pairs scans bpy.data.objects for _low/_high name pairs
        # returns e.g. [(<Object "Cube_low">, <Object "Cube_high">),
        #               (<Object "Chair_low">, <Object "Chair_high">)]
        # with use_low_as_high=True: [(<Object "Cube_low">, <Object "Cube_low">), ...]
        pairs = find_mesh_pairs(use_low_as_high=use_low_as_high)
        if not pairs:
            if use_low_as_high:
                self.report({'WARNING'}, "No _low meshes found in scene")
            else:
                self.report({'WARNING'},
                            "No valid _low/_high pairs found — enable 'Use Low as High' if you have no high poly")
            return {'CANCELLED'}

        # pair_low_names = ["Cube_low", "Chair_low"]
        # We only bake the one object the user has selected, not everything in the scene
        pair_low_names = [low.name for low, high in pairs]
        if obj.name not in pair_low_names:
            self.report({'ERROR'}, f"'{obj.name}' was not matched — check scene for a corresponding _high mesh")
            return {'CANCELLED'}

        # Validate vertex colors match if enabled
        if scene.smb_use_vertex_colors and len(scene.smb_vertex_colors) > 0:
            from ..vertex_colors import get_unique_vertex_colors
            mesh_colors = get_unique_vertex_colors(obj)
            detected_colors = {
                tuple(round(item.color[i], 3) for i in range(3))
                for item in scene.smb_vertex_colors
            }
            if mesh_colors != detected_colors:
                self.report({'ERROR'}, "Vertex colors don't match this mesh — run 'Detect Vertex Colors' again")
                return {'CANCELLED'}

        # Filter down to just the selected object's pair
        # e.g. obj.name = "Chair_low"
        # pairs = [(<Object "Chair_low">, <Object "Chair_high">)]
        pairs = [(low, high) for low, high in pairs if low.name == obj.name]

        # ── Prepare mesh ─────────────────────────────────────────────────────
        # Wipe any existing materials from the low poly before exporting
        # so SP gets a clean mesh with no leftover SMB_VC_ materials on it
        for low, high in pairs:
            clear_materials(low)

        # colors = {(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.2, 0.2, 0.2)}
        # Each tuple is (R, G, B) in 0.0-1.0 range, rounded to 3 decimal places
        colors = get_unique_vertex_colors(pairs[0][0])
        print(f"Found {len(colors)} vertex colors:", colors)

        # Writes Chair_low.fbx and Chair_high.fbx into fbx_folder
        # If use_low_as_high, copies Chair_low.fbx -> Chair_high.fbx instead of re-exporting
        # Ensure every low mesh has vertex color data before export
        # SP needs it to bake the ID map — if there's none we inject a
        # temporary all-white layer and remove it after the FBX is written
        for low, high in pairs:
            injected_layer = ensure_vertex_color_layer(low)
            print(f"Exporting pair: {low.name} <- {high.name}")
            export_pair(low, high, fbx_folder)
            if injected_layer:
                low.data.color_attributes.remove(
                    low.data.color_attributes[injected_layer]
                )
                print(f"[SMB] Removed temporary color layer from {low.name}")

        # ── Build color -> smart material mapping ────────────────────────────
        color_mapping = {}
        # color_mapping result examples:
        # vertex color mode:  {"#FF0000": "Metal_Rusty", "#00FF00": "Fabric_Cotton"}
        # single mat mode:    {"#FF0000": "Steel", "#00FF00": "Steel", "#333333": "Steel"}
        # nothing assigned:   {}

        if scene.smb_use_vertex_colors:
            low_obj = pairs[0][0]
            mesh = low_obj.data

            # Find the color layer
            color_layer = None
            for attr in mesh.color_attributes:
                if attr.data_type in ('BYTE_COLOR', 'FLOAT_COLOR'):
                    color_layer = attr
                    break

            if color_layer:
                # Build a map from rounded color -> representative raw color from actual mesh data
                rounded_to_raw = {}
                precision = 3

                if color_layer.domain == 'CORNER':
                    for loop in mesh.loops:
                        c = color_layer.data[loop.index].color
                        key = tuple(round(x, precision) for x in c[:3])
                        if key not in rounded_to_raw:
                            rounded_to_raw[key] = (c[0], c[1], c[2])
                elif color_layer.domain == 'POINT':
                    for i in range(len(mesh.vertices)):
                        c = color_layer.data[i].color
                        key = tuple(round(x, precision) for x in c[:3])
                        if key not in rounded_to_raw:
                            rounded_to_raw[key] = (c[0], c[1], c[2])

                # Now match each UI item to its raw mesh color via the rounded key
                for item in scene.smb_vertex_colors:
                    if item.smart_material and item.smart_material != 'NONE':
                        rounded_key = tuple(round(item.color[i], precision) for i in range(3))
                        raw = rounded_to_raw.get(rounded_key)
                        if raw:
                            r, g, b = raw[0], raw[1], raw[2]
                        else:
                            # Fallback: use item.color directly
                            r, g, b = item.color[0], item.color[1], item.color[2]
                        key = f"{r:.6f},{g:.6f},{b:.6f}"
                        color_mapping[key] = item.smart_material
                        print(f"[SMB] Color key for {item.hex_name}: {key}")
        else:
            single_mat = scene.smb_single_smart_material
            if single_mat and single_mat != 'NONE':
                colors = get_unique_vertex_colors(pairs[0][0])
                for color in colors:
                    r, g, b = color[0], color[1], color[2]
                    key = f"{r:.6f},{g:.6f},{b:.6f}"
                    color_mapping[key] = single_mat

        print(f"[SMB] Color mapping: {color_mapping}")

        # ── Validate export preset ───────────────────────────────────────────
        preset_name = ""
        if export_textures:
            # preset_name = "PBR Metallic Roughness"  (name of the .spexp file loaded from SP)
            preset_name = scene.smb_export_preset
            if not preset_name:
                self.report({'ERROR'}, "No export preset selected")
                return {'CANCELLED'}

        # ── Write config for Substance Painter ──────────────────────────────
        # SP reads this JSON on startup via smb_bridge_startup.py -> pipeline.py -> load_working_dir.py
        # config_json_path = "C:\Program Files\Adobe\Adobe Substance 3D Painter\resources\python\startup\bake_config.json"
        config_json_path = os.path.join(SP_STARTUP, "bake_config.json")
        with open(config_json_path, "w", encoding="utf-8") as file:
            json.dump({
                # Where SP looks for the _low.fbx and _high.fbx files
                # "C:\Users\eline\MyBakeFolder\chair\fbx"
                "bake_folder": str(fbx_folder),

                # Where SP exports the final texture PNGs, or "" to skip texture export
                # "C:\Users\eline\MyBakeFolder\chair\textures"  or  ""
                "texture_out": str(textures_folder) if export_textures else "",

                # Where SP saves the .spp project file, or "" to skip
                # "C:\Users\eline\MyBakeFolder\chair\projects"  or  ""
                "projects_folder": str(projects_folder) if export_project else "",

                # {"#FF0000": "Metal_Rusty", "#00FF00": "Fabric_Cotton"}  or  {}
                "color_mapping": color_mapping,

                # 11 for 2048px,  12 for 4096px,  9 for 512px
                "size_log2": size_log2,

                # "PBR Metallic Roughness"  or  ""
                "export_preset": preset_name,

                # True  -> SP deletes the fbx/ folder after baking (user unchecked Export FBX)
                # False -> fbx/ files are kept permanently
                "delete_fbx_after": not export_fbx,

                "use_low_as_high": use_low_as_high,
            }, file, indent=4)

        # ── Launch Substance Painter ─────────────────────────────────────────
        # Copies smb_bridge_startup.py and smb_bridge/ into SP's startup folder
        # so SP auto-runs the pipeline script when it opens
        scene.smb_last_bake_time = str(time.time())
        scene.smb_last_baked_material = ""
        scene.smb_last_bake_resolution = resolution
        scene.smb_last_bake_texture_count = 0
        scene.smb_last_bake_folder = str(textures_folder)

        install_sp_files()

        # Popen launches SP as a separate process and returns immediately (non-blocking)
        # sp_process = <subprocess.Popen object at 0x...>
        # sp_process.poll() = None while SP is running,  0 (or exit code) when SP closes
        sp_process = launch_substance_painter(SP_EXE)

        # ── Start watcher ────────────────────────────────────────────────────
        if export_textures:
            # Full watcher: polls the textures folder every 2s
            # When PNG files appear and their sizes stop growing, it applies them to the mesh
            from .bake_watcher import OBJECT_OT_bake_watcher
            OBJECT_OT_bake_watcher._sp_process = sp_process
            bpy.ops.object.bake_watcher(
                'INVOKE_DEFAULT',
                bake_folder=textures_folder,    # "C:\Users\eline\MyBakeFolder\chair\textures"
                low_mesh_name=pairs[0][0].name  # "Chair_low"
            )
        else:
            # Exit-only watcher: bake_folder="" so it never looks for textures
            # Just waits for SP to close, then removes bridge files from SP startup
            self._start_exit_watcher(context, sp_process)
            self.report({'INFO'}, "Done - textures export skipped.")

        self.report({'INFO'}, f"Exported {len(pairs)} pair(s) -> {bake_folder}")
        return {'FINISHED'}

    def _start_exit_watcher(self, context, sp_process):
        # Starts the watcher with empty paths — it won't look for textures,
        # it will just wait for SP to exit and then clean up the bridge files
        if sp_process is None:
            return
        from .bake_watcher import OBJECT_OT_bake_watcher
        OBJECT_OT_bake_watcher._sp_process = sp_process
        bpy.ops.object.bake_watcher(
            'INVOKE_DEFAULT',
            bake_folder="",  # empty = exit-only mode, no texture polling
            low_mesh_name=""
        )