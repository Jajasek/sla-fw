# This file is part of the SLA firmware
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from unittest.mock import Mock, PropertyMock, AsyncMock, patch, call

from slafw.tests.base import SlafwTestCase

from slafw.configs.hw import HwConfig
from slafw.configs.unit import Ustep
from slafw.hardware.printer_model import PrinterModel
from slafw.hardware.sl1.tilt import TiltSL1
from slafw.hardware.sl1.tower import TowerSL1


@patch("slafw.hardware.sl1.tilt.TiltSL1.moving", PropertyMock(return_value=False))
class TestTiltTuningProfiles(SlafwTestCase):
    # pylint: disable=no-value-for-parameter

    def setUp(self) -> None:
        super().setUp()
        self.config = HwConfig()
        self.power_led = Mock()
        self.mcc = Mock()
        self.mcc.doGetInt.return_value = True
        self.config.tiltHeight = Ustep(5000)

    def test_SL1(self):
        printer_model = PrinterModel.SL1
        tower = TowerSL1(self.mcc, self.config, self.power_led, printer_model)
        tilt = TiltSL1(self.mcc, self.config, self.power_led, tower, printer_model)
        tilt.start()

        positions = [Ustep(0), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(4600)), call(Ustep(5000))],
            "profile" : [call(tilt.profiles.moveFast), call(tilt.profiles.layerRelease)],
            "asleep" : [],
            "sleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(tilt.layer_up_wait, tilt.get_tune_profile_up(False), positions, expected_results)
        self._check_tilt_method(tilt.layer_up_wait, tilt.get_tune_profile_up(True), positions, expected_results)
#        expected_results = {
#            "move" : [call(Ustep(2800)), call(Ustep(5000))],
#            "profile" : [call(tilt.profiles.layerMoveSlow), call(tilt.profiles.superSlow)],
#            "asleep" : [],
#            "sleep" : [call(1.0), call(0.0)],
#        }
#        self._check_tilt_method(tilt.layer_up_wait, TiltSpeed.SUPERSLOW, positions, expected_results)
        positions = [Ustep(5000), Ustep(5000), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(0))],
            "profile" : [call(tilt.profiles.layerRelease), call(tilt.profiles.layerMoveFast)],
            "asleep" : [call(0.0), call(0.0)],
            "sleep" : [],
        }
        self._check_tilt_method(tilt.layer_down_wait, tilt.get_tune_profile_down(False), positions, expected_results)
        positions = [Ustep(5000), Ustep(4350), Ustep(4350), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(4350)), call(Ustep(0))],
            "profile" : [call(tilt.profiles.layerRelease), call(tilt.profiles.layerMoveSlow)],
            "asleep" : [call(1.0), call(0.0)],
            "sleep" : [],
        }
        self._check_tilt_method(tilt.layer_down_wait, tilt.get_tune_profile_down(True), positions, expected_results)
        positions = [Ustep(5000), Ustep(2800), Ustep(2800), Ustep(0)]
#        expected_results = {
#            "move" : [call(Ustep(2800)), call(Ustep(0))],
#            "profile" : [call(tilt.profiles.superSlow), call(tilt.profiles.layerMoveSlow)],
#            "asleep" : [call(0.0), call(0.0)],
#            "sleep" : [],
#        }
#        self._check_tilt_method(tilt.layer_down_wait, TiltSpeed.SUPERSLOW, positions, expected_results)

    def test_SL1S(self):
        printer_model = PrinterModel.SL1S
        tower = TowerSL1(self.mcc, self.config, self.power_led, printer_model)
        tilt = TiltSL1(self.mcc, self.config, self.power_led, tower, printer_model)
        tilt.start()

        positions = [Ustep(0), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(4400)), call(Ustep(5000))],
            "profile" : [call(tilt.profiles.moveFast), call(tilt.profiles.layerMoveFast)],
            "asleep" : [],
            "sleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(tilt.layer_up_wait, tilt.get_tune_profile_up(False), positions, expected_results)
        expected_results = {
            "move" : [call(Ustep(3800)), call(Ustep(5000))],
            "profile" : [call(tilt.profiles.moveFast), call(tilt.profiles.layerMoveFast)],
            "asleep" : [],
            "sleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(tilt.layer_up_wait, tilt.get_tune_profile_up(True), positions, expected_results)
#        expected_results = {
#            "move" : [call(Ustep(2800)), call(Ustep(5000))],
#            "profile" : [call(tilt.profiles.layerMoveSlow), call(tilt.profiles.superSlow)],
#            "asleep" : [],
#            "sleep" : [call(0.0), call(0.0)],
#        }
#        self._check_tilt_method(tilt.layer_up_wait, TiltSpeed.SUPERSLOW, positions, expected_results)
        positions = [Ustep(5000), Ustep(5000), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(0))],
            "profile" : [call(tilt.profiles.layerMoveFast), call(tilt.profiles.moveFast)],
            "asleep" : [call(0.0), call(0.0)],
            "sleep" : [],
        }
        self._check_tilt_method(tilt.layer_down_wait, tilt.get_tune_profile_down(False), positions, expected_results)
        expected_results = {
            "move" : [call(Ustep(0))],
            "profile" : [call(tilt.profiles.layerMoveFast), call(tilt.profiles.layerMoveSlow)],
            "asleep" : [call(0.0), call(0.0)],
            "sleep" : [],
        }
        self._check_tilt_method(tilt.layer_down_wait, tilt.get_tune_profile_down(True), positions, expected_results)
#        positions = [Ustep(5000), Ustep(2800), Ustep(2800), Ustep(0)]
#        expected_results = {
#            "move" : [call(Ustep(2800)), call(Ustep(0))],
#            "profile" : [call(tilt.profiles.superSlow), call(tilt.profiles.layerMoveSlow)],
#            "asleep" : [call(0.0), call(0.0)],
#            "sleep" : [],
#        }
#        self._check_tilt_method(tilt.layer_down_wait, TiltSpeed.SUPERSLOW, positions, expected_results)

    @patch("slafw.hardware.sl1.tilt.TiltSL1.move")
    @patch("slafw.hardware.sl1.tilt.TiltSL1.position", new_callable=PropertyMock)
    @patch("slafw.hardware.sl1.axis.AxisSL1.actual_profile", new_callable=PropertyMock)
    @patch("slafw.hardware.sl1.tilt.asyncio.sleep", new_callable=AsyncMock)
    @patch("slafw.hardware.sl1.tilt.sleep")
    def _check_tilt_method(self, fce, params, positions, expected,
            sleep_m, asleep_m, profile_m, position_m, move_m):
        # pylint: disable=too-many-arguments
        position_m.side_effect = positions
        fce(params)
#        print(f"position: {position_m.call_args_list}")
#        print(f"move: {move_m.call_args_list}")
#        print(f"actual_profile: {profile_m.call_args_list}")
#        print(f"asyncio.sleep: {asleep_m.call_args_list}")
#        print(f"sleep: {sleep_m.call_args_list}")
        # DO NOT USE assert_has_calls() - "There can be extra calls before or after the specified calls."
        self.assertEqual(move_m.call_args_list, expected["move"])
        self.assertEqual(profile_m.call_args_list, expected["profile"])
        if expected["asleep"]:
            self.assertEqual(asleep_m.call_args_list, expected["asleep"])
        else:
            asleep_m.assert_not_called()
        if expected["sleep"]:
            self.assertEqual(sleep_m.call_args_list, expected["sleep"])
        else:
            sleep_m.assert_not_called()

if __name__ == "__main__":
    unittest.main()
