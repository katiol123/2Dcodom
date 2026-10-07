# CLAUDE.md

PixelForge: Python engine that generates all pixel-art graphics in code. Only dependency: Pillow (export).

## Commands
- `python -m unittest discover -s tests` — tests (fast, <1s)
- `python -m pixelforge build out` — render all presets to `out/` (~10s); `out/` is gitignored
- `python -m pixelforge unit <preset|random:SEED> out`

## How to add graphics
- New humanoid unit: add a `HumanoidSpec` to `PRESETS` in `pixelforge/units/humanoid.py` (data only).
- New gear/body part: add shapes to bones in `build_rig` (shapes: `Limb`, `Blob`, `Poly`, `Pixels`, `Custom`).
- New animation: write a `*_poses(spec, rig)` function returning `Pose`s (use `_with(base, ...)` with
  body-space angles: 0 right, 90 down, -90 up; sprites face right), register it in `build_humanoid`.
- New creature type: build a `Rig` like `build_quad_rig` in `units/creatures.py`, or draw directly into a
  `PartBuffer` like `_slime_frame`.
- Always render and *look* at the result (Read the PNG at scale 8-10) before committing; tune angles visually.

## Style rules (see docs/PIXEL_ART_GUIDE.md)
- Colors via `Material.of(name, base)` (hue-shifted 5-step ramp); light top-left; selout outline.
- Back limbs: `depth=-1`, lower z. Parts that overlap the torso should sit behind it unless they must show.
- Keep shapes widths snapped (handled by `Limb`/`Blob`); no alpha except drop shadows; fade via `fx.dissolve`.
- Attack timing: long anticipation, ~50ms smear, held impact with `events=["hit"]`.
