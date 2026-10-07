# Пиксель-арт: конспект референсов и как движок их реализует

Перед написанием движка я собрал типовые приёмы жанра из туториалов и
ассет-паков (Lospec, itch.io, CG Cookie, Pixnote/Saint11-подобные разборы
анимации, процедурные генераторы спрайтов в духе Dave Bollinger). Ниже —
правила, которые из этого следуют, и место в коде, где каждое реализовано.

## 1. Цвет

| Правило из референсов | Реализация |
|---|---|
| **Ограниченная палитра** держит стиль цельным | `palette.py`: PICO-8, ENDESGA-32, Sweetie-16, DB16; `Canvas.quantize(palette)` |
| **Hue shifting**: тени холоднее (к синему/фиолетовому) и насыщеннее, света теплее (к жёлтому) и чуть менее насыщенные | `color.shade()` / `color.ramp()` — 5-ступенчатая рампа с поворотом тона |
| Не использовать чистый чёрный для контура | `palette.INK` = `#181425` (тёмно-фиолетовый); в режиме selout контур берётся из рампы материала |
| Серые цвета почти не сдвигать по тону | в `shade()` сила сдвига зависит от насыщенности |

## 2. Свет и объём

| Правило | Реализация |
|---|---|
| Единое направление света (обычно сверху-слева) для всех спрайтов, тайлов и иконок | `Shader.light = (-1, -1.2)` по умолчанию везде |
| **Избегать pillow shading** (затемнения всех краёв к центру) | нормали считаются по силуэту «группы»; светлый ободок только на стороне к свету, тень — на противоположной |
| Тень шире блика | `shadow_width=2`, блик всегда 1px |
| Дальние конечности темнее ближних (side-view) | `Bone.depth = -1` сдвигает рампу на шаг |
| Перекрывающиеся части читаются за счёт тени на заднем объекте | «окклюзионные контуры» в `Shader.level_at` |
| Блики-спекуляры только у металла/стекла | `Material(shiny=True)` |

## 3. Контур (outline)

| Правило | Реализация |
|---|---|
| **Selective outline (selout)**: контур окрашен в тёмный цвет материала и светлее на освещённой стороне | `Shader(outline="selout")`, `selout_lit_mix` |
| Альтернатива — однотонный тёмный контур / без контура | `outline="color"` / `"none"` |
| Без диагональных «углов» контура силуэт выглядит мягче | `corners=False` (4-связность) по умолчанию |
| Детали внутри силуэта (глаза, блики) без контура | `Ink(outline=False)` / `Pixels(level=...)` |

## 4. Чистота пикселей

| Правило | Реализация |
|---|---|
| Pixel-perfect линии без «двойных» углов | `Grid.line` — Брезенхем |
| Ширина конечности не должна «мигать» между кадрами | `rig._snap`: чётная ширина — привязка к целым координатам, нечётная — к центрам пикселей |
| Никакой полупрозрачности/сглаживания — переходы и исчезновение через **dithering** | `fx.bayer`, `fx.dither_pick`, `fx.dissolve` |
| Масштабирование только целыми кратными, nearest-neighbour | `Canvas.scaled`, `to_image(scale)` |

## 5. Анимация

Нормы количества кадров из референсов: walk 4–8 (8 для 32px+), attack 3–6,
death 4–6+, idle 2–4 медленных кадра. Idle-поза — «база», из которой
выходят и в которую возвращаются все анимации.

| Правило | Реализация (`units/humanoid.py`) |
|---|---|
| Walk: contact → down → passing → up, руки в противофазе ногам, тело проседает при постановке ноги | 8 кадров по фазе синуса; колено сгибается в фазе переноса; **ground lock** держит опорную стопу на земле, проседание корпуса получается само |
| Idle: «дыхание» — грудь опускается на 1px, ноги стоят | `Pose.offsets={"torso": (0, 1)}` |
| Attack: **anticipation** (замах, держится дольше) → быстрый **smear-кадр** (40–60 мс) → **impact** с удержанием → recovery | кадры 240 / 50 / 220 / 140 / 120 мс; `fx.smear_arc` рисует серповидный смаз; событие `hit` на кадре удара |
| Hurt: 1 кадр белой вспышки + отдача назад | `fx.flash` + `Pose.shift` |
| Death: удар → подкашивание → падение → отскок → лежание; потом растворение | вращение корня, `ground_all`, анимация `vanish` через дизеринг с «горящим» краем |
| Squash & stretch с сохранением объёма | слизень: `rx * ry = const` |
| Взгляд и спрайты рисуются вправо, влево — зеркалом | `Sprite.flipped()` |

## 6. Тайлы и UI

* Тайлы бесшовные: шум и вороной-ячейки «заворачиваются» по краям тайла (`fx.ValueNoise`, тороидальное расстояние в `cobblestone`).
* Кирпич/доски: светлая верхняя/левая грань, тёмная нижняя — тот же свет сверху-слева.
* UI: скосы-рамки (светлая грань сверху-слева), 9-slice, полоски здоровья с 3 тонами, пиксельный шрифт 3×5 (латиница + кириллица).

## Источники

* [Lospec — статьи о пиксель-арте (outlines, hue shifting)](https://lospec.com/articles/category:articles)
* [Lospec — Pixel art outlines part 2: using color](https://lospec.com/articles/pixel-art-outlines-part-2-using-color)
* [itch.io — Pixel tutorial: selective outlines](https://itch.io/t/2422252/pixel-tutorial-selective-outlines)
* [CG Cookie — Fundamentals of Pixel Art](https://cgcookie.com/courses/fundamentals-of-pixel-art)
* [Pinnguaq — уроки пиксель-арта (anti-aliasing, hue shifting)](https://pinnguaq.com/?p=1300)
* [Sprite animation frames — сколько кадров на анимацию](https://www.sprite-ai.art/blog/sprite-animation-frames)
* [Animation principles for pixel art](https://www.sprite-ai.art/guides/animation-principles)
* [Wayline — Sprite Animation course](https://www.wayline.io/learn/sprite-animation)
* [Примеры ассет-паков: characters pack](https://dreamir.itch.io/characters-pack), [skeleton pack](https://pixollie.itch.io/skeleton-character-asset-pack), [zombie](https://lazerpants.itch.io/zombie-pixel-art-character)
* [Dave Bollinger — Pixel Spaceships (процедурная генерация по маске)](https://www.raster.art/artwork/pixel-spaceships-solos-by-dave-bollinger/about)
* [gb-sprite — процедурные спрайты/VFX, Bayer-дизеринг](https://hackage-origin.haskell.org/package/gb-sprite)
* Палитры: [ENDESGA 32](https://lospec.com/palette-list/endesga-32), PICO-8, Sweetie 16, DawnBringer 16
