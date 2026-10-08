# CLAUDE.md

PixelForge: Python engine that generates all pixel-art graphics in code. Only dependency: Pillow (export).

## Commands
- `python -m unittest discover -s tests` — tests (~4s; the first run also builds the battle sprite cache)
- `python -m pixelforge build out` — render all presets to `out/` (~10s); `out/` is gitignored
- `python -m pixelforge unit <preset|random:SEED> out`
- `python battle.py` — auto-battle demo (pygame); `--record x.mp4` renders headless; `--seed N`
- `python -m game.balance 2000 random` — per-class win rates on random squads; run after any stat/AI change.
  Every class has an intended `tier` (weak / below / average / above / boss) chosen *before* its stats; the
  report flags classes outside their tier's aim (`TIER_AIM` in balance.py: weak ~28-40%, average 43-57%,
  above 53-65%). Bosses (troll) are excluded. `python -m game.balance 40` — classic mirror (~50/50)
- `python -m game.cardsim 64 40` — card/campaign balance: AI plays every realm; per-realm cities, income,
  desertions and per-card draw/play rates. Run after any card, prosperity or campaign-rule change.
- Hire price / upkeep (`PRICES` in units.py) come from those measured win rates (formula in the comment);
  re-derive them after big balance changes. Cheap weak units (militia, slinger, zombie, war dog, goblins) exist
  so realms short of gold can still hire.

## Battle game (game/)
- `sim.py`/`ai.py` must stay pygame-free (tests and balance run headless). Rendering only in `render.py`.
- Damage happens on the sprite's `hit`/`cast` event frame (timings come from the exported sheet JSON).
- Every unit has a seeded look (`look_for` in units.py: class-defining gear fixed, faces vary). Sheets are named
  `<class>_<team>_<spec hash>` and cached in `.cache/battle/<hash of pixelforge>/`; `SpriteFactory` builds missing
  ones in worker processes and prefetches the next battle. Tests/balance use `match.headless_world` (seed-0 timings).
- Summons (skeletons, nest goblins, rider who survives) need a sheet: list them in `SUMMONS` (assets.py) by owner,
  then `world.summon(owner, x, y, key)`. After 90 s healing fades out (`FATIGUE_AT` in sim.py) to end stalemates.
- New class: `UnitType` in `ROSTER` (set `tier` first) + `TRAITS` entry + branch in `look_for` + behaviour in
  `ai.py` (per-unit hooks: `NEW_PASSIVES`, `NEW_ABILITIES`, `NEW_ACTIONS`, `_new_melee_mods/_after`), then rebalance
  and add it to some city pools in factions.py. Damage modifiers are data: `missile_mult`, `physical_mult`,
  `magic_mult`, `fire_mult`, `immune`, `incorporeal`, `shield`. `Unit.base_key` is the hired class (druid -> bear).
- Charges (`status["charge"]`) are countered by `COUNTERS` (spearman, halberdier, militia) whenever the rusher
  comes within reach, not only when it targets them. Cornered shooters (`cornered`) stop kiting and shoot.
- Unit descriptions live in `TRAITS` (units.py): perks (green), flaws (red), behavior (blue); one independent trait
  per entry, `("NAME", "short description")`; keep them true to the mechanics. Menu shows them in that order.
  Plain stats (HP, armor, speed, damage, range, cooldown, dodge) are shown as stats, never as traits.
- No screen shake (user request); impact feel comes from hit-stop and slow-mo.
- Crispness (user request): units use `CRISP` shader settings (near-black tinted outline, no lit-side outline,
  despeckle); the ground stays calm (2 tones); the window is DPI-aware on Windows and `present()` only ever
  scales by whole numbers (letterboxed in fullscreen).
- Inspect visually: record with `--record`, then `ffmpeg ... -vf "fps=6,tile=3x3"` to look at frame sequences.

## World map (game/factions.py, worldgen.py, mapview.py)
- `battle.py` starts on the faction select (`select.py`: banners, spectator = Chronicler), then the world map;
  "БЫСТРЫЙ БОЙ" opens the squad builder, ESC there returns to the map. Wheel zooms the map out only (`ZOOMS`).
- Officers (`officers.py`): 12-22 per faction, first = leader; leadership caps squad power (sum of unit `cost`),
  6 stats 1..20, `bio()` built from faction origin + best/worst stat + quirk (`{м|ж}` gender forms).
- `campaign.py` (pygame-free): gold, troops standing in cities (`free`), officers' squads (max 7), hire/assign
  rules, `allegiance` (officers may defect). ARMY/HIRE buttons only for the player's own cities.
- Action cards (docs/CARDS.md): everything on the map is a card played for ОД (5/turn, khanate 6). Data in
  `cards.py` (catalogue, `PERSONAL` cards, `deck_for` = base set + faction card + council members' cards +
  stat-threshold cards), effects/targets in `cardplay.py` (`EFFECTS`, `options` step by step), turn engine and
  battles in `campaign.py`, AI values in `campaign_ai.py` (`VALUE`), UI in `cardui.py`. New card: `_c(...)` in
  `_CARDS` + `@effect` + AI value + put it in a pool/unique list; then `python -m game.cardsim 64 40` and check
  per-realm cities/income and the card's play rate; regenerate docs/CARDS.md tables.
- City prosperity (`PROSPERITY` in factions.py, 1..10) sets tax income; AI realms must stay pygame-free.
- Hiring is open only in cities with an active СБОР ВОЙСК (`camp.muster`, turns from council ВЕРБОВКА).
- Officers change during a campaign (`growth.py`): XP/levels (weak officers learn faster, by *starting*
  presence), wounds/complacency, feats (one of each per campaign, `cards.FEATS`), loyalty events and
  defections. Use `camp.ostats/olead/stat()/leadership()/presence()/personal()` and the council wrappers
  (`camp.totals/thresholds/hand_size/...`), never the static `Officer.stats` in game logic or UI.
  `cardsim` reports growth by starting calibre and feat rates; aim: the weakest fifth climbs (~5 levels,
  some reach the council), the strongest rarely lose a stat (~15%), defections < 1 per realm.
- Storms: `Campaign.attack` -> defender's answer card (`_answer`) -> `battle_hook` (real battle) or `_formula` ->
  `_settle` (fallen roll `fate_odds`: wounded/escaped/dead). The map runs card plays and turns in a worker thread
  (`campaign_runner.Runner`); a storm involving the player (or an AI storm he chose to watch) asks the screen to
  fight it (`battle.py` builds it with `match.campaign_battle`, units carry `tag` = troop id). Tests fight such
  battles with `match.headless_campaign_world`.
- Courses (`COURSES` in cards.py) set the 6 base cards; vices (`VICE_OF`) are extra personal cards of 30 officers.
- Diplomacy (`diplomacy.py`, UI `diploui.py`): war by default, truce/alliance/trade by proposal (1 AP),
  answered by `evaluate` (weighted reasons, shown in the UI; the player answers AI envoys via `diplo_hook`),
  `declare_war` = betrayal. Relation tiers (`TIERS`/`TIER_EFFECTS`) have mechanical effects - keep the texts
  true. The hegemon (`hegemon`) is feared: coalitions form against it. AI: `ai_turn` (one proposal a turn).
- World events (`events.py`): ~2 a campaign (`CHANCE`, `GAP`); timed ones live in `camp.active` and change
  rules in campaign.py. Check each event's impact with `python -m game.cardsim events 48` after changes.
- Map overlays: city badges (officers, garrison), storm arrows since the player's last turn
  (`camp.attacks`), В ОСАДЕ plaque. The camera may slide half a screen past the map edge; zooming back in
  restores the view left when zooming out (`zoom_back`).
- Rulers (`camp.leader`, `succession.py`): never defect; may die (battle, fallen city, illness, realm's fall).
  Heir = best `heir_score` (court merit `camp.claim` + presence/level/loyalty), never chosen directly. New
  ruler's cards become the ruler's cards, the dead ruler's stay as `Realm.legacy` (one ruler only); then
  political instability (`Realm.unrest`). Use `camp.is_leader(o)`, never `rank == 0`, for "the ruler".
  Dead officers stay in `camp.dead` (excluded from `officers_of/officers_in`).
- Officer faces are NOT pixel art (user request): `faces.py` paints them with Pillow (supersampled curves);
  charismatic (high `presence`) = richer, plain = simpler. Painted pictures go through `hires.HIRES` so
  `present()` redraws them sharp after the integer upscale; faces/names are clickable via `OfficerCard`.
- 8 playable *human* factions (`FACTIONS`) + non-playable goblins (`GOBLINS`: no diplomacy, always war,
  lairs all over the map). Relations 1..100 with a reason for every pair (`_REL`); keep reasons true to the lore.
- Recruit pools belong to cities (3-6 units); keys not in `ROSTER` must be in `NEW_UNITS` (planned units).
- `worldgen.py` is numpy-only (no pygame). Coast/lake/rivers are control points; ground culture = nearest
  non-goblin city (`Faction.culture`); goblin lairs get swamp pockets. The map PNG is cached by `map_key()`.
- New city: `City` in `CITIES` + pairs in `ROADS`; tests check land, spacing, connectivity, no sea roads.
- Docs in docs/CAMPAIGN.md are generated from this data - regenerate the tables when the data changes.

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
