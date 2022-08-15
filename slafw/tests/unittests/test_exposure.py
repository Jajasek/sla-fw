# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from pathlib import Path
from time import sleep
from typing import Optional

from unittest.mock import Mock, patch, MagicMock, AsyncMock, call

from slafw.tests.base import SlafwTestCaseDBus, RefCheckTestCase
from slafw.hardware.printer_model import PrinterModel
from slafw.image.exposure_image import ExposureImage
from slafw import defines
from slafw.errors.errors import (
    NotUVCalibrated,
    ResinTooLow,
    ProjectErrorCantRead,
    TiltHomeFailed, WarningEscalation,
)
from slafw.errors.warnings import PrintingDirectlyFromMedia, ResinNotEnough
from slafw.configs.runtime import RuntimeConfig
from slafw.configs.unit import Nm
from slafw.exposure.exposure import Exposure
from slafw.states.exposure import ExposureState
from slafw.tests.mocks.hardware import HardwareMock
from slafw.project.project import ExposureUserProfile


def change_dir(path: str):
    return Path(defines.previousPrints) / Path(path).name

def setupHw() -> HardwareMock:
    hw = HardwareMock(printer_model = PrinterModel.SL1)
    hw.connect()
    hw.start()
    hw.config.uvPwm = 250
    hw.config.calibrated = True
    return hw


class TestExposure(SlafwTestCaseDBus, RefCheckTestCase):
    PROJECT = str(SlafwTestCaseDBus.SAMPLES_DIR / "numbers.sl1")
    PROJECT_LAYER_CHANGE = str(SlafwTestCaseDBus.SAMPLES_DIR / "layer_change.sl1")
    PROJECT_LAYER_CHANGE_SAFE = str(SlafwTestCaseDBus.SAMPLES_DIR / "layer_change_safe_profile.sl1")
    BROKEN_EMPTY_PROJECT = str(SlafwTestCaseDBus.SAMPLES_DIR / "empty_file.sl1")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exposure: Optional[Exposure] = None

    def setUp(self):
        super().setUp()
        defines.statsData = str(self.TEMP_DIR / "stats.toml")
        defines.previousPrints = str(self.TEMP_DIR)
        defines.lastProjectHwConfig = change_dir(defines.lastProjectHwConfig)
        defines.lastProjectFactoryFile = change_dir(defines.lastProjectFactoryFile)
        defines.lastProjectConfigFile = change_dir(defines.lastProjectConfigFile)
        defines.lastProjectPickler = change_dir(defines.lastProjectPickler)

        self.hw = setupHw()
        self.runtime_config = RuntimeConfig()
        self.exposure_image = Mock()
        self.exposure_image.__class__ = ExposureImage
        self.exposure_image.__reduce__ = lambda x: (Mock, ())
        self.exposure_image.sync_preloader.return_value = 100

    def tearDown(self):
        self.hw.exit()
        super().tearDown()

    def test_exposure_init_not_calibrated(self):
        hw = HardwareMock(printer_model = PrinterModel.SL1)
        hw.connect()
        hw.start()
        with self.assertRaises(NotUVCalibrated):
            exposure = Exposure(0, hw, self.exposure_image, self.runtime_config)
            exposure.read_project(TestExposure.PROJECT)

    def test_exposure_init(self):
        exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config)
        exposure.read_project(TestExposure.PROJECT)

    def test_exposure_load(self):
        exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config)
        exposure.read_project(TestExposure.PROJECT)
        exposure.startProject()

    def test_exposure_start_stop(self):
        exposure = self._run_exposure(self.hw)
        self.assertNotEqual(exposure.state, ExposureState.FAILURE)
        self.assertIsNone(exposure.warning)

    def test_resin_enough(self):
        hw = setupHw()
        hw.get_resin_volume_async = AsyncMock(return_value = defines.resinMaxVolume)
        exposure = self._run_exposure(hw)
        self.assertNotEqual(exposure.state, ExposureState.FAILURE)
        self.assertIsNone(exposure.warning)

    def test_resin_warning(self):
        hw = setupHw()
        hw.get_resin_volume_async = AsyncMock(return_value = defines.resinMinVolume + 0.1)
        exposure = self._run_exposure(hw)
        self.assertIsInstance(exposure.fatal_error, WarningEscalation)
        self.assertIsInstance(exposure.fatal_error.warning, ResinNotEnough)  # pylint: disable=no-member

    def test_resin_error(self):
        hw = setupHw()
        hw.get_resin_volume_async = AsyncMock(return_value = defines.resinMinVolume - 0.1)
        exposure = self._run_exposure(hw)
        self.assertIsInstance(exposure.fatal_error, ResinTooLow)

    def test_broken_empty_project(self):
        exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config)
        with self.assertRaises(ProjectErrorCantRead):
            exposure.read_project(self.BROKEN_EMPTY_PROJECT)
        self.assertIsInstance(exposure.fatal_error, ProjectErrorCantRead)

    def test_stuck_recovery_success(self):
        hw = setupHw()
        hw.tilt.layer_down_wait = MagicMock(side_effect=TiltHomeFailed())
        exposure = self._start_exposure(hw)

        for i in range(30):
            print(f"Waiting for exposure {i}, state: ", exposure.state)
            if exposure.state == ExposureState.CHECK_WARNING:
                print(exposure.warning)
                if isinstance(exposure.warning, PrintingDirectlyFromMedia):
                    exposure.confirm_print_warning()
                else:
                    exposure.reject_print_warning()
            if exposure.state in ExposureState.finished_states():
                self._exposure_check(exposure)
                self.assertEqual(exposure.state, ExposureState.FINISHED)
                return
            if exposure.state == ExposureState.STUCK:
                hw.tilt.layer_down_wait = None
                exposure.doContinue()
            if exposure.state == ExposureState.POUR_IN_RESIN:
                exposure.confirm_resin_in()
            sleep(1)

        raise TimeoutError("Waiting for exposure failed")

    def test_stuck_recovery_fail(self):
        hw = setupHw()
        hw.tilt.layer_down_wait = MagicMock(side_effect=TiltHomeFailed())
        exposure = self._start_exposure(hw)

        for i in range(30):
            print(f"Waiting for exposure {i}, state: ", exposure.state)
            if exposure.state == ExposureState.CHECK_WARNING:
                print(exposure.warning)
                if isinstance(exposure.warning, PrintingDirectlyFromMedia):
                    exposure.confirm_print_warning()
                else:
                    exposure.reject_print_warning()
            if exposure.state in ExposureState.finished_states():
                self._exposure_check(exposure)
                self.assertEqual(exposure.state, ExposureState.FAILURE)
                return
            if exposure.state == ExposureState.STUCK:
                hw.tilt.sync_ensure = MagicMock(side_effect=TiltHomeFailed())
                exposure.doContinue()
            if exposure.state == ExposureState.POUR_IN_RESIN:
                exposure.confirm_resin_in()
            sleep(1)

        raise TimeoutError("Waiting for exposure failed")

    def test_resin_refilled(self):
        hw = setupHw()
        fake_resin_volume = 100.0
        hw.get_resin_volume_async = AsyncMock(return_value = fake_resin_volume)
        exposure = self._start_exposure(hw)
        feedme_done = False

        for i in range(60):
            print(f"Waiting for exposure {i}, state: ", exposure.state)
            if exposure.state == ExposureState.PRINTING:
                if not feedme_done:
                    self.assertLess(exposure.resin_volume, defines.resinMaxVolume)
                    exposure.doFeedMe()
                    feedme_done = True
                else:
                    self.assertEqual(exposure.resin_volume, defines.resinMaxVolume)
            if exposure.state == ExposureState.FEED_ME:
                exposure.doContinue()
            if exposure.state in ExposureState.finished_states():
                self.assertNotEqual(exposure.state, ExposureState.FAILURE)
                return
            if exposure.state == ExposureState.POUR_IN_RESIN:
                exposure.confirm_resin_in()
            sleep(0.5)

        raise TimeoutError("Waiting for exposure failed")

    def test_resin_not_refilled(self):
        hw = setupHw()
        fake_resin_volume = 100.0
        hw.get_resin_volume.return_value = fake_resin_volume
        exposure = self._start_exposure(hw)
        feedme_done = False

        for i in range(60):
            print(f"Waiting for exposure {i}, state: ", exposure.state)
            if exposure.state == ExposureState.PRINTING:
                if not feedme_done:
                    exposure.doFeedMe()
                    feedme_done = True
                else:
                    self.assertLessEqual(fake_resin_volume, exposure.resin_volume)
            if exposure.state == ExposureState.FEED_ME:
                exposure.doBack()
            if exposure.state == ExposureState.POUR_IN_RESIN:
                exposure.confirm_resin_in()
            if exposure.state in ExposureState.finished_states():
                self.assertNotEqual(exposure.state, ExposureState.FAILURE)
                return
            sleep(0.5)

        raise TimeoutError("Waiting for exposure failed")

    def test_exposure_force_slow_tilt(self):
        defines.livePreviewImage = str(self.TEMP_DIR / "live.png")
        defines.displayUsageData = str(self.TEMP_DIR / "display_usage.npz")
        hw = setupHw()
        print(hw.config.limit4fast)
        hw.config.limit4fast = 45
        exposure_image = ExposureImage(hw)
        exposure_image.start()

        hw.config.forceSlowTiltHeight = 0  # do not force any extra slow tilts
        exposure = self._run_exposure(hw, TestExposure.PROJECT_LAYER_CHANGE, exposure_image)
        self.assertEqual(exposure.state, ExposureState.FINISHED)
        # 13 slow layers at beginning + 4 large layers in project
        self.assertEqual(exposure.slow_layers_done, 13 + 4)

        hw.config.forceSlowTiltHeight = 100000  # 100 um -> force 2 slow layers
        exposure = self._run_exposure(hw, TestExposure.PROJECT_LAYER_CHANGE, exposure_image)
        self.assertEqual(exposure.state, ExposureState.FINISHED)
        # 13 slow layers at beginning + 4 large layers in project + 4 layers after area change
        self.assertEqual(exposure.slow_layers_done, 13 + 4 + 4)

    def test_exposure_user_profile(self):
        self.hw.config.limit4fast = 100
        exposure = self._run_exposure(self.hw, TestExposure.PROJECT_LAYER_CHANGE)
        self.assertEqual(exposure.state, ExposureState.FINISHED)
        # 13 slow layers at beginning
        self.assertEqual(exposure.slow_layers_done, 13)
        self.assertEqual(205040, exposure.estimate_total_time_ms())

        defines.exposure_safe_delay_before = 0.1    # 0.01 s
        exposure = self._run_exposure(self.hw, TestExposure.PROJECT_LAYER_CHANGE_SAFE)
        self.assertEqual(exposure.state, ExposureState.FINISHED)
        self.assertEqual(exposure.slow_layers_done, exposure.project.total_layers)
        delay_time = exposure.project.total_layers * defines.exposure_safe_delay_before * 100
        force_slow_time = exposure.project._layers_fast * (self.hw.config.tiltSlowTime - self.hw.config.tiltFastTime)\
                          * 1000  # pylint: disable = protected-access
        self.assertEqual(201040 + delay_time + force_slow_time, exposure.estimate_total_time_ms())

    def _start_exposure(self, hw, project = None, expo_img = None) -> Exposure:
        if project is None:
            project = TestExposure.PROJECT
        if expo_img is None:
            expo_img = self.exposure_image
        exposure = Exposure(0, hw, expo_img, self.runtime_config)
        exposure.read_project(project)
        exposure.startProject()
        exposure.confirm_print_start()
        return exposure

    def _run_exposure(self, hw, project = None, expo_img = None) -> Exposure:
        exposure = self._start_exposure(hw, project, expo_img)

        for i in range(50):
            print(f"Waiting for exposure {i}, state: ", exposure.state)
            if exposure.state == ExposureState.CHECK_WARNING:
                print(exposure.warning)
                if isinstance(exposure.warning, PrintingDirectlyFromMedia):
                    exposure.confirm_print_warning()
                else:
                    exposure.reject_print_warning()
            if exposure.state in ExposureState.finished_states():
                return self._exposure_check(exposure)
            if exposure.state == ExposureState.POUR_IN_RESIN:
                exposure.confirm_resin_in()
            sleep(1)

        raise TimeoutError("Waiting for exposure failed")

    @staticmethod
    def _exposure_check(exposure: Exposure):
        print("Running exposure check")
        if exposure.state not in ExposureState.finished_states():
            exposure.doExitPrint()
        exposure.waitDone()
        return exposure


class TestLayers(SlafwTestCaseDBus):
    PROJECT_LAYER_CHANGE = str(SlafwTestCaseDBus.SAMPLES_DIR / "layer_change.sl1")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exposure: Optional[Exposure] = None
        self.sleep_mock = None

    def setUp(self):
        super().setUp()
        defines.statsData = str(self.TEMP_DIR / "stats.toml")
        defines.previousPrints = str(self.TEMP_DIR)
        defines.lastProjectHwConfig = change_dir(defines.lastProjectHwConfig)
        defines.lastProjectFactoryFile = change_dir(defines.lastProjectFactoryFile)
        defines.lastProjectConfigFile = change_dir(defines.lastProjectConfigFile)
        defines.lastProjectPickler = change_dir(defines.lastProjectPickler)

        self.hw = setupHw()
        self.runtime_config = RuntimeConfig()
        self.exposure_image = Mock()
        self.exposure_image.__class__ = ExposureImage
        self.exposure_image.__reduce__ = lambda x: (Mock, ())
        self.exposure_image.sync_preloader.return_value = 100

        self.hw.tower.move_ensure = MagicMock()
        self.hw.tilt.layer_up_wait = MagicMock()
        self.hw.tilt.layer_down_wait = MagicMock()
        self.exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config)
        self.exposure.read_project(TestExposure.PROJECT_LAYER_CHANGE)
        self.exposure.startProject()

    def tearDown(self):
        self.hw.exit()
        super().tearDown()

    @patch("slafw.exposure.exposure.sleep")
    def test_layer_moves(self, sleep_mock):
        self.sleep_mock = sleep_mock
        # verify "input" parameters
        self.assertTrue(self.hw.config.tilt)
        self.assertEqual(Nm(50000), self.hw.config.calib_tower_offset_nm)
        self.assertEqual(0, self.hw.config.delayBeforeExposure)
        self.assertEqual(0, self.hw.config.delayAfterExposure)
        self.assertEqual(5, self.hw.config.stirringDelay)
        self.assertEqual(1290240, self.hw.white_pixels_threshold)
        self.assertEqual(13, self.exposure.project.first_slow_layers)

        # DEFAULT profile
        expected_results = {
            "start_inside" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(1.0), call(100.0)],
            },
            "start_last" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.DEFAULT)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(False)],
                "sleep" : [call(1.0), call(100.0)],
            },
            "start_outside" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.DEFAULT)],
#                "tilt_down_calls" : [call(TiltSpeed.DEFAULT)],
                "tilt_up_calls" : [call(False)],
                "tilt_down_calls" : [call(False)],
                "sleep" : [call(100.0)]
            },
            "big_first" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.DEFAULT)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(False)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(100.0)],
            },
            "big_inside" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(1.0), call(100.0)],
            },
            "big_last" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.DEFAULT)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(False)],
                "sleep" : [call(1.0), call(100.0)],
            },
            "big_outside" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.DEFAULT)],
#                "tilt_down_calls" : [call(TiltSpeed.DEFAULT)],
                "tilt_up_calls" : [call(False)],
                "tilt_down_calls" : [call(False)],
                "sleep" : [call(100.0)]
            },
        }
        self._check_all_layer_variants(ExposureUserProfile.DEFAULT, expected_results)

        # SAFE profile
        expected_results = {
            "start_inside" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(3.0), call(100.0)],
            },
            "start_last" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(3.0), call(100.0)],
            },
            "start_outside" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(3.0), call(100.0)],
            },
            "big_first" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(3.0), call(100.0)],
            },
            "big_inside" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(3.0), call(100.0)],
            },
            "big_last" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(3.0), call(100.0)],
            },
            "big_outside" : {
                "tower_move_calls" : [call(Nm(50000))],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SLOW)],
                "tilt_up_calls" : [call(True)],
                "tilt_down_calls" : [call(True)],
                "sleep" : [call(3.0), call(100.0)],
            },
        }
#        self._check_all_layer_variants(ExposureUserProfile.SAFE, expected_results)

        # HIGH_VISCOSITY profile
        expected_results = {
            "start_inside" : {
                "tower_move_calls" : [call(4040), call(40)],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SUPERSLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SUPERSLOW)],
                "sleep" : [call(3.5), call(100.0)],
            },
            "start_last" : {
                "tower_move_calls" : [call(4040), call(40)],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SUPERSLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SUPERSLOW)],
                "sleep" : [call(3.5), call(100.0)],
            },
            "start_outside" : {
                "tower_move_calls" : [call(4040), call(40)],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SUPERSLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SUPERSLOW)],
                "sleep" : [call(3.5), call(100.0)],
            },
            "big_first" : {
                "tower_move_calls" : [call(4040), call(40)],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SUPERSLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SUPERSLOW)],
                "sleep" : [call(3.5), call(100.0)],
            },
            "big_inside" : {
                "tower_move_calls" : [call(4040), call(40)],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SUPERSLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SUPERSLOW)],
                "sleep" : [call(3.5), call(100.0)],
            },
            "big_last" : {
                "tower_move_calls" : [call(4040), call(40)],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SUPERSLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SUPERSLOW)],
                "sleep" : [call(3.5), call(100.0)],
            },
            "big_outside" : {
                "tower_move_calls" : [call(4040), call(40)],
#                "tilt_up_calls" : [call(tilt_speed=TiltSpeed.SUPERSLOW)],
#                "tilt_down_calls" : [call(TiltSpeed.SUPERSLOW)],
                "sleep" : [call(3.5), call(100.0)],
            },
        }
#        self._check_all_layer_variants(ExposureUserProfile.HIGH_VISCOSITY, expected_results)

        self.exposure = None

    def _check_all_layer_variants(self, user_profile, expected_results):
        self.exposure.project.exposure_user_profile = user_profile

        # start - first layers (3 + numFade)
#        test_parameters = { "tilt_speed" : TiltSpeed.SLOW, "actual_layer" : 0, "white_pixels" : 1000}
        test_parameters = { "slow_move" : True, "actual_layer" : 0, "white_pixels" : 1000}
        self._check_layer_variant(test_parameters, expected_results["start_inside"])
        for _ in range(12):
            self._check_layer_variant({}, expected_results["start_inside"])
        self._check_layer_variant({}, expected_results["start_last"])
        for _ in range(10):
            self._check_layer_variant({}, expected_results["start_outside"])

        # big exposured area (limit4fast and 1 mm after)
        test_parameters = { "actual_layer" : 1000, "white_pixels" : 1300000}
        self._check_layer_variant(test_parameters, expected_results["big_first"])
        for _ in range(5):
            self._check_layer_variant({}, expected_results["big_inside"])
        self._check_layer_variant({"white_pixels" : 1000}, expected_results["big_inside"])
        for _ in range(19):
            self._check_layer_variant({}, expected_results["big_inside"])
        self._check_layer_variant({}, expected_results["big_last"])
        for _ in range(10):
            self._check_layer_variant({}, expected_results["big_outside"])

    def _check_layer_variant(self, test_parameters, expected_result):
        # pylint: disable = protected-access
        self.hw.tower.move_ensure.reset_mock()
        self.hw.tilt.layer_up_wait.reset_mock()
        self.hw.tilt.layer_down_wait.reset_mock()
        self.sleep_mock.reset_mock()
#        if "tilt_speed" in test_parameters:
#            self.exposure._tilt_speed = test_parameters["tilt_speed"]
        if "slow_move" in test_parameters:
            self.exposure._slow_move = test_parameters["slow_move"]
        if "actual_layer" in test_parameters:
            self.exposure.actual_layer = test_parameters["actual_layer"]
        else:
            self.exposure.actual_layer += 1
        if "white_pixels" in test_parameters:
            self.exposure_image.sync_preloader.return_value = test_parameters["white_pixels"]
        success, _ = self.exposure._do_frame((110000,), False, False, 50000)
        self.assertTrue(success)
#        print(f"move_ensure: {self.hw.tower.move_ensure.call_args_list}")
#        print(f"layer_up_wait: {self.hw.tilt.layer_up_wait.call_args_list}")
#        print(f"layer_down_wait: {self.hw.tilt.layer_down_wait.call_args_list}")
#        print(f"sleep: {self.sleep_mock.call_args_list}")
        # DO NOT USE assert_has_calls() - "There can be extra calls before or after the specified calls."
        self.assertEqual(self.hw.tower.move_ensure.call_args_list, expected_result["tower_move_calls"])
        self.assertEqual(self.hw.tilt.layer_up_wait.call_args_list, expected_result["tilt_up_calls"])
        self.assertEqual(self.hw.tilt.layer_down_wait.call_args_list, expected_result["tilt_down_calls"])
        self.assertEqual(self.sleep_mock.call_args_list, expected_result["sleep"])


if __name__ == "__main__":
    unittest.main()
