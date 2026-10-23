# Gridfinity v2 for Fusion 360

A Fusion 360 add-in that makes Gridfinity **bins** and **baseplates** as normal, editable Fusion features, and lets you **edit them later without losing your own sketches**.

- Bins: any size up to 20 × 20 units, 1–40U tall, hollow or solid, stacking lip
- Hollow bin extras: divider compartments, label shelf, finger scoop
- Magnet sockets (default 6.5 × 2.4 mm for 6 × 2 magnets) and M3 screw holes
- Baseplates with edge padding and underside magnet pads
- **Edit** remembers each item's settings. Make a bin bigger and your sketches stay put.
- Print-bed size check (default 256 mm, Bambu A1), remembers your last settings

Version 2.0.0 · MIT license · Windows (tested), macOS (should work, untested)

## Install

1. Download the latest **gridfinity_v2.zip** from the [Releases](../../releases) page and unzip it somewhere permanent (for example `Documents`).
2. The folder must be named exactly **`gridfinity_v2`**. If you used GitHub's green *Code → Download ZIP* button, the folder comes out as `gridfinity_v2-main`. Rename it, or Fusion won't load it.
3. In Fusion: **Utilities → Scripts and Add-Ins** (Shift+S) → **Add-Ins** tab → **+** → pick the `gridfinity_v2` folder.
4. Select **gridfinity_v2** → **Run**. Tick **Run on Startup** to keep it.
5. **Gridfinity Create v2** and **Edit Gridfinity Item v2** appear in **Solid → Create**, next to Hole. If they only show in the Create dropdown, hover one, click **⋮** and choose **Pin to Toolbar**.

> **Part designs:** newer Fusion "Part" designs allow only one component. The add-in offers to switch the design to **Hybrid** the first time you create an item.

## Create options

| Option | Notes |
|---|---|
| X / Y units | 1–10 from the list, or Custom up to 20. 42 mm grid, 0.5 mm clearance. |
| Z units | 1–20 from the list, or Custom (decimals allowed) up to 40. 7 mm per U, foot bottom to rim. |
| Bin type | Hollow or Solid |
| Stacking lip | 4.4 mm above the rim (0.7 / 1.8 / 1.9 mm profile) |
| Compartments X / Y | Hollow only. Equal compartments, 1.2 mm dividers |
| Label shelf | Hollow only. 12 mm shelf on the back wall with a 45° underside (no supports) |
| Finger scoop | Hollow only. Round scoop along the front wall |
| Magnet sockets | Default 6.5 × 2.4 mm, 0.5 mm lead-in, 4 per cell at ±13 mm |
| Screw holes (M3) | Ø3 mm under each magnet position, never through the floor |
| Base edge padding | Baseplates only. Extra border per side, cells stay on the grid |
| Printer bed size | Warns when the item won't fit (default 256 mm) |

The line at the bottom of the dialog tells you what's wrong (OK stays disabled until it's fixed) and, in Edit, what your change will do.

## Editing and your sketches

| Change | What happens |
|---|---|
| **Make it bigger** in X/Y (Z may change too) | Rebuilt in place. **All your sketches are kept**: rim and lip sketches follow the new height, floor sketches stay put, and the lower-left corner doesn't move. Your extrudes/cuts are removed after a warning that says how many. |
| **Make it smaller** in any direction (even if the other grows) | Rebuilt from scratch after a warning. Your sketches on it may be removed. |
| Height only | Walls and lip rebuilt; feet, magnets and sketches kept |
| Magnets / screw holes only | Updated in place |
| Compartments / label / scoop only | Updated in place |
| Hollow ↔ Solid, lip on/off | Rebuilt after a warning |
| Baseplates | Rebuilt after a warning |

This works for sketches inside the bin, and for sketches you draw on a bin's faces from the main design. Two limits:
- Sketches on a **side wall** can't follow a rebuild. They're counted in the warning so you know to re-attach them.
- **Projected edges** inside a sketch can break, because the edges they came from get rebuilt.

Tip: the **Gridfinity custom sketch plane** inside every bin sits at the rim and always follows height changes, which makes it a good place for labels and cut-outs.

## For developers

```
gridfinity_v2.py          entry point (run/stop)
gf/constants.py           every dimension (mm) and ID
gf/config.py              settings, validation, edit planning — no Fusion imports
gf/ui.py                  the dialog
gf/commands.py            buttons, create and edit flow
gf/bin_geometry.py        bin modelling
gf/base_geometry.py       baseplate modelling
gf/edit_ops.py            edits that keep your sketches
gf/managed.py             tells add-in sketches/features apart from yours (by attribute tag)
gf/util.py                Fusion helpers
tests/test_config.py      `python -m pytest tests` (no Fusion needed)
TESTING.md                manual test checklist for Fusion
```

Errors are logged to Fusion's **Text Commands** window (View → Show Text Commands), prefixed `[Gridfinity v2]`. Stop/Run reloads all modules, so code edits don't need a Fusion restart.

Items made with the original 0.5.x add-in can be edited with v2.

## License

MIT. See [LICENSE](LICENSE). Gridfinity is Zack Freedman's open modular storage system; this add-in is an independent tool for making compatible parts.
