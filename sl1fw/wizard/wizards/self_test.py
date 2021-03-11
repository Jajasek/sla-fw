# This file is part of the SL1 firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Iterable

from sl1fw.configs.hw import HwConfig
from sl1fw.configs.runtime import RuntimeConfig
from sl1fw.functions.system import hw_all_off
from sl1fw.libHardware import Hardware
from sl1fw.image.exposure_image import ExposureImage
from sl1fw.states.wizard import WizardId
from sl1fw.states.wizard import WizardState
from sl1fw.wizard.actions import UserActionBroker
from sl1fw.wizard.checks.calibration_info import CalibrationInfo
from sl1fw.wizard.checks.display import DisplayTest
from sl1fw.wizard.checks.resin import ResinSensorTest
from sl1fw.wizard.checks.sn import SerialNumberTest
from sl1fw.wizard.checks.speaker import SpeakerTest
from sl1fw.wizard.checks.sysinfo import SystemInfoTest
from sl1fw.wizard.checks.temperature import TemperatureTest
from sl1fw.wizard.checks.tilt import TiltRangeTest, TiltHomeTest
from sl1fw.wizard.checks.tower import TowerHomeTest, TowerRangeTest
from sl1fw.wizard.checks.uvfans import UVFansTest
from sl1fw.wizard.checks.uvleds import UVLEDsTest
from sl1fw.wizard.group import CheckGroup
from sl1fw.wizard.setup import Configuration, TankSetup, PlatformSetup
from sl1fw.wizard.wizard import Wizard


class SelfTestPart1CheckGroup(CheckGroup):
    def __init__(self, hw: Hardware, hw_config: HwConfig, exposure_image: ExposureImage, runtime_config: RuntimeConfig):
        super().__init__(
            Configuration(TankSetup.REMOVED, PlatformSetup.PRINT),
            [
                SerialNumberTest(hw),
                SystemInfoTest(hw),
                TemperatureTest(hw),
                SpeakerTest(),
                TiltHomeTest(hw),
                TiltRangeTest(hw),
                TowerHomeTest(hw, hw_config),
                UVLEDsTest(hw, hw_config),
                UVFansTest(hw, hw_config),
                DisplayTest(hw, exposure_image, runtime_config),
                CalibrationInfo(hw_config),
            ],
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.prepare_wizard_part_1_done, WizardState.PREPARE_WIZARD_PART_1)


class SelfTestPart2CheckGroup(CheckGroup):
    def __init__(self, hw: Hardware, hw_config: HwConfig):
        super().__init__(
            Configuration(TankSetup.PRINT, PlatformSetup.RESIN_TEST),
            [
                ResinSensorTest(hw, hw_config)
            ]
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.prepare_wizard_part_2_done, WizardState.PREPARE_WIZARD_PART_2)


class SelfTestPart3CheckGroup(CheckGroup):
    def __init__(self, hw: Hardware, hw_config: HwConfig):
        super().__init__(
            Configuration(TankSetup.PRINT, PlatformSetup.PRINT),
            [
                TowerRangeTest(hw, hw_config)
            ]
        )

    async def setup(self, actions: UserActionBroker):
        await self.wait_for_user(actions, actions.prepare_wizard_part_3_done, WizardState.PREPARE_WIZARD_PART_3)


class SelfTestWizard(Wizard):
    def __init__(self, hw: Hardware, hw_config: HwConfig, exposure_image: ExposureImage, runtime_config: RuntimeConfig):
        super().__init__(
            WizardId.SELF_TEST,
            [
                SelfTestPart1CheckGroup(hw, hw_config, exposure_image, runtime_config),
                SelfTestPart2CheckGroup(hw, hw_config),
                SelfTestPart3CheckGroup(hw, hw_config),
            ],
            hw,
            exposure_image,
            runtime_config,
        )
        self._exposure_image = exposure_image

    @property
    def name(self) -> str:
        return "self_test"

    @classmethod
    def get_alt_names(cls) -> Iterable[str]:
        names = ["wizard_data.toml", "thewizard_data.toml", "wizard_data"]
        names.extend(super().get_alt_names())
        return names

    def run(self):
        try:
            super().run()
        except Exception:
            hw_all_off(self._hw, self._exposure_image)
            raise