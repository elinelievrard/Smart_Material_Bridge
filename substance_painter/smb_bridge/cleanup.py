import os
import substance_painter.smb_bridge.project as sp_project
import substance_painter.application as sp_app

def cleanup_files(low_path, high_path, name):
    for path in [low_path, high_path]:
        try:
            os.remove(path)
            print(f"[SP] Removed: {path}")
        except Exception as e:
            print(f"[SP] Cleanup warning: {e}")

def finish_or_continue(pairs, working_dir, index, process_next_fn):
    if index + 1 >= len(pairs):
        print("[SP] All done, closing Substance Painter...")
        sp_project.execute_when_not_busy(sp_app.close)
    else:
        sp_project.execute_when_not_busy(
            lambda: process_next_fn(pairs, working_dir, index + 1)
        )