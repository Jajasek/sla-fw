# This file is part of the SL1 firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import deque
from dataclasses import dataclass
from typing import Optional, Callable

from PySignal import Signal

from sl1fw.libHardware import Hardware
from sl1fw.states.wizard import WizardState


@dataclass
class PushState:
    state: WizardState


class UserAction:
    def __init__(self):
        self.callback: Optional[Callable] = None

    def __call__(self, *args, **kwargs):
        if not self.callback:
            raise KeyError("User action not registered")
        self.callback(*args, **kwargs)

    def register_callback(self, callback: Callable):
        if self.callback:
            raise ValueError("Callback already registered")
        self.callback = callback

    def unregister_callback(self):
        self.callback = None


class WarnLevelCounter:
    def __init__(self, hw: Hardware):
        self._hw = hw
        self._level_counter = 0

    def __enter__(self):
        self._level_counter += 1
        self._hw.powerLed("warn")

    def __exit__(self, *_):
        assert self._level_counter > 0
        self._level_counter -= 1
        if self._level_counter == 0:
            self._hw.powerLed("normal")


class UserActionBroker:
    # pylint: disable=too-many-instance-attributes
    def __init__(self, hw: Hardware):
        self._states = deque()
        self.states_changed = Signal()
        self._hw = hw
        self._warn_level_counter = WarnLevelCounter(hw)

        self.prepare_calibration_platform_insert_done = UserAction()
        self.prepare_calibration_platform_align_done = UserAction()
        self.prepare_calibration_tank_placement_done = UserAction()
        self.prepare_calibration_tilt_align_done = UserAction()
        self.prepare_calibration_finish_done = UserAction()
        self.prepare_displaytest_done = UserAction()

        self.report_display = UserAction()
        self.report_audio = UserAction()
        self.tilt_move = UserAction()
        self.tilt_aligned = UserAction()

        # Unboxing
        self.safety_sticker_removed = UserAction()
        self.side_foam_removed = UserAction()
        self.tank_foam_removed = UserAction()
        self.display_foil_removed = UserAction()

        # Wizard
        self.prepare_wizard_part_1_done = UserAction()
        self.prepare_wizard_part_2_done = UserAction()
        self.prepare_wizard_part_3_done = UserAction()

    def push_state(self, state: PushState):
        self._states.append(state)
        self.states_changed.emit()

    def drop_state(self, state: PushState):
        self._states.remove(state)
        self.states_changed.emit()

    @property
    def led_warn(self):
        return self._warn_level_counter