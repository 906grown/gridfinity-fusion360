"""Create / Edit commands: event handlers and the edit decision flow."""

import json
import os

import adsk.core
import adsk.fusion

from . import base_geometry
from . import bin_geometry
from . import config as cfg
from . import constants as C
from . import edit_ops
from . import managed
from . import ui
from . import util

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
LAST_SETTINGS = os.path.join(ADDIN_DIR, 'last_settings.json')

# Handlers live as long as the add-in (button handlers) or the dialog (the rest).
_app_handlers = []
_dialog_handlers = []


def keep(event, handler, store):
    event.add(handler)
    store.append(handler)


# ---------------------------------------------------------------------------
# Saved settings on the component
# ---------------------------------------------------------------------------
def get_config(occurrence):
    if not occurrence:
        return None
    attr = (occurrence.component.attributes.itemByName(C.ATTR_GROUP, C.ATTR_NAME) or
            occurrence.attributes.itemByName(C.ATTR_GROUP, C.ATTR_NAME))
    if not attr:
        return None
    try:
        return cfg.normalize(json.loads(attr.value))
    except ValueError:
        util.log_exception('Saved settings could not be read')
        return None


def save_config(occurrence, config):
    payload = json.dumps(cfg.normalize(config), sort_keys=True)
    occurrence.component.attributes.add(C.ATTR_GROUP, C.ATTR_NAME, payload)
    occurrence.attributes.add(C.ATTR_GROUP, C.ATTR_NAME, payload)


# ---------------------------------------------------------------------------
# Command created
# ---------------------------------------------------------------------------
class CommandCreated(adsk.core.CommandCreatedEventHandler):
    def __init__(self, editing):
        super().__init__()
        self.editing = editing

    def notify(self, args):
        try:
            command = args.command
            command.isExecutedWhenPreEmpted = False
            state = ui.DialogState(self.editing)
            _dialog_handlers.clear()
            ui.add_inputs(command, state, None if self.editing else cfg.load_last(LAST_SETTINGS))
            keep(command.inputChanged, InputChanged(state), _dialog_handlers)
            keep(command.validateInputs, ValidateInputs(state), _dialog_handlers)
            keep(command.execute, Execute(state), _dialog_handlers)
            keep(command.destroy, Destroy(), _dialog_handlers)
        except Exception:
            util.error_box('Could not open {}'.format('Edit Gridfinity Item' if self.editing else C.ADDIN_NAME))


class Destroy(adsk.core.CommandEventHandler):
    def notify(self, args):
        # Dropping the per-dialog handlers stops them piling up over a session.
        _dialog_handlers.clear()


class InputChanged(adsk.core.InputChangedEventHandler):
    def __init__(self, state):
        super().__init__()
        self.state = state

    def notify(self, args):
        try:
            changed, inputs, state = args.input, args.inputs, self.state
            if changed.id == 'targetBin':
                self._load_target(changed, inputs)
            if changed.id in ('xUnits', 'yUnits', 'zUnits'):
                state.changed_axes.add(changed.id[0])
            if changed.id in ('customXEnabled', 'customYEnabled', 'customZEnabled', 'customX', 'customY', 'customZ'):
                state.changed_axes.add(changed.id[6].lower())
            if changed.id == 'preserveDesign':
                state.preserve_touched = True
            ui.refresh(inputs, state)
        except Exception:
            util.error_box('Input update failed')

    def _load_target(self, selection, inputs):
        state = self.state
        state.original, state.changed_axes, state.preserve_touched = None, set(), False
        if selection.selectionCount < 1:
            return
        occurrence = adsk.fusion.Occurrence.cast(selection.selection(0).entity)
        config = get_config(occurrence)
        if not config:
            util.ui().messageBox('Select a bin or base created by this add-in.')
            selection.clearSelection()
            return
        state.original = dict(config)
        ui.load_values(inputs, config)


class ValidateInputs(adsk.core.ValidateInputsEventHandler):
    def __init__(self, state):
        super().__init__()
        self.state = state

    def notify(self, args):
        try:
            args.areInputsValid = not ui.errors(args.inputs, self.state)
        except Exception:
            util.log_exception('Validation failed')
            args.areInputsValid = False


class Execute(adsk.core.CommandEventHandler):
    def __init__(self, state):
        super().__init__()
        self.state = state

    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            config = ui.read_config(inputs, self.state)
            errors, warnings = cfg.validate(config, ui.bed_mm(inputs))
            if errors:
                util.ui().messageBox('\n'.join(errors), 'Gridfinity')
                return
            if warnings and not util.confirm('\n'.join(warnings) + '\n\nContinue anyway?', 'Gridfinity'):
                return
            design = adsk.fusion.Design.cast(util.app().activeProduct)
            if not design:
                raise RuntimeError('Open a Fusion design before creating a bin.')
            if self.state.editing:
                run_edit(inputs, self.state, config)
            else:
                if not allow_components(design):
                    return
                run_create(design, config)
                remember = dict(config, product=ui.product(inputs), bed_mm=ui.bed_mm(inputs))
                cfg.save_last(LAST_SETTINGS, remember)
        except Exception:
            util.error_box('Gridfinity failed')


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def allow_components(design, ask=True):
    """Newer Fusion 'Part' designs hold a single component; offer to switch to Hybrid."""
    try:
        if design.designIntent != adsk.fusion.DesignIntentTypes.PartDesignIntentType:
            return True
    except Exception:
        return True       # older Fusion without design intent
    if ask and not util.confirm(
            'This is a Part design, which can only hold one component. Switch it to a Hybrid design '
            'so each Gridfinity item can be its own component?', 'Gridfinity'):
        return False
    design.designIntent = adsk.fusion.DesignIntentTypes.HybridDesignIntentType
    return True


def creation_parent(design):
    """The component you are working in, unless that is itself a Gridfinity item (then root)."""
    active = design.activeComponent
    if not active or active.attributes.itemByName(C.ATTR_GROUP, C.ATTR_NAME):
        return design.rootComponent
    return active


def run_create(design, config, parent=None, transform=None, center=(0.0, 0.0)):
    parent = parent or creation_parent(design)
    try:
        was_active = design.activeOccurrence     # None when the root is active
    except Exception:
        was_active = None
    if cfg.is_base(config):
        occurrence = base_geometry.generate_base(config, parent, transform)
    else:
        config['_center_x_cm'], config['_center_y_cm'] = center
        occurrence = bin_geometry.generate_bin(config, parent, transform,
                                               center_x=center[0], center_y=center[1])
    save_config(occurrence, config)
    # Fusion activates a newly added component; step back to where you were working so
    # the next item isn't nested inside this one.
    try:
        if was_active is not None and was_active.isValid and was_active.component != occurrence.component:
            was_active.activate()
        else:
            design.activateRootComponent()
    except Exception:
        util.log_exception('Could not re-activate the previous component')
    return occurrence


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------
REGENERATE_MESSAGES = {
    'type': ('Changing between Hollow and Solid rebuilds the bin from scratch. Your sketches and '
             'features on this bin will be removed. Continue?'),
    'shrink': ('At least one footprint direction is getting smaller (this counts as shrinking even if '
               'the other grows). The bin will be rebuilt from scratch and your sketches and features '
               'on it will be removed. Continue?'),
    'other': ('Changing the stacking lip rebuilds the item from scratch; your sketches and features '
              'on it will be removed. Continue?'),
    'preserve_off': ('"Preserve existing design" is off, so the item will be rebuilt from scratch and '
                     'your sketches and features on it will be removed. Continue?'),
    'base': 'This will replace the base with newly generated geometry. Continue?',
}


def run_edit(inputs, state, config):
    target = inputs.itemById('targetBin')
    if target.selectionCount != 1:
        raise RuntimeError('Select one Gridfinity bin or base to edit.')
    occurrence = adsk.fusion.Occurrence.cast(target.selection(0).entity)
    old = get_config(occurrence)
    if not old:
        raise RuntimeError('The selected component was not created by this add-in.')
    preserve_input = inputs.itemById('preserveDesign')
    preserve = bool(preserve_input.value) if preserve_input else False
    plan = cfg.plan_edit(old, config, preserve)
    action = plan['action']
    new = cfg.normalize(config)
    component = occurrence.component

    if action == cfg.NOTHING:
        util.ui().messageBox('Nothing changed.', 'Gridfinity')
        return

    if action == cfg.REGENERATE:
        if not util.confirm(REGENERATE_MESSAGES.get(plan['reason'], REGENERATE_MESSAGES['other']),
                            'Rebuild Gridfinity Item'):
            return
        # Rebuild where the old item was: same parent component, position and centre.
        parent, transform = bin_geometry.placement_of(occurrence)
        center = (0.0, 0.0)
        if not cfg.is_base(new) and not cfg.is_base(old):
            # Keep the lower-left corner where it was, the same as growing does.
            cx, cy = edit_ops.bin_center(component, old)
            (ow, od), (nw, nd) = cfg.bin_size_mm(old), cfg.bin_size_mm(new)
            center = (cx + (nw - ow) / 20.0, cy + (nd - od) / 20.0)
        run_create(component.parentDesign, new, parent, transform, center)
        occurrence.deleteMe()
        return

    if action == cfg.EXPAND:
        removed = len(managed.custom_features(component))
        message = ('Growing the footprint rebuilds the bin in place. All your sketches and construction '
                   'planes are kept, and sketches on the rim follow the new height.')
        if removed:
            message += ' {} of your modeled features (extrusions, cuts, fillets...) will be removed.'.format(removed)
        upright = len(edit_ops.side_wall_sketches(occurrence))
        if upright:
            message += (' {} sketch(es) drawn directly on a side wall will lose their wall and need '
                        're-attaching.'.format(upright))
        if not util.confirm(message + ' Continue?', 'Grow Gridfinity Bin'):
            return
        edit_ops.expand(occurrence, old, new)

    elif action == cfg.HEIGHT:
        old_top, new_top = bin_geometry.body_top_cm(old), bin_geometry.body_top_cm(new)
        growing = new_top > old_top
        affected = edit_ops.custom_features_above(component, old_top if growing else new_top,
                                                  include_boundary=growing)
        if affected:
            if not util.confirm(
                    'Changing the height will remove {} of your modeled features that sit on or cross the '
                    'old rim. Their sketches stay. The foot grid and magnets are kept. Continue?'.format(
                        len(affected)), 'Resize Bin Height'):
                return
        elif not growing and not util.confirm(
                'This shortens the walls and moves the stacking lip down. Your sketches and the foot '
                'grid are kept. Continue?', 'Decrease Bin Height'):
            return
        edit_ops.rebuild_height(occurrence, old, new, affected)

    elif action == cfg.IN_PLACE:
        edit_ops.update_in_place(occurrence, old, new, plan['bottom'], plan['interior'])

    component.name = bin_geometry.component_name(new)
    save_config(occurrence, new)


# ---------------------------------------------------------------------------
# Add-in start / stop
# ---------------------------------------------------------------------------
def _drop(panel, control_id):
    control = panel.controls.itemById(control_id) if panel else None
    if control:
        control.deleteMe()
    definition = util.ui().commandDefinitions.itemById(control_id)
    if definition:
        definition.deleteMe()


def _panel():
    workspace = util.ui().workspaces.itemById(C.WORKSPACE_ID)
    return workspace.toolbarPanels.itemById(C.PANEL_ID) if workspace else None


def start():
    panel = _panel()
    if not panel:
        raise RuntimeError('Could not find the Solid workspace Create panel.')
    resources = os.path.join(ADDIN_DIR, 'Resources')
    after = 'FusionHoleCommand'      # sit right after Hole, where the original's buttons were
    for command_id, name, tip, icons, editing in (
            (C.CREATE_ID, C.ADDIN_NAME, 'Create a Gridfinity bin or base.', 'GridfinityBinCreate', False),
            (C.EDIT_ID, 'Edit Gridfinity Item v2', 'Edit a saved Gridfinity bin or base.', 'GridfinityBinEdit', True)):
        _drop(panel, command_id)
        definition = util.ui().commandDefinitions.addButtonDefinition(
            command_id, name, tip, os.path.join(resources, icons))
        keep(definition.commandCreated, CommandCreated(editing), _app_handlers)
        try:
            control = panel.controls.addCommand(definition, after, False)
        except Exception:
            control = panel.controls.addCommand(definition)
        after = command_id
        # Show the buttons right on the toolbar, not only inside the Create dropdown.
        control.isPromotedByDefault = True
        control.isPromoted = True


def stop():
    panel = _panel()
    _drop(panel, C.CREATE_ID)
    _drop(panel, C.EDIT_ID)
    _dialog_handlers.clear()
    _app_handlers.clear()
