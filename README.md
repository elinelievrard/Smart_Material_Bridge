# Demo_Keyframe_Rotation
Blender add-on to demonstrate live editing a multi file add-on.

# Use
- Install the multi file add-on
- Ensure that the module loader is available to and imported in the __init__.py file.
- Call the refresh method from module loader.
  - When ran, refresh() will reload all files in the current add-on's directory.
- In Blender, create a keymap that runs the script.reload function.
- Press the key for script.reload to cause Blender to reload the __init__.py file, which will then trigger a refresh of all other relevant files for the add-on.

# Related Video
This repository was created as a demonstration to go along with the following video which explores working with multi file add-ons in Blender. 
https://youtu.be/MUldFndjvw4
