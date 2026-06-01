import os
import time

_addon_startup_time = None  # Track when addon loads

bl_info = {
    "name": "Smart Material Bridge",
    "blender": (4, 1, 1),
    "category": "Object",
}

import bpy
try:
    from .interface.ui import OBJECT_PT_bake_panel, RESOLUTION_ITEMS
    from .interface.classes.bake_preview import OBJECT_OT_bake_preview
    from .interface.classes.bake_watcher import OBJECT_OT_bake_watcher
    from .interface.classes.refresh_overwrite_folder import SMB_OT_refresh_overwrite_folder, SMB_OT_reset_bake_folder, SMB_OT_open_bake_folder
    from .interface.functions.get_smart_materials import get_export_preset_items, get_smart_material_items
    from .interface.vertex_colors import (
        SMB_VertexColorItem,
        OBJECT_OT_detect_vertex_colors,
        SMB_OT_show_vertex_colors,
        SMB_OT_clear_vertex_color_materials,
        SMB_OT_pick_vertex_paint_color
    )

except Exception as e:
    import traceback
    traceback.print_exc()
    raise

classes = [
    SMB_VertexColorItem,
    OBJECT_PT_bake_panel,
    OBJECT_OT_bake_preview,
    OBJECT_OT_bake_watcher,
    OBJECT_OT_detect_vertex_colors,
    SMB_OT_refresh_overwrite_folder,
    SMB_OT_show_vertex_colors,
    SMB_OT_clear_vertex_color_materials,
    SMB_OT_pick_vertex_paint_color,
    SMB_OT_reset_bake_folder,
    SMB_OT_open_bake_folder,
]

def register():
    global _addon_startup_time
    _addon_startup_time = time.time()

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.bake_base_folder = bpy.props.StringProperty(
        name="Bake Folder",
        default=os.path.join(os.path.expanduser("~"), "MyBakeFolder"),
        subtype='DIR_PATH'
    )
    bpy.types.Scene.smb_resolution = bpy.props.EnumProperty(
        name="Resolution",
        items=RESOLUTION_ITEMS,
        default='2048'
    )
    bpy.types.Scene.smb_vertex_colors = bpy.props.CollectionProperty(
        type=SMB_VertexColorItem
    )
    bpy.types.Scene.smb_status = bpy.props.StringProperty(
        name="SMB Status",
        default=""
    )
    bpy.types.Scene.smb_export_fbx = bpy.props.BoolProperty(
        name="Export FBX",
        default=True
    )
    bpy.types.Scene.smb_export_project = bpy.props.BoolProperty(
        name="Export SP Project",
        default=True
    )
    bpy.types.Scene.smb_export_textures = bpy.props.BoolProperty(
        name="Export Textures",
        default=True
    )
    bpy.types.Scene.smb_overwrite_bake = bpy.props.BoolProperty(
        name="Overwrite Bake Folder",
        default=False
    )
    bpy.types.Scene.smb_overwrite_folder = bpy.props.StringProperty(
        name="Overwrite Folder",
        default="",
        subtype='DIR_PATH'
    )
    bpy.types.Scene.smb_export_preset = bpy.props.EnumProperty(
        name="Export Preset",
        items=get_export_preset_items,
    )
    bpy.types.Scene.smb_bake_folder_name = bpy.props.StringProperty(
        name="Bake Name",
        default=""
    )
    bpy.types.Scene.smb_use_vertex_colors = bpy.props.BoolProperty(
        name="Use Vertex Colors",
        description="Assign different smart materials per vertex color. Disable to apply one material to the whole mesh",
        default=True
    )
    bpy.types.Scene.smb_single_smart_material = bpy.props.EnumProperty(
        name="Smart Material",
        items=get_smart_material_items,
    )
    bpy.types.Scene.smb_use_low_as_high = bpy.props.BoolProperty(
        name="Use Low as High",
        description="Use the low poly mesh as its own high poly — no _high mesh needed",
        default=False
    )
    bpy.types.Scene.smb_last_baked_material = bpy.props.StringProperty(
        name="Last Baked Material",
        default=""
    )
    bpy.types.Scene.smb_save_blend = bpy.props.BoolProperty(
        name="Save Blender File",
        description="Save a copy of the current .blend file into the bake folder under a Blender/ subfolder",
        default=False
    )
    bpy.types.Scene.smb_last_bake_time = bpy.props.StringProperty(
        name="Last Bake Time",
        default=""
    )
    bpy.types.Scene.smb_last_bake_resolution = bpy.props.StringProperty(
        name="Last Bake Resolution",
        default=""
    )
    bpy.types.Scene.smb_last_bake_texture_count = bpy.props.IntProperty(
        name="Last Bake Texture Count",
        default=0
    )
    bpy.types.Scene.smb_bake_summary_expanded = bpy.props.BoolProperty(
        name="Bake Summary Expanded",
        default=True
    )
    bpy.types.Scene.smb_last_bake_folder = bpy.props.StringProperty(
        name="Last Bake Folder",
        default=""
    )

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.smb_status
    del bpy.types.Scene.smb_export_fbx
    del bpy.types.Scene.smb_export_project
    del bpy.types.Scene.smb_export_textures
    del bpy.types.Scene.smb_overwrite_bake
    del bpy.types.Scene.smb_overwrite_folder
    del bpy.types.Scene.smb_export_preset
    del bpy.types.Scene.smb_bake_folder_name
    del bpy.types.Scene.smb_use_vertex_colors
    del bpy.types.Scene.smb_single_smart_material
    del bpy.types.Scene.smb_use_low_as_high
    del bpy.types.Scene.bake_base_folder
    del bpy.types.Scene.smb_resolution
    del bpy.types.Scene.smb_vertex_colors
    del bpy.types.Scene.smb_last_baked_material
    del bpy.types.Scene.smb_save_blend
    del bpy.types.Scene.smb_last_bake_time
    del bpy.types.Scene.smb_last_bake_resolution
    del bpy.types.Scene.smb_last_bake_texture_count
    del bpy.types.Scene.smb_bake_summary_expanded
    del bpy.types.Scene.smb_last_bake_folder