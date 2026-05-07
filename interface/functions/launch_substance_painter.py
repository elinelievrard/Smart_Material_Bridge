import subprocess

# 🔹 Launch Substance Painter non-blocking
def launch_substance_painter(sp_path=r"C:\Program Files\Adobe\Adobe Substance 3D Painter\Adobe Substance 3D Painter.exe"):
    try:
        subprocess.Popen([sp_path])
        print(f"Substance Painter launched: {sp_path}")
    except Exception as e:
        print(f"Error launching Substance Painter: {e}")