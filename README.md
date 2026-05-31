# Smart Material Bridge

A Blender add-on that automates the full pipeline from mesh baking to final textured asset, bridging Blender and Adobe Substance 3D Painter in a single click. Handy to apply smart materials to your blender meshes. Afterwards you can adjust in Substance Painter with the baking and applying already done. 

## Requirements

- Blender 4.1+
- Adobe Substance 3D Painter
- Windows 10 / 11

## Installation

1. Download `Smart_Material_Bridge.zip`
2. In Blender go to **Edit → Preferences → Add-ons → Install**
3. Select the zip and enable **Smart Material Bridge**
4. Open the **SMB** tab in the N-Panel (press N in the 3D Viewport)

## Usage

1. Name your meshes with `_low` / `_high` suffixes (e.g. `Barrel_low`, `Barrel_high`)
2. (optional) Apply vertex colors to the low poly if you want per-material smart material assignment
3. Select the `_low` mesh
4. In the SMB panel: set bake folder, resolution, export options, and preset
5. Click **Detect Vertex Colors** and assign smart materials to each color
6. Click **Bake Preview** — SP launches, bakes, exports, and closes automatically
7. Textures are applied to the mesh in Blender once SP finishes

## Troubleshooting

| Problem | Solution |
|---|---|
| **Crash within Substance Painter** | Try baking again, reconfigure the settings, restart Blender, restart your PC, or delete the `.spp` project file if one was created. |
| **Materials did not apply** | Every export preset uses different texture naming conventions. Textures are imported into Blender but may not be automatically connected to the right BSDF inputs. Go to the Shading tab and connect them manually if needed. |

> ⚠ **Avoid running multiple bakes back-to-back** — Some background processes can take a few moments to fully finish after a bake completes. Waiting 10–20 seconds between bakes helps prevent issues.
> 

© 2025–2026 Eline Lievrard
