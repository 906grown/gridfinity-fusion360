"""Command dialog: inputs, show/hide rules, loading saved settings, reading the dialog."""

import adsk.core

from . import config as cfg
from . import constants as C


class DialogState:
    """Per-dialog state (one instance per open Create/Edit dialog)."""

    def __init__(self, editing):
        self.editing = editing
        self.original = None          # saved config of the item being edited
        self.changed_axes = set()     # axes whose dropdown the user touched
        self.preserve_touched = False


TEXT = adsk.core.DropDownStyles.TextListDropDownStyle
INTERIOR_INPUTS = ('compartmentsX', 'compartmentsY', 'labelShelf', 'fingerScoop')
BIN_ONLY = ('zUnits', 'customZEnabled', 'customZ', 'binType', 'stackingLip', 'screwHoles') + INTERIOR_INPUTS
BASE_ONLY = ('basePaddingX', 'basePaddingY')


def mm(value):
    return adsk.core.ValueInput.createByString('{} mm'.format(value))


def add_inputs(command, state, last=None):
    inputs = command.commandInputs
    if state.editing:
        target = inputs.addSelectionInput('targetBin', 'Existing item', 'Select a Gridfinity bin or base.')
        target.addSelectionFilter('Occurrences')
        target.setSelectionLimits(1, 1)
    product = inputs.addDropDownCommandInput('productType', 'Item type' if state.editing else 'Create type', TEXT)
    product.listItems.add('Bin', True)
    product.listItems.add('Base', False)
    product.isEnabled = not state.editing

    for axis, top in (('X', 10), ('Y', 10), ('Z', 20)):
        menu = inputs.addDropDownCommandInput(axis.lower() + 'Units', axis + ' units', TEXT)
        for count in range(1, top + 1):
            menu.listItems.add(str(count), count == 1)
        inputs.addBoolValueInput('custom{}Enabled'.format(axis), 'Custom ' + axis, True, '', False)
        if axis == 'Z':
            inputs.addFloatSpinnerCommandInput('customZ', 'Custom Z (u)', '', 1.0,
                                               float(C.MAX_UNITS_Z), 0.01, 1.0)
        else:
            inputs.addIntegerSpinnerCommandInput('custom' + axis, 'Custom {} (u)'.format(axis),
                                                 1, C.MAX_UNITS_XY, 1, 1)

    kind = inputs.addDropDownCommandInput('binType', 'Bin type', TEXT)
    kind.listItems.add('Hollow', False)
    kind.listItems.add('Solid', True)
    inputs.addBoolValueInput('stackingLip', 'Stacking lip', True, '', True)

    inputs.addIntegerSpinnerCommandInput('compartmentsX', 'Compartments along X', 1, C.MAX_DIVISIONS, 1, 1)
    inputs.addIntegerSpinnerCommandInput('compartmentsY', 'Compartments along Y', 1, C.MAX_DIVISIONS, 1, 1)
    inputs.addBoolValueInput('labelShelf', 'Label shelf (back wall)', True, '', False)
    inputs.addBoolValueInput('fingerScoop', 'Finger scoop (front wall)', True, '', False)

    inputs.addBoolValueInput('magnetSockets', 'Magnet sockets', True, '', False)
    inputs.addValueInput('magnetDiameter', 'Magnet hole diameter', 'mm', mm(C.MAGNET_DIAMETER))
    inputs.addValueInput('magnetDepth', 'Magnet hole depth', 'mm', mm(C.MAGNET_DEPTH))
    inputs.addBoolValueInput('screwHoles', 'Screw holes (M3)', True, '', False)
    inputs.addValueInput('basePaddingX', 'X edge padding (each side)', 'mm', mm(0))
    inputs.addValueInput('basePaddingY', 'Y edge padding (each side)', 'mm', mm(0))
    inputs.addValueInput('bedSize', 'Printer bed size', 'mm', mm(C.DEFAULT_BED))
    if state.editing:
        preserve = inputs.addBoolValueInput('preserveDesign', 'Preserve existing design', True, '', False)
        preserve.isEnabled = False
        preserve.tooltip = ('Growing X/Y, changing Z, magnets/screws, or interior options keeps your '
                            'sketches. Any shrinking axis rebuilds the item from scratch.')
    status = inputs.addTextBoxCommandInput('status', '', '', 3, True)
    status.isFullWidth = True

    if not state.editing and last:
        load_values(inputs, cfg.normalize(dict(last, type=last.get('type', 'Solid'))), last)
    refresh(inputs, state)


def _select(menu, name):
    for i in range(menu.listItems.count):
        item = menu.listItems.item(i)
        item.isSelected = (item.name == name)


def _select_closest(menu, value):
    best, best_delta = None, None
    for i in range(menu.listItems.count):
        item = menu.listItems.item(i)
        delta = abs(float(item.name) - value)
        if best_delta is None or delta < best_delta:
            best, best_delta = item, delta
    best.isSelected = True


def load_values(inputs, config, extra=None):
    """Fill the dialog from a saved config (Edit) or remembered settings (Create)."""
    is_base = cfg.is_base(config)
    _select(inputs.itemById('productType'), 'Base' if is_base else 'Bin')
    axes = ['x', 'y'] + ([] if is_base else ['z'])
    for axis in axes:
        value = float(config[axis])
        _select_closest(inputs.itemById(axis + 'Units'), value)
        custom = inputs.itemById('custom' + axis.upper())
        custom.value = int(round(value)) if axis != 'z' else value
        enabled = inputs.itemById('custom{}Enabled'.format(axis.upper()))
        # Values the dropdown can't show (e.g. 12 units or 2.5U) stay on the custom control.
        menu_max = 20 if axis == 'z' else 10
        enabled.value = value > menu_max or abs(value - round(value)) > 1e-6
    if is_base:
        inputs.itemById('basePaddingX').expression = '{} mm'.format(config.get('padding_x_mm', 0.0))
        inputs.itemById('basePaddingY').expression = '{} mm'.format(config.get('padding_y_mm', 0.0))
    else:
        _select(inputs.itemById('binType'), config.get('type', 'Solid'))
        inputs.itemById('stackingLip').value = bool(config.get('lip', True))
        inputs.itemById('screwHoles').value = bool(config.get('screw_holes', False))
        inputs.itemById('compartmentsX').value = int(config.get('compartments_x', 1))
        inputs.itemById('compartmentsY').value = int(config.get('compartments_y', 1))
        inputs.itemById('labelShelf').value = bool(config.get('label', False))
        inputs.itemById('fingerScoop').value = bool(config.get('scoop', False))
    inputs.itemById('magnetSockets').value = bool(config.get('magnets', False))
    inputs.itemById('magnetDiameter').expression = '{} mm'.format(config.get('magnet_diameter_mm', C.MAGNET_DIAMETER))
    inputs.itemById('magnetDepth').expression = '{} mm'.format(config.get('magnet_depth_mm', C.MAGNET_DEPTH))
    bed = (extra or {}).get('bed_mm')
    if bed:
        inputs.itemById('bedSize').expression = '{} mm'.format(bed)


def _axis_value(inputs, axis, state):
    custom_on = inputs.itemById('custom{}Enabled'.format(axis.upper())).value
    if custom_on:
        return float(inputs.itemById('custom' + axis.upper()).value)
    menu = inputs.itemById(axis + 'Units')
    selected = menu.selectedItem
    value = float(selected.name) if selected else 1.0
    # Editing: an untouched dropdown keeps the item's real value (it may be a
    # custom size the dropdown cannot show), so nothing changes by accident.
    if state.editing and state.original and axis not in state.changed_axes and axis in state.original:
        return float(state.original[axis])
    return value


def product(inputs):
    item = inputs.itemById('productType').selectedItem
    return item.name if item else 'Bin'


def read_config(inputs, state):
    magnets = {
        'magnets': inputs.itemById('magnetSockets').value,
        'magnet_diameter_mm': inputs.itemById('magnetDiameter').value * 10.0,
        'magnet_depth_mm': inputs.itemById('magnetDepth').value * 10.0,
    }
    x, y = _axis_value(inputs, 'x', state), _axis_value(inputs, 'y', state)
    if product(inputs) == 'Base':
        return dict(type='Base', x=x, y=y, wall_mm=C.WALL, config_version=C.CONFIG_VERSION,
                    padding_x_mm=inputs.itemById('basePaddingX').value * 10.0,
                    padding_y_mm=inputs.itemById('basePaddingY').value * 10.0, **magnets)
    kind = inputs.itemById('binType').selectedItem
    return dict(type=kind.name if kind else 'Solid', x=x, y=y, z=_axis_value(inputs, 'z', state),
                z_units_mode=2, config_version=C.CONFIG_VERSION,
                lip=inputs.itemById('stackingLip').value, wall_mm=C.WALL,
                screw_holes=inputs.itemById('screwHoles').value,
                compartments_x=int(inputs.itemById('compartmentsX').value),
                compartments_y=int(inputs.itemById('compartmentsY').value),
                label=inputs.itemById('labelShelf').value,
                scoop=inputs.itemById('fingerScoop').value, **magnets)


def bed_mm(inputs):
    value = inputs.itemById('bedSize').value * 10.0
    return value if value > 0 else C.DEFAULT_BED


def refresh(inputs, state):
    """Show/hide and enable/disable inputs to match the current choices."""
    is_bin = product(inputs) == 'Bin'
    for input_id in BIN_ONLY:
        inputs.itemById(input_id).isVisible = is_bin
    for input_id in BASE_ONLY:
        inputs.itemById(input_id).isVisible = not is_bin
    for axis in 'XYZ':
        on = inputs.itemById('custom{}Enabled'.format(axis)).value
        inputs.itemById('custom' + axis).isEnabled = on
        inputs.itemById(axis.lower() + 'Units').isEnabled = not on
    magnets = inputs.itemById('magnetSockets').value
    inputs.itemById('magnetDiameter').isEnabled = magnets
    inputs.itemById('magnetDepth').isEnabled = magnets
    kind = inputs.itemById('binType').selectedItem
    hollow = is_bin and kind is not None and kind.name == 'Hollow'
    for input_id in INTERIOR_INPUTS:
        inputs.itemById(input_id).isEnabled = hollow
    preserve = inputs.itemById('preserveDesign')
    if preserve:
        preserve.isVisible = is_bin
        _refresh_preserve(inputs, state, preserve)
    _refresh_status(inputs, state)


def _refresh_preserve(inputs, state, preserve):
    if not state.original:
        return
    try:
        available = cfg.preserve_available(state.original, read_config(inputs, state))
    except Exception:
        available = False
    preserve.isEnabled = available
    if not available:
        preserve.value = False
    elif not state.preserve_touched:
        preserve.value = True


def _refresh_status(inputs, state):
    status = inputs.itemById('status')
    if state.editing and not state.original:
        status.formattedText = 'Select a bin or base made by this add-in.'
        return
    try:
        config = read_config(inputs, state)
        errors, warnings = cfg.validate(config, bed_mm(inputs))
    except Exception as exc:
        status.formattedText = str(exc)
        return
    lines = ['<b>Fix:</b> ' + e for e in errors] + ['Note: ' + w for w in warnings]
    if state.editing and state.original and not errors:
        plan = cfg.plan_edit(state.original, config, inputs.itemById('preserveDesign').value)
        lines.append({
            cfg.EXPAND: 'Grows the footprint and keeps your sketches.',
            cfg.HEIGHT: 'Changes the height and keeps your sketches.',
            cfg.IN_PLACE: 'Updates in place; nothing else is touched.',
            cfg.NOTHING: 'No changes yet.',
        }.get(plan['action'], 'Rebuilds from scratch; your sketches may be removed.'))
    status.formattedText = '<br>'.join(lines)


def errors(inputs, state):
    if state.editing and not state.original:
        return ['no item selected']
    try:
        return cfg.validate(read_config(inputs, state), bed_mm(inputs))[0]
    except Exception as exc:
        return [str(exc)]
