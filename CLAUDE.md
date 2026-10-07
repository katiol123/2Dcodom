# CLAUDE.md

PixelForge: Python engine that generates all pixel-art graphics in code. Only dependency: Pillow (export).

## Commands
- `python -m unittest discover -s tests` — tests (~4s; the first run also builds the battle sprite cache)
- `python -m pixelforge build out` — render all presets to `out/` (~10s); `out/` is gitignored
- `python -m pixelforge unit <preset|random:SEED> out`
- `python battle.py` — auto-battle demo (pygame); `--record x.mp4` renders headless; `--seed N`
- `python -m game.balance 300 random` — per-class win rates on random squads; run after any stat/AI change
  (aim: every class ~41-60%, 30-50 s fights); `python -m game.balance 40` — classic mirror (~50/50)

## Battle game (game/)
- `sim.py`/`ai.py` must stay pygame-free (tests and balance run headless). Rendering only in `render.py`.
- Damage happens on the sprite's `hit`/`cast` event frame (timings come from the exported sheet JSON).
- Every unit has a seeded look (`look_for` in units.py: class-defining gear fixed, faces vary). Sheets are named
  `<class>_<team>_<spec hash>` and cached in `.cache/battle/<hash of pixelforge>/`; `SpriteFactory` builds missing
  ones in worker processes and prefetches the next battle. Tests/balance use `match.headless_world` (seed-0 timings).
- New class: `UnitType` in `ROSTER` + `TRAITS` entry + branch in `look_for` + behaviour in `ai.py`, then rebalance.
- Unit descriptions live in `TRAITS` (units.py): perks (green), flaws (red), behavior (blue); one independent trait
  per entry, `("NAME", "short description")`; keep them true to the mechanics. Menu shows them in that order.
  Plain stats (HP, armor, speed, damage, range, cooldown, dodge) are shown as stats, never as traits.
- No screen shake (user request); impact feel comes from hit-stop and slow-mo.
- Inspect visually: record with `--record`, then `ffmpeg ... -vf "fps=6,tile=3x3"` to look at frame sequences.

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
