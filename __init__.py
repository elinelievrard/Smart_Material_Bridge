import sys

import subprocess

bl_info = {
    "name": "Smart Material Bridge",
    "blender": (4, 1, 1),
    "category": "Object",
}

import bpy
# very important to put the . because pycharm will know but blender does not
try:
    from .interface.ui import OBJECT_PT_bake_panel
    from .startup.restart_blender import SMB_OT_restart_blender
    from .interface.classes.bake_preview import OBJECT_OT_bake_preview
    from .interface.classes.bake_watcher import OBJECT_OT_bake_watcher
    from .handle_sp_files import install_sp_files, uninstall_sp_files
except Exception as e:
    import traceback
    traceback.print_exc()
    raise

classes = [
    OBJECT_PT_bake_panel,
    SMB_OT_restart_blender,
    OBJECT_OT_bake_preview,
    OBJECT_OT_bake_watcher,
]

addon_keymaps = []

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    install_sp_files()

def unregister():
    # Remove keymap

    for cls in classes:
        bpy.utils.unregister_class(cls)

    uninstall_sp_files()
