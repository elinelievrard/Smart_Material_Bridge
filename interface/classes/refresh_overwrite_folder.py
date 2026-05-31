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