import bpy

class OBJECT_PT_bake_panel(bpy.types.Panel):
    bl_label = "Bake Tool"
    bl_idname = "OBJECT_PT_bake_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Bake"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "bake_base_folder")   # Base folder selector
        layout.operator("object.bake_preview")   # Bake button
        layout.operator("object.detect_vertex_colors") # Detect vertex colors button