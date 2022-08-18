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
from slafw.exposure.profiles import LayerProfilesSL1


@patch("slafw.hardware.sl1.tilt.TiltSL1.moving", PropertyMock(return_value=False))
class LayerProfilesBase(SlafwTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.config = HwConfig()
        self.power_led = Mock()
        self.mcc = Mock()
        self.mcc.doGetInt.return_value = True
        self.config.tiltHeight = Ustep(5000)

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
        sleep_m.assert_not_called()
        if expected["asleep"]:
            self.assertEqual(asleep_m.call_args_list, expected["asleep"])
        else:
            asleep_m.assert_not_called()


class TestLayerProfilesSL1(LayerProfilesBase):
    # pylint: disable=no-value-for-parameter
    def setUp(self) -> None:
        super().setUp()
        printer_model = PrinterModel.SL1
        tower = TowerSL1(self.mcc, self.config, self.power_led, printer_model)
        self.tilt = TiltSL1(self.mcc, self.config, self.power_led, tower, printer_model)
        self.tilt.start()
        self.layer_profiles = LayerProfilesSL1(
                factory_file_path=self.SLAFW_DIR / "data/SL1/default_layer_profiles.json")

    def test_profile_fast_up(self):
        positions = [Ustep(0), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(4600)), call(Ustep(5000))],
            "profile" : [call(self.tilt.profiles.moveFast), call(self.tilt.profiles.layerRelease)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_up_wait, self.layer_profiles.fast, positions, expected_results)

    def test_profile_slow_up(self):
        positions = [Ustep(0), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(4600)), call(Ustep(5000))],
            "profile" : [call(self.tilt.profiles.moveFast), call(self.tilt.profiles.layerRelease)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_up_wait, self.layer_profiles.slow, positions, expected_results)

    def test_profile_super_slow_up(self):
        positions = [Ustep(0), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(2800)), call(Ustep(5000))],
            "profile" : [call(self.tilt.profiles.layerMoveSlow), call(self.tilt.profiles.superSlow)],
            "asleep" : [call(1.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_up_wait, self.layer_profiles.super_slow, positions, expected_results)

    def test_profile_fast_down(self):
        positions = [Ustep(5000), Ustep(5000), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(0))],
            "profile" : [call(self.tilt.profiles.layerRelease), call(self.tilt.profiles.layerMoveSlow)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_down_wait, self.layer_profiles.fast, positions, expected_results)

    def test_profile_slow_down(self):
        positions = [Ustep(5000), Ustep(4350), Ustep(4350), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(4350)), call(Ustep(0))],
            "profile" : [call(self.tilt.profiles.layerRelease), call(self.tilt.profiles.layerMoveSlow)],
            "asleep" : [call(1.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_down_wait, self.layer_profiles.slow, positions, expected_results)

    def test_profile_super_slow_down(self):
        positions = [Ustep(5000), Ustep(2800), Ustep(2800), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(2800)), call(Ustep(0))],
            "profile" : [call(self.tilt.profiles.superSlow), call(self.tilt.profiles.layerMoveSlow)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_down_wait, self.layer_profiles.super_slow, positions, expected_results)


class TestLayerProfilesSL1S(LayerProfilesBase):
    # pylint: disable=no-value-for-parameter
    def setUp(self) -> None:
        super().setUp()
        printer_model = PrinterModel.SL1S
        tower = TowerSL1(self.mcc, self.config, self.power_led, printer_model)
        self.tilt = TiltSL1(self.mcc, self.config, self.power_led, tower, printer_model)
        self.tilt.start()
        self.layer_profiles = LayerProfilesSL1(
                factory_file_path=self.SLAFW_DIR / "data/SL1S/default_layer_profiles.json")

    def test_profile_fast_up(self):
        positions = [Ustep(0), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(4400)), call(Ustep(5000))],
            "profile" : [call(self.tilt.profiles.moveFast), call(self.tilt.profiles.layerMoveFast)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_up_wait, self.layer_profiles.fast, positions, expected_results)

    def test_profile_slow_up(self):
        positions = [Ustep(0), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(3800)), call(Ustep(5000))],
            "profile" : [call(self.tilt.profiles.moveFast), call(self.tilt.profiles.layerMoveFast)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_up_wait, self.layer_profiles.slow, positions, expected_results)

    def test_profile_super_slow_up(self):
        positions = [Ustep(0), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(2800)), call(Ustep(5000))],
            "profile" : [call(self.tilt.profiles.layerMoveSlow), call(self.tilt.profiles.superSlow)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_up_wait, self.layer_profiles.super_slow, positions, expected_results)

    def test_profile_fast_down(self):
        positions = [Ustep(5000), Ustep(5000), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(0))],
            "profile" : [call(self.tilt.profiles.layerMoveFast), call(self.tilt.profiles.layerMoveSlow)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_down_wait, self.layer_profiles.fast, positions, expected_results)

    def test_profile_slow_down(self):
        positions = [Ustep(5000), Ustep(5000), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(0))],
            "profile" : [call(self.tilt.profiles.layerMoveFast), call(self.tilt.profiles.layerMoveSlow)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_down_wait, self.layer_profiles.slow, positions, expected_results)

    def test_profile_super_slow_down(self):
        positions = [Ustep(5000), Ustep(2800), Ustep(2800), Ustep(0)]
        expected_results = {
            "move" : [call(Ustep(2800)), call(Ustep(0))],
            "profile" : [call(self.tilt.profiles.superSlow), call(self.tilt.profiles.layerMoveSlow)],
            "asleep" : [call(0.0), call(0.0)],
        }
        self._check_tilt_method(self.tilt.layer_down_wait, self.layer_profiles.super_slow, positions, expected_results)

if __name__ == "__main__":
    unittest.main()
