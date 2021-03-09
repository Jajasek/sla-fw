# This file is part of the SL1 firmware
# Copyright (C) 2020-2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Optional, Dict, Any

from sl1fw.functions.checks import resin_sensor
from sl1fw.libHardware import Hardware
from sl1fw.wizard.actions import UserActionBroker
from sl1fw.wizard.checks.base import WizardCheckType, SyncDangerousCheck
from sl1fw.wizard.setup import Configuration, TankSetup, PlatformSetup, Resource


class ResinSensorTest(SyncDangerousCheck):
    def __init__(self, hw: Hardware):
        super().__init__(
            hw,
            WizardCheckType.RESIN_SENSOR,
            Configuration(TankSetup.PRINT, PlatformSetup.RESIN_TEST),
            [Resource.TOWER, Resource.TOWER_DOWN],
        )
        self._hw = hw

        self.wizard_resin_volume_ml: Optional[float] = None

    def task_run(self, actions: UserActionBroker):
        self.wait_cover_closed_sync()
        with actions.led_warn:
            self.wizard_resin_volume_ml = resin_sensor(self._hw, self._logger)

    def get_result_data(self) -> Dict[str, Any]:
        return {"wizardResinVolume": self.wizard_resin_volume_ml}
