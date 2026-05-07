# bake_watcher.py
import bpy
import os

class OBJECT_OT_bake_watcher(bpy.types.Operator):
    bl_idname = "object.bake_watcher"
    bl_label = "Bake Watcher"

    _timer = None
    bake_folder: bpy.props.StringProperty()
    low_mesh_name: bpy.props.StringProperty()

    def modal(self, context, event):
        if event.type == 'TIMER':
            normal_map_files = [f for f in os.listdir(self.bake_folder) if f.endswith("_normal.png")]

            if normal_map_files:
                normal_map_path = os.path.join(self.bake_folder, normal_map_files[0])
                print(f"Normal map ready: {normal_map_files[0]}")
                self.report({'INFO'}, f"Bake finished: {normal_map_files[0]}")

                self.apply_normal_map(context, normal_map_path)

                context.window_manager.event_timer_remove(self._timer)
                return {'FINISHED'}
            else:
                print("Waiting for normal map...")

        return {'PASS_THROUGH'}

    def apply_normal_map(self, context, normal_map_path):
        obj = bpy.data.objects.get(self.low_mesh_name)
        if not obj:
            print(f"[Watcher] Object not found: {self.low_mesh_name}")
            return

        mat = obj.active_material
        if not mat or not mat.use_nodes:
            print("[Watcher] No node material found")
            return

        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Add or reuse image texture node
        tex_node = nodes.get("SMB_NormalMap")
        if not tex_node:
            tex_node = nodes.new("ShaderNodeTexImage")
            tex_node.name = "SMB_NormalMap"
            tex_node.location = (-400, 0)

        # Load the baked image
        image = bpy.data.images.load(normal_map_path, check_existing=True)
        image.colorspace_settings.name = 'Non-Color'
        tex_node.image = image

        # Add or reuse normal map node
        normal_node = nodes.get("SMB_NormalMapNode")
        if not normal_node:
            normal_node = nodes.new("ShaderNodeNormalMap")
            normal_node.name = "SMB_NormalMapNode"
            normal_node.location = (-200, 0)

        # Find BSDF and connect
        bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf:
            links.new(tex_node.outputs['Color'], normal_node.inputs['Color'])
            links.new(normal_node.outputs['Normal'], bsdf.inputs['Normal'])
            print(f"[Watcher] Normal map applied to {self.low_mesh_name}")

    def invoke(self, context, event):
        self._timer = context.window_manager.event_timer_add(2.0, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)