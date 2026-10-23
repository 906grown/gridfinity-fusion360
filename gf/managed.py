"""Which sketches and features belong to the add-in, and which are the user's.

v2 tags everything it creates (attribute ROLE_ATTR). Bins made by v1 carry
only partial tags, so a single legacy name registry (constants.LEGACY_*) is
used for them. Once a component holds any tagged sketch, names are ignored
for sketches: a user sketch named "Bin walls" is then never deleted.
"""

from . import constants as C
from . import util

# Categories
FOUNDATION = 'foundation'
HEIGHT = 'height'
BOTTOM = 'bottom'
BASE = 'base'
OTHER = 'other'      # add-in owned, no special handling


def _role_category(role):
    if not role:
        return None
    if role == C.ROLE_FOUNDATION:
        return FOUNDATION
    if role in C.HEIGHT_ROLES or role.startswith('bin-height'):
        return HEIGHT
    if role.startswith('magnet') or role == C.ROLE_MAGNET or role.startswith('screw'):
        return BOTTOM
    if role.startswith('baseplate') or role == C.ROLE_BASE:
        return BASE
    if role == 'generated':
        return None          # v1 generic tag: fall back to names
    return OTHER


def _legacy_name_category(name):
    if name in C.LEGACY_FOUNDATION_EXACT or name.startswith(C.LEGACY_FOUNDATION_PREFIX):
        return FOUNDATION
    if name in C.LEGACY_MAGNET_EXACT or name == C.MAGNET_SKETCH_NAME:
        return BOTTOM
    if name in C.LEGACY_HEIGHT_EXACT or name.startswith(C.LEGACY_HEIGHT_PREFIX):
        return HEIGHT
    if name in C.LEGACY_BASE_EXACT or name.startswith(C.LEGACY_BASE_PREFIX):
        return BASE
    return None


# ---------------------------------------------------------------------------
# Sketches
# ---------------------------------------------------------------------------
TAGS_COMPLETE = 'sketch_tags_complete'


def uses_tags(component):
    """True once v2 has built the whole item, so every add-in sketch carries a tag.

    A v1 item that only had magnets edited by v2 holds a few tagged sketches next
    to untagged v1 ones; it must still be read by the legacy names.
    """
    try:
        return bool(component.attributes.itemByName(C.ATTR_GROUP, TAGS_COMPLETE))
    except Exception:
        return False


def mark_fully_tagged(component):
    component.attributes.add(C.ATTR_GROUP, TAGS_COMPLETE, '1')


def sketch_category(sketch, tagged_mode=None):
    if util.is_tagged(sketch):
        return _role_category(util.role_of(sketch)) or OTHER
    if tagged_mode is None:
        tagged_mode = uses_tags(sketch.parentComponent)
    if tagged_mode and sketch.name != C.MAGNET_SKETCH_NAME:
        return None
    return _legacy_name_category(sketch.name)


def custom_sketches(component):
    tagged_mode = uses_tags(component)
    return [s for s in component.sketches if sketch_category(s, tagged_mode) is None]


def generated_sketches(component, categories=None):
    tagged_mode = uses_tags(component)
    found = []
    for sketch in component.sketches:
        category = sketch_category(sketch, tagged_mode)
        if category is not None and (categories is None or category in categories):
            found.append(sketch)
    return found


def delete_sketches(sketches, what):
    """Delete add-in sketches, then any add-in plane that no longer carries a sketch."""
    sketches = [s for s in sketches if s.isValid]
    if not sketches:
        return
    component = sketches[0].parentComponent
    plane_names = []
    for sketch in sketches:
        plane = util.support_plane(sketch)
        try:
            # The add-in's own support planes: tagged (v2) or carrying a v1 generated sketch.
            if (plane and plane.isParametric and plane.name not in plane_names and
                    plane != component.xYConstructionPlane and plane.name != C.CUSTOM_PLANE_NAME and
                    not plane.name.startswith(('Gridfinity sketch plane', 'Gridfinity rim +'))):
                plane_names.append(plane.name)
        except Exception:
            continue
    for sketch in reversed(sketches):
        if sketch.isValid and not sketch.deleteMe():
            raise RuntimeError('Fusion could not remove {} "{}".'.format(what, sketch.name))
    # Look the planes up again by name: references taken before the deletes can go stale.
    remaining = set()
    for sketch in component.sketches:
        plane = util.support_plane(sketch)
        if plane:
            remaining.add(plane.name)
    for name in plane_names:
        if name in remaining:
            continue
        plane = component.constructionPlanes.itemByName(name)
        try:
            if plane and not plane.deleteMe():
                util.log('Could not remove unused plane ' + name)
        except Exception:
            util.log_exception('Left unused plane {} in place'.format(name))


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------
def feature_category(feature, foundation_end=None):
    category = _role_category(util.role_of(feature)) if util.is_tagged(feature) else None
    if category:
        return category
    names = [s.name for s in util.feature_source_sketches(feature)]
    for name in names:
        category = _legacy_name_category(name)
        if category:
            return category
    lower = feature.name.lower()
    if 'magnet' in lower or 'screw' in lower:
        return BOTTOM
    if lower.startswith(('stacking lip', 'cut stacking lip')):
        return HEIGHT
    if lower.startswith(('gridfinity base foot', 'gridfinity base deck')):
        return FOUNDATION
    if lower.startswith(('baseplate ',)):
        return BASE
    try:
        if foundation_end is not None and feature.timelineObject.index < foundation_end:
            return FOUNDATION
    except Exception:
        pass
    if util.is_tagged(feature) or lower.startswith('gridfinity '):
        return OTHER
    return None


def legacy_foundation_end(component):
    """Timeline index of the first wall/body feature (v1 bins without role tags)."""
    indexes = []
    for item in util.model_features(component):
        names = [s.name for s in util.feature_source_sketches(item.entity)]
        if any(name in ('Bin walls', 'Solid bin body') for name in names):
            indexes.append(item.index)
    return min(indexes) if indexes else None


def features_by_category(component, categories):
    end = legacy_foundation_end(component)
    return [item for item in util.model_features(component)
            if feature_category(item.entity, end) in categories]


def custom_features(component):
    end = legacy_foundation_end(component)
    return [item.entity for item in util.model_features(component)
            if feature_category(item.entity, end) is None]


def body_height_feature(component):
    """The walls / solid-body extrusion that sets the bin height."""
    for item in util.model_features(component):
        feature = item.entity
        if util.role_of(feature) == C.ROLE_HEIGHT:
            return feature
        if any(s.name in ('Bin walls', 'Solid bin body')
               for s in util.feature_source_sketches(feature)):
            return feature
    return None


def hide_generated(component, include_custom_plane=True):
    """Hide the add-in's sketches and planes; leave the user's visibility alone."""
    for sketch in generated_sketches(component):
        sketch.isLightBulbOn = False
    for plane in component.constructionPlanes:
        try:
            if util.is_tagged(plane) or (include_custom_plane and plane.name == C.CUSTOM_PLANE_NAME):
                plane.isLightBulbOn = False
        except Exception:
            continue
