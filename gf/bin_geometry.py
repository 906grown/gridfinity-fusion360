"""Bin geometry: foot grid, walls/body, stacking lip, interior options, magnets/screws."""

import adsk.core
import adsk.fusion

from . import config as cfg
from . import constants as C
from . import managed
from . import util
from .constants import cm

OPS = adsk.fusion.FeatureOperations


# ---------------------------------------------------------------------------
# Occurrence placement (fixes v1 dropping edited bins at the root origin)
# ---------------------------------------------------------------------------
def new_occurrence(parent_component, transform=None):
    matrix = transform.copy() if transform else adsk.core.Matrix3D.create()
    return parent_component.occurrences.addNewComponent(matrix)


def placement_of(occurrence):
    """(parent component, transform) that put this occurrence where it is."""
    native = occurrence.nativeObject if occurrence.nativeObject else occurrence
    context = occurrence.assemblyContext
    parent = context.component if context else occurrence.component.parentDesign.rootComponent
    return parent, native.transform2


# ---------------------------------------------------------------------------
# Stable sketch plane at the rim
# ---------------------------------------------------------------------------
def custom_sketch_plane(component):
    for plane in component.constructionPlanes:
        if plane.name == C.CUSTOM_PLANE_NAME:
            return plane
    return None


def ensure_custom_sketch_plane(component, body_top_cm):
    """Keep a work plane at the nominal rim, anchored to XY, ahead of its sketches."""
    plane = custom_sketch_plane(component)
    if not plane:
        plane = util.new_plane(component, body_top_cm)
        plane.name = C.CUSTOM_PLANE_NAME
        return plane
    attached = []
    for sketch in managed.custom_sketches(component):
        try:
            support = util.support_plane(sketch)
            if support and support.name == plane.name:
                attached.append(sketch)
        except Exception:
            continue
    plane.timelineObject.rollTo(True)
    definition = adsk.fusion.ConstructionPlaneOffsetDefinition.cast(plane.definition)
    if not definition:
        raise RuntimeError('Could not update the Gridfinity custom sketch plane.')
    if not definition.redefine(adsk.core.ValueInput.createByReal(body_top_cm),
                               component.xYConstructionPlane):
        raise RuntimeError('Could not re-anchor the Gridfinity custom sketch plane to the bin rim.')
    component.parentDesign.timeline.moveToEnd()
    if attached:
        first = min(s.timelineObject.index for s in attached)
        if plane.timelineObject.index > first and not plane.timelineObject.reorder(first):
            raise RuntimeError('Could not place the Gridfinity custom sketch plane before its sketches.')
    return plane


# ---------------------------------------------------------------------------
# Foundation (feet + deck)
# ---------------------------------------------------------------------------
def build_foundation(component, config, centers, center_x, center_y):
    width_mm, depth_mm = cfg.bin_size_mm(config)
    nx, ny = int(round(config['x'])), int(round(config['y']))
    sections = []
    for index, (z, size, radius) in enumerate(C.FOOT_SECTIONS):
        plane = component.xYConstructionPlane if z == 0 else util.new_plane(component, cm(z))
        sections.append(util.rounded_sketch(
            component, plane, 'Base profile section {}'.format(index + 1), C.ROLE_FOUNDATION,
            centers, cm(size), cm(size), cm(radius)))
    maps = [util.profiles_by_center(sketch) for sketch in sections]

    deck_sketch = util.rounded_sketch(
        component, util.new_plane(component, cm(C.FOOT_HEIGHT)), 'Gridfinity base deck',
        C.ROLE_FOUNDATION, [(center_x, center_y)], cm(width_mm), cm(depth_mm), cm(C.OUTER_RADIUS))
    util.extrude(component, deck_sketch.profiles.item(0), cm(C.DECK), OPS.NewBodyFeatureOperation,
                 C.ROLE_FOUNDATION, 'Gridfinity base deck')

    def foot(center):
        key = (round(center[0], 6), round(center[1], 6))
        profiles = [m.get(key) for m in maps]
        if not all(profiles):
            raise RuntimeError('Could not find a base profile for cell {}.'.format(key))
        return util.loft(component, profiles, OPS.JoinFeatureOperation, C.ROLE_FOUNDATION,
                         'Gridfinity base foot {:.0f},{:.0f}'.format(center[0] * 10, center[1] * 10))

    first = min(centers)            # lowest X, then lowest Y: the pattern grows +X/+Y
    first_foot = foot(first)
    try:
        util.pattern_grid(component, first_foot, nx, ny, cm(C.PITCH), C.ROLE_FOUNDATION,
                          'Gridfinity base foot pattern')
    except Exception:
        util.log_exception('Foot pattern failed; using one loft per cell')
        for center in centers:
            if center != first:
                foot(center)


# ---------------------------------------------------------------------------
# Walls / solid body and the stacking lip
# ---------------------------------------------------------------------------
def build_body(component, config, center_x, center_y, body_top_cm):
    width_cm, depth_cm = [cm(v) for v in cfg.bin_size_mm(config)]
    floor_cm = cm(C.FLOOR_TOP)
    height = body_top_cm - floor_cm
    if height <= 0:
        raise RuntimeError('Selected height is too small for the base and walls.')
    plane = util.new_plane(component, floor_cm)
    if config['type'] == 'Hollow':
        wall = cm(cfg.hollow_wall_mm(config))
        if width_cm <= 2 * wall or depth_cm <= 2 * wall:
            raise RuntimeError('The selected X/Y dimensions leave no room for a hollow interior.')
        sketch = util.new_sketch(component, plane, 'Bin walls', C.ROLE_HEIGHT)
        util.rounded_rect(sketch, center_x, center_y, width_cm, depth_cm, cm(C.OUTER_RADIUS))
        inner_radius = 0.08 if config['lip'] else max(0.1, cm(C.OUTER_RADIUS) - wall)
        util.rounded_rect(sketch, center_x, center_y, width_cm - 2 * wall, depth_cm - 2 * wall,
                          inner_radius)
        profile = util.ring_profile(sketch)
        if not profile:
            raise RuntimeError('Could not identify the wall ring profile.')
        util.extrude(component, profile, height, OPS.JoinFeatureOperation, C.ROLE_HEIGHT, 'Bin walls')
    else:
        sketch = util.rounded_sketch(component, plane, 'Solid bin body', C.ROLE_HEIGHT,
                                     [(center_x, center_y)], width_cm, depth_cm, cm(C.OUTER_RADIUS))
        util.extrude(component, sketch.profiles.item(0), height, OPS.JoinFeatureOperation,
                     C.ROLE_HEIGHT, 'Solid bin body')


def build_lip(component, config, center_x, center_y, body_top_cm):
    """Raise a full 4.4 mm perimeter, then cut the 45/vertical/45 opening into it."""
    width_cm, depth_cm = [cm(v) for v in cfg.bin_size_mm(config)]
    outer = util.rounded_sketch(component, util.new_plane(component, body_top_cm),
                                'Stacking lip outer profile', C.ROLE_LIP, [(center_x, center_y)],
                                width_cm, depth_cm, cm(C.OUTER_RADIUS))
    util.extrude(component, outer.profiles.item(0), cm(C.LIP_HEIGHT), OPS.JoinFeatureOperation,
                 C.ROLE_LIP, 'Stacking lip 4.4 mm raised perimeter')

    def opening(name, key):
        height, size, radius = C.LIP_SECTIONS[key]
        sketch = util.new_sketch(component, util.new_plane(component, body_top_cm + cm(height)),
                                 name, C.ROLE_LIP)
        shrink = cm(C.FOOT_TOP - size)
        util.rounded_rect(sketch, center_x, center_y, width_cm - shrink, depth_cm - shrink,
                          max(0.05, cm(C.OUTER_RADIUS) - cm(3.75 - radius)))
        profiles = util.single_loop_profiles(sketch)
        if not profiles:
            raise RuntimeError('Could not create stacking lip opening profile: ' + name)
        return profiles[0]

    util.loft(component, [opening('Stacking lip lower ramp bottom', 'lower_bottom'),
                          opening('Stacking lip lower ramp top', 'lower_top')],
              OPS.CutFeatureOperation, C.ROLE_LIP, 'Cut stacking lip lower 45 degree ramp (0.7 mm)')
    land = opening('Stacking lip vertical land', 'lower_top')
    util.extrude(component, land, cm(1.8), OPS.CutFeatureOperation, C.ROLE_LIP,
                 'Cut stacking lip vertical land (1.8 mm)')
    util.loft(component, [opening('Stacking lip upper ramp bottom', 'upper_bottom'),
                          opening('Stacking lip upper ramp top', 'upper_top')],
              OPS.CutFeatureOperation, C.ROLE_LIP, 'Cut stacking lip upper 45 degree ramp (1.9 mm)')


# ---------------------------------------------------------------------------
# Interior options (hollow bins): compartments, label shelf, finger scoop
# ---------------------------------------------------------------------------
def build_interior(component, config, center_x, center_y, body_top_cm):
    if config.get('type') != 'Hollow':
        return
    width_cm, depth_cm = [cm(v) for v in cfg.bin_size_mm(config)]
    wall = cm(cfg.hollow_wall_mm(config))
    inner_w, inner_d = width_cm - 2 * wall, depth_cm - 2 * wall
    x1, y1 = center_x - inner_w / 2.0, center_y - inner_d / 2.0
    floor_cm = cm(C.FLOOR_TOP)
    room = body_top_cm - floor_cm
    t = cm(C.DIVIDER_THICKNESS)
    overlap = 0.01

    nx, ny = int(config.get('compartments_x', 1)), int(config.get('compartments_y', 1))
    if (nx > 1 or ny > 1) and room > 0:
        sketch = util.new_sketch(component, util.new_plane(component, floor_cm),
                                 'Gridfinity compartment dividers', C.ROLE_INTERIOR)
        if nx > 1:
            cell = (inner_w - (nx - 1) * t) / nx
            for k in range(1, nx):
                left = x1 + k * cell + (k - 1) * t
                util.rect(sketch, left, y1 - overlap, left + t, y1 + inner_d + overlap)
        if ny > 1:
            cell = (inner_d - (ny - 1) * t) / ny
            for k in range(1, ny):
                bottom = y1 + k * cell + (k - 1) * t
                util.rect(sketch, x1 - overlap, bottom, x1 + inner_w + overlap, bottom + t)
        profiles = [sketch.profiles.item(i) for i in range(sketch.profiles.count)]
        util.extrude(component, profiles, room, OPS.JoinFeatureOperation, C.ROLE_INTERIOR,
                     'Gridfinity compartment dividers')

    if config.get('label') and room >= cm(4.0):
        thick = cm(C.LABEL_THICKNESS)
        reach = min(cm(C.LABEL_DEPTH), room - thick - cm(0.5), inner_d / max(ny, 1) * 0.6)
        back = y1 + inner_d
        top = body_top_cm
        # Flat shelf at the rim with a 45-degree underside, so it prints without support.
        sketch = util.sketch_polygon_yz(component, center_x, 'Gridfinity label shelf', C.ROLE_INTERIOR, [
            (back + overlap, top), (back - reach, top), (back - reach, top - thick),
            (back + overlap, top - thick - reach - overlap)])
        util.extrude(component, sketch.profiles.item(0), inner_w + 2 * overlap,
                     OPS.JoinFeatureOperation, C.ROLE_INTERIOR, 'Gridfinity label shelf', symmetric=True)

    if config.get('scoop') and room >= cm(4.0):
        radius = min(cm(C.SCOOP_RADIUS), room - cm(0.5), inner_d / max(ny, 1) * 0.5)
        build_scoop(component, center_x, y1, floor_cm, radius, inner_w + 2 * overlap)


def build_scoop(component, center_x, front_y, floor_z, radius, length):
    """Concave fillet between the front wall and the floor (finger scoop)."""
    plane = util.new_plane(component, center_x, component.yZConstructionPlane)
    try:
        if abs(plane.geometry.origin.x - center_x) > 1e-6:
            plane.deleteMe()
            plane = util.new_plane(component, -center_x, component.yZConstructionPlane)
    except Exception:
        util.log_exception('Could not check the scoop plane direction')
    util.tag(plane, C.ROLE_INTERIOR)
    sketch = util.new_sketch(component, plane, 'Gridfinity finger scoop', C.ROLE_INTERIOR)
    P = lambda y, z: sketch.modelToSketchSpace(adsk.core.Point3D.create(center_x, y, z))
    e = 0.01   # tuck the profile slightly into the wall and floor so it fuses
    corner = P(front_y - e, floor_z - e)
    up = P(front_y - e, floor_z + radius)
    wall_tangent = P(front_y, floor_z + radius)
    floor_tangent = P(front_y + radius, floor_z)
    out = P(front_y + radius, floor_z - e)
    mid = P(front_y + radius - radius * 0.7071067811865476, floor_z + radius - radius * 0.7071067811865476)
    lines = sketch.sketchCurves.sketchLines
    lines.addByTwoPoints(corner, up)
    lines.addByTwoPoints(up, wall_tangent)
    sketch.sketchCurves.sketchArcs.addByThreePoints(wall_tangent, mid, floor_tangent)
    lines.addByTwoPoints(floor_tangent, out)
    lines.addByTwoPoints(out, corner)
    profile = sketch.profiles.item(0)
    util.extrude(component, profile, length, OPS.JoinFeatureOperation, C.ROLE_INTERIOR,
                 'Gridfinity finger scoop', symmetric=True)


# ---------------------------------------------------------------------------
# Bottom features: magnet sockets and screw holes
# ---------------------------------------------------------------------------
def magnet_sketch(component, config, centers, existing=None):
    sketch = existing or util.new_sketch(component, component.xYConstructionPlane,
                                         C.MAGNET_SKETCH_NAME, C.ROLE_MAGNET)
    sketch.name = C.MAGNET_SKETCH_NAME
    radius = cm(config.get('magnet_diameter_mm', C.MAGNET_DIAMETER)) / 2.0
    for mx, my in cfg.magnet_points_cm(centers):
        sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(mx, my, 0), radius)
    return sketch


def fillet_socket_openings(component, points, diameter_mm, opening_zs_cm, radius_mm=C.MAGNET_LEAD_IN):
    """0.5 mm lead-in on the exposed circular edge of each magnet socket."""
    radius_cm = cm(diameter_mm) / 2.0
    tol = 0.0002
    selected = adsk.core.ObjectCollection.create()
    for body in component.bRepBodies:
        for edge in body.edges:
            try:
                b = edge.boundingBox
                if abs(b.maxPoint.z - b.minPoint.z) > tol:
                    continue
                if not any(abs(b.minPoint.z - z) <= tol for z in opening_zs_cm):
                    continue
                if (abs(b.maxPoint.x - b.minPoint.x - 2 * radius_cm) > tol or
                        abs(b.maxPoint.y - b.minPoint.y - 2 * radius_cm) > tol):
                    continue
                cx, cy = (b.minPoint.x + b.maxPoint.x) / 2.0, (b.minPoint.y + b.maxPoint.y) / 2.0
                if any(abs(cx - px) <= tol and abs(cy - py) <= tol for px, py in points):
                    selected.add(edge)
            except Exception:
                continue
    if selected.count == 0:
        return None
    fillets = component.features.filletFeatures
    fillet_input = fillets.createInput()
    fillet_input.edgeSetInputs.addConstantRadiusEdgeSet(
        selected, adsk.core.ValueInput.createByReal(cm(radius_mm)), False)
    try:
        fillet = fillets.add(fillet_input)
    except Exception:
        util.log_exception('Magnet lead-in fillet skipped')
        return None
    fillet.name = 'Gridfinity magnet socket lead-in fillet'
    return util.tag(fillet, 'magnet-socket-fillet')


def build_bottom(component, config, centers, existing_magnet_sketch=None):
    """Magnet sockets and/or screw holes. Reuses a magnet sketch if its size still fits."""
    if config.get('magnets'):
        sketch = existing_magnet_sketch or magnet_sketch(component, config, centers)
        profiles = [sketch.profiles.item(i) for i in range(sketch.profiles.count)]
        util.extrude(component, profiles, cm(config.get('magnet_depth_mm', C.MAGNET_DEPTH)),
                     OPS.CutFeatureOperation, C.ROLE_MAGNET, 'Gridfinity magnet socket cut')
        fillet_socket_openings(component, cfg.magnet_points_cm(centers),
                               float(config.get('magnet_diameter_mm', C.MAGNET_DIAMETER)), [0.0])
        sketch.isLightBulbOn = False
    if config.get('screw_holes'):
        sketch = util.new_sketch(component, component.xYConstructionPlane,
                                 'Gridfinity screw holes', 'screw-holes')
        radius = cm(C.SCREW_DIAMETER) / 2.0
        for mx, my in cfg.magnet_points_cm(centers):
            sketch.sketchCurves.sketchCircles.addByCenterRadius(adsk.core.Point3D.create(mx, my, 0), radius)
        profiles = [sketch.profiles.item(i) for i in range(sketch.profiles.count)]
        util.extrude(component, profiles, cm(cfg.screw_depth_mm()), OPS.CutFeatureOperation,
                     'screw-holes', 'Gridfinity screw hole cut')
        sketch.isLightBulbOn = False


def remove_bottom_features(component):
    items = managed.features_by_category(component, (managed.BOTTOM,))
    util.delete_timeline_objects(items, 'the magnet / screw cuts')


# ---------------------------------------------------------------------------
# Whole bin
# ---------------------------------------------------------------------------
def body_top_cm(config):
    return cm(C.U_HEIGHT * float(config['z']))


def component_name(config):
    return 'Gridfinity {} {:.0f}x{:.0f}x{:g}u'.format(config['type'], config['x'], config['y'],
                                                       round(float(config['z']), 2))


def generate_bin(config, parent=None, transform=None, occurrence=None, center_x=0.0, center_y=0.0,
                 skip_foundation=False, skip_bottom=False, magnet_sketch_to_reuse=None):
    if occurrence is None:
        occurrence = new_occurrence(parent, transform)
    component = occurrence.component
    component.name = component_name(config)
    centers = cfg.cell_centers_cm(config, center_x, center_y)
    top = body_top_cm(config)

    if not skip_foundation:
        build_foundation(component, config, centers, center_x, center_y)
        if not any(managed.sketch_category(s, False) is not None and not util.is_tagged(s)
                   for s in component.sketches):
            managed.mark_fully_tagged(component)     # no untagged v1 sketches remain
    build_body(component, config, center_x, center_y, top)
    if config.get('lip'):
        build_lip(component, config, center_x, center_y, top)
    build_interior(component, config, center_x, center_y, top)
    ensure_custom_sketch_plane(component, top)
    if not skip_bottom:
        build_bottom(component, config, centers, magnet_sketch_to_reuse)
    managed.hide_generated(component)
    return occurrence
