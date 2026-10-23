"""Edits that keep the user's work: footprint growth, height changes, in-place option updates.

The rule (unchanged from v1, and the reason this file exists):
  * Growing X/Y keeps every user sketch and construction plane. Rim sketches
    follow the new height. Modeled features are rebuilt and user extrusions are
    removed after a confirmation that lists how many.
  * Shrinking any axis is a fresh rebuild (handled in commands.py), which may
    remove user sketches.
"""

import adsk.core
import adsk.fusion

from . import bin_geometry as geo
from . import config as cfg
from . import constants as C
from . import managed
from . import util
from .constants import cm

TOL = 0.015   # 0.15 mm, in cm


# ---------------------------------------------------------------------------
# Small queries
# ---------------------------------------------------------------------------
def bin_center(component, saved):
    """Centre of the bin in its component (saved value, else measured body box)."""
    if '_center_x_cm' in saved and '_center_y_cm' in saved:
        return float(saved['_center_x_cm']), float(saved['_center_y_cm'])
    if component.bRepBodies.count:
        b = component.bRepBodies.item(0).boundingBox
        return (b.minPoint.x + b.maxPoint.x) / 2.0, (b.minPoint.y + b.maxPoint.y) / 2.0
    return 0.0, 0.0


def plane_height(plane):
    try:
        geometry = plane.geometry
        if abs(abs(geometry.normal.z) - 1.0) > 0.001:
            return None
        return geometry.origin.z
    except Exception:
        return None


def custom_sketches_on_top(component, top_cm, skip_planes=()):
    """User sketches drawn directly on the rim face (they must move before the rim is rebuilt)."""
    skip = set(p.name for p in skip_planes)
    found = []
    for sketch in managed.custom_sketches(component):
        plane = util.support_plane(sketch)
        if plane and plane.name in skip:
            continue
        on_face, normal_z, height = util.sketch_frame(sketch)
        if on_face and abs(abs(normal_z) - 1.0) < 1e-6 and abs(height - top_cm) <= TOL:
            found.append(sketch)
    return found


def custom_offset_planes_at(component, height_cm):
    """User offset planes at the rim (not the add-in's own support planes)."""
    generated_support = set()
    custom_names = set(s.name for s in managed.custom_sketches(component))
    for sketch in component.sketches:
        if sketch.name in custom_names:
            continue
        try:
            plane = util.support_plane(sketch)
            if plane:
                generated_support.add(plane.name)
        except Exception:
            pass
    found = []
    for plane in component.constructionPlanes:
        if plane.name in generated_support or util.is_tagged(plane):
            continue
        height = plane_height(plane)
        if (adsk.fusion.ConstructionPlaneOffsetDefinition.cast(plane.definition) and
                height is not None and abs(height - height_cm) <= TOL):
            found.append(plane)
    return found


def move_offset_planes(planes, component, new_height_cm):
    """Re-anchor rim work planes to XY so they track the new height."""
    for plane in planes:
        if not plane or not plane.isValid:
            continue
        plane.timelineObject.rollTo(True)
        definition = adsk.fusion.ConstructionPlaneOffsetDefinition.cast(plane.definition)
        if definition and not definition.redefine(
                adsk.core.ValueInput.createByReal(new_height_cm), component.xYConstructionPlane):
            raise RuntimeError('Fusion could not move construction plane "{}" to the resized bin rim.'.format(
                plane.name))
    component.parentDesign.timeline.moveToEnd()


def keep_plane_before(plane, sketches):
    sketches = [s for s in sketches if s.isValid]
    if not sketches:
        return
    first = min(s.timelineObject.index for s in sketches)
    if plane.timelineObject.index > first and not plane.timelineObject.reorder(first):
        raise RuntimeError('Could not keep construction plane "{}" ahead of its sketches.'.format(plane.name))


def redefine_keep_xy(sketch, support_plane):
    """Move a sketch onto a new support without shifting it in X/Y."""
    old_origin = sketch.origin.copy()
    if not sketch.redefine(support_plane):
        raise RuntimeError('Fusion could not reattach custom sketch "{}".'.format(sketch.name))
    anchor = sketch.modelToSketchSpace(old_origin)
    if abs(anchor.x) <= 1e-7 and abs(anchor.y) <= 1e-7:
        return
    entities = adsk.core.ObjectCollection.create()
    for i in range(sketch.sketchCurves.count):
        entities.add(sketch.sketchCurves.item(i))
    for i in range(sketch.sketchTexts.count):
        entities.add(sketch.sketchTexts.item(i))
    if entities.count == 0:
        for i in range(sketch.sketchPoints.count):
            entities.add(sketch.sketchPoints.item(i))
    if entities.count == 0:
        return
    move = adsk.core.Matrix3D.create()
    move.translation = adsk.core.Vector3D.create(anchor.x, anchor.y, 0)
    if not sketch.move(entities, move):
        raise RuntimeError('Fusion could not keep the X/Y position of sketch "{}".'.format(sketch.name))


def custom_features_above(component, cutoff_cm, include_boundary=False):
    """User features that depend on, or reach above, the given rim height."""
    body = managed.body_height_feature(component)
    if not body:
        return managed.custom_features(component)
    body_index = body.timelineObject.index

    def above(z):
        return z >= cutoff_cm - 0.001 if include_boundary else z > cutoff_cm + 0.001

    affected = []
    for feature in managed.custom_features(component):
        try:
            if feature.timelineObject.index <= body_index:
                continue
        except Exception:
            continue
        top = util.feature_max_z(feature)
        sketches = util.feature_source_sketches(feature)
        hit = top is not None and top > cutoff_cm + 0.001
        for sketch in sketches:
            try:
                _, normal_z, height = util.sketch_frame(sketch)
                if abs(abs(normal_z) - 1.0) < 1e-6 and above(height):
                    hit = True       # drawn on (or above) the rim that is about to move
            except Exception:
                continue
        if hit:
            affected.append(feature)
    return affected


def fix_legacy_deck(component):
    """v1 bins built before the 1.2 mm deck: bring the deck to the current thickness."""
    for item in util.model_features(component):
        feature = item.entity
        names = [s.name for s in util.feature_source_sketches(feature)]
        if feature.name != 'Gridfinity base deck' and 'Gridfinity base deck' not in names:
            continue
        extent = adsk.fusion.DistanceExtentDefinition.cast(feature.extentOne)
        distance = adsk.fusion.ModelParameter.cast(extent.distance) if extent else None
        if not distance or abs(distance.value - cm(C.DECK)) < 1e-6:
            return
        item.rollTo(True)
        distance.value = cm(C.DECK)
        component.parentDesign.timeline.moveToEnd()
        return


def _external_face_sketches(occurrence):
    """Sketches in the main design (root) that were drawn on this bin's faces.

    Clicking a bin face without activating the bin puts the sketch in the root,
    outside the bin. Fusion only reveals which face it is after rolling the
    timeline back to just before the sketch, so this rolls back, looks, and
    returns to the end. Returns (sketch, normal_z, height_cm) in bin space.
    """
    component = occurrence.component
    design = component.parentDesign
    root = design.rootComponent
    if component == root:
        return []
    to_bin = occurrence.transform2.copy()
    to_bin.invert()
    found = []
    for sketch in list(root.sketches):
        try:
            if not util.sketch_frame(sketch)[0]:
                continue
            sketch.timelineObject.rollTo(True)
            try:
                face = adsk.fusion.BRepFace.cast(sketch.referencePlane)
                ours = face is not None and face.body.parentComponent == component
            finally:
                design.timeline.moveToEnd()
            if not ours:
                continue
            matrix = sketch.transform.copy()
            matrix.transformBy(to_bin)          # sketch space -> bin space
            found.append((sketch, matrix.getCell(2, 2), matrix.getCell(2, 3)))
        except Exception:
            design.timeline.moveToEnd()
            util.log_exception('Could not check sketch "{}"'.format(sketch.name))
    return found


def face_sketches(occurrence):
    """Every face-based user sketch tied to this bin: (sketch, normal_z, height_cm, is_external)."""
    entries = []
    for sketch in managed.custom_sketches(occurrence.component):
        try:
            on_face, normal_z, height = util.sketch_frame(sketch)
        except Exception:
            continue
        if on_face:
            entries.append((sketch, normal_z, height, False))
    entries += [(s, nz, h, True) for s, nz, h in _external_face_sketches(occurrence)]
    return entries


def _is_flat(normal_z):
    return abs(abs(normal_z) - 1.0) < 1e-6


def side_wall_sketches(occurrence):
    """Sketches on upright faces (inside or outside the bin): they cannot follow a rebuild."""
    return [entry[0] for entry in face_sketches(occurrence) if not _is_flat(entry[1])]


RIM_PLANE_PREFIX = 'Gridfinity rim +'
FIXED_PLANE_PREFIX = 'Gridfinity sketch plane '


def _anchor_plane(component, height_cm, old_top_cm):
    """A plane for a sketch at this height: rim-relative at/above the rim, fixed below it."""
    above = height_cm - old_top_cm
    if above >= -TOL:
        rim = geo.custom_sketch_plane(component)
        if abs(above) <= TOL:
            return rim
        name, base, offset = '{}{:.2f} mm'.format(RIM_PLANE_PREFIX, above * 10.0), rim, above
    else:
        name, base, offset = '{}{:.2f} mm'.format(FIXED_PLANE_PREFIX, height_cm * 10.0), None, height_cm
    plane = component.constructionPlanes.itemByName(name)
    if plane is None:
        plane = util.new_plane(component, offset, base)
        plane.name = name
        plane.isLightBulbOn = False
    return plane


def anchor_face_sketches(occurrence, old_top_cm):
    """Move flat-face sketches (inside the bin or drawn on it from the main design) onto planes.

    The faces disappear when the bin is rebuilt. Sketches at or above the rim
    follow the rim to its new height; lower ones (floor, underside) stay put.
    X/Y never changes.
    """
    component = occurrence.component
    moved = 0
    for sketch, normal_z, height, external in face_sketches(occurrence):
        if not _is_flat(normal_z):
            continue
        plane = _anchor_plane(component, height, old_top_cm)
        keep_plane_before(plane, [sketch])
        target = plane.createForAssemblyContext(occurrence) if external else plane
        redefine_keep_xy(sketch, target)
        moved += 1
    return moved


# ---------------------------------------------------------------------------
# Rim sketch / plane bookkeeping shared by the height and expand paths
# ---------------------------------------------------------------------------
class RimKeeper:
    """Remember rim sketches and planes before a rebuild and put them back after."""

    def __init__(self, component, old_top_cm, new_top_cm, extra_features=()):
        self.component = component
        self.new_top = new_top_cm
        self.sketch_visibility = {s.name: s.isLightBulbOn for s in managed.custom_sketches(component)}
        own_plane = geo.custom_sketch_plane(component)
        self.planes = custom_offset_planes_at(component, old_top_cm)
        if own_plane and all(p.name != own_plane.name for p in self.planes):
            self.planes.append(own_plane)
        # Planes that carry sketches of features about to be removed must follow too.
        custom_names = set(s.name for s in managed.custom_sketches(component))
        self.to_relocate = custom_sketches_on_top(component, old_top_cm, self.planes)
        for feature in extra_features:
            for sketch in util.feature_source_sketches(feature):
                if sketch.name not in custom_names:
                    continue
                if all(s.name != sketch.name for s in self.to_relocate):
                    self.to_relocate.append(sketch)
                try:
                    plane = util.support_plane(sketch)
                    if (plane and adsk.fusion.ConstructionPlaneOffsetDefinition.cast(plane.definition)
                            and all(p.name != plane.name for p in self.planes)):
                        self.planes.append(plane)
                except Exception:
                    pass
        self.keep_visible = set(s.name for s in self.to_relocate)
        plane_names = set(p.name for p in self.planes)
        self.to_relocate = [s for s in self.to_relocate
                            if not (util.support_plane(s) and util.support_plane(s).name in plane_names)]
        self.plane_visibility = {p.name: p.isLightBulbOn for p in self.planes}
        self.sketches_by_plane = {}
        for plane in self.planes:
            names = set()
            for sketch in managed.custom_sketches(component):
                try:
                    support = util.support_plane(sketch)
                    if support and support.name == plane.name:
                        names.add(sketch.name)
                except Exception:
                    continue
            self.sketches_by_plane[plane.name] = names

    def detach(self):
        """Before deleting the old body: move face-based rim sketches to the stable plane."""
        support = geo.ensure_custom_sketch_plane(self.component, self.new_top)
        if self.to_relocate:
            keep_plane_before(support, self.to_relocate)
            for sketch in self.to_relocate:
                redefine_keep_xy(sketch, support)
        move_offset_planes(self.planes, self.component, self.new_top)

    def restore(self):
        """After the rebuild: keep planes ahead of their sketches and restore visibility."""
        support = geo.ensure_custom_sketch_plane(self.component, self.new_top)
        keep_plane_before(support, self.to_relocate)
        move_offset_planes(self.planes, self.component, self.new_top)
        current = {s.name: s for s in managed.custom_sketches(self.component)}
        for plane in self.planes:
            if plane and plane.isValid:
                keep_plane_before(plane, [current[n] for n in self.sketches_by_plane.get(plane.name, ())
                                          if n in current])
        for name, sketch in current.items():
            if name in self.sketch_visibility:
                sketch.isLightBulbOn = True if name in self.keep_visible else self.sketch_visibility[name]
        for plane in self.planes:
            if plane and plane.isValid:
                plane.isLightBulbOn = self.plane_visibility.get(plane.name, False)


# ---------------------------------------------------------------------------
# Edit paths
# ---------------------------------------------------------------------------
def rebuild_height(occurrence, old, new, affected_features):
    """Z change: rebuild walls, lip and interior; keep the foot grid and user sketches."""
    component = occurrence.component
    cx, cy = bin_center(component, old)      # measure before anything is removed
    old_top, new_top = geo.body_top_cm(old), geo.body_top_cm(new)
    keeper = RimKeeper(component, old_top, new_top, affected_features)
    keeper.detach()
    anchor_face_sketches(occurrence, old_top)

    magnet = util.find_sketch(component, C.MAGNET_SKETCH_NAME)
    geo.remove_bottom_features(component)     # downstream of the walls: remove first

    tokens = set()
    for feature in affected_features:
        try:
            tokens.add(feature.entityToken)
        except Exception:
            pass
    remove = managed.features_by_category(component, (managed.HEIGHT,))
    for item in util.model_features(component):
        try:
            if item.entity.entityToken in tokens and item not in remove:
                remove.append(item)
        except Exception:
            continue
    util.delete_timeline_objects(remove, 'a height-dependent feature (its sketch was kept)')
    managed.delete_sketches(managed.generated_sketches(component, (managed.HEIGHT,)),
                            'an old wall / lip sketch')
    managed.delete_sketches([s for s in component.sketches if s.name == 'Gridfinity screw holes'],
                            'the old screw hole sketch')
    fix_legacy_deck(component)

    new['_center_x_cm'], new['_center_y_cm'] = cx, cy
    reuse = _reusable_magnet_sketch(magnet, old, new)
    geo.generate_bin(new, occurrence=occurrence, center_x=cx, center_y=cy, skip_foundation=True,
                     magnet_sketch_to_reuse=reuse)
    keeper.restore()


def expand(occurrence, old, new):
    """Footprint grows (Z may change too): rebuild in place, keep sketches and planes.

    The original lower-left corner stays put; new cells grow toward +X/+Y.
    """
    component = occurrence.component
    cx, cy = bin_center(component, old)      # measure before the body is removed
    old_top, new_top = geo.body_top_cm(old), geo.body_top_cm(new)
    keeper = RimKeeper(component, old_top, new_top)
    keeper.detach()
    anchor_face_sketches(occurrence, old_top)

    util.delete_timeline_objects(util.model_features(component), 'a modeled feature during expansion')
    managed.delete_sketches(managed.generated_sketches(component), 'an old Gridfinity sketch')

    old_w, old_d = [cm(v) for v in cfg.bin_size_mm(old)]
    new_w, new_d = [cm(v) for v in cfg.bin_size_mm(new)]
    cx, cy = cx + (new_w - old_w) / 2.0, cy + (new_d - old_d) / 2.0
    new['_center_x_cm'], new['_center_y_cm'] = cx, cy
    geo.generate_bin(new, occurrence=occurrence, center_x=cx, center_y=cy)
    keeper.restore()


def update_in_place(occurrence, old, new, bottom, interior):
    """Only magnets/screws and/or interior options changed: leave everything else alone."""
    component = occurrence.component
    cx, cy = bin_center(component, old)
    new['_center_x_cm'], new['_center_y_cm'] = cx, cy
    centers = cfg.cell_centers_cm(new, cx, cy)
    if interior:
        items = [item for item in util.model_features(component)
                 if util.role_of(item.entity) == C.ROLE_INTERIOR]
        util.delete_timeline_objects(items, 'the old dividers / label / scoop')
        managed.delete_sketches([s for s in component.sketches if util.role_of(s) == C.ROLE_INTERIOR],
                                'an old interior sketch')
        geo.build_interior(component, new, cx, cy, geo.body_top_cm(new))
    if bottom:
        magnet = util.find_sketch(component, C.MAGNET_SKETCH_NAME)
        geo.remove_bottom_features(component)
        reuse = _reusable_magnet_sketch(magnet, old, new)
        managed.delete_sketches([s for s in component.sketches if s.name == 'Gridfinity screw holes'],
                                'the old screw hole sketch')
        geo.build_bottom(component, new, centers, reuse)
    managed.hide_generated(component, include_custom_plane=False)


def _reusable_magnet_sketch(magnet, old, new):
    """Keep the old magnet sketch only when the hole size is unchanged; otherwise delete it."""
    if not magnet or not magnet.isValid:
        return None
    if new.get('magnets') and cfg.same(old, new, ('magnet_diameter_mm',)):
        return magnet
    managed.delete_sketches([magnet], 'the old magnet sketch')
    return None
