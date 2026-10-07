"""Writes build/icon.ico (the sword item icon) for the Windows .exe."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image  # noqa: E402

from pixelforge.assets.items import sword  # noqa: E402

out = os.path.join(ROOT, "build", "icon.ico")
os.makedirs(os.path.dirname(out), exist_ok=True)
base = sword().to_image()
big = base.resize((256, 256), Image.NEAREST)
big.save(out, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icon ->", out)
