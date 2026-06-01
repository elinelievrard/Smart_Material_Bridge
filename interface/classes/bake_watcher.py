# =============================================================================
# Blender and Substance Painter are separate applications, so Blender
# cannot directly know when SP has finished its work. This watcher acts
# as a bridge between them.
#
# How it works:
#
# - Runs a timer event every 2 seconds (non-blocking modal operator)
# - Monitors the export folder for new PNG texture files
# - Waits until files appear (indicating SP has started exporting)
# - Tracks total file size and waits until it stops increasing (ensures export is fully finished, not mid-write)
# - Detects early exit of Substance Painter (cancel/crash case)
# - Once export is complete:
#     • Loads textures into Blender
#     • Creates a new Principled BSDF material
#     • Auto-connects BaseColor / Roughness / Metallic / Normal maps
# - Cleans up bridge startup files used by Substance Painter
#
# Blender uses a "modal operator" so this runs without freezing the UI.
# Instead of looping, it wakes up on timer events while the UI stays responsive.
# =============================================================================
import time

import bpy
import os
from ...handle_sp_files import uninstall_sp_files

# Maps texture file name suffixes to their Principled BSDF input names
# The bool indicates whether the channel needs a Normal Map node in between
# e.g. "Chair_low_BaseColor.png" -> ("Base Color", False) -> direct link to BSDF
# e.g. "Chair_low_Normal.png"    -> ("Normal", True)      -> needs Normal Map node between texture and BSDF
CHANNEL_SUFFIX_MAP = {
    "BaseColor": ("Base Color", False),
    "Roughness":  ("Roughness",  False),
    "Metallic":   ("Metallic",   False),
    "Normal":     ("Normal",     True),
}

def get_unique_material_name(base="SMB_Material"):
    # Increments until it finds a name not already used in this .blend file
    # If SMB_Material_1 and SMB_Material_2 exist, returns "SMB_Material_3"
    # bpy.data.materials is a collection of all materials in the current .blend
    # "SMB_Material_1" in bpy.data.materials = True / False
    i = 1
    while True:
        name = f"{base}_{i}"
        if name not in bpy.data.materials:
            return name
        i += 1


class OBJECT_OT_bake_watcher(bpy.types.Operator):
    _last_bake_completed_time = None

    bl_idname = "object.bake_watcher"
    bl_label = "Bake Watcher"

    _timer = None
    # SP process handle stored as a class variable so bake_preview.py can set it
    # before invoking this operator — bpy props can't hold Python objects like Popen
    # _sp_process = <subprocess.Popen object>  while SP is running
    # _sp_process = None                        after SP exits or on first run
    _sp_process = None

    # bake_folder   = "C:\Users\eline\MyBakeFolder\chair\textures"  or  ""  (exit-only mode)
    # low_mesh_name = "Chair_low"  or  ""  (exit-only mode)
    bake_folder: bpy.props.StringProperty()
    low_mesh_name: bpy.props.StringProperty()

    # ── Status helpers ───────────────────────────────────────────────────────

    def _set_status(self, context, message):
        # self._tick = 0,1,2,3,4... increments every timer event (every 2 seconds)
        # self._tick % 3 cycles through 0,1,2,0,1,2...
        # dots = "." / ".." / "..."  -> gives the animated "..." effect in the panel
        dots = "." * ((self._tick % 3) + 1)
        # full = "Baking in Substance Painter."  /  "Baking in Substance Painter.."  etc.
        full = f"{message}{dots}"
        # Shows in the SMB panel box
        context.scene.smb_status = full
        # Shows in the bottom-left status bar of Blender: "SMB: Baking in Substance Painter..."
        context.workspace.status_text_set(f"SMB: {full}")
        # Changes the mouse cursor to a spinning wait cursor while SP is running
        context.window.cursor_set('WAIT')
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                # Tells Blender this area needs to redraw so the panel updates live
                area.tag_redraw()

    def _clear_status(self, context):
        # Resets everything _set_status changed back to defaults
        context.scene.smb_status = ""
        context.workspace.status_text_set(None)   # None removes the status bar text entirely
        context.window.cursor_set('DEFAULT')       # back to normal arrow cursor
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _cleanup_sp_files(self):
        # Removes smb_bridge_startup.py and smb_bridge/ from SP's startup folder
        # Called whenever SP exits, successfully or not, so we don't leave stale scripts
        try:
            uninstall_sp_files()
            print("[Watcher] SP startup files removed")
        except Exception as e:
            print(f"[Watcher] Could not remove SP files: {e}")

    # ── Modal loop ───────────────────────────────────────────────────────────

    def modal(self, context, event):
        # Blender calls this every time an event fires while the operator is running
        # event.type = 'TIMER' fires every 2 seconds (set in invoke below)
        # event.type can also be 'MOUSEMOVE', 'KEYDOWN' etc. — we ignore those
        if event.type == 'TIMER':
            self._tick += 1

            # poll() returns None if the process is still running
            # poll() returns 0 (or another exit code) the moment SP closes
            sp_exited = (
                OBJECT_OT_bake_watcher._sp_process is not None and
                OBJECT_OT_bake_watcher._sp_process.poll() is not None
            )

            # self.bake_folder = "" means exit-only mode — skip all texture polling
            if not self.bake_folder:
                all_pngs = []
            else:
                # os.listdir returns all filenames in the folder as strings
                # e.g. ["Chair_low_BaseColor.png", "Chair_low_Normal.png", "Chair_low_Roughness.png"]
                # or   []  if SP hasn't exported yet
                all_pngs = [
                    f for f in os.listdir(self.bake_folder)
                    if f.endswith(".png")
                ]

            if all_pngs:
                # Sum up total bytes of all PNG files in the textures folder
                # e.g. 3 files at 2MB each = 6291456 bytes
                # While SP is still writing, this number grows each poll
                # When it stays the same two polls in a row, export is done
                total_size = sum(
                    os.path.getsize(os.path.join(self.bake_folder, f))
                    for f in all_pngs
                )
                if total_size == self._last_size and total_size > 0:
                    # Size hasn't changed since last poll — files are fully written
                    # self._last_size starts at -1 so 0-byte files don't trigger this
                    self._clear_status(context)
                    print("[Watcher] Export complete, applying textures")
                    self.apply_textures(context)
                    context.window_manager.event_timer_remove(self._timer)
                    self._cleanup_sp_files()
                    OBJECT_OT_bake_watcher._sp_process = None
                    return {'FINISHED'}
                else:
                    # Size changed — SP is still writing files, keep waiting
                    self._last_size = total_size
                    self._set_status(context, "Exporting textures")

            elif sp_exited:
                # SP has closed but no PNGs appeared — user cancelled inside SP, or SP crashed
                self._clear_status(context)
                print("[Watcher] SP exited without producing textures — stopping watcher")
                context.window_manager.event_timer_remove(self._timer)
                self._cleanup_sp_files()
                OBJECT_OT_bake_watcher._sp_process = None
                OBJECT_OT_bake_watcher._last_bake_completed_time = time.time()
                self.report({'WARNING'}, "SMB: SP closed without exporting textures")
                return {'FINISHED'}

            else:
                # No PNGs yet and SP is still open — still baking
                self._set_status(context, "Baking in Substance Painter")

        # PASS_THROUGH lets all other Blender events (mouse, keyboard etc.) work normally
        # FINISHED would stop the modal — we only return that when we're truly done
        return {'PASS_THROUGH'}

    # ── Texture application ──────────────────────────────────────────────────

    def apply_textures(self, context):
        # self.low_mesh_name = "Chair_low"
        # bpy.data.objects.get returns the object or None if not found
        obj = bpy.data.objects.get(self.low_mesh_name)
        if not obj:
            print(f"[Watcher] Object not found: {self.low_mesh_name}")
            return

        # all_files = ["Chair_low_BaseColor.png", "Chair_low_Normal.png",
        #              "Chair_low_Roughness.png", "Chair_low_Metallic.png"]
        all_files = os.listdir(self.bake_folder)

        # Creates a new material with a unique name, e.g. "SMB_Material_1"
        mat_name = get_unique_material_name()
        mat = bpy.data.materials.new(name=mat_name)
        # use_nodes = True enables the node graph for this material
        mat.use_nodes = True

        # Assign to slot 0 if one exists, otherwise append a new slot
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        # Clear default nodes (Principled BSDF + Material Output that Blender adds automatically)
        nodes.clear()

        # Build the base shader from scratch
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 0)
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        # x_offset tracks where to place each new texture node so they don't overlap
        # starts at -800 and moves right by 300 for each channel
        # e.g. BaseColor node at (-800, 0), Roughness at (-500, 0), Metallic at (-200, 0)
        x_offset = -800
        matched_any = False

        for channel, (bsdf_input, needs_normal_node) in CHANNEL_SUFFIX_MAP.items():
            # channel = "BaseColor", bsdf_input = "Base Color", needs_normal_node = False
            # channel = "Normal",    bsdf_input = "Normal",     needs_normal_node = True

            # next() with a default of None returns the first matching filename or None
            # e.g. channel = "BaseColor"
            # match = "Chair_low_BaseColor.png"  if found
            # match = None                        if not found
            match = next(
                (f for f in all_files if channel in f and f.endswith(".png")), None
            )
            if not match:
                print(f"[Watcher] No file found for channel: {channel}, skipping")
                continue

            matched_any = True
            # tex_path = "C:\Users\eline\MyBakeFolder\chair\textures\Chair_low_BaseColor.png"
            tex_path = os.path.join(self.bake_folder, match)
            # Loads the image into bpy.data.images — check_existing=True reuses it if already loaded
            image = bpy.data.images.load(tex_path, check_existing=True)
            tex_node = nodes.new("ShaderNodeTexImage")
            tex_node.image = image
            tex_node.location = (x_offset, 0)

            if needs_normal_node:
                # Normal maps must go: Texture -> Normal Map node -> BSDF Normal input
                # Non-Color because normal maps are data, not sRGB color
                image.colorspace_settings.name = 'Non-Color'
                normal_node = nodes.new("ShaderNodeNormalMap")
                normal_node.location = (x_offset + 300, 0)
                links.new(tex_node.outputs['Color'], normal_node.inputs['Color'])
                links.new(normal_node.outputs['Normal'], bsdf.inputs['Normal'])
            else:
                # Roughness and Metallic are raw data values, not colors — set Non-Color
                # BaseColor is the only one that stays sRGB (default), so we skip it
                if channel != "BaseColor":
                    image.colorspace_settings.name = 'Non-Color'
                # Direct link: Texture Color output -> BSDF input (e.g. "Roughness")
                links.new(tex_node.outputs['Color'], bsdf.inputs[bsdf_input])

            x_offset += 300
            print(f"[Watcher] Connected {channel} -> {bsdf_input}")

        # Handle any extra PNGs that don't match BaseColor/Roughness/Metallic/Normal
        # These come from packed export presets (e.g. "Chair_low_AO.png", "Chair_low_Emissive.png")
        # They get loaded as orphan texture nodes — visible in the shader editor but not auto-connected
        known_channels = set(CHANNEL_SUFFIX_MAP.keys())
        # known_channels = {"BaseColor", "Roughness", "Metallic", "Normal"}
        for f in all_files:
            if not f.endswith(".png"):
                continue
            # Skip files already handled above
            # any("BaseColor" in "Chair_low_BaseColor.png", ...) = True -> skip
            if any(ch in f for ch in known_channels):
                continue
            tex_path = os.path.join(self.bake_folder, f)
            image = bpy.data.images.load(tex_path, check_existing=True)
            tex_node = nodes.new("ShaderNodeTexImage")
            tex_node.image = image
            tex_node.location = (x_offset, 0)
            # Treat all unknown maps as Non-Color data (safe default)
            image.colorspace_settings.name = 'Non-Color'
            x_offset += 300
            print(f"[Watcher] Loaded extra texture: {f} (not auto-connected, packed map)")

        # Force-reload all images in the material
        # Blender caches images by path — if SP overwrote them since last bake,
        # reload() forces Blender to re-read from disk instead of showing the stale version
        for node in mat.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                try:
                    node.image.reload()
                    print(f"[Watcher] Reloaded image: {node.image.name}")
                except Exception as e:
                    print(f"[Watcher] Could not reload image: {e}")

        if matched_any:
            print(f"[Watcher] Applied material '{mat_name}' to {self.low_mesh_name}")
            context.scene.smb_last_baked_material = mat_name
            context.scene.smb_last_bake_texture_count = len([
                n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE'
            ])
            self.report({'INFO'}, f"SMB: Material '{mat_name}' applied!")
        else:
            # No standard channels matched at all — likely a fully packed/custom preset
            # Textures are still loaded in the shader editor, just not wired up
            print(f"[Watcher] No standard channels found — textures loaded as orphan nodes")
            self.report({'INFO'}, f"SMB: Textures loaded (packed preset — connect manually)")

        OBJECT_OT_bake_watcher._last_bake_completed_time = time.time()

    # ── Invoke / Cancel ──────────────────────────────────────────────────────

    def invoke(self, context, event):
        self._tick = 0
        # _last_size starts at -1 so a total_size of 0 never falsely triggers "export done"
        self._last_size = -1
        self._set_status(context, "Starting Substance Painter")
        # event_timer_add fires a TIMER event every 2.0 seconds on the given window
        # returns a timer handle we store so we can remove it later with event_timer_remove
        self._timer = context.window_manager.event_timer_add(2.0, window=context.window)
        # Registers this operator as a modal operator — Blender now calls modal() on every event
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        # Called when the user presses Escape or another operator cancels this one
        self._clear_status(context)
        if self._timer:
            # Stops the 2-second timer so modal() stops being called
            context.window_manager.event_timer_remove(self._timer)
        self._cleanup_sp_files()
        OBJECT_OT_bake_watcher._sp_process = None