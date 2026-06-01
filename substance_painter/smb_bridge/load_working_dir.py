import os
import json
import time

STARTUP_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CONFIG_PATH = os.path.join(STARTUP_DIR, "bake_config.json")


def load_working_dir():
    if not os.path.exists(CONFIG_PATH):
        print(f"[SP] No bake_config.json found at {CONFIG_PATH}")
        return None, {}, None, None, 11, "", False

    try:
        config_age = time.time() - os.path.getmtime(CONFIG_PATH)
        if config_age > 600:
            print(f"[SP] Config is {config_age:.0f}s old — ignoring stale config")
            return None, {}, None, None, 11, "", False

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

        working_dir      = config.get("bake_folder")
        color_mapping    = config.get("color_mapping", {})
        texture_out      = config.get("texture_out")
        projects_folder  = config.get("projects_folder")
        size_log2        = config.get("size_log2", 11)
        export_preset    = config.get("export_preset", "")
        delete_fbx_after = config.get("delete_fbx_after", False)
        use_low_as_high = config.get("use_low_as_high", False)

        if not working_dir:
            print("[SP] bake_folder key missing from config")
            return None, {}, None, None, 11, "", False

        print(f"[SP] Working dir: {working_dir}")
        print(f"[SP] Texture out: {texture_out}")
        print(f"[SP] Color mapping: {color_mapping}")
        return working_dir, color_mapping, texture_out, projects_folder, size_log2, export_preset, delete_fbx_after, use_low_as_high

    except Exception as e:
        print(f"[SP] Failed to load config: {e}")
        return None, {}, None, None, 11, "", False