import bpy
import os

RESOLUTION_ITEMS = [
    ('512',  '512',   ''),
    ('1024', '1024',  ''),
    ('2048', '2048',  ''),
    ('4096', '4096',  ''),
    ('8192', '8192',  ''),
]

RESOLUTION_TO_LOG2 = {
    '512':  9,
    '1024': 10,
    '2048': 11,
    '4096': 12,
    '8192': 13,
}

class OBJECT_PT_bake_panel(bpy.types.Panel):
    bl_label = "Smart Material Bridge"
    bl_idname = "OBJECT_PT_bake_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SMB'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "bake_base_folder", text="Bake Folder")
        layout.prop(scene, "smb_bake_folder_name", text="Bake Name")

        raw_name = scene.smb_bake_folder_name.strip()

        if raw_name and not scene.smb_overwrite_bake:
            clean_name = "_".join(raw_name.split())
            clean_name = "".join(c for c in clean_name if c.isalnum() or c in "_-")
            existing_path = os.path.join(scene.bake_base_folder, clean_name)
            if os.path.exists(existing_path):
                # Figure out what the actual new name will be
                i = 1
                while os.path.exists(os.path.join(scene.bake_base_folder, f"{clean_name}_{i}")):
                    i += 1
                new_name = f"{clean_name}_{i}"
                box = layout.box()
                box.label(
                    text=f"Folder already exists — will be saved as '{new_name}'",
                    icon='INFO'
                )

        layout.prop(scene, "smb_resolution", text="Resolution")

        col = layout.column(align=True)
        col.prop(scene, "smb_export_fbx")

        row = col.row(align=True)
        row.enabled = scene.smb_export_fbx
        row.prop(scene, "smb_export_project")

        col.prop(scene, "smb_export_textures")

        effective_project_export = scene.smb_export_project and scene.smb_export_fbx

        if (
            not scene.smb_export_fbx and
            not effective_project_export and
            not scene.smb_export_textures
        ):
            layout.separator()
            box = layout.box()
            box.alert = True
            box.label(text="Nothing can be exported.", icon='ERROR')
            box.label(text="Enable at least one export option.")
            return

        if scene.smb_export_textures:
            row = col.row(align=True)
            row.prop(scene, "smb_export_preset", text="Preset")

        layout.separator()
        layout.prop(scene, "smb_overwrite_bake")

        if scene.smb_overwrite_bake:
            box = layout.box()
            overwrite_col = box.column(align=True)

            row = overwrite_col.row(align=True)
            row.prop(scene, "smb_overwrite_folder", text="")
            row.operator("smb.refresh_overwrite_folder", text="", icon='FILE_REFRESH')

            overwrite = scene.smb_overwrite_folder.strip()
            base = scene.bake_base_folder.strip()

            overwrite_col.separator()

            if not overwrite:
                has_subfolders = False
                if base and os.path.exists(base):
                    has_subfolders = any(
                        os.path.isdir(os.path.join(base, d))
                        for d in os.listdir(base)
                    )
                if has_subfolders:
                    overwrite_col.label(text="Pick a folder to overwrite.", icon='INFO')
                else:
                    overwrite_col.label(text="Nothing to overwrite.", icon='INFO')
            else:
                norm_overwrite = os.path.normpath(overwrite)
                norm_base = os.path.normpath(base)

                if not os.path.exists(norm_overwrite):
                    overwrite_col.label(text="Folder no longer exists — pick again.", icon='CANCEL')
                elif norm_overwrite == norm_base:
                    overwrite_col.label(text="Cannot overwrite the root Bake Folder.", icon='CANCEL')
                elif not norm_overwrite.startswith(norm_base + os.sep):
                    overwrite_col.label(text="Must be inside the Bake Folder!", icon='CANCEL')
                else:
                    overwrite_col.label(
                        text=f"Will overwrite: {os.path.basename(norm_overwrite)}",
                        icon='ERROR'
                    )
                    overwrite_col.label(text="Bake Name is ignored when overwriting.", icon='INFO')

        layout.separator()

        can_bake = True
        bake_error = ""

        if scene.smb_overwrite_bake:
            overwrite = scene.smb_overwrite_folder.strip()
            base = scene.bake_base_folder.strip()

            if not overwrite:
                can_bake = False
                bake_error = "Overwrite folder not valid."
            else:
                norm_overwrite = os.path.normpath(overwrite)
                norm_base = os.path.normpath(base)

                if not os.path.exists(norm_overwrite):
                    can_bake = False
                    bake_error = "Overwrite folder not valid."
                elif norm_overwrite == norm_base:
                    can_bake = False
                    bake_error = "Overwrite folder not valid."
                elif not norm_overwrite.startswith(norm_base + os.sep):
                    can_bake = False
                    bake_error = "Overwrite folder not valid."

        layout.prop(scene, "smb_use_low_as_high")

        # Check active object is a valid _low mesh
        obj = context.object
        has_valid_selection = (
                obj is not None and
                obj.type == 'MESH' and
                obj.name.endswith("_low")
        )

        if not has_valid_selection:
            can_bake = False
            bake_error = "Select a _low mesh to bake."

        layout.separator()

        row = layout.row()
        row.enabled = can_bake
        row.operator("object.bake_preview", text="Bake Preview", icon='RENDER_STILL')

        if not can_bake:
            box = layout.box()
            box.alert = True
            box.label(text=bake_error, icon='ERROR')

        if hasattr(scene, "smb_status") and scene.smb_status:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Processing...", icon='SORTTIME')
            col.label(text=scene.smb_status)

        layout.separator()
        layout.prop(scene, "smb_use_vertex_colors")

        if scene.smb_use_vertex_colors:
            row = layout.row(align=True)
            row.operator("object.detect_vertex_colors", text="Detect Vertex Colors", icon='GROUP_VCOL')
            row.operator("smb.show_vertex_colors", text="Show Colors", icon='SHADING_SOLID')
            row.operator("smb.clear_vertex_color_materials", text="", icon='TRASH')

            if not hasattr(scene, "smb_vertex_colors"):
                layout.label(text="Reload addon to enable color detection", icon='ERROR')
                return

            if len(scene.smb_vertex_colors) > 0:
                layout.separator()
                layout.label(text=f"Found {len(scene.smb_vertex_colors)} colors:")
                for item in scene.smb_vertex_colors:
                    box = layout.box()
                    row = box.row(align=True)
                    row.prop(item, "color", text="")
                    row.label(text=item.hex_name)
                    box.prop(item, "smart_material", text="Material")

                    r, g, b = item.color[0], item.color[1], item.color[2]
                    brightness = (r + g + b) / 3.0
                    if brightness < 0.15:
                        warn_row = box.row()
                        warn_row.alert = True
                        warn_row.label(text="Too dark — may not bake reliably", icon='ERROR')
            else:
                layout.label(text="No colors detected yet", icon='INFO')
        else:
            layout.prop(scene, "smb_single_smart_material", text="Smart Material")