import bpy
import os
from ...handle_sp_files import uninstall_sp_files

CHANNEL_SUFFIX_MAP = {
    "BaseColor": ("Base Color", False),
    "Roughness":  ("Roughness",  False),
    "Metallic":   ("Metallic",   False),
    "Normal":     ("Normal",     True),
}

def get_unique_material_name(base="SMB_Material"):
    i = 1
    while True:
        name = f"{base}_{i}"
        if name not in bpy.data.materials:
            return name
        i += 1


class OBJECT_OT_bake_watcher(bpy.types.Operator):
    bl_idname = "object.bake_watcher"
    bl_label = "Bake Watcher"

    _timer = None
    _sp_process = None  # set via class variable before invoke, not a bpy prop

    bake_folder: bpy.props.StringProperty()
    low_mesh_name: bpy.props.StringProperty()

    def _set_status(self, context, message):
        dots = "." * ((self._tick % 3) + 1)
        full = f"{message}{dots}"
        context.scene.smb_status = full
        context.workspace.status_text_set(f"SMB: {full}")
        context.window.cursor_set('WAIT')
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _clear_status(self, context):
        context.scene.smb_status = ""
        context.workspace.status_text_set(None)
        context.window.cursor_set('DEFAULT')
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    def _cleanup_sp_files(self):
        """Uninstall SP startup files now that SP has finished."""
        try:
            uninstall_sp_files()
            print("[Watcher] SP startup files removed")
        except Exception as e:
            print(f"[Watcher] Could not remove SP files: {e}")

    def modal(self, context, event):
        if event.type == 'TIMER':
            self._tick += 1

            # Check if SP process has exited — if so, clean up files regardless
            # of whether textures appeared yet (SP may have crashed or been closed early)
            sp_exited = (
                OBJECT_OT_bake_watcher._sp_process is not None and
                OBJECT_OT_bake_watcher._sp_process.poll() is not None
            )

            if not self.bake_folder:
                all_pngs = []
            else:
                all_pngs = [
                    f for f in os.listdir(self.bake_folder)
                    if f.endswith(".png")
                ]

            if all_pngs:
                total_size = sum(
                    os.path.getsize(os.path.join(self.bake_folder, f))
                    for f in all_pngs
                )
                if total_size == self._last_size and total_size > 0:
                    self._clear_status(context)
                    print("[Watcher] Export complete, applying textures")
                    self.apply_textures(context)
                    context.window_manager.event_timer_remove(self._timer)
                    self._cleanup_sp_files()
                    OBJECT_OT_bake_watcher._sp_process = None
                    return {'FINISHED'}
                else:
                    self._last_size = total_size
                    self._set_status(context, "Exporting textures")

            elif sp_exited:
                # SP closed but no textures arrived — user may have cancelled or
                # export was skipped. Clean up and stop watching.
                self._clear_status(context)
                print("[Watcher] SP exited without producing textures — stopping watcher")
                context.window_manager.event_timer_remove(self._timer)
                self._cleanup_sp_files()
                OBJECT_OT_bake_watcher._sp_process = None
                self.report({'WARNING'}, "SMB: SP closed without exporting textures")
                return {'FINISHED'}

            else:
                self._set_status(context, "Baking in Substance Painter")

        return {'PASS_THROUGH'}

    def apply_textures(self, context):
        obj = bpy.data.objects.get(self.low_mesh_name)
        if not obj:
            print(f"[Watcher] Object not found: {self.low_mesh_name}")
            return

        all_files = os.listdir(self.bake_folder)

        mat_name = get_unique_material_name()
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 0)
        links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

        x_offset = -800
        matched_any = False

        for channel, (bsdf_input, needs_normal_node) in CHANNEL_SUFFIX_MAP.items():
            match = next(
                (f for f in all_files if channel in f and f.endswith(".png")), None
            )
            if not match:
                print(f"[Watcher] No file found for channel: {channel}, skipping")
                continue

            matched_any = True
            tex_path = os.path.join(self.bake_folder, match)
            image = bpy.data.images.load(tex_path, check_existing=True)
            tex_node = nodes.new("ShaderNodeTexImage")
            tex_node.image = image
            tex_node.location = (x_offset, 0)

            if needs_normal_node:
                image.colorspace_settings.name = 'Non-Color'
                normal_node = nodes.new("ShaderNodeNormalMap")
                normal_node.location = (x_offset + 300, 0)
                links.new(tex_node.outputs['Color'], normal_node.inputs['Color'])
                links.new(normal_node.outputs['Normal'], bsdf.inputs['Normal'])
            else:
                if channel != "BaseColor":
                    image.colorspace_settings.name = 'Non-Color'
                links.new(tex_node.outputs['Color'], bsdf.inputs[bsdf_input])

            x_offset += 300
            print(f"[Watcher] Connected {channel} → {bsdf_input}")

        known_channels = set(CHANNEL_SUFFIX_MAP.keys())
        for f in all_files:
            if not f.endswith(".png"):
                continue
            if any(ch in f for ch in known_channels):
                continue
            tex_path = os.path.join(self.bake_folder, f)
            image = bpy.data.images.load(tex_path, check_existing=True)
            tex_node = nodes.new("ShaderNodeTexImage")
            tex_node.image = image
            tex_node.location = (x_offset, 0)
            image.colorspace_settings.name = 'Non-Color'
            x_offset += 300
            print(f"[Watcher] Loaded extra texture: {f} (not auto-connected, packed map)")

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
            self.report({'INFO'}, f"SMB: Material '{mat_name}' applied!")
        else:
            print(f"[Watcher] No standard channels found — textures loaded as orphan nodes")
            self.report({'INFO'}, f"SMB: Textures loaded (packed preset — connect manually)")

    def invoke(self, context, event):
        self._tick = 0
        self._last_size = -1
        self._set_status(context, "Starting Substance Painter")
        self._timer = context.window_manager.event_timer_add(2.0, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self._clear_status(context)
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        # Clean up SP files if the user cancels the watcher manually
        self._cleanup_sp_files()
        OBJECT_OT_bake_watcher._sp_process = None