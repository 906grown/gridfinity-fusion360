"""Run outside Fusion:  python -m pytest tests   (from the gridfinity_v2 folder)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gf import config as cfg  # noqa: E402

BIN = dict(type='Hollow', x=2, y=2, z=3, lip=True, wall_mm=1.2, magnets=False,
           magnet_diameter_mm=6.5, magnet_depth_mm=2.4, screw_holes=False,
           compartments_x=1, compartments_y=1, label=False, scoop=False, z_units_mode=2)


def edit(**changes):
    new = dict(BIN)
    new.update(changes)
    return new


def action(new, preserve=True, old=BIN):
    return cfg.plan_edit(old, new, preserve)


# --- the sketch rule: grow keeps, shrink rebuilds ---------------------------------
def test_grow_x_keeps_sketches():
    assert action(edit(x=3))['action'] == cfg.EXPAND


def test_grow_both_and_height_keeps_sketches():
    assert action(edit(x=3, y=4, z=5))['action'] == cfg.EXPAND


def test_grow_with_new_interior_and_magnets_keeps_sketches():
    assert action(edit(x=3, compartments_x=3, magnets=True))['action'] == cfg.EXPAND


def test_shrink_rebuilds():
    plan = action(edit(x=1))
    assert plan['action'] == cfg.REGENERATE and plan['reason'] == 'shrink'


def test_grow_one_shrink_other_counts_as_shrink():
    plan = action(edit(x=3, y=1))
    assert plan['action'] == cfg.REGENERATE and plan['reason'] == 'shrink'


def test_grow_with_preserve_off_rebuilds():
    plan = action(edit(x=3), preserve=False)
    assert plan['action'] == cfg.REGENERATE and plan['reason'] == 'preserve_off'


# --- other paths ---------------------------------------------------------------------
def test_height_up_and_down():
    assert action(edit(z=6))['action'] == cfg.HEIGHT
    assert action(edit(z=2))['action'] == cfg.HEIGHT


def test_magnets_only_in_place():
    plan = action(edit(magnets=True))
    assert plan['action'] == cfg.IN_PLACE and plan['bottom'] and not plan['interior']


def test_interior_only_in_place():
    plan = action(edit(label=True, compartments_y=2))
    assert plan['action'] == cfg.IN_PLACE and plan['interior'] and not plan['bottom']


def test_type_and_lip_changes_rebuild():
    assert action(edit(type='Solid'))['reason'] == 'type'
    assert action(edit(lip=False))['reason'] == 'other'


def test_nothing_changed():
    assert action(dict(BIN))['action'] == cfg.NOTHING


def test_bases_always_rebuild_when_changed():
    base = dict(type='Base', x=2, y=2, padding_x_mm=0, padding_y_mm=0, magnets=False,
                magnet_diameter_mm=6.5, magnet_depth_mm=2.4)
    assert cfg.plan_edit(base, dict(base))['action'] == cfg.NOTHING
    assert cfg.plan_edit(base, dict(base, x=3))['action'] == cfg.REGENERATE


def test_preserve_available():
    assert cfg.preserve_available(BIN, edit(x=3))
    assert not cfg.preserve_available(BIN, edit(x=1))


# --- legacy configs -------------------------------------------------------------------
def test_v1_config_upgrades():
    old = {'type': 'Solid', 'x': 1.0, 'y': 1.0, 'z': 2.0, 'lip': True, 'wall_mm': 1.2,
           'magnets': True}
    new = cfg.normalize(old)
    assert new['z'] == 3.0                      # v1 stored Z above an extra base unit
    assert new['magnet_diameter_mm'] == 6.0     # keeps the old 6 x 2 holes
    assert new['compartments_x'] == 1 and new['label'] is False
    # normalizing twice must not add another unit
    assert cfg.normalize(new)['z'] == 3.0


def test_v1_config_with_units_mode_kept():
    old = {'type': 'Hollow', 'x': 1, 'y': 1, 'z': 4, 'z_units_mode': 2, 'lip': True}
    assert cfg.normalize(old)['z'] == 4


def test_adding_v2_options_to_v1_bin_is_in_place():
    v1 = {'type': 'Hollow', 'x': 2, 'y': 2, 'z': 3, 'z_units_mode': 2, 'lip': True, 'wall_mm': 1.2,
          'magnets': False, 'magnet_diameter_mm': 6.0, 'magnet_depth_mm': 2.0}
    new = cfg.normalize(v1)
    new['scoop'] = True
    assert cfg.plan_edit(v1, new)['action'] == cfg.IN_PLACE


# --- validation -----------------------------------------------------------------------
def test_too_many_units_is_an_error():
    errors, _ = cfg.validate(edit(x=25))
    assert errors


def test_bed_warning():
    _, warnings = cfg.validate(edit(x=7, y=1), bed_mm=256)
    assert any('print bed' in w for w in warnings)
    _, warnings = cfg.validate(edit(x=6, y=6), bed_mm=256)
    assert not warnings


def test_magnet_depth_limits():
    assert cfg.validate(edit(magnets=True, magnet_depth_mm=4.5))[0]
    assert not cfg.validate(edit(magnets=True, magnet_depth_mm=2.4))[0]
    assert cfg.validate(edit(magnets=True, magnet_diameter_mm=12))[0]


def test_screw_holes_limit_magnet_depth():
    assert cfg.validate(edit(magnets=True, screw_holes=True, magnet_depth_mm=4.2))[0]
    assert not cfg.validate(edit(magnets=True, screw_holes=True, magnet_depth_mm=2.4))[0]


def test_compartments_too_narrow():
    assert cfg.validate(edit(x=1, compartments_x=5))[0]
    assert not cfg.validate(edit(x=2, compartments_x=4))[0]


def test_shallow_bin_warns_for_label():
    _, warnings = cfg.validate(edit(z=1, label=True))
    assert warnings


def test_base_padding_negative():
    base = dict(type='Base', x=2, y=2, padding_x_mm=-1, padding_y_mm=0, magnets=False)
    assert cfg.validate(base)[0]


def test_cell_centers():
    centers = cfg.cell_centers_cm({'x': 2, 'y': 1})
    assert [(round(x, 6), round(y, 6)) for x, y in centers] == [(-2.1, 0.0), (2.1, 0.0)]
    assert len(cfg.magnet_points_cm(centers)) == 8


def test_last_settings_round_trip(tmp_path):
    path = str(tmp_path / 'last.json')
    assert cfg.save_last(path, dict(BIN, bed_mm=256, product='Bin', _center_x_cm=4))
    loaded = cfg.load_last(path)
    assert loaded['x'] == 2 and loaded['bed_mm'] == 256 and '_center_x_cm' not in loaded
    assert cfg.load_last(str(tmp_path / 'missing.json')) == {}


def test_remembered_settings_do_not_gain_a_unit(tmp_path):
    path = str(tmp_path / 'last.json')
    cfg.save_last(path, cfg.normalize(dict(BIN, z=3)))
    assert cfg.normalize(cfg.load_last(path))['z'] == 3


def test_v2_config_without_units_mode_is_not_legacy():
    assert cfg.normalize({'type': 'Solid', 'x': 1, 'y': 1, 'z': 1, 'config_version': 3})['z'] == 1
