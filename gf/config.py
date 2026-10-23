"""Saved settings, validation and edit planning. Pure Python (no adsk import)."""

import json
import os

from . import constants as C

# Option groups. An edit's path depends on which groups changed.
SIZE_KEYS = ('x', 'y', 'z')
BODY_KEYS = ('type', 'lip', 'wall_mm')
BOTTOM_KEYS = ('magnets', 'magnet_diameter_mm', 'magnet_depth_mm', 'screw_holes')
INTERIOR_KEYS = ('compartments_x', 'compartments_y', 'label', 'scoop')
BASE_KEYS = ('x', 'y', 'padding_x_mm', 'padding_y_mm',
             'magnets', 'magnet_diameter_mm', 'magnet_depth_mm')

BIN_DEFAULTS = {
    'x': 1.0, 'y': 1.0, 'z': 1.0, 'type': 'Solid', 'lip': True, 'wall_mm': C.WALL,
    'magnets': False, 'magnet_diameter_mm': C.MAGNET_DIAMETER, 'magnet_depth_mm': C.MAGNET_DEPTH,
    'screw_holes': False,
    'compartments_x': 1, 'compartments_y': 1, 'label': False, 'scoop': False,
}
BASE_DEFAULTS = {
    'x': 1.0, 'y': 1.0, 'type': 'Base', 'padding_x_mm': 0.0, 'padding_y_mm': 0.0,
    'wall_mm': C.WALL, 'magnets': False,
    'magnet_diameter_mm': C.MAGNET_DIAMETER, 'magnet_depth_mm': C.MAGNET_DEPTH,
}


def is_base(config):
    return (config or {}).get('type') == 'Base'


def normalize(config):
    """Bring a saved config (v1 or v2) up to the current schema without changing its shape."""
    config = dict(config)
    legacy = not config.get('z_units_mode') and 'config_version' not in config
    if config.get('type') in ('Hollow', 'Solid') and 'z' in config and legacy:
        # v1 before z_units_mode stored Z above an extra 7 mm base unit.
        config['z'] = float(config['z']) + 1.0
        config['z_units_mode'] = 2
    defaults = BASE_DEFAULTS if is_base(config) else BIN_DEFAULTS
    for key, value in defaults.items():
        if key not in config:
            # Old saved items keep their own magnet size (v1 default was 6 x 2).
            if key == 'magnet_diameter_mm':
                value = 6.0
            elif key == 'magnet_depth_mm':
                value = 2.0
            config[key] = value
    if not is_base(config):
        config['z_units_mode'] = 2
    config['config_version'] = C.CONFIG_VERSION
    return config


def same(old, new, keys):
    """True when every key matches (numbers compared with a tolerance)."""
    for key in keys:
        a, b = old.get(key), new.get(key)
        if isinstance(a, bool) or isinstance(b, bool):
            if bool(a) != bool(b):
                return False
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(float(a) - float(b)) > C.SAFETY:
                return False
        elif a != b:
            return False
    return True


# ---------------------------------------------------------------------------
# Geometry helpers that need no Fusion objects
# ---------------------------------------------------------------------------
def bin_size_mm(config):
    return (C.PITCH * int(round(config['x'])) - C.BIN_CLEARANCE,
            C.PITCH * int(round(config['y'])) - C.BIN_CLEARANCE)


def bin_height_mm(config):
    return C.U_HEIGHT * float(config['z']) + (C.LIP_HEIGHT if config.get('lip') else 0.0)


def base_size_mm(config):
    return (C.PITCH * int(round(config['x'])) + 2.0 * float(config.get('padding_x_mm', 0.0)),
            C.PITCH * int(round(config['y'])) + 2.0 * float(config.get('padding_y_mm', 0.0)))


def hollow_wall_mm(config):
    return C.LIP_WALL if config.get('lip') else float(config.get('wall_mm', C.WALL))


def interior_height_mm(config):
    return C.U_HEIGHT * float(config['z']) - C.FLOOR_TOP


def cell_centers_cm(config, center_x_cm=0.0, center_y_cm=0.0):
    """Cell centres (cm) for an x by y grid centred on (center_x, center_y)."""
    nx, ny = int(round(config['x'])), int(round(config['y']))
    p = C.cm(C.PITCH)
    return [(center_x_cm + (ix + 0.5) * p - nx * p / 2.0,
             center_y_cm + (iy + 0.5) * p - ny * p / 2.0)
            for ix in range(nx) for iy in range(ny)]


def magnet_points_cm(cell_centers):
    off = C.cm(C.MAGNET_OFFSET)
    return [(cx + dx, cy + dy) for cx, cy in cell_centers
            for dx in (-off, off) for dy in (-off, off)]


def screw_depth_mm():
    return min(6.0, C.FLOOR_TOP - C.SCREW_MIN_ROOF)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate(config, bed_mm=C.DEFAULT_BED):
    """Return (errors, warnings). Errors block creation; warnings ask to continue."""
    errors, warnings = [], []
    for axis in ('x', 'y'):
        value = float(config[axis])
        if value < 1 or value > C.MAX_UNITS_XY or abs(value - round(value)) > C.SAFETY:
            errors.append('{} must be a whole number of units from 1 to {}.'.format(
                axis.upper(), C.MAX_UNITS_XY))
    magnets = bool(config.get('magnets'))
    diameter = float(config.get('magnet_diameter_mm', C.MAGNET_DIAMETER))
    depth = float(config.get('magnet_depth_mm', C.MAGNET_DEPTH))
    if magnets:
        lo, hi = C.MAGNET_DIAMETER_RANGE
        if not lo <= diameter <= hi:
            errors.append('Magnet diameter must be between {:g} and {:g} mm.'.format(lo, hi))
    if is_base(config):
        if float(config.get('padding_x_mm', 0)) < 0 or float(config.get('padding_y_mm', 0)) < 0:
            errors.append('Base edge padding must be zero or greater.')
        if magnets and not 0.5 <= depth <= 6.0:
            errors.append('Base magnet thickness must be between 0.5 and 6 mm.')
        w, d = base_size_mm(config)
        height = C.BASE_HEIGHT + (depth if magnets else 0.0)
    else:
        z = float(config['z'])
        if z < 1 or z > C.MAX_UNITS_Z:
            errors.append('Z must be from 1 to {} units.'.format(C.MAX_UNITS_Z))
        max_depth = C.FOOT_HEIGHT - 0.75
        if config.get('screw_holes'):
            max_depth = min(max_depth, screw_depth_mm() - 0.5)
        if magnets and not 0.5 <= depth <= max_depth:
            errors.append('Magnet socket depth must be between 0.5 and {:.2f} mm{}.'.format(
                max_depth, ' with screw holes on' if config.get('screw_holes') else ''))
        if config.get('type') == 'Hollow':
            inner_w, inner_d = [s - 2 * hollow_wall_mm(config) for s in bin_size_mm(config)]
            for key, span in (('compartments_x', inner_w), ('compartments_y', inner_d)):
                count = int(config.get(key, 1))
                if count < 1 or count > C.MAX_DIVISIONS:
                    errors.append('Compartments must be from 1 to {}.'.format(C.MAX_DIVISIONS))
                elif count > 1 and (span - (count - 1) * C.DIVIDER_THICKNESS) / count < 8.0:
                    errors.append('{} compartments along {} would be narrower than 8 mm.'.format(
                        count, key[-1].upper()))
            room = interior_height_mm(config)
            if (config.get('label') or config.get('scoop')) and room < 4.0:
                warnings.append('This bin is too shallow for a label shelf or scoop; '
                                'they will be skipped.')
        w, d = bin_size_mm(config)
        height = bin_height_mm(config)
    if w > bed_mm or d > bed_mm:
        warnings.append('{:.1f} x {:.1f} mm is larger than your {:.0f} mm print bed.'.format(w, d, bed_mm))
    if height > bed_mm:
        warnings.append('{:.1f} mm tall is taller than your {:.0f} mm print bed.'.format(height, bed_mm))
    return errors, warnings


# ---------------------------------------------------------------------------
# Edit planning
# ---------------------------------------------------------------------------
REGENERATE = 'regenerate'   # new geometry; custom sketches and features are lost
EXPAND = 'expand'           # footprint grows: rebuild in place, keep sketches/planes
HEIGHT = 'height'           # Z changes: rebuild walls/lip/interior, keep foot + sketches
IN_PLACE = 'in_place'       # only bottom (magnets/screws) and/or interior options
NOTHING = 'nothing'


def plan_edit(old, new, preserve=True):
    """Decide how an edit is applied.

    Rule from the original add-in, kept on purpose: growing the footprint keeps
    the user's sketches; any shrinking axis (even if the other grows) rebuilds
    from scratch and may remove them.
    Returns dict(action, reason, bottom, interior).
    """
    old, new = normalize(old), normalize(new)
    result = {'action': NOTHING, 'reason': '', 'bottom': False, 'interior': False}
    if is_base(old) or is_base(new):
        if is_base(old) and is_base(new) and same(old, new, BASE_KEYS):
            return result
        result.update(action=REGENERATE, reason='base')
        return result

    shrink = new['x'] < old['x'] - C.SAFETY or new['y'] < old['y'] - C.SAFETY
    grow = (new['x'] > old['x'] + C.SAFETY or new['y'] > old['y'] + C.SAFETY) and not shrink
    z_changed = abs(float(new['z']) - float(old['z'])) > C.SAFETY
    body_same = same(old, new, BODY_KEYS)
    bottom = not same(old, new, BOTTOM_KEYS)
    interior = not same(old, new, INTERIOR_KEYS)
    result['bottom'], result['interior'] = bottom, interior

    if not (shrink or grow or z_changed or bottom or interior or not body_same):
        return result
    if old.get('type') != new.get('type'):
        result.update(action=REGENERATE, reason='type')
    elif shrink:
        result.update(action=REGENERATE, reason='shrink')
    elif not body_same:
        result.update(action=REGENERATE, reason='other')
    elif not preserve:
        result.update(action=REGENERATE, reason='preserve_off')
    elif grow:
        result.update(action=EXPAND)
    elif z_changed:
        result.update(action=HEIGHT)
    else:
        result.update(action=IN_PLACE)
    return result


def preserve_available(old, new):
    return plan_edit(old, new, preserve=True)['action'] in (EXPAND, HEIGHT, IN_PLACE)


# ---------------------------------------------------------------------------
# Remembered settings for the Create dialog
# ---------------------------------------------------------------------------
REMEMBER_KEYS = tuple(sorted(set(BIN_DEFAULTS) | set(BASE_DEFAULTS) |
                             {'bed_mm', 'product', 'z_units_mode', 'config_version'}))


def load_last(path):
    try:
        with open(path, 'r') as handle:
            data = json.load(handle)
        return {k: v for k, v in data.items() if k in REMEMBER_KEYS}
    except (OSError, ValueError, AttributeError):
        return {}


def save_last(path, values):
    try:
        data = {k: v for k, v in values.items() if k in REMEMBER_KEYS}
        tmp = path + '.tmp'
        with open(tmp, 'w') as handle:
            json.dump(data, handle, indent=1, sort_keys=True)
        os.replace(tmp, path)
        return True
    except OSError:
        return False
