"""Gridfinity bins and baseplates for Fusion 360 (v2).

Entry point only; the work is in the gf package:
  constants.py      every dimension and ID
  config.py         saved settings, validation, edit planning (no Fusion imports)
  ui.py             the dialog
  commands.py       button handlers, create and edit flow
  bin_geometry.py   bin modelling
  base_geometry.py  baseplate modelling
  edit_ops.py       edits that keep your sketches (grow, height, in-place)
  managed.py        tells add-in sketches/features apart from yours
  util.py           small Fusion helpers
"""

import sys
import traceback

import adsk.core

# Fusion keeps sub-modules cached between Stop and Run, so edits to gf/*.py would
# not load until Fusion restarts. Drop the cached copies so Run always loads fresh.
_prefix = (__package__ or __name__) + '.gf'   # Fusion names the add-in module itself as the package
for _name in [n for n in list(sys.modules) if n == _prefix or n.startswith(_prefix + '.')]:
    del sys.modules[_name]

from .gf import commands  # noqa: E402


def run(context):
    try:
        commands.start()
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            'Gridfinity v2 could not start:\n{}'.format(traceback.format_exc()))


def stop(context):
    try:
        commands.stop()
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(
            'Gridfinity v2 could not stop cleanly:\n{}'.format(traceback.format_exc()))
