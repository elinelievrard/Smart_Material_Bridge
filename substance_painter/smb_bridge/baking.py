from PySide6.QtCore import QUrl
import substance_painter.smb_bridge.baking as sp_bake
from substance_painter.smb_bridge.baking import BakingParameters, MeshMapUsage

def setup_baking(texture_sets, high_path):
    sp_bake.unlink_all_common_parameters()

    high_url = QUrl.fromLocalFile(high_path).toString()
    print(f"[SP] High poly URL: {high_url}")

    property_values = {}
    for tset in texture_sets:
        bake_params = BakingParameters.from_texture_set(tset)
        bake_params.set_textureset_enabled(True)
        bake_params.set_enabled_bakers([MeshMapUsage.Normal])
        common = bake_params.common()
        property_values[common["HipolyMesh"]] = high_url

    BakingParameters.set(property_values)

def start_baking(texture_sets):
    print("[SP] Starting bake...")
    for tset in texture_sets:
        sp_bake.bake_async(tset)