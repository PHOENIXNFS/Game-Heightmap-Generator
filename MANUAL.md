# Terrain Heightmap Generator
## Instruction Manual for Everyone

This manual walks you through the whole program, one panel at a time. You do
not need any programming or 3D-modelling experience — if you can drag a
slider and click a button, you can use this tool.

**How to read this manual**

- **New here?** Start with [Part 1](#1-getting-started) and follow
  [Part 2](#2-your-first-map-in-five-minutes) — you will have a map to export
  in about five minutes.
- **Looking something up?** Jump straight to [Part 4](#4-the-control-panel)
  for a plain-English explanation of every slider and button.
- **Stuck?** Go to [Part 10](#10-tips-and-troubleshooting).

---

## Table of contents

1. [Getting started](#1-getting-started)
2. [Your first map in five minutes](#2-your-first-map-in-five-minutes)
3. [Understanding your screen](#3-understanding-your-screen)
4. [The control panel](#4-the-control-panel)
   - [Toolbar](#41-toolbar-the-buttons-along-the-top)
   - [MAP panel](#42-map-panel)
   - [ISLANDS panel](#43-islands-panel)
   - [LANDSCAPE panel](#44-landscape-panel)
   - [TERRAIN NOISE panel](#45-terrain-noise-panel)
   - [SMOOTHING panel](#46-smoothing-panel)
   - [HYDRAULIC EROSION panel](#47-hydraulic-erosion-panel)
   - [MASKS panel](#48-masks-panel)
   - [STATS panel](#49-stats-panel)
5. [The previews](#5-the-previews)
6. [Undo, redo, save and load](#6-undo-redo-save-and-load)
7. [Exporting your map](#7-exporting-your-map)
8. [Putting your map into a game engine](#8-putting-your-map-into-a-game-engine)
9. [Recipes — quick starting points](#9-recipes--quick-starting-points)
10. [Tips and troubleshooting](#10-tips-and-troubleshooting)
11. [Glossary](#11-glossary)

---

## 1. Getting started

### What this program does

This program creates **heightmaps** — black-and-white images where every
pixel's brightness says how high the ground is at that spot. Game engines
(Unreal Engine, Unity, Godot and others) turn that image into real 3D
terrain: bright areas become hills and mountains, dark areas become valleys
and seabed.

You design the terrain by moving sliders and dragging islands around on
screen, watch it update live in 2D and 3D, then export a file your engine
can import.

Everything happens **on your own computer**. Nothing is uploaded to the
internet, there is no account to create, and no data leaves your machine.

### Starting the program (Windows)

1. Find the file **`server.bat`** in the program's folder.
2. **Double-click it.** A black window opens — leave it open, it is the
   program's engine room.
3. The first time you run it, it prepares itself and installs what it needs.
   This can take a few minutes; later starts are almost instant.
4. When it is ready it prints an address, for example:

   ```
   Terrain Heightmap Generator — http://127.0.0.1:8765
   ```

5. **Copy that address into your web browser** (Chrome, Edge or Firefox all
   work). If your browser opens the page by itself, even better — you are in.

> **Tip:** The number after the address (`8765`) can change if that number is
> already in use by another program. Always use the address the black window
> prints.

### Stopping the program

Close the black window. That's it. Your settings are not lost — use **Save**
(see [§6](#6-undo-redo-save-and-load)) before you close if you want to keep
your work.

---

## 2. Your first map in five minutes

Follow this once, start to finish, and the rest of the manual will make
sense.

1. **Start the program** (double-click `server.bat`) and open the address in
   your browser.
2. You will see an island in the **2D PREVIEW** on the right and a raised,
   3D version of it below. On the left is the control panel.
3. **Move the island:** press the middle of the island in the 2D preview and
   drag it somewhere else.
4. **Make it bigger:** drag the small square handle on the island's edge.
5. **Change the sea level:** drag the **Sea level** slider in the MAP panel
   right — the water rises and floods the low ground; left — it drops away.
6. **Add a second island:** **double-click** on an empty patch of water in
   the 2D preview. A new island appears, and a new card appears in the
   ISLANDS panel on the left.
7. **Give it a different look:** click that island's **↻** button next to
   *Terrain seed*, or drag its **Peaks** slider to add mountains.
8. When you like what you see, set **Full res** in the MAP panel to the size
   you need (try **2048** first), then press **Generate Full Res** in the
   top toolbar and wait for the button to finish counting percentages.
9. Press **PNG16** in the toolbar. Your heightmap downloads to your
   **Downloads** folder as `hmg_2048x2048.png`.

Done — that file is your terrain. [Part 7](#7-exporting-your-map) explains
which file format to pick and why.

---

## 3. Understanding your screen

The window is split into three areas:

```
┌───────────────────────────────────────────────────────────────┐
│ TOOLBAR:  Seed · Preview res · Generate Full Res · PNG16 …    │
├──────────────┬────────────────────────────────────────────────┤
│              │                                                │
│  CONTROL     │   2D PREVIEW  — top-down map, drag islands     │
│  PANEL       │                                                │
│  (left)      ├────────────────────────────────────────────────┤
│              │                                                │
│  MAP         │   3D PREVIEW  — walk around your terrain       │
│  ISLANDS     │                                                │
│  NOISE …     │                                                │
└──────────────┴────────────────────────────────────────────────┘
```

- **Toolbar (top)** — the buttons you use at the *end* of your work:
  resolution, rendering, exporting, saving, undo.
- **Control panel (left)** — every setting, grouped into collapsible-looking
  sections called *panels*. Previews refresh on their own as you change
  anything here; there is no Apply button.
- **Previews (right)** — the 2D map on top and the 3D view below it. They
  always show the same terrain.

**Hover over almost any label or button** and a small yellow note (tooltip)
appears explaining what it does in one line.

---

## 4. The control panel

### 4.1 Toolbar (the buttons along the top)

| Button | What it does |
| --- | --- |
| **Seed** + **↻** | The master random number. The same seed always rebuilds the exact same terrain, so a seed is like a recipe reference. The **↻** button rolls a new random one. *This only appears in Landscape mode* — islands each carry their own seeds instead (see [§4.3](#43-islands-panel)). |
| **Preview res** | Detail of the two preview windows: **256 / 512 / 1024**. Higher = sharper preview, slightly slower. Never changes the exported file. |
| **Generate Full Res** | Renders the final, full-size heightmap using the **Full res** size you chose. While it runs the button shows a percentage. **You must do this before you can export.** |
| **PNG16 / RAW16 / EXR** | Download your heightmap in one of three formats. Greyed out until a full-res render is finished and current. See [§7](#7-exporting-your-map). |
| **Save** | Downloads your whole setup as a small file named `heightmap-config.json`. Keep it and you can reload your exact map later. |
| **Load** | Reads a saved `heightmap-config.json` back in. |
| **↶ / ↷** | Undo and redo. Keyboard: **Ctrl+Z** to undo, **Ctrl+Shift+Z** or **Ctrl+Y** to redo (Cmd on Mac). See [§6](#6-undo-redo-save-and-load). |

> **Important habit:** whenever you change *any* setting, the export buttons
> switch off again — that's the program telling you the last full render is
> out of date. Just press **Generate Full Res** once more and they come back.

### 4.2 MAP panel

| Control | What it does | Things to try |
| --- | --- | --- |
| **Mode** | **Islands** = separate islands in a sea. **Landscape** = one continuous piece of inland terrain running off all four edges, with no water at all. | Switch between them to see the same noise settings in both worlds. |
| **Full res** | The size of the exported file: **512, 1024, 2048, 4096, 8192**, or **Custom…** for any width and height you type (64–8192). The **linked** tick-box keeps width and height equal. | Start at 1024 or 2048 while experimenting; go big only for the final export. |
| **Sea level** | The waterline, from 0 (no water) to 1 (everything flooded). Terrain below it becomes ocean. *Hidden in Landscape mode, which has no sea.* | 0.06 is the gentle default. Push it to 0.20 to drown the lowlands, or 0.01 for an archipelago of barely-raised atolls. |

Sea level is *real* height, not a painting layer: raising it genuinely
floods the land, and lowering it reveals the seabed that was always there.

### 4.3 ISLANDS panel

Each island gets its own **card** full of controls, so one island's settings
never disturb another. This is where most of the fun is.

**Panel buttons**

- **+ add** — appends a new island in the middle of the map.
- **↻ seeds** — gives *every* island brand-new random seeds (a whole new
  archipelago, same layout).

**Working with cards**

- **Click a card** to select that island — it becomes highlighted in the 2D
  preview, with its number printed on it.
- **Tick box** (top-left of the card) — turn the island off and on without
  deleting it. Great for "what does this look like without that one?"
- **×** (top-right) — delete the island. (If you delete the very last one,
  a fresh default island takes its place so the map is never empty.)

**Shape and position controls**

| Control | Range | What it does |
| --- | --- | --- |
| **X / Y** | numbers | Exact centre position. Dragging in the preview is easier — these are for fine nudges. |
| **Shape seed** + **↻** | huge numbers | Controls the *outline*: bays, peninsulas, lobes, rotation. Lock a seed you like and change other things freely — the coast stays. |
| **Terrain seed** + **↻** | huge numbers | Controls the *surface*: the rolling plain, mountains and erosion. Reroll it to reshape the land **under the same outline**. |
| **Size** | 0.02 – 0.9 | How big the island is, as a fraction of the map. |
| **Aspect** | 0.3 – 3.0 | Stretches it into an ellipse. 1.0 = round, 2.0 = twice as wide as tall. |
| **Shape** | 0 – 1 | Footprint variety: **0** = clean circle, **1** = strongly lobed, organic outline. |
| **Coast** | 0 – 1 | Shore steepness: **0** = sharp cliff-like drop at the waterline, **1** = long gentle beach slope. It changes the *angle*, not the island's size. |
| **Rotation** | 0 – 360° | Turns the island. You can also drag the orange dot in the preview. |

**Elevation controls** (the *ELEVATION* section of the card)

| Control | Range | What it does |
| --- | --- | --- |
| **Land** | 0.02 – 0.5 | Height of the island's flat lowland. Keep it above sea level or your island is a reef. |
| **Peaks** | 0 – 0.6 | How high mountains rise *above* the plain. |
| **Coverage** | 0 – 1 | How much of the island is high ground: **0** = flat atoll, **1** = mountains everywhere. |
| **Mount. size** | 0.5 – 2.5 | Breadth of each massif: low = scattered hills, high = one big range. |

> **Two seeds, two jobs.** *Shape seed* = where the coast is. *Terrain seed*
> = what grows on it. Found a coastline you love but hate the hills? Lock
> the Shape seed, reroll the Terrain seed. It is the single most useful habit
> in this program.

**Direct editing in the 2D preview** (often faster than sliders):

- **Drag the middle** of an island → move it.
- **Drag the small square handle** on its edge → resize.
- **Drag the orange dot** → rotate.
- **Click anywhere on the island** → select its card.
- **Double-click empty water** → add a new island right there.

Islands are always kept fully inside the map frame, so an island can never
be cut off at the border — dragging stops at the edge on purpose.

### 4.4 LANDSCAPE panel

Appears only when **Mode = Landscape**. It has four controls, applied to
the whole map:

| Control | Range | What it does |
| --- | --- | --- |
| **Plain height** | 0.02 – 0.6 | The height most of the map sits at — the "ground floor". |
| **Mountain height** | 0 – 0.6 | How far ranges rise above that floor. |
| **Mountain coverage** | 0 – 1 | How much of the map is mountainous: **0** endless plain, **1** mountains edge to edge. |
| **Mountain size** | 0.6 – 2.0 | Scattered hills (low) vs. one broad massif (high). |

In this mode there is no coast and no sea, so the **Coast** slider and
**Coast roughness** do nothing — the terrain simply runs off the edges.

### 4.5 TERRAIN NOISE panel

These five sliders control the texture of the ground itself, in both modes.
(In Landscape mode the **Coast roughness** slider hides itself, and
**Terrain detail** appears under the name **Plain roll** — same slider,
worded for a map with no shore.)

| Control | Range | What it does | Things to try |
| --- | --- | --- | --- |
| **Feature size** | 0.5 – 20 | Spacing of the hills. **Low = broad, gentle hills; high = tight, bumpy hills.** 2.5 keeps the tuned default look. | 1.0 for big rolling landscape, 8–12 for rugged bumpy ground. |
| **Terrain detail** | 0 – 1 | How much fine bumpiness is added on top. At **0** the lowland is perfectly flat. *In Landscape mode this same slider is renamed **Plain roll** — there it controls how much the lowland rolls up and down around the plain height.* | 0 = "I want a clean buildable plain", 1 = maximum crunch. |
| **Coast roughness** | 0 – 1 | How much the *waterline* wiggles in and out. Islands mode only. | 0.6+ gives gnarly, fjord-like coasts. |
| **Detail falloff** | 0.05 – 0.95 | How quickly each finer layer fades out. Low = smooth hills, high = detail stays strong all the way down. | 0.35 for soft, 0.7 for craggy. |
| **Octaves** | 1 – 10 | Number of noise layers stacked together. More layers = more fine detail. | 6 is the default; drop to 2–3 for stylised, smooth terrain. |
| **↻ reset** | — | Puts all five sliders back to their starting values (2.5 / 0.40 / 0.35 / 0.50 / 6). |

### 4.6 SMOOTHING panel

| Control | Range | What it does |
| --- | --- | --- |
| **Thermal** | 0 – 1 | Weathering: steep crests crumble and round into soft shoulders. It never moves the coastline. Raise it to kill spiky, unnatural ridges. |
| **Blur** | 0 – 1 | A gentle overall softening that removes leftover scratches and speckles. Use sparingly — too much melts your mountains. |

Rule of thumb: **Thermal fixes the ridgelines, Blur fixes the surface.**

### 4.7 HYDRAULIC EROSION panel

Simulates rain: thousands of droplets roll downhill, carve valleys and drop
sediment where the ground flattens. This is what makes terrain look like
real geology instead of noise.

| Control | Range | What it does |
| --- | --- | --- |
| ☐ **enabled** | on/off | Turns the whole simulation on or off. The sliders below are greyed out when it's off. |
| **Droplets** | 0 – 400,000 (default 60,000) | How many raindrops. More = deeper, more convincing valleys — and a slower render. |
| **Steps** | 0 – 120 (default 30) | How far each droplet travels. Longer paths = longer, more connected river valleys. |

Try **60,000 / 30** first; if the terrain looks too soft, go to **150,000**.
Droplet counts are automatically scaled for your map size, so a preview and
a 4096 export look alike.

### 4.8 MASKS panel

Masks are extra helper images (plain black-and-white PNGs) that engines use
to blend materials — for example, rock on steep ground and grass
everywhere else. They are created at your **Full res** size, right after
**Generate Full Res**.

| Control | What it does |
| --- | --- |
| **Steepness** (0 – 1) | How steep the ground must be to count as "rock". Careful — this slider runs on a percentile scale, so **higher means *less* rock**: 0 marks quite steep ground as rock, 1 only the very steepest. |
| **Water mask** | White (255) below sea level, black (0) on land. Use it to place water, foam or sand. *Islands mode only* — in Landscape mode this button stays greyed out because there is no sea. |
| **Slope mask** | White where the ground is steep, black where it is flat, with a soft feathered edge so it blends smoothly. |

### 4.9 STATS panel

Live numbers for the preview you are looking at:

- **min / max / mean** — lowest, highest and average height (0 to 1).
- **land %** — how much of the map is above sea level (islands mode only).
- **preview … in …ms** — the preview size and how long it took to render.
  After a full render it briefly shows how long *that* took.

`max` is worth watching: it tells you how tall your terrain will be once
imported (see [§8](#8-putting-your-map-into-a-game-engine)).

---

## 5. The previews

### 2D PREVIEW (top-down map)

- **Drag the island body** to move it, **the square handle** to resize,
  **the orange dot** to rotate.
- **Double-click empty water** to drop in a new island.
- Each island shows its number, matching the number on its card.
- Selected island is highlighted.

### 3D PREVIEW (the terrain in relief)

| Action | Result |
| --- | --- |
| **Left-drag** | Orbit around the terrain |
| **Mouse wheel** | Zoom in and out |
| **Right-drag** | Pan the view sideways |
| **Double-click** | Reset to the default view |

Both previews use identical shading and the same rock threshold, so if
something looks steep in 2D it looks steep in 3D — they will never
disagree.

**Preview res** (toolbar) only changes how sharp these two windows are.
The exported file always uses the **Full res** setting.

---

## 6. Undo, redo, save and load

### Undo / redo

- **↶** or **Ctrl+Z** — step back one change.
- **↷** or **Ctrl+Shift+Z** / **Ctrl+Y** — step forward again.
- Covers: slider drags, moved/resized/rotated islands, added or deleted
  islands, seed rerolls, and loading a config.
- The history keeps the last **50** states. Making a new change clears the
  redo branch (exactly like a word processor).
- Typing in a number box has its own ordinary text undo — edit the text,
  press Ctrl+Z, and you get your *typing* back, not your whole map.

### Save / load

- **Save** downloads `heightmap-config.json` — a small text file holding
  every setting of your current map. It contains no images and no secrets.
- **Load** picks that file (or any config file you have) and restores it.
  Partial files work too: anything missing simply keeps its default value.

**Get into the habit of pressing Save before you close.** It is the only
way to reopen an exact map later — every slider, every seed, every island.

---

## 7. Exporting your map

### The golden rule

> **Every change → Generate Full Res → then export.**

Export buttons are disabled whenever the settings have moved on since the
last full render. If they look greyed out, that's the whole reason.

### Choosing a format

| Button | File | Use it when |
| --- | --- | --- |
| **PNG16** | `hmg_2048x2048.png` | The default choice. A 16-bit grayscale image, read directly by **Unreal Engine's landscape importer**, Unity with a heightmap importer, and most image-based pipelines. |
| **RAW16** | `hmg_2048x2048.raw` | Your engine or tool wants a bare list of numbers instead of an image. You must tell it the width and height yourself. |
| **EXR** | `hmg_2048x2048.exr` | Professional float pipelines — **Blender, Houdini, compositing** — where you want perfectly smooth height precision. |

All three contain the *same* terrain; only the packaging differs. When in
doubt, use **PNG16**.

### What you get

- Files land in your browser's **Downloads** folder, named with their size
  so you can tell versions apart.
- Heights are exported **exactly as the preview shows them** — nothing is
  stretched or rescaled behind your back. What you see in the STATS panel
  is what the file contains.
- Masks download separately as `hmg_2048x2048_water.png` and
  `hmg_2048x2048_slope.png`.

### Recommended export workflow

1. Design at a small **Preview res** (256 or 512) — fast feedback.
2. When the look is right, set **Full res** to your target size.
3. Press **Generate Full Res** and let it finish (seconds at 1024, a minute
   or two at 4096, longer at 8192).
4. Press **PNG16** (plus any masks you need).
5. Press **Save** so you can reproduce the map later.

---

## 8. Putting your map into a game engine

A heightmap only stores *relative* height from 0 to 1. The final size in
metres is always chosen **inside your engine's import dialog** — every
engine has one, and that's where you decide "this map is 512 metres wide
and 400 metres tall".

Typical path for **Unreal Engine**:

1. Import the **PNG16** file through Unreal's landscape import tool.
2. Set the map's width/depth and the height scale in that dialog.
3. Because our exports are *not* rescaled, terrain will land at the same
   proportions you saw in the 3D preview — no surprise 7× walls of rock.

Practical sizes:

| Full res | Good for |
| --- | --- |
| 1024 | Prototyping, small levels |
| 2048 | Standard game map |
| 4096 | Large open-world tile |
| 8192 | Cinematic / giant maps (needs a patient computer) |

Use the **slope mask** to paint rock automatically, and the **water mask**
to place your water surface exactly at the generator's sea level.

---

## 9. Recipes — quick starting points

Set **Mode** as noted, then dial in the sliders. Nothing here is sacred —
nudge from these bases.

### 🏝 Tropical island chain
*Mode: Islands*
- Sea level **0.06**, island **Coast** **0.8–1.0** (gentle beaches)
- **Shape** **0.4–0.6**, **Coast roughness** **0.3–0.5**
- **Land** **0.10–0.15**, **Peaks** **0.15**, **Coverage** **0.15**
- Noise: **Feature size** **2.5**, **Terrain detail** **0.4**, **Octaves** **6**
- Erosion on: **60,000** droplets, **30** steps

### 🗻 Rugged mountain island
- **Land** **0.12**, **Peaks** **0.45**, **Coverage** **0.6**, **Mount. size** **1.5**
- **Feature size** **5–8**, **Terrain detail** **0.7**, **Detail falloff** **0.6**
- Erosion: **150,000** droplets, **50** steps
- **Thermal** **0.6** to round the sharpest spikes, **Blur** **0.3**

### 🏜 Flat atoll / buildable island
- **Peaks** **0**, **Coverage** **0**
- **Terrain detail** **0.15**, **Feature size** **1.5**
- **Blur** **0.6** for a silky-smooth plain
- Perfect base for a base-building game

### 🌄 Inland mountain tile (no water)
*Mode: Landscape*
- **Plain height** **0.12**, **Mountain height** **0.35**
- **Coverage** **0.25**, **Mount. size** **1.2**
- Noise: **Feature size** **3.5**, **Octaves** **7**
- Erosion: **120,000** droplets, **40** steps

### 🌊 Fjord coast (dramatic shoreline)
- **Coast** **0.0–0.15** (steep drop), **Coast roughness** **0.7–1.0**
- **Shape** **0.8–1.0**, reroll **Shape seed** a few times
- **Peaks** **0.35**, **Coverage** **0.45**

**A quick tour of the main levers**

| I want… | Turn… |
| --- | --- |
| Bigger, calmer hills | Feature size ↓ |
| More small bumps | Feature size ↑, Octaves ↑ |
| Higher mountains | Peaks ↑ (or Mountain height in Landscape) |
| More land covered in rock | Coverage ↑ |
| Deeper valleys | Droplets ↑, Steps ↑ |
| Smoother, cleaner terrain | Thermal ↑, Blur ↑, Terrain detail ↓ |
| A wilder coastline | Coast roughness ↑, Shape ↑, reroll Shape seed |
| The same land, reshuffled | Reroll **Terrain seed** only |
| A whole new world | **↻ seeds** in the ISLANDS header |

---

## 10. Tips and troubleshooting

**The export buttons are grey.**
You changed something after the last full render. Press **Generate Full Res**
and wait for it to finish.

**I moved a slider and nothing happened in the preview.**
The preview redraws automatically but takes a moment — give it a second,
especially at Preview res 1024 or with heavy erosion. Also check you are in
the right mode (Coast settings, for example, only apply to Islands).

**Water mask button is greyed out.**
You are in Landscape mode, which has no sea. Switch to Islands.

**The Seed box in the toolbar disappeared.**
Normal — that box belongs to Landscape mode. In Islands mode each island
has its own two seeds.

**My island won't drag off the edge of the map.**
Intentional: islands are kept fully inside the frame so nothing gets sliced
by the border. Make the map bigger (Custom… Full res) or shrink the island.

**I flooded everything by raising Sea level.**
Undo it (**Ctrl+Z**), or lower Sea level again. Terrain below the waterline
is always there — it just isn't visible.

**8192 export is taking forever / my computer is struggling.**
Large maps need time and memory. Export at 2048 or 4096 first — most games
don't need more — and close other heavy programs.

**The page looks broken or half-updated after the program was updated.**
Press **Ctrl+F5** (Cmd+Shift+R on Mac) to force a full refresh.

**I closed the black window and the page stopped working.**
That window *is* the program. Double-click `server.bat` again.

**I lost my map.**
If you pressed **Save** at some point, use **Load** and pick the
`heightmap-config.json` file from your Downloads folder. If you didn't save,
**Ctrl+Z** can walk back through your last 50 changes.

**Can I run two copies at once?**
Yes — the launcher picks a free address automatically if the usual one is
taken. Just use whichever address it prints.

**Nothing leaves my computer.**
Correct — the program runs entirely on `127.0.0.1` (your own machine). No
accounts, no telemetry, no uploads.

---

## 11. Glossary

| Term | Meaning |
| --- | --- |
| **Heightmap** | An image where pixel brightness = ground height. |
| **Sea level** | The height at which water begins; terrain below it is ocean. |
| **Seed** | A number that fully determines the random look of the terrain — same seed, same map, every time. |
| **Shape seed / Terrain seed** | The two per-island seeds: one fixes the coastline, the other the land on top. |
| **Octaves** | How many layers of noise are stacked: more layers = more fine detail. |
| **Feature size** | How tightly packed the hills are — low for broad hills, high for bumpy ground. |
| **Erosion** | The simulated rainfall pass that carves valleys and deposits sediment. |
| **Thermal smoothing** | A weathering pass that rounds off sharp ridge crests. |
| **Mask** | A helper black-and-white image telling the engine where one material ends and another begins (water, rock). |
| **Full res** | The pixel size of the file you export — unrelated to preview sharpness. |
| **16-bit (PNG16 / RAW16)** | 65,536 shades of grey instead of 256, so heights are smooth rather than stepped. |

---

*Technical documentation, the HTTP API and the configuration reference live
in [README.md](README.md). This manual covers the visual interface.*