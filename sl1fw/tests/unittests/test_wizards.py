# This file is part of the SL1 firmware
# Copyright (C) 2020-2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import unittest
from shutil import copyfile
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from pathlib import Path
import pydbus
import toml

from sl1fw import defines
from sl1fw.configs.hw import HwConfig
from sl1fw.configs.runtime import RuntimeConfig
from sl1fw.errors.errors import UVTooDimm, UVTooBright, UVDeviationTooHigh
from sl1fw.hardware.printer_model import PrinterModel
from sl1fw.states.wizard import WizardState, WizardId
from sl1fw.tests.base import Sl1fwTestCase
from sl1fw.tests.mocks.hardware import Hardware
from sl1fw.tests.mocks.uv_meter import UVMeterMock
from sl1fw.wizard.actions import UserActionBroker
from sl1fw.wizard.checks.base import Check, WizardCheckType
from sl1fw.wizard.group import CheckGroup
from sl1fw.wizard.setup import Configuration, PlatformSetup, TankSetup
from sl1fw.wizard.wizard import Wizard
from sl1fw.wizard.wizard import serializer
from sl1fw.wizard.wizards.calibration import CalibrationWizard
from sl1fw.wizard.wizards.displaytest import DisplayTestWizard
from sl1fw.wizard.wizards.factory_reset import FactoryResetWizard, PackingWizard
from sl1fw.wizard.wizards.self_test import SelfTestWizard
from sl1fw.wizard.wizards.unboxing import CompleteUnboxingWizard, KitUnboxingWizard
from sl1fw.wizard.wizards.uv_calibration import UVCalibrationWizard


class TestGroup(CheckGroup):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setup_mock = AsyncMock()

    async def setup(self, actions: UserActionBroker):
        self.setup_mock(actions)


class TestWizardInfrastructure(Sl1fwTestCase):
    # pylint: disable=no-self-use

    def test_wizard_group_run(self):
        group = AsyncMock()
        group.checks = []
        # group.setup.return_value = None

        wizard = Wizard(WizardId.SELF_TEST, [group], Mock(), Mock())
        self.assertEqual(WizardState.INIT, wizard.state)
        wizard.start()
        wizard.join()

        self.assertEqual(WizardState.DONE, wizard.state)
        group.run.assert_called()
        group.run.assert_awaited()

    def test_wizard_failure(self):
        # pylint: disable = too-many-ancestors
        class Test(MagicMock, Check):
            async def async_task_run(self, actions: UserActionBroker):
                pass

            def __init__(self):
                MagicMock.__init__(self)
                Check.__init__(self, WizardCheckType.UNKNOWN, Mock(), [])

        check = Test()
        exception = Exception("Synthetic fail")
        task_body = AsyncMock()
        task_body.side_effect = exception
        check.async_task_run = task_body
        wizard = Wizard(WizardId.SELF_TEST, [TestGroup(Mock(), [check])], Mock(), Mock())
        wizard.start()
        wizard.join()

        self.assertEqual(WizardState.FAILED, wizard.state)
        self.assertEqual(exception, wizard.exception)

    def test_wizard_warning(self):
        warning = Warning("Warning")

        class Test(Check):
            async def async_task_run(self, actions: UserActionBroker):
                self.add_warning(warning)

            def __init__(self):
                super().__init__(WizardCheckType.UNKNOWN, Mock(), [])

        check = Test()
        wizard = Wizard(WizardId.SELF_TEST, [TestGroup(Mock(), [check])], Mock(), Mock())
        wizard.start()
        wizard.join()

        self.assertEqual(WizardState.DONE, wizard.state)
        self.assertIn(warning, wizard.warnings)

    def test_group_setup(self):
        test = TestGroup(Mock(), [])
        actions = Mock()
        asyncio.run(test.run(actions))
        test.setup_mock.assert_called()

    def test_check_execution(self):
        check = AsyncMock()
        actions = Mock()
        group = TestGroup(Mock(), [check])
        asyncio.run(group.run(actions))

        check.run.assert_called()

    def test_configuration_match(self):
        check = Mock()
        check.configuration = Configuration(TankSetup.UV, PlatformSetup.RESIN_TEST)

        with self.assertRaises(ValueError):
            TestGroup(Configuration(TankSetup.PRINT, PlatformSetup.PRINT), [check])

    def test_check_progress(self):
        class TestCheck(Check):
            async def async_task_run(self, actions: UserActionBroker):
                self.progress = 0.5

        check = TestCheck(WizardCheckType.UNKNOWN, Mock(), [])
        callback = Mock()
        callback.__name__ = "callback"
        check.data_changed.connect(lambda: callback(check.data["progress"]))

        asyncio.run(check.run(Mock(), Mock(), Mock()))

        callback.assert_any_call(0)
        callback.assert_any_call(0.5)
        callback.assert_any_call(1)


class TestWizardsBase(Sl1fwTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.exposure_image = Mock() # wizards use weakly-reference to exposure_image

    def test_display_test(self):
        wizard = DisplayTestWizard(Hardware(), self.exposure_image, RuntimeConfig())

        def on_state_changed():
            if wizard.state == WizardState.PREPARE_DISPLAY_TEST:
                wizard.prepare_displaytest_done()
            if wizard.state == WizardState.TEST_DISPLAY:
                wizard.report_display(True)

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)

    def test_display_test_fail(self):
        wizard = DisplayTestWizard(Hardware(), self.exposure_image, RuntimeConfig())

        def on_state_changed():
            if wizard.state == WizardState.PREPARE_DISPLAY_TEST:
                wizard.prepare_displaytest_done()
            if wizard.state == WizardState.TEST_DISPLAY:
                wizard.report_display(False)
            if wizard.state == WizardState.STOPPED:
                wizard.abort()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, expected_state=WizardState.FAILED)
        self.assertEqual("#10120", wizard.data["displaytest_exception"]["code"])

    def _run_wizard(self, wizard: Wizard, limit_s: int = 5, expected_state=WizardState.DONE):
        wizard.start()
        wizard.join(limit_s)

        while wizard.is_alive() and wizard.state not in WizardState.finished_states():
            if wizard.state == WizardState.STOPPED:
                wizard.abort()
            else:
                try:
                    wizard.cancel()
                except RuntimeError:
                    pass  # Wizard might have reached stopped in the meantime

        wizard.join(limit_s * 3)
        self.assertFalse(wizard.is_alive())
        self.assertEqual(expected_state, wizard.state)


class TestWizards(TestWizardsBase):
    def setUp(self) -> None:
        super().setUp()

        self.hw_config_file = self.TEMP_DIR / "reset_config.toml"
        self.hw_config_factory_file = self.TEMP_DIR / "reset_config_factory.toml"

        hw_config = HwConfig(self.hw_config_file, self.hw_config_factory_file, is_master=True,)
        self.hw = Hardware(hw_config)
        self.runtime_config = RuntimeConfig()
        self.exposure_image = Mock() # wizards use weakly-reference to exposure_image

        # Mock factory data
        defines.uvCalibDataPath = self.TEMP_DIR / defines.uvCalibDataFilename
        self.hw.config.uvPwm = 210
        copyfile(self.SAMPLES_DIR / "uvcalib_data-60.toml", defines.uvCalibDataPathFactory)
        copyfile(self.SAMPLES_DIR / "self_test_data.json", defines.factoryMountPoint / "self_test_data.json")

        # Setup files that are touched by packing wizard
        defines.apikeyFile = self.TEMP_DIR / "apikey"
        defines.apikeyFile.touch()
        defines.local_time_path = self.TEMP_DIR / "localtime"
        defines.local_time_path.touch()
        defines.slicerProfilesFile = self.TEMP_DIR / "slicer_profiles"
        defines.slicerProfilesFile.touch()
        defines.internalProjectPath = self.TEMP_DIR / "projects"
        defines.internalProjectPath.mkdir()
        (defines.internalProjectPath / "dummy_project.sl1").touch()
        defines.remoteConfig = self.TEMP_DIR / "remote_config"
        defines.remoteConfig.write_text("DUMMY TEXT")
        defines.factory_enable = self.TEMP_DIR / "factory"
        defines.factory_enable.touch()
        defines.serial_service_enabled = self.TEMP_DIR / "serial"
        defines.serial_service_enabled.touch()
        defines.ssh_service_enabled = self.TEMP_DIR / "ssh"
        defines.ssh_service_enabled.touch()
        defines.nginx_api_key = self.TEMP_DIR / "nginx_api_key"
        defines.nginx_http_digest = self.TEMP_DIR / "nginx_http_digest"
        defines.nginx_enabled = self.TEMP_DIR / "nginx_enabled"
        defines.nginx_api_key.touch()
        defines.nginx_http_digest.touch()
        defines.nginx_enabled.symlink_to(defines.nginx_http_digest)

        # Mock changed settings
        self.time_date.SetNTP(not self.time_date.DEFAULT_NTP, False)
        self.time_date.SetTimezone("Europe/Prague", False)
        self.locale.SetLocale("en_US.utf-8", False)

    def tearDown(self) -> None:
        del self.hw
        super().tearDown()

    def _run_wizard(self, wizard: Wizard, limit_s: int = 5, expected_state=WizardState.DONE):
        with patch("sl1fw.wizard.checks.factory_reset.copyfile"), patch(
            "sl1fw.wizard.checks.factory_reset.subprocess"
        ), patch("sl1fw.wizard.checks.factory_reset.ch_mode_owner"):
            super()._run_wizard(wizard, limit_s, expected_state)

    def test_self_test_success(self):
        self.hw.config.uvWarmUpTime = 0
        wizard = SelfTestWizard(self.hw, self.exposure_image, RuntimeConfig())

        def on_state_changed():
            if wizard.state == WizardState.PREPARE_WIZARD_PART_1:
                wizard.prepare_wizard_part_1_done()
            if wizard.state == WizardState.TEST_AUDIO:
                wizard.report_audio(True)
            if wizard.state == WizardState.TEST_DISPLAY:
                wizard.report_display(True)
            if wizard.state == WizardState.PREPARE_WIZARD_PART_2:
                wizard.prepare_wizard_part_2_done()
            if wizard.state == WizardState.PREPARE_WIZARD_PART_3:
                wizard.prepare_wizard_part_3_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)

        wizard_data_path = defines.configDir / wizard.get_data_filename()
        self.assertTrue(wizard_data_path.exists(), "Wizard data file exists")
        print(f"Wizard data:\n{wizard_data_path.read_text()}")
        with wizard_data_path.open("rt") as file:
            data = serializer.load(file)

        self.assertEqual("CZPX0819X009XC00151", data["a64SerialNo"])
        self.assertIn("osVersion", data)
        self.assertEqual("CZPX0619X678XC12345", data["mcSerialNo"])
        self.assertEqual("1.0.0", data["mcFwVersion"])
        self.assertEqual("6c", data["mcBoardRev"])

        self.assertEqual(96000, data["towerHeight"])
        self.assertEqual(4928, data["tiltHeight"])
        self.assertIn("uvPwm", data)

        self.assertListEqual([11203, 11203, 11203], data["wizardUvVoltageRow1"])
        self.assertListEqual([11203, 11203, 11203], data["wizardUvVoltageRow2"])
        self.assertListEqual([11203, 11203, 11203], data["wizardUvVoltageRow3"])
        self.assertListEqual(
            [self.hw.config.fan1Rpm, self.hw.config.fan2Rpm, self.hw.config.fan3Rpm], data["wizardFanRpm"],
        )
        self.assertEqual(46.7, data["wizardTempUvInit"])
        self.assertEqual(46.7, data["wizardTempUvWarm"])
        self.assertEqual(26.1, data["wizardTempAmbient"])
        self.assertEqual(53.5, data["wizardTempA64"])
        self.assertEqual(defines.resinWizardMaxVolume, data["wizardResinVolume"])
        self.assertEqual(0, data["towerSensitivity"])
        self._assert_final_state("showWizard", expected_value=False)

    def test_self_test_fail(self):
        self.hw.config.uvWarmUpTime = 0
        wizard = SelfTestWizard(self.hw, self.exposure_image, RuntimeConfig())

        def on_state_changed():
            if wizard.state == WizardState.PREPARE_WIZARD_PART_1:
                wizard.cancel()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, limit_s=1, expected_state=WizardState.CANCELED)
        self._assert_final_state("showWizard", expected_value=None)

    def _assert_final_state(self, item: str, expected_value: bool):
        hwConfig_path = Path(self.hw_config_file)
        self.assertTrue(hwConfig_path.exists(), "HwConfig file exists")
        with hwConfig_path.open("rt") as file:
            data = toml.load(file)
        if expected_value is None:
            self.assertRaises(KeyError, data.__getitem__, item)
        elif expected_value is False:
            self.assertFalse(data[item])
        else:
            self.assertTrue(data[item])

    def test_unboxing_complete(self):
        wizard = CompleteUnboxingWizard(self.hw, RuntimeConfig())

        def on_state_changed():
            if wizard.state == WizardState.REMOVE_SAFETY_STICKER:
                wizard.safety_sticker_removed()
            if wizard.state == WizardState.REMOVE_SIDE_FOAM:
                wizard.side_foam_removed()
            if wizard.state == WizardState.REMOVE_TANK_FOAM:
                wizard.tank_foam_removed()
            if wizard.state == WizardState.REMOVE_DISPLAY_FOIL:
                wizard.display_foil_removed()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)

    def test_unboxing_kit(self):
        wizard = KitUnboxingWizard(self.hw, RuntimeConfig())

        def on_state_changed():
            if wizard.state == WizardState.REMOVE_DISPLAY_FOIL:
                wizard.display_foil_removed()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)

    def test_packing_complete(self):
        self.runtime_config.factory_mode = True
        self.hw.boardData = ("TEST complete", False)
        self._run_wizard(PackingWizard(self.hw, self.runtime_config))
        self._check_factory_reset(unboxing=True, factory_mode=True)

    def test_packing_kit(self):
        self.runtime_config.factory_mode = True
        self.hw.boardData = ("TEST kit", True)
        self._run_wizard(PackingWizard(self.hw, self.runtime_config))
        self._check_factory_reset(unboxing=True, factory_mode=True)

    def test_factory_reset_complete(self):
        self.runtime_config.factory_mode = False
        self.hw.boardData = ("TEST kit", False)
        self._run_wizard(FactoryResetWizard(self.hw, self.runtime_config, True))
        self._check_factory_reset(unboxing=False, factory_mode=False)

    def test_factory_reset_kit(self):
        self.runtime_config.factory_mode = False
        self.hw.boardData = ("TEST kit", True)
        self._run_wizard(FactoryResetWizard(self.hw, self.runtime_config, True))
        self._check_factory_reset(unboxing=False, factory_mode=False)

    def _check_factory_reset(self, unboxing: bool, factory_mode: bool):
        # Assert factory reset was performed
        self.assertEqual(unboxing, self.hw.config.showUnboxing)
        self.assertFalse(defines.apikeyFile.exists(), "API-Key file deleted")
        self.assertFalse(defines.uvCalibDataPath.exists(), "User UV calibration data reset")

        self.assertFalse(defines.slicerProfilesFile.exists(), "Slicer profiles removed")

        self.assertEqual(
            factory_mode, bool(list(defines.internalProjectPath.glob("*"))), "Internal projects removed",
        )

        hw_config = HwConfig(self.hw_config_file)
        hw_config.read_file()
        self.assertTrue(hw_config.showUnboxing == unboxing, "config reset check")
        self.assertEqual(not factory_mode, defines.factory_enable.exists(), "factory is disabled check")
        self.assertFalse(defines.serial_service_enabled.exists(), "serial is disabled check")
        self.assertFalse(defines.ssh_service_enabled.exists(), "ssh is disabled check")
        self.assertEqual(
            pydbus.SystemBus().get("org.freedesktop.NetworkManager").ListConnections(), ["ethernet"],
        )  # all wifi connections deleted

        self.assertEqual(False, defines.remoteConfig.exists())
        self.assertTrue(self.hostname.hostname_set, "Hostname changed by factory reset")
        self.assertTrue(self.time_date.is_default_ntp(), "NTP reset to default")
        print(self.locale.Locale)
        self.assertTrue(self.locale.is_default(), "Locale set to default")

        # Local time should be actualy replaced by default,
        # but the copyfile is mocked. This only checks successful delete.
        self.assertFalse(defines.local_time_path.exists(), "Timezone reset to default")

    def test_calibration_success(self):
        wizard = CalibrationWizard(self.hw, RuntimeConfig())

        def on_state_changed():
            if wizard.state == WizardState.PREPARE_CALIBRATION_INSERT_PLATFORM_TANK:
                wizard.prepare_calibration_platform_tank_done()
            if wizard.state == WizardState.PREPARE_CALIBRATION_TILT_ALIGN:
                wizard.prepare_calibration_tilt_align_done()
            if wizard.state == WizardState.LEVEL_TILT:
                wizard.tilt_aligned()
            if wizard.state == WizardState.PREPARE_CALIBRATION_PLATFORM_ALIGN:
                wizard.prepare_calibration_platform_align_done()
            if wizard.state == WizardState.PREPARE_CALIBRATION_FINISH:
                wizard.prepare_calibration_finish_done()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard)
        self._assert_final_state(item="calibrated", expected_value=True)

    def test_calibration_fail(self):
        wizard = CalibrationWizard(self.hw, RuntimeConfig())

        def on_state_changed():
            if wizard.state == WizardState.PREPARE_CALIBRATION_INSERT_PLATFORM_TANK:
                wizard.cancel()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, limit_s=1, expected_state=WizardState.CANCELED)
        self._assert_final_state(item="calibrated", expected_value=None)

class TestUVCalibration(TestWizardsBase):
    def setUp(self) -> None:
        super().setUp()

        self.hw_config_file = self.TEMP_DIR / "reset_config.toml"
        self.hw_config_factory_file = self.TEMP_DIR / "reset_config_factory.toml"
        defines.counterLog = self.TEMP_DIR / "counter.log"

        hw_config = HwConfig(self.hw_config_file, self.hw_config_factory_file, is_master=True,)
        self.hw = Hardware(hw_config)
        self.runtime_config = RuntimeConfig()
        self.exposure_image = Mock()
        self.exposure_image.printer_model = PrinterModel.SL1
        self.uv_meter = UVMeterMock(self.hw)

    def tearDown(self) -> None:
        del self.hw
        del self.uv_meter
        super().tearDown()

    def test_uv_calibration_no_boost(self):
        with patch("sl1fw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(
                self.hw, self.exposure_image, self.runtime_config, False, False
            )
            self._run_uv_calibration(wizard)

        # Check wizard data
        self.assertFalse(wizard.data["boost"])
        self.assertEqual("CZPX0819X009XC00151", wizard.data["a64SerialNo"])
        self.assertEqual("CZPX0619X678XC12345", wizard.data["mcSerialNo"])
        self.assertEqual("6c", wizard.data["mcBoardRev"])
        self.assertEqual(6912, wizard.data["uvLedCounter_s"])
        self.assertEqual(3600, wizard.data["displayCounter_s"])
        self.assertEqual(0, wizard.data["uvSensorType"])
        self.assertListEqual(
            [140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0, 140.0],
            wizard.data["uvSensorData"],
        )
        self.assertEqual(140.0, wizard.data["uvMean"])
        self.assertEqual(0.0, wizard.data["uvStdDev"])
        self.assertEqual(140.0, wizard.data["uvMinValue"])
        self.assertEqual(140.0, wizard.data["uvMaxValue"])
        self.assertEqual(200, wizard.data["uvFoundPwm"])
        self._assert_final_uv_pwm(self.hw.printer_model.calibration_parameters(True).min_pwm)

    def test_uv_calibration_boost(self):
        with patch("sl1fw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(
                self.hw, self.exposure_image, self.runtime_config, False, False
            )
            self.uv_meter.multiplier = 0.79
            self._run_uv_calibration(wizard)
            self.assertTrue(wizard.data["boost"])  # Boosted as led+display too weak
            self.assertFalse(defines.counterLog.exists())  # Counter log not written as nothing was reset
        self._assert_final_uv_pwm(self.hw.printer_model.calibration_parameters(True).min_pwm)

    def test_uv_calibration_boost_difference(self):
        with patch("sl1fw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            self.hw.config.data_factory_values["uvPwm"] = 100
            wizard = UVCalibrationWizard(
                self.hw, self.exposure_image, self.runtime_config, False, False
            )
            self.uv_meter.multiplier = 0.85
            self._run_uv_calibration(wizard)
            self.assertTrue(wizard.data["boost"])  # Boosted as PWM differs too much from previous setup
        self._assert_final_uv_pwm(self.hw.printer_model.calibration_parameters(True).min_pwm)

    def test_uv_calibration_no_boost_replace_display(self):
        with patch("sl1fw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            self.hw.config.data_factory_values["uvPwm"] = 100
            wizard = UVCalibrationWizard(self.hw, self.exposure_image, self.runtime_config, True, False)
            self.uv_meter.multiplier = 0.85
            self._run_uv_calibration(wizard)
            self.assertFalse(wizard.data["boost"])  # Not boosted despite difference from previous setup, setup changed

            self.assertEqual(0, self.hw.getUvStatistics()[1])  # Display replaced
            self.assertEqual(6912, self.hw.getUvStatistics()[0])  # UV LED stays
            self.assertTrue(defines.counterLog.exists())  # Counter log written as display was replaced
            with defines.counterLog.open("r") as f:
                log = toml.load(f)
                for data in log.values():
                    # Log record contains original counter values
                    self.assertEqual(6912, data["uvLed_seconds"])
                    self.assertEqual(3600, data["display_seconds"])
        self._assert_final_uv_pwm(self.hw.printer_model.calibration_parameters(True).min_pwm)

    def test_uv_calibration_boost_replace_led(self):
        with patch("sl1fw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(self.hw, self.exposure_image, self.runtime_config, False, True)
            self.uv_meter.multiplier = 0.75
            self._run_uv_calibration(wizard)
            self.assertTrue(wizard.data["boost"])  # Too weak needs boost even when changed

            self.assertEqual(3600, self.hw.getUvStatistics()[1])  # Display stays
            self.assertEqual(0, self.hw.getUvStatistics()[0])  # UV LED replaced
            self.assertTrue(defines.counterLog.exists())  # Counter log written as UV LED was replaced
        self._assert_final_uv_pwm(self.hw.printer_model.calibration_parameters(True).min_pwm)

    def test_uv_calibration_dim(self):
        with patch("sl1fw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(
                self.hw, self.exposure_image, self.runtime_config, False, False
            )
            self.uv_meter.multiplier = 0.1
            self._run_uv_calibration(wizard, expected_state=WizardState.FAILED)
            self.assertIsInstance(wizard.exception, UVTooDimm)
        self._assert_final_uv_pwm(0)

    def test_uv_calibration_bright(self):
        with patch("sl1fw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(
                self.hw, self.exposure_image, self.runtime_config, False, False
            )
            self.uv_meter.multiplier = 10
            self._run_uv_calibration(wizard, expected_state=WizardState.FAILED)
            self.assertIsInstance(wizard.exception, UVTooBright)
        self._assert_final_uv_pwm(0)

    def test_uv_calibration_dev(self):
        with patch("sl1fw.wizard.wizards.uv_calibration.UvLedMeterMulti", self.uv_meter):
            wizard = UVCalibrationWizard(
                self.hw, self.exposure_image, self.runtime_config, False, False
            )
            self.uv_meter.noise = 70
            self._run_uv_calibration(wizard, expected_state=WizardState.FAILED)
            self.assertIsInstance(wizard.exception, UVDeviationTooHigh)
        self._assert_final_uv_pwm(0)

    def _run_uv_calibration(self, wizard: UVCalibrationWizard, expected_state=WizardState.DONE):
        def on_state_changed():
            if wizard.state == WizardState.TEST_DISPLAY:
                wizard.report_display(True)
            if wizard.state == WizardState.UV_CALIBRATION_PREPARE:
                wizard.uv_calibration_prepared()
            if wizard.state == WizardState.UV_CALIBRATION_PLACE_UV_METER:
                wizard.uv_meter_placed()
            if wizard.state == WizardState.UV_CALIBRATION_APPLY_RESULTS:
                wizard.uv_apply_result()
            if wizard.state == WizardState.STOPPED:
                wizard.abort()

        wizard.state_changed.connect(on_state_changed)
        self._run_wizard(wizard, limit_s=15, expected_state=expected_state)

    def _assert_final_uv_pwm(self, expected_value: int):
        hwConfig_path = Path(self.hw_config_file)
        self.assertTrue(hwConfig_path.exists(), "HwConfig file exists")
        with hwConfig_path.open("rt") as file:
            data = toml.load(file)
        if expected_value == 0:
            self.assertRaises(KeyError, data.__getitem__, "uvPwm")
        else:
            self.assertGreater(data["uvPwm"], expected_value)

if __name__ == "__main__":
    unittest.main()
