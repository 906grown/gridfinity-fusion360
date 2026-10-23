"""Small Fusion helpers shared by the geometry and edit modules."""

import traceback

import adsk.core
import adsk.fusion

from . import constants as C

HALF_PI = 1.5707963267948966


# ---------------------------------------------------------------------------
# Logging / messages
# ---------------------------------------------------------------------------
def app():
    return adsk.core.Application.get()


def ui():
    return app().userInterface


def log(message):
    """Write to Fusion's Text Commands window (View > Show Text Commands)."""
    try:
        app().log('[Gridfinity v2] ' + str(message))
    except Exception:
        print('[Gridfinity v2] ' + str(message))


def log_exception(context):
    log('{}:\n{}'.format(context, traceback.format_exc()))


def error_box(context):
    log_exception(context)
    ui().messageBox('{}:\n{}'.format(context, traceback.format_exc()))


def confirm(message, title):
    result = ui().messageBox(message, title,
                             adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                             adsk.core.MessageBoxIconTypes.WarningIconType)
    return result == adsk.core.DialogResults.DialogYes


# ---------------------------------------------------------------------------
# Ownership tags (features and sketches)
# ---------------------------------------------------------------------------
def tag(entity, role='generated'):
    """Mark a feature or sketch as made by this add-in."""
    try:
        entity.attributes.add(C.ATTR_GROUP, C.OWNER_ATTR, C.OWNER_VALUE)
        entity.attributes.add(C.ATTR_GROUP, C.ROLE_ATTR, role)
    except Exception:
        log_exception('Could not tag {}'.format(getattr(entity, 'name', entity)))
    return entity


def is_tagged(entity):
    try:
        owner = entity.attributes.itemByName(C.ATTR_GROUP, C.OWNER_ATTR)
        return bool(owner and owner.value == C.OWNER_VALUE)
    except Exception:
        return False


def role_of(entity):
    try:
        role = entity.attributes.itemByName(C.ATTR_GROUP, C.ROLE_ATTR)
        return role.value if role else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Timeline helpers
# ---------------------------------------------------------------------------
def model_features(component):
    """Timeline objects of this component's modeled features (no sketches/planes)."""
    timeline = component.parentDesign.timeline
    found = []
    for index in range(timeline.count):
        item = timeline.item(index)
        entity = item.entity
        if not entity:
            continue
        try:
            if entity.parentComponent != component:
                continue
            if 'Feature' in entity.objectType:
                found.append(item)
        except Exception:
            continue
    return found


def delete_timeline_objects(items, what):
    """Delete timeline objects newest-first so earlier ones are never orphaned."""
    for item in sorted(items, key=lambda obj: obj.index, reverse=True):
        if not item.deleteObject():
            raise RuntimeError('Fusion could not remove {}.'.format(what))


def feature_source_sketches(feature):
    """Sketches whose profiles drive a feature (handles single or many profiles)."""
    sketches = []
    try:
        profile = feature.profile
    except Exception:
        return sketches
    candidates = []
    if profile is None:
        return sketches
    if hasattr(profile, 'count') and hasattr(profile, 'item'):
        candidates = [profile.item(i) for i in range(profile.count)]
    else:
        candidates = [profile]
    for item in candidates:
        try:
            sketch = item.parentSketch
            if sketch and all(sketch != s for s in sketches):
                sketches.append(sketch)
        except Exception:
            continue
    return sketches


def feature_max_z(feature):
    maximum = None
    try:
        for index in range(feature.faces.count):
            value = feature.faces.item(index).boundingBox.maxPoint.z
            maximum = value if maximum is None else max(maximum, value)
    except Exception:
        pass
    return maximum


def support_plane(sketch):
    """The construction plane a sketch sits on, or None (face-based or unreadable)."""
    try:
        return adsk.fusion.ConstructionPlane.cast(sketch.referencePlane)
    except Exception:
        return None


def sketch_frame(sketch):
    """(on_a_face, normal_z, height_cm) in component space.

    Fusion refuses to return a face reference while the timeline sits after the
    sketch ("referencePlane is a BRefFace"), so the face test reads that error and
    the height/normal come from the sketch transform instead.
    """
    try:
        reference = sketch.referencePlane
        on_face = reference is not None and 'BRepFace' in reference.objectType
    except Exception as exc:
        on_face = 'BRefFace' in str(exc) or 'BRepFace' in str(exc)
    matrix = sketch.transform
    return on_face, matrix.getCell(2, 2), matrix.getCell(2, 3)


def find_sketch(component, name):
    for sketch in component.sketches:
        if sketch.name == name:
            return sketch
    return None


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------
def new_plane(component, offset_cm, base=None):
    plane_input = component.constructionPlanes.createInput()
    plane_input.setByOffset(base or component.xYConstructionPlane,
                            adsk.core.ValueInput.createByReal(offset_cm))
    return component.constructionPlanes.add(plane_input)


def new_sketch(component, plane, name, role):
    sketch = component.sketches.add(plane)
    sketch.name = name
    tag(sketch, role)
    # Tag the add-in's own offset planes too, so they are cleaned up with the sketch.
    construction = adsk.fusion.ConstructionPlane.cast(plane)
    if construction and construction.isParametric and construction.name != C.CUSTOM_PLANE_NAME:
        if construction != component.xYConstructionPlane and not is_tagged(construction):
            tag(construction, role)
    return sketch


def rounded_rect(sketch, cx, cy, width_cm, depth_cm, radius_cm):
    """One closed rounded rectangle (sketch coordinates, cm)."""
    x1, x2 = cx - width_cm / 2.0, cx + width_cm / 2.0
    y1, y2 = cy - depth_cm / 2.0, cy + depth_cm / 2.0
    r = min(radius_cm, width_cm / 2.0 - 0.00001, depth_cm / 2.0 - 0.00001)
    lines = sketch.sketchCurves.sketchLines
    arcs = sketch.sketchCurves.sketchArcs
    p = adsk.core.Point3D.create
    lines.addByTwoPoints(p(x1 + r, y1, 0), p(x2 - r, y1, 0))
    arcs.addByCenterStartSweep(p(x2 - r, y1 + r, 0), p(x2 - r, y1, 0), HALF_PI)
    lines.addByTwoPoints(p(x2, y1 + r, 0), p(x2, y2 - r, 0))
    arcs.addByCenterStartSweep(p(x2 - r, y2 - r, 0), p(x2, y2 - r, 0), HALF_PI)
    lines.addByTwoPoints(p(x2 - r, y2, 0), p(x1 + r, y2, 0))
    arcs.addByCenterStartSweep(p(x1 + r, y2 - r, 0), p(x1 + r, y2, 0), HALF_PI)
    lines.addByTwoPoints(p(x1, y2 - r, 0), p(x1, y1 + r, 0))
    arcs.addByCenterStartSweep(p(x1 + r, y1 + r, 0), p(x1, y1 + r, 0), HALF_PI)


def rect(sketch, x1, y1, x2, y2):
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        adsk.core.Point3D.create(x1, y1, 0), adsk.core.Point3D.create(x2, y2, 0))


def rounded_sketch(component, plane, name, role, centers, width_cm, depth_cm, radius_cm):
    sketch = new_sketch(component, plane, name, role)
    for cx, cy in centers:
        rounded_rect(sketch, cx, cy, width_cm, depth_cm, radius_cm)
    return sketch


def profiles_by_center(sketch):
    result = {}
    for profile in sketch.profiles:
        bounds = profile.boundingBox
        key = (round((bounds.minPoint.x + bounds.maxPoint.x) / 2.0, 6),
               round((bounds.minPoint.y + bounds.maxPoint.y) / 2.0, 6))
        result[key] = profile
    return result


def single_loop_profiles(sketch):
    return [p for p in sketch.profiles if p.profileLoops.count == 1]


def ring_profile(sketch):
    for profile in sketch.profiles:
        if profile.profileLoops.count > 1:
            return profile
    return None


def limit_to_component(feature_input, component, operation):
    """Cuts must only touch this item's own bodies.

    Without this, a cut made while several items overlap at the origin also
    cuts the neighbouring items (and Fusion files the feature under them).
    """
    ops = adsk.fusion.FeatureOperations
    if operation not in (ops.CutFeatureOperation, ops.IntersectFeatureOperation):
        return
    bodies = [component.bRepBodies.item(i) for i in range(component.bRepBodies.count)]
    if bodies:
        feature_input.participantBodies = bodies


def extrude(component, profiles, distance_cm, operation, role='generated', name=None,
            symmetric=False):
    """Extrude one profile or a list of profiles as a single feature."""
    if isinstance(profiles, (list, tuple)):
        collection = adsk.core.ObjectCollection.create()
        for profile in profiles:
            collection.add(profile)
        profiles = collection
    ext_input = component.features.extrudeFeatures.createInput(profiles, operation)
    limit_to_component(ext_input, component, operation)
    distance = adsk.core.ValueInput.createByReal(distance_cm)
    if symmetric:
        ext_input.setSymmetricExtent(distance, True)
    else:
        ext_input.setDistanceExtent(False, distance)
    feature = component.features.extrudeFeatures.add(ext_input)
    if name:
        feature.name = name
    return tag(feature, role)


def loft(component, sections, operation, role, name=None):
    loft_input = component.features.loftFeatures.createInput(operation)
    limit_to_component(loft_input, component, operation)
    for profile in sections:
        loft_input.loftSections.add(profile)
    loft_input.isSolid = True
    feature = component.features.loftFeatures.add(loft_input)
    if name:
        feature.name = name
    return tag(feature, role)


def pattern_grid(component, feature, nx, ny, pitch_cm, role, name=None):
    """Copy a feature across an nx by ny grid in +X/+Y. Returns None for 1x1."""
    if nx <= 1 and ny <= 1:
        return None
    entities = adsk.core.ObjectCollection.create()
    entities.add(feature)
    patterns = component.features.rectangularPatternFeatures
    first_axis, first_count = (component.xConstructionAxis, nx) if nx > 1 else (component.yConstructionAxis, ny)
    pattern_input = patterns.createInput(
        entities, first_axis,
        adsk.core.ValueInput.createByReal(first_count),
        adsk.core.ValueInput.createByReal(pitch_cm),
        adsk.fusion.PatternDistanceType.SpacingPatternDistanceType)
    if nx > 1 and ny > 1:
        pattern_input.setDirectionTwo(component.yConstructionAxis,
                                      adsk.core.ValueInput.createByReal(ny),
                                      adsk.core.ValueInput.createByReal(pitch_cm))
    try:
        pattern_input.patternComputeOption = adsk.fusion.PatternComputeOptions.AdjustPatternCompute
    except Exception:
        pass
    feature = patterns.add(pattern_input)
    if name:
        feature.name = name
    return tag(feature, role)


def sketch_polygon_yz(component, x_cm, name, role, points_yz):
    """Closed polygon in the plane x = x_cm, from model (y, z) points in cm."""
    plane = new_plane(component, x_cm, component.yZConstructionPlane)
    try:
        if abs(plane.geometry.origin.x - x_cm) > 1e-6:
            # The YZ plane's normal pointed the other way; flip the offset.
            plane.deleteMe()
            plane = new_plane(component, -x_cm, component.yZConstructionPlane)
    except Exception:
        log_exception('Could not check the YZ offset plane direction')
    tag(plane, role)
    sketch = new_sketch(component, plane, name, role)
    to_sketch = lambda y, z: sketch.modelToSketchSpace(adsk.core.Point3D.create(x_cm, y, z))
    pts = [to_sketch(y, z) for y, z in points_yz]
    lines = sketch.sketchCurves.sketchLines
    for a, b in zip(pts, pts[1:] + pts[:1]):
        lines.addByTwoPoints(a, b)
    return sketch
