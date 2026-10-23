"""All Gridfinity dimensions and add-in identifiers in one place.

Dimensions are millimetres; the Fusion API works in centimetres, so geometry
code converts with ``cm()`` at the point of use. Nothing here imports adsk, so
this module (and config.py) can be unit-tested outside Fusion.
"""

VERSION = '2.0.0'


def cm(mm):
    """Millimetres -> Fusion API centimetres."""
    return float(mm) / 10.0


# --- Add-in identity ----------------------------------------------------------
ADDIN_NAME = 'Gridfinity Create v2'
CREATE_ID = 'GridfinityBinCreateV2'
EDIT_ID = 'GridfinityBinEditV2'
PANEL_ID = 'SolidCreatePanel'
WORKSPACE_ID = 'FusionSolidEnvironment'
# Same attribute group as v1 so v2 can read and edit bins made by the original.
ATTR_GROUP = 'GridfinityBin'
ATTR_NAME = 'settings'
OWNER_ATTR = 'feature_owner'
ROLE_ATTR = 'feature_role'
OWNER_VALUE = 'GridfinityBinAddin'
CONFIG_VERSION = 3          # bumped from v1 (which had no version key)

# --- Grid -----------------------------------------------------------------------
PITCH = 42.0                # cell pitch
BIN_CLEARANCE = 0.5         # total X/Y clearance of a bin (0.25 per side)
U_HEIGHT = 7.0              # one height unit
OUTER_RADIUS = 3.75         # bin outer corner radius

# Bin foot profile: (z, size, corner radius) sections. 0.8 / 1.8 / 2.15 mm.
FOOT_SECTIONS = [
    (0.00, 35.6, 0.8),
    (0.80, 37.2, 1.6),
    (2.60, 37.2, 1.6),
    (4.75, 41.5, 3.75),
]
FOOT_HEIGHT = 4.75
FOOT_TOP = 41.5
DECK = 1.2                  # printable deck above the foot
FLOOR_TOP = FOOT_HEIGHT + DECK      # 5.95
WALL = 1.2                  # hollow wall without a lip

# Stacking lip: 0.7 mm 45-degree ramp, 1.8 mm land, 1.9 mm 45-degree ramp.
LIP_HEIGHT = 4.4
# (height above rim, opening size, opening radius) for each lip section.
LIP_SECTIONS = {
    'lower_bottom': (0.0, 35.8, 0.8),
    'lower_top': (0.7, 37.2, 1.6),
    'upper_bottom': (2.5, 37.2, 1.6),
    'upper_top': (4.4, 41.0, 3.5),
}
LIP_WALL = (FOOT_TOP - 35.8) / 2.0  # 2.85 mm: hollow wall matching the lip bottom

# Magnets (bins and bases share positions).
MAGNET_OFFSET = 13.0        # from the cell centre, each axis
MAGNET_DIAMETER = 6.5       # fits a 6 x 2 mm magnet on FDM prints
MAGNET_DEPTH = 2.4
MAGNET_LEAD_IN = 0.5
MAGNET_DIAMETER_RANGE = (2.0, 9.0)   # 9 mm keeps the hole inside the foot
SCREW_DIAMETER = 3.0        # M3 screw hole under each magnet
SCREW_MIN_ROOF = 0.6        # material left above a blind screw hole

# Baseplate.
BASE_HEIGHT = 5.0
BASE_RADIUS = 4.0
# (z, size, radius) cavity sections, 0.35 mm relief included.
BASE_CAVITY = [
    (0.35, 36.30, 1.15),
    (1.05, 37.70, 1.85),
    (2.85, 37.70, 1.85),
    (5.00, 42.00, 4.00),
]
BASE_CAVITY_BOTTOM = (35.15, 0.75)
BASE_PAD_EXTRA = 4.0        # magnet pad = magnet diameter + 4 mm
BASE_PAD_FILLET = 1.0       # 1.5 mm never solves next to the socket profile; 1.0 does

# Interior options (hollow bins).
DIVIDER_THICKNESS = 1.2
LABEL_DEPTH = 12.0          # how far the label shelf reaches in from the back wall
LABEL_THICKNESS = 1.2
SCOOP_RADIUS = 10.0         # finger scoop along the front wall
MAX_DIVISIONS = 10          # compartments per axis

# Limits.
MAX_UNITS_XY = 20
MAX_UNITS_Z = 40
DEFAULT_BED = 256.0         # Bambu A1
SAFETY = 1e-6

# --- Feature / sketch roles ---------------------------------------------------
ROLE_FOUNDATION = 'foundation'
ROLE_HEIGHT = 'bin-height'          # walls / solid body
ROLE_LIP = 'bin-height-lip'
ROLE_INTERIOR = 'bin-height-interior'   # dividers, label, scoop
ROLE_MAGNET = 'magnet'
ROLE_BASE = 'base'
HEIGHT_ROLES = (ROLE_HEIGHT, ROLE_LIP, ROLE_INTERIOR)

CUSTOM_PLANE_NAME = 'Gridfinity custom sketch plane'
MAGNET_SKETCH_NAME = 'Magnet sockets - 4 per base cell'

# --- Legacy (v1) generated sketch names -----------------------------------------
# v1 identified its own sketches by name only. v2 tags every sketch it makes;
# these lists are used only for components that contain no tagged sketches.
LEGACY_FOUNDATION_EXACT = {'Gridfinity base deck'}
LEGACY_FOUNDATION_PREFIX = ('Base profile section ', 'Expansion foot profile section ')
LEGACY_MAGNET_EXACT = {
    'Magnet sockets - 4 per base cell', 'Expansion magnet sockets',
    'Through holes in underside magnet pads', 'Underside square magnet corner pads',
}
LEGACY_HEIGHT_EXACT = {
    'Bin walls', 'Solid bin body', 'Stacking lip outer profile',
    'Expanded bin outer wall profile', 'Gridfinity preserved expansion floor',
    'Stacking lip transition bottom', 'Stacking lip transition top', 'Stacking lip upper rim',
}
LEGACY_HEIGHT_PREFIX = (
    'Stacking lip section ', 'Stacking lip lower ramp ', 'Stacking lip upper ramp ',
    'Stacking lip vertical land', 'Expanded stacking lip section ',
    'Open preserved bin through old', 'Remove old solid-bin lip divider ',
)
LEGACY_BASE_EXACT = {'Base plate 1x1 footprint'}
LEGACY_BASE_PREFIX = ('Baseplate profile section ',)
