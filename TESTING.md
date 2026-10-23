# Test checklist (Fusion)

Open **View > Show Text Commands** before starting; any `[Gridfinity v2]` lines there are useful to copy back.

## A. Start-up
1. Stop the original add-in. Run gridfinity_v2. Both v2 buttons appear in Solid > Create, with icons.

## B. Create
2. Default bin (1x1x1 Solid, lip). Check size 41.5 x 41.5 and height 11.4 mm.
3. 3x2x3 Hollow, lip. Timeline should show one foot plus a pattern (not 6 lofts).
4. 2x2x4 Hollow with 3 x 2 compartments, label shelf, scoop. Check dividers, shelf at the back (+Y), scoop at the front (-Y).
5. 2x1x3 with magnets + screw holes. Check 6.5 mm holes 2.4 deep with lead-in, Ø3 holes above them, floor not pierced.
6. 7x1: bed-size warning appears. Custom X 25: OK button disabled with a "Fix:" note.
7. Base 3x2 with magnets and 5 mm X padding.
8. Open Create again: last settings are pre-filled.
9. Create while a sub-component is active: the bin lands inside it.

## C. Edit — the sketch rule
10. On bin 3 draw a sketch on the **rim** and one on the **inside floor**; extrude one of them.
11. Edit it to 4x2: warning says how many features will be removed. After: both sketches still there, in the same X/Y, the rim one at the rim; the foot grid is 4x2.
12. Edit to 4x2x5: rim sketch rises to the new rim.
13. Edit to 3x2 (shrink): warning about rebuilding; the bin is rebuilt (sketches may go).
14. Edit a 3x2 bin to 4x1 (X up, Y down): counts as a shrink and asks before rebuilding.

## D. Edit — other paths
15. Z only, up and down: foot and magnets kept, lip moved.
16. Magnets on/off and diameter change only: in place, nothing else changes.
17. Compartments/label/scoop only: in place.
18. Hollow -> Solid: rebuild warning.
19. Move a bin (or put it in a sub-component), then do a rebuild-type edit: it stays where it was.
20. Edit a bin made by the **original** add-in: settings load, a magnet-only edit is in place, a grow keeps sketches.
21. Edit a custom 12-unit bin and only add magnets: in place, not a rebuild.

## E. Clean-up
22. After several edits the browser has no pile of unused planes.
23. Stop the add-in: buttons disappear, no error.
