import sys
import bpy
import subprocess

class SMB_OT_restart_blender(bpy.types.Operator):
    """Restart Blender to fully reload the add-on"""
    bl_idname = "smb.restart_blender"
    bl_label = "Restart Blender"

    def execute(self, context):
        blend_file = r"C:\Users\eline\OneDrive\Documenten\GGP\y2\ToolsAutomation\Exam\example_file_addon.blend"
        blender_exe = bpy.app.binary_path

        bpy.ops.wm.save_as_mainfile(filepath=blend_file)

        open_console_cmd = "import bpy; bpy.ops.wm.console_toggle()"

        subprocess.Popen([
            blender_exe,
            blend_file,
            "--python-expr", open_console_cmd
        ])

        bpy.ops.wm.quit_blender()
        return {'FINISHED'}