# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminIntValue, AdminBoolValue, AdminFixedValue
from slafw.admin.menus.settings.base import SettingsMenu
from slafw.admin.menus.hardware.profiles import Profiles


class ExposureSettingsMenu(SettingsMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control, printer)
        self.add_items(
            (
                AdminAction(
                    "Layer change profiles",
                    lambda: self.enter(Profiles(self._control, printer, printer.layer_profiles)),
                    "statistics_color"
                 ),
                AdminAction(
                    "Exposure profiles",
                    lambda: self.enter(Profiles(self._control, printer, printer.exposure_profiles)),
                    "uv_calibration"
                 ),
                AdminFixedValue.from_value(
                    "Force slow tilt height [mm]",
                    self._temp,
                    "forceSlowTiltHeight",
                    10000,
                    6,
                    "move_resin_tank_color"),
                AdminIntValue.from_value(
                    "Limit for fast tilt [%]",
                    self._temp,
                    "limit4fast",
                    1,
                    "limit_color"),
                AdminBoolValue.from_value(
                    "Up&Down UV on",
                    self._temp,
                    "upAndDownUvOn",
                    "tower_offset_color"),
                AdminIntValue.from_value(
                    "Up&down wait [s]",
                    self._temp,
                    "upanddownwait",
                    1,
                    "exposure_times_color"),
                AdminIntValue.from_value(
                    "Up&down every n-th layer",
                    self._temp,
                    "upanddowneverylayer",
                    1,
                    "tower_offset_color"),
                AdminFixedValue.from_value(
                    "Up&down Z offset [mm]",
                    self._temp,
                    "up_and_down_z_offset_nm",
                    1,
                    6,
                    "calibration_color"),
                AdminFixedValue.from_value(
                    "Up&down exposure compensation [s]",
                    self._temp,
                    "upAndDownExpoComp",
                    1,
                    1,
                    "exposure_times_color"),
            )
        )
