# 🔹 Utility: Find all _low/_high mesh pairs
import bpy


def find_mesh_pairs():
    pairs = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        if obj.name.endswith("_low"):
            base_name = obj.name[:-4]
            high_name = base_name + "_high"
            high_obj = bpy.data.objects.get(high_name)
            if high_obj and high_obj.type == 'MESH':
                pairs.append((obj, high_obj))
    return pairs