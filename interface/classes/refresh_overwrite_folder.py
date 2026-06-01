import bpy
import os

class SMB_OT_refresh_overwrite_folder(bpy.types.Operator):
    bl_idname = "smb.refresh_overwrite_folder"
    bl_label = "Refresh"
    bl_description = "Set overwrite folder to the first bake_N folder inside the Bake Folder"

    def execute(self, context):
        scene = context.scene
        base = scene.bake_base_folder.strip()

        if not base or not os.path.exists(base):
            self.report({'WARNING'}, "Bake Folder does not exist yet.")
            scene.smb_overwrite_folder = ""
            return {'FINISHED'}

        # Find all existing subfolders directly inside the Bake Folder
        try:
            subfolders = [
                os.path.join(base, d) for d in os.listdir(base)
                if os.path.isdir(os.path.join(base, d))
            ]
        except Exception as e:
            self.report({'WARNING'}, f"Could not read Bake Folder: {e}")
            scene.smb_overwrite_folder = ""
            return {'FINISHED'}

        if not subfolders:
            self.report({'INFO'}, "No subfolders found in Bake Folder.")
            scene.smb_overwrite_folder = ""
            return {'FINISHED'}

        # Pick the most recently modified one
        latest = max(subfolders, key=os.path.getmtime)
        scene.smb_overwrite_folder = latest
        self.report({'INFO'}, f"Set to: {os.path.basename(latest)}")
        return {'FINISHED'}

class SMB_OT_reset_bake_folder(bpy.types.Operator):
    bl_idname = "smb.reset_bake_folder"
    bl_label = "Reset Bake Folder"
    bl_description = "Reset to default bake folder"

    def execute(self, context):
        import os
        context.scene.bake_base_folder = os.path.join(os.path.expanduser("~"), "MyBakeFolder")
        return {'FINISHED'}

class SMB_OT_open_bake_folder(bpy.types.Operator):
    bl_idname = "smb.open_bake_folder"
    bl_label = "Open Bake Folder"
    bl_description = "Open the last bake folder in Windows Explorer"

    def execute(self, context):
        import os
        folder = context.scene.smb_last_bake_folder.strip()
        # Open the parent (bake root), not the textures/ subfolder
        display_folder = os.path.dirname(folder) if folder else ""
        if display_folder and os.path.exists(display_folder):
            os.startfile(display_folder)
        else:
            self.report({'WARNING'}, "Folder no longer exists")
        return {'FINISHED'}