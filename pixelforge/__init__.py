"""PixelForge - procedural pixel-art graphics engine.

Layers (low to high):

* :mod:`color`, :mod:`palette`  - hue-shifted ramps, classic palettes
* :mod:`canvas`                  - pixel-perfect primitives on grids
* :mod:`shading`                 - materials + light/outline shader
* :mod:`rig`                     - skeletal rig rendered to pixel art
* :mod:`anim`, :mod:`fx`         - animations, timing, dithering effects
* :mod:`export`                  - sprite sheets (PNG+JSON), GIF previews
* :mod:`units`, :mod:`assets`    - ready generators (humanoids, slimes,
  tiles, items, UI, VFX)
"""

from .color import rgba, ramp, shade, mix, to_hex
from .palette import Palette, PALETTES, PICO8, ENDESGA32, SWEETIE16, DB16
from .canvas import Grid, Canvas
from .shading import Material, Ink, PartBuffer, Shader, shade_mask
from .rig import Rig, Bone, Pose, Limb, Blob, Poly, Pixels, Custom
from .anim import Frame, Animation, Sprite, tween, from_poses
from . import fx, export, text

__version__ = "0.1.0"
