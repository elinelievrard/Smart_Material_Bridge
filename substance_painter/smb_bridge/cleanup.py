import os
import shutil

def cleanup_files(fbx_folder, delete_fbx_after):
    """FBX files are kept as permanent copies in fbx/ — nothing to clean up."""
    if delete_fbx_after:
        if os.path.isdir(fbx_folder):
            shutil.rmtree(fbx_folder)
            print(f"[SP] Deleted FBX folder (not requested by user): {fbx_folder}")
    else:
        print(f"[SP] FBX files retained in: {fbx_folder}")

