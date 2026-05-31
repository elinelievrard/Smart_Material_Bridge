import os

def _find_sp_base():
    candidates = [
        os.path.join(os.environ.get("PROGRAMFILES", ""), "Adobe", "Adobe Substance 3D Painter"),
        r"C:\Program Files\Adobe\Adobe Substance 3D Painter",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

SP_BASE = _find_sp_base()
SP_EXE             = os.path.join(SP_BASE, "Adobe Substance 3D Painter.exe") if SP_BASE else None
SP_STARTUP         = os.path.join(SP_BASE, "resources", "python", "startup") if SP_BASE else None
SP_SMART_MATERIALS = os.path.join(SP_BASE, "resources", "starter_assets", "smart-materials") if SP_BASE else None
SP_EXPORT_PRESETS  = os.path.join(SP_BASE, "resources", "starter_assets", "export-presets") if SP_BASE else None