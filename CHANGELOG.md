# Changelog

## 2.0.0 — from 0.5.40

### Fixes
- **Edits that rebuild no longer jump to the origin.** The new item is created in the same parent component, at the same position, and around the same centre as the one it replaces. New items go into the active component.
- **Magnet default is now 6.5 × 2.4 mm** (was 6.0 × 2.0, too tight for 6 × 2 magnets). Items you already made keep their saved size.
- **Input limits.** Custom X/Y up to 20, Z up to 40; magnet diameter 2–9 mm, depth limited so it can't cut through the foot; compartments can't get narrower than 8 mm. Problems show in the dialog and the OK button stays off. A print-bed check (default 256 mm) warns when the item is too big.
- **Your sketches are told apart by tag, not by name.** Every sketch, feature and plane the add-in makes is tagged. The four mismatched name lists from 0.5.40 are now one list, used only for items made by the old version. A sketch of yours called "Bin walls" is no longer at risk.
- **Editing a custom size (e.g. 12 units) no longer looks like a shrink.** Untouched axes keep their real value, so adding magnets to a 12-unit bin is an in-place update, not a full rebuild.
- **Floor sketches survive footprint growth.** Sketches on flat faces are moved to matching planes before the rebuild; sketches on side walls are counted in the warning.
- Old planes are removed with their sketches instead of piling up after every edit.
- Handlers are released when a dialog closes.
- "Nothing changed" no longer rebuilds the item.

### Found and fixed while testing in Fusion (2026-10-23)
- **Cuts reached into other items** (also in 0.5.40): when items overlapped at the origin, a cut on one also cut its neighbours and Fusion filed the feature under the wrong component. Cuts are now limited to the item's own body.
- **New-style Part designs** only allow one component; Create now offers to switch the design to Hybrid.
- New items were being nested inside the previously created item; Fusion activates a new component, so the add-in now steps back to the root.
- Remembered settings added one U to Z on every reopen.
- A v1 bin that had a v2 magnet edit lost track of its old sketches on the next grow.
- Sketches on faces could not be read while the timeline was at the end (Fusion "BRefFace" error); floor and rim face sketches are now detected from the sketch's own position.
- Unused planes are now actually removed after edits (stale references skipped the clean-up).
- Rebuilds (shrink, Hollow/Solid) keep the lower-left corner in place, like growing does.
- Base magnet pad fillet starts at 1.0 mm (1.5 never solved), saving several seconds.
- **Sketches drawn on a bin from the main design** (without activating the bin) are now kept on edits too: rim/lip sketches follow the rim, floor sketches stay put.
- Buttons sit on the toolbar right after Hole, like the original.
- Stop/Run now reloads every module, so updates load without restarting Fusion.
- Remembered and dialog settings are marked as v2 so they're never mistaken for old saved items.

### New
- Compartments (X and Y), label shelf, finger scoop (hollow bins).
- M3 screw holes under the magnet positions.
- Remembers your last Create settings.
- Printer bed size setting.
- Live status line in the dialog.
- Changing only magnets/screws or only interior options updates in place.

### Faster
- One foot (and one baseplate socket) is modelled, then copied with a Rectangular Pattern. If Fusion can't pattern it, it falls back to one loft per cell.
- Magnet and screw holes are one cut feature each, not one per hole.

### Code
- Split into modules (see README). All dimensions in `constants.py` in mm.
- `except:` replaced with `except Exception:` plus logging to Text Commands.
- Duplicate cell-centre / magnet-position / settings-compare code merged.
- Removed unused functions (`_add_polygon`, `_add_rect`, `_add_rounded_polygon`, `_move_stacking_lip_planes`, `_remove_custom_sketches`, `_ring_profile`, `_set_bin_body_height`).
- Unit tests for settings, validation and the edit rules (`tests/`).
