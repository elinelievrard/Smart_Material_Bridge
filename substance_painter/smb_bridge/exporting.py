import substance_painter.export as sp_export

def export_textures(texture_sets, working_dir):
    export_config = {
        "exportPath": working_dir,
        "exportShaderParams": False,
        "defaultExportPreset": "NormalOnly",
        "exportPresets": [
            {
                "name": "NormalOnly",
                "maps": [
                    {
                        "fileName": "$mesh_normal",
                        "channels": [
                            {"destChannel": "R", "srcChannel": "R", "srcMapType": "meshMap", "srcMapName": "normal_base"},
                            {"destChannel": "G", "srcChannel": "G", "srcMapType": "meshMap", "srcMapName": "normal_base"},
                            {"destChannel": "B", "srcChannel": "B", "srcMapType": "meshMap", "srcMapName": "normal_base"}
                        ],
                        "parameters": {
                            "fileFormat": "png", "bitDepth": "8",
                            "dithering": False, "paddingAlgorithm": "infinite",
                            "dilationDistance": 16, "sizeLog2": 11
                        }
                    }
                ]
            }
        ],
        "exportList": [{"rootPath": tset.name} for tset in texture_sets],
        "exportParameters": [
            {
                "parameters": {
                    "fileFormat": "png", "bitDepth": "8",
                    "dithering": False, "paddingAlgorithm": "infinite",
                    "dilationDistance": 16, "sizeLog2": 11
                }
            }
        ]
    }

    result = sp_export.export_project_textures(export_config)
    print(f"[SP] Export status: {result.status}")
    print(f"[SP] Exported files: {result.textures}")
    return result