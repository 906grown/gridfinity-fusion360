"""Baseplate geometry: 42 mm cells, optional edge padding and underside magnet pads."""

import adsk.core
import adsk.fusion

from . import bin_geometry
from . import config as cfg
from . import constants as C
from . import managed
from . import util
from .constants import cm

OPS = adsk.fusion.FeatureOperations


def magnet_pad_outline(sketch, cx, cy, size_cm, inward_x, inward_y, corner_radius_cm):
    """Square pad with one rounded corner facing the cell centre."""
    x1, x2 = cx - size_cm / 2.0, cx + size_cm / 2.0
    y1, y2 = cy - size_cm / 2.0, cy + size_cm / 2.0
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]   # CCW: BL, BR, TR, TL
    previous_dirs = [(0, 1), (-1, 0), (0, -1), (1, 0)]
    next_dirs = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    target = {(-1, -1): 0, (1, -1): 1, (1, 1): 2, (-1, 1): 3}[(inward_x, inward_y)]
    r = min(corner_radius_cm, size_cm * 0.38)
    p = adsk.core.Point3D.create
    lines = sketch.sketchCurves.sketchLines
    arcs = sketch.sketchCurves.sketchArcs

    def shifted(i, d):
        return (corners[i][0] + d[0] * r, corners[i][1] + d[1] * r)

    entries = [shifted(i, previous_dirs[i]) if i == target else corners[i] for i in range(4)]
    exits = [shifted(i, next_dirs[i]) if i == target else corners[i] for i in range(4)]

    def line(a, b):
        if abs(a[0] - b[0]) > 1e-7 or abs(a[1] - b[1]) > 1e-7:
            lines.addByTwoPoints(p(a[0], a[1], 0), p(b[0], b[1], 0))

    def arc(i):
        corner = corners[i]
        center = (corner[0] + r * (previous_dirs[i][0] + next_dirs[i][0]),
                  corner[1] + r * (previous_dirs[i][1] + next_dirs[i][1]))
        arcs.addByCenterStartSweep(p(center[0], center[1], 0), p(entries[i][0], entries[i][1], 0),
                                   util.HALF_PI)

    current = exits[0]
    for i in range(1, 4):
        line(current, entries[i])
        if i == target:
            arc(i)
        current = exits[i]
    line(current, entries[0])
    if target == 0:
        arc(0)


def fillet_pad_tops(component, points, pad_half_cm, face_z_cm, radius_mm):
    """Round where each pad meets the grid; retry smaller radii, never fail the base."""
    if component.bRepBodies.count == 0:
        return
    body = component.bRepBodies.item(0)
    selected = adsk.core.ObjectCollection.create()
    tol = 0.0001
    for edge in body.edges:
        b = edge.boundingBox
        if abs(b.maxPoint.z - b.minPoint.z) > tol or abs(b.minPoint.z - face_z_cm) > tol:
            continue
        for cx, cy in points:
            x_min, x_max, y_min, y_max = cx - pad_half_cm, cx + pad_half_cm, cy - pad_half_cm, cy + pad_half_cm
            if (b.minPoint.x < x_min - tol or b.maxPoint.x > x_max + tol or
                    b.minPoint.y < y_min - tol or b.maxPoint.y > y_max + tol):
                continue
            if (abs(b.minPoint.x - x_min) <= tol or abs(b.maxPoint.x - x_max) <= tol or
                    abs(b.minPoint.y - y_min) <= tol or abs(b.maxPoint.y - y_max) <= tol):
                selected.add(edge)
                break
    if selected.count == 0:
        return
    for candidate in sorted({radius_mm, 0.5, 0.25}, reverse=True):
        try:
            fillet_input = component.features.filletFeatures.createInput()
            fillet_input.edgeSetInputs.addConstantRadiusEdgeSet(
                selected, adsk.core.ValueInput.createByReal(cm(candidate)), False)
            util.tag(component.features.filletFeatures.add(fillet_input), 'magnet-pad-fillet')
            return
        except Exception:
            util.log('Pad fillet {} mm failed, trying smaller'.format(candidate))
    util.log('Pad fillet skipped')


def generate_base(config, parent=None, transform=None):
    nx, ny = int(round(config['x'])), int(round(config['y']))
    width_mm, depth_mm = cfg.base_size_mm(config)
    magnets = bool(config.get('magnets'))
    extra_cm = cm(config.get('magnet_depth_mm', C.MAGNET_DEPTH)) if magnets else 0.0
    centers = cfg.cell_centers_cm(config)

    occurrence = bin_geometry.new_occurrence(parent, transform)
    component = occurrence.component
    managed.mark_fully_tagged(component)
    component.name = 'Gridfinity Base {:.0f}x{:.0f}'.format(config['x'], config['y'])

    frame = util.rounded_sketch(component, util.new_plane(component, -extra_cm), 'Base plate 1x1 footprint',
                                C.ROLE_BASE, [(0.0, 0.0)], cm(width_mm), cm(depth_mm), cm(C.BASE_RADIUS))
    util.extrude(component, frame.profiles.item(0), cm(C.BASE_HEIGHT) + extra_cm,
                 OPS.NewBodyFeatureOperation, C.ROLE_BASE, 'Baseplate frame')

    # Hollow socket per cell (opens through the underside), 0.35 mm relief.
    bottom_size, bottom_radius = C.BASE_CAVITY_BOTTOM
    sections = [(-0.01 - extra_cm, bottom_size, bottom_radius)]
    if extra_cm > 0:
        sections.append((-0.01, bottom_size, bottom_radius))
    sections += [(cm(z), size, radius) for z, size, radius in C.BASE_CAVITY]
    maps = []
    for index, (z_cm, size, radius) in enumerate(sections):
        sketch = util.rounded_sketch(component, util.new_plane(component, z_cm),
                                     'Baseplate profile section {}'.format(index + 1), 'baseplate-cavity',
                                     centers, cm(size), cm(size), cm(radius))
        maps.append(util.profiles_by_center(sketch))

    def cavity(center):
        key = (round(center[0], 6), round(center[1], 6))
        profiles = [m.get(key) for m in maps]
        if not all(profiles):
            raise RuntimeError('Could not find the baseplate hollow profile for cell {}.'.format(key))
        return util.loft(component, profiles, OPS.CutFeatureOperation, 'baseplate-cavity',
                         'Baseplate cell socket')

    first = min(centers)
    first_cavity = cavity(first)
    try:
        util.pattern_grid(component, first_cavity, nx, ny, cm(C.PITCH), 'baseplate-cavity',
                          'Baseplate cell socket pattern')
    except Exception:
        util.log_exception('Cell socket pattern failed; using one loft per cell')
        for center in centers:
            if center != first:
                cavity(center)

    if magnets:
        diameter = float(config.get('magnet_diameter_mm', C.MAGNET_DIAMETER))
        pad_half = cm(diameter + C.BASE_PAD_EXTRA) / 2.0
        points = cfg.magnet_points_cm(centers)
        pads = util.new_sketch(component, util.new_plane(component, -extra_cm),
                               'Underside square magnet corner pads', C.ROLE_MAGNET)
        for (mx, my), (cx, cy) in zip(points, [c for c in centers for _ in range(4)]):
            magnet_pad_outline(pads, mx, my, 2.0 * pad_half,
                               -1 if mx > cx else 1, -1 if my > cy else 1,
                               min(0.40, 0.76 * pad_half))
        profiles = [pads.profiles.item(i) for i in range(pads.profiles.count)]
        # Join 0.1 mm into the plate so each pad fuses cleanly.
        util.extrude(component, profiles, extra_cm + 0.01, OPS.JoinFeatureOperation, C.ROLE_MAGNET,
                     'Baseplate magnet pads')
        fillet_pad_tops(component, points, pad_half, 0.01, C.BASE_PAD_FILLET)
        holes = util.new_sketch(component, util.new_plane(component, -extra_cm - 0.01),
                                'Through holes in underside magnet pads', C.ROLE_MAGNET)
        for mx, my in points:
            holes.sketchCurves.sketchCircles.addByCenterRadius(
                adsk.core.Point3D.create(mx, my, 0), cm(diameter) / 2.0)
        profiles = [holes.profiles.item(i) for i in range(holes.profiles.count)]
        util.extrude(component, profiles, extra_cm + 0.02, OPS.CutFeatureOperation, C.ROLE_MAGNET,
                     'Baseplate magnet holes')
        bin_geometry.fillet_socket_openings(component, points, diameter, [-extra_cm])

    managed.hide_generated(component)
    return occurrence
