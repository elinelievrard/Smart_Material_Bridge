import os

root = r"C:\Users\eline\AppData\Roaming\Blender Foundation\Blender\5.0\scripts\addons\Smart_Material_Bridge"

for dirpath, dirnames, filenames in os.walk(root):
    for filename in filenames:
        if filename.endswith(".py"):
            filepath = os.path.join(dirpath, filename)

            print(f"\n{'='*60}")
            print(f"FILE: {filepath}")
            print('='*60)

            with open(filepath, "r", encoding="utf-8") as f:
                print(f.read())