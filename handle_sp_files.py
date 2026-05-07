import shutil
import os

def get_sp_startup_path():
    # Default SP install path, adjust if needed
    return r"C:\Program Files\Adobe\Adobe Substance 3D Painter\resources\python\startup"

def install_sp_files():
    sp_startup = get_sp_startup_path()

    if not os.path.exists(sp_startup):
        print("[SMB] Substance Painter not found, skipping SP install")
        return

    addon_dir = os.path.dirname(os.path.realpath(__file__))
    sp_source = os.path.join(addon_dir, "substance_painter")

    # Copy entry point file
    shutil.copy2(
        os.path.join(sp_source, "smb_bridge_startup.py"),
        os.path.join(sp_startup, "smb_bridge_startup.py")
    )

    # Copy smb_bridge package, remove old version first
    dst_pkg = os.path.join(sp_startup, "smb_bridge")
    if os.path.exists(dst_pkg):
        shutil.rmtree(dst_pkg)
    shutil.copytree(
        os.path.join(sp_source, "smb_bridge"),
        dst_pkg
    )

    print("[SMB] Substance Painter files installed!")

def uninstall_sp_files():
    sp_startup = get_sp_startup_path()
    try:
        entry = os.path.join(sp_startup, "smb_bridge_startup.py")
        pkg = os.path.join(sp_startup, "smb_bridge")
        if os.path.exists(entry):
            os.remove(entry)
        if os.path.exists(pkg):
            shutil.rmtree(pkg)
        print("[SMB] Substance Painter files removed")
    except Exception as e:
        print(f"[SMB] SP uninstall warning: {e}")