import subprocess

def launch_substance_painter(sp_path):
    try:
        process = subprocess.Popen([sp_path])
        print(f"[SMB] Substance Painter launched: {sp_path}")
        return process
    except Exception as e:
        print(f"[SMB] Error launching Substance Painter: {e}")
        return None