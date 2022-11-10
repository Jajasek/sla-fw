# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from time import sleep
from typing import Optional

from unittest.mock import Mock, patch, MagicMock, AsyncMock, call

from slafw.tests.base import SlafwTestCaseDBus, RefCheckTestCase
from slafw.hardware.sl1.hardware import HardwareSL1
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
from slafw.configs.hw import HwConfig
from slafw.configs.runtime import RuntimeConfig
from slafw.configs.unit import Nm, Ms
from slafw.exposure.exposure import Exposure
from slafw.exposure.profiles import ExposureProfilesSL1, LayerProfilesSL1
from slafw.states.exposure import ExposureState
from slafw.tests.mocks.hardware import HardwareMock


def setupHw() -> HardwareMock:
    hw = HardwareMock(printer_model = PrinterModel.SL1)
    hw.connect()
    hw.start()
    hw.config.uvPwm = 250
    hw.config.calibrated = True
    return hw


@patch("slafw.exposure.exposure.sleep", Mock()) # do it faster, much faster ;-)
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
        self.hw = setupHw()
        self.runtime_config = RuntimeConfig()
        self.exposure_image = Mock()
        self.exposure_image.__class__ = ExposureImage
        self.exposure_image.__reduce__ = lambda x: (Mock, ())
        self.exposure_image.sync_preloader.return_value = 100
        self.ep = ExposureProfilesSL1(default_file_path=self.SAMPLES_DIR / "profiles_exposure.json")
        self.lp = LayerProfilesSL1(default_file_path=self.SAMPLES_DIR / "profiles_layer.json")

    def tearDown(self):
        self.hw.exit()
        super().tearDown()

    def test_exposure_init_not_calibrated(self):
        hw = HardwareMock(printer_model = PrinterModel.SL1)
        hw.connect()
        hw.start()
        with self.assertRaises(NotUVCalibrated):
            exposure = Exposure(0, hw, self.exposure_image, self.runtime_config, self.ep, self.lp)
            exposure.read_project(TestExposure.PROJECT)

    def test_exposure_init(self):
        exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config, self.ep, self.lp)
        exposure.read_project(TestExposure.PROJECT)

    def test_exposure_load(self):
        exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config, self.ep, self.lp)
        exposure.read_project(TestExposure.PROJECT)
        exposure.startProject()

    def test_pickle_profile(self):
        exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config, self.ep, self.lp)
        exposure.exposure_profiles.default.delay_after_exposure_large_fill_ms = 23755
        exposure.read_project(TestExposure.PROJECT)
        self.assertEqual(13740, exposure.estimate_remain_time_ms())
        exposure.save()
        new_exposure = Exposure.load(Mock(), self.hw, self.ep, self.lp)
        self.assertEqual(13740, new_exposure.estimate_remain_time_ms())
        self.assertEqual(exposure.exposure_profiles, new_exposure.exposure_profiles)
        self.assertEqual(exposure.project.exposure_profile, new_exposure.project.exposure_profile)

    def test_exposure_start_stop(self):
        exposure = self._wait_exposure(self._start_exposure(self.hw))
        self.assertNotEqual(exposure.state, ExposureState.FAILURE)
        self.assertIsNone(exposure.warning)

    def test_resin_enough(self):
        hw = setupHw()
        hw.get_resin_volume_async = AsyncMock(return_value = defines.resinMaxVolume)
        exposure = self._wait_exposure(self._start_exposure(hw))
        self.assertNotEqual(exposure.state, ExposureState.FAILURE)
        self.assertIsNone(exposure.warning)

    def test_resin_warning(self):
        hw = setupHw()
        hw.get_resin_volume_async = AsyncMock(return_value = defines.resinMinVolume + 0.1)
        exposure = self._wait_exposure(self._start_exposure(hw))
        self.assertIsInstance(exposure.fatal_error, WarningEscalation)
        self.assertIsInstance(exposure.fatal_error.warning, ResinNotEnough)  # pylint: disable=no-member

    def test_resin_error(self):
        hw = setupHw()
        hw.get_resin_volume_async = AsyncMock(return_value = defines.resinMinVolume - 0.1)
        exposure = self._wait_exposure(self._start_exposure(hw))
        self.assertIsInstance(exposure.fatal_error, ResinTooLow)

    def test_broken_empty_project(self):
        exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config, self.ep, self.lp)
        with self.assertRaises(ProjectErrorCantRead):
            exposure.read_project(self.BROKEN_EMPTY_PROJECT)
        self.assertIsInstance(exposure.fatal_error, ProjectErrorCantRead)

    def test_stuck_recovery_success(self):
        hw = setupHw()
        hw.tilt.layer_peel_moves = MagicMock(side_effect=TiltHomeFailed())
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
                hw.tilt.layer_peel_moves = MagicMock()
                exposure.doContinue()
            if exposure.state == ExposureState.POUR_IN_RESIN:
                exposure.confirm_resin_in()
            sleep(1)

        raise TimeoutError("Waiting for exposure failed")

    def test_stuck_recovery_fail(self):
        hw = setupHw()
        hw.tilt.layer_peel_moves = MagicMock(side_effect=TiltHomeFailed())
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
        hw.config.limit4fast = 45
        exposure_image = ExposureImage(hw)
        exposure_image.start()

        hw.config.forceSlowTiltHeight = 0  # do not force any extra slow tilts
        exposure = self._start_exposure(hw, TestExposure.PROJECT_LAYER_CHANGE, exposure_image)
        self._wait_exposure(exposure)
        self.assertEqual(exposure.state, ExposureState.FINISHED)
        # 13 slow layers at beginning + 4 large layers in project
        self.assertEqual(exposure.slow_layers_done, 13 + 4)

        hw.config.forceSlowTiltHeight = 100000  # 100 um -> force 2 slow layers
        exposure = self._start_exposure(hw, TestExposure.PROJECT_LAYER_CHANGE, exposure_image)
        self._wait_exposure(exposure)
        self.assertEqual(exposure.state, ExposureState.FINISHED)
        # 13 slow layers at beginning + 4 large layers in project + 4 layers after area change
        self.assertEqual(exposure.slow_layers_done, 13 + 4 + 4)

    def test_exposure_profile(self):
        self.hw.config.limit4fast = 100
        exposure = self._start_exposure(self.hw, TestExposure.PROJECT_LAYER_CHANGE)
        self._wait_exposure(exposure)
        self.assertEqual(exposure.state, ExposureState.FINISHED)
        # 13 slow layers at beginning
        self.assertEqual(exposure.slow_layers_done, 13)
        self.assertEqual(205040, exposure.estimate_total_time_ms())

        delay = 10  # 0.01 s
        self.lp.slow.delay_before_exposure_ms = Ms(delay)
        exposure = self._start_exposure(self.hw, TestExposure.PROJECT_LAYER_CHANGE_SAFE)
        self._wait_exposure(exposure)
        self.assertEqual(exposure.state, ExposureState.FINISHED)

        delay_time = exposure.project.total_layers * delay
        force_slow_time = exposure.project._layers_fast * \
            int(self.lp.fast.moves_time_ms - self.lp.super_fast.moves_time_ms) # pylint: disable = protected-access
        self.assertEqual(201040 + delay_time + force_slow_time, exposure.estimate_total_time_ms())

    def _start_exposure(self, hw, project = None, expo_img = None) -> Exposure:
        if project is None:
            project = TestExposure.PROJECT
        if expo_img is None:
            expo_img = self.exposure_image
        exposure = Exposure(0, hw, expo_img, self.runtime_config, self.ep, self.lp)
        exposure.read_project(project)
        exposure.startProject()
        exposure.confirm_print_start()
        return exposure

    def _wait_exposure(self, exposure: Exposure) -> Exposure:
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
    # pylint: disable = too-many-instance-attributes
    PROJECT_LAYER_CHANGE = str(SlafwTestCaseDBus.SAMPLES_DIR / "layer_change.sl1")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exposure: Optional[Exposure] = None
        self.sleep_mock = None

    def setUp(self):
        super().setUp()
        self.hw_config = HwConfig(self.SAMPLES_DIR / "hardware.cfg")
        self.hw_config.read_file()
        self.hw = HardwareSL1(self.hw_config, PrinterModel.SL1)
        self.hw.connect()
        self.hw.start()
        self.hw.config.uvPwm = 250
        self.hw.config.calibrated = True
        self.runtime_config = RuntimeConfig()
        self.exposure_image = Mock()
        self.exposure_image.__class__ = ExposureImage
        self.exposure_image.__reduce__ = lambda x: (Mock, ())
        self.exposure_image.sync_preloader.return_value = 100

        self.hw.tower.move_ensure_async = AsyncMock()
        self.hw.tilt.layer_up_wait_async = AsyncMock()
        self.hw.tilt.layer_down_wait_async = AsyncMock()

        self.ep = ExposureProfilesSL1(default_file_path=self.SAMPLES_DIR / "profiles_exposure.json")
        self.lp = LayerProfilesSL1(default_file_path=self.SAMPLES_DIR / "profiles_layer.json")
        self.exposure = Exposure(0, self.hw, self.exposure_image, self.runtime_config, self.ep, self.lp)
        self.exposure._exposure_simple = MagicMock()    # pylint: disable = protected-access
        self.exposure.read_project(TestExposure.PROJECT_LAYER_CHANGE)
        self.exposure.startProject()

        # verify "input" parameters
        self.assertEqual(36864, self.hw.white_pixels_threshold)
        self.assertEqual(13, self.exposure.project.first_slow_layers)

    def tearDown(self):
        self.exposure = None
        self.hw.exit()
        super().tearDown()

    @patch("slafw.exposure.exposure.sleep")
    def test_default_profile(self, sleep_mock):
        self.sleep_mock = sleep_mock
        expected_results = {
            "start_inside" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.fast)],
                "tilt_down_calls" : [call(self.lp.fast)],
                "sleep" : [call(1.0)],
            },
            "start_last" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_fast)],
                "tilt_down_calls" : [call(self.lp.super_fast)],
                "sleep" : [call(1.0)],
            },
            "start_outside" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_fast)],
                "tilt_down_calls" : [call(self.lp.super_fast)],
                "sleep" : []
            },
            "big_first" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.fast)],
                "tilt_down_calls" : [call(self.lp.fast)],
                "sleep" : [],
            },
            "big_inside" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.fast)],
                "tilt_down_calls" : [call(self.lp.fast)],
                "sleep" : [call(1.0)],
            },
            "big_last" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_fast)],
                "tilt_down_calls" : [call(self.lp.super_fast)],
                "sleep" : [call(1.0)],
            },
            "big_outside" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_fast)],
                "tilt_down_calls" : [call(self.lp.super_fast)],
                "sleep" : []
            },
            "last" : {
                "tower_move_calls" : [],
                "tilt_up_calls" : [],
                "tilt_down_calls" : [call(self.lp.super_fast)],
                "sleep" : []
            },
        }
        self._check_all_layer_variants(self.ep.default, expected_results)

    @patch("slafw.exposure.exposure.sleep")
    def test_safe_profile(self, sleep_mock):
        self.sleep_mock = sleep_mock
        expected_results = {
            "start_inside" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.slow)],
                "tilt_down_calls" : [call(self.lp.slow)],
                "sleep" : [call(3.0)],
            },
            "start_last" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.slow)],
                "tilt_down_calls" : [call(self.lp.slow)],
                "sleep" : [call(3.0)],
            },
            "start_outside" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.slow)],
                "tilt_down_calls" : [call(self.lp.slow)],
                "sleep" : [call(3.0)],
            },
            "big_first" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.slow)],
                "tilt_down_calls" : [call(self.lp.slow)],
                "sleep" : [call(3.0)],
            },
            "big_inside" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.slow)],
                "tilt_down_calls" : [call(self.lp.slow)],
                "sleep" : [call(3.0)],
            },
            "big_last" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.slow)],
                "tilt_down_calls" : [call(self.lp.slow)],
                "sleep" : [call(3.0)],
            },
            "big_outside" : {
                "tower_move_calls" : [call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.slow)],
                "tilt_down_calls" : [call(self.lp.slow)],
                "sleep" : [call(3.0)],
            },
            "last" : {
                "tower_move_calls" : [],
                "tilt_up_calls" : [],
                "tilt_down_calls" : [call(self.lp.slow)],
                "sleep" : [call(3.0)],
            },
        }
        self._check_all_layer_variants(self.ep.safe, expected_results)

    @patch("slafw.exposure.exposure.sleep")
    def test_high_viscosity_profile(self, sleep_mock):
        self.sleep_mock = sleep_mock
        expected_results = {
            "start_inside" : {
                "tower_move_calls" : [call(Nm(5000000)), call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_slow)],
                "tilt_down_calls" : [call(self.lp.super_slow)],
                "sleep" : [call(3.5)],
            },
            "start_last" : {
                "tower_move_calls" : [call(Nm(5000000)), call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_slow)],
                "tilt_down_calls" : [call(self.lp.super_slow)],
                "sleep" : [call(3.5)],
            },
            "start_outside" : {
                "tower_move_calls" : [call(Nm(5000000)), call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_slow)],
                "tilt_down_calls" : [call(self.lp.super_slow)],
                "sleep" : [call(3.5)],
            },
            "big_first" : {
                "tower_move_calls" : [call(Nm(5000000)), call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_slow)],
                "tilt_down_calls" : [call(self.lp.super_slow)],
                "sleep" : [call(3.5)],
            },
            "big_inside" : {
                "tower_move_calls" : [call(Nm(5000000)), call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_slow)],
                "tilt_down_calls" : [call(self.lp.super_slow)],
                "sleep" : [call(3.5)],
            },
            "big_last" : {
                "tower_move_calls" : [call(Nm(5000000)), call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_slow)],
                "tilt_down_calls" : [call(self.lp.super_slow)],
                "sleep" : [call(3.5)],
            },
            "big_outside" : {
                "tower_move_calls" : [call(Nm(5000000)), call(Nm(0))],
                "tilt_up_calls" : [call(self.lp.super_slow)],
                "tilt_down_calls" : [call(self.lp.super_slow)],
                "sleep" : [call(3.5)],
            },
            "last" : {
                "tower_move_calls" : [call(Nm(5000000))],
                "tilt_up_calls" : [],
                "tilt_down_calls" : [call(self.lp.super_slow)],
                "sleep" : [call(3.5)],
            },
        }
        self._check_all_layer_variants(self.ep.high_viscosity, expected_results)

    def _check_all_layer_variants(self, user_profile, expected_results):
        self.exposure.project.exposure_profile = user_profile

        # start - first layers (3 + numFade)
        test_parameters = {
                "actual_layer_profile" : self.lp[user_profile.large_fill_layer_profile],
                "actual_layer" : 0,
                "white_pixels" : 100}
        print("start_inside")
        self._check_layer_variant(test_parameters, expected_results["start_inside"])
        for i in range(12):
            print(i)
            self._check_layer_variant({}, expected_results["start_inside"])
        print("start_last")
        self._check_layer_variant({}, expected_results["start_last"])
        print("start_outside")
        for i in range(10):
            print(i)
            self._check_layer_variant({}, expected_results["start_outside"])

        # big exposured area (limit4fast and 1 mm after)
        test_parameters = { "actual_layer" : 1000, "white_pixels" : 40000}
        print("big_first")
        self._check_layer_variant(test_parameters, expected_results["big_first"])
        print("big_inside")
        for i in range(5):
            print(i)
            self._check_layer_variant({}, expected_results["big_inside"])
        self._check_layer_variant({"white_pixels" : 100}, expected_results["big_inside"])
        for i in range(19):
            print(i)
            self._check_layer_variant({}, expected_results["big_inside"])
        print("big_last")
        self._check_layer_variant({}, expected_results["big_last"])
        print("big_outside")
        for i in range(10):
            print(i)
            self._check_layer_variant({}, expected_results["big_outside"])

        print("last")
        self._check_layer_variant({}, expected_results["last"], last = True)

    def _check_layer_variant(self, test_parameters, expected_result, last = False):
        # pylint: disable = protected-access
        self.hw.tower.move_ensure_async.reset_mock()
        self.hw.tilt.layer_up_wait_async.reset_mock()
        self.hw.tilt.layer_down_wait_async.reset_mock()
        self.sleep_mock.reset_mock()
        if "actual_layer_profile" in test_parameters:
            self.exposure.actual_layer_profile = test_parameters["actual_layer_profile"]
        if "actual_layer" in test_parameters:
            self.exposure.actual_layer = test_parameters["actual_layer"]
        else:
            self.exposure.actual_layer += 1
        if "white_pixels" in test_parameters:
            self.exposure_image.sync_preloader.return_value = test_parameters["white_pixels"]
        success, _ = self.exposure._do_frame((100,), False, 50000, last)
        self.assertTrue(success)
#        print(f"move_ensure_async: {self.hw.tower.move_ensure_async.call_args_list}")
#        print(f"layer_up_wait_async: {self.hw.tilt.layer_up_wait_async.call_args_list}")
#        print(f"layer_down_wait_async: {self.hw.tilt.layer_down_wait_async.call_args_list}")
#        print(f"sleep: {self.sleep_mock.call_args_list}")
        # DO NOT USE assert_has_calls() - "There can be extra calls before or after the specified calls."
        self.assertEqual(self.hw.tower.move_ensure_async.call_args_list, expected_result["tower_move_calls"])
        self.assertEqual(self.hw.tilt.layer_up_wait_async.call_args_list, expected_result["tilt_up_calls"])
        self.assertEqual(self.hw.tilt.layer_down_wait_async.call_args_list, expected_result["tilt_down_calls"])
        self.assertEqual(self.sleep_mock.call_args_list, expected_result["sleep"])


if __name__ == "__main__":
    unittest.main()
