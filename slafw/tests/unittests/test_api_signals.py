# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
import weakref

from time import sleep
from unittest.mock import Mock, call
from datetime import datetime, timedelta, timezone

import time_machine

from pydbus import SystemBus

from slafw.api.printer0 import Printer0
from slafw.api.standard0 import Standard0
from slafw.api.exposure0 import Exposure0, Exposure0State
from slafw.errors.warnings import PrinterWarning, ResinLow, AmbientTemperatureOutOfRange, AmbientTooCold
from slafw.errors.errors import PrinterException, FanFailed
from slafw.exposure.persistence import ExposurePickler
from slafw.exposure.profiles import ExposureProfilesSL1, LayerProfilesSL1
from slafw.image.exposure_image import ExposureImage
from slafw.state_actions.manager import ActionManager
from slafw.states.exposure import ExposureState, ExposureCheck, ExposureCheckResult
from slafw.tests.mocks.printer import Printer
from slafw.tests.mocks.hardware import setupHw
from slafw.tests.base import SlafwTestCaseDBus, RefCheckTestCase
from slafw.wizard.data_package import WizardDataPackage


class TestExposureSignals(SlafwTestCaseDBus, RefCheckTestCase):
    PROJECT = str(SlafwTestCaseDBus.SAMPLES_DIR / "numbers.sl1")

    def setUp(self):
        super().setUp()
        self.hw = setupHw()
        exposure_image = Mock()
        exposure_image.__class__ = ExposureImage
        exposure_image.__reduce__ = lambda x: (Mock, ())
        exposure_image.sync_preloader.return_value = 100
        ep = ExposureProfilesSL1(default_file_path=self.SAMPLES_DIR / "profiles_exposure.json")
        lp = LayerProfilesSL1(default_file_path=self.SAMPLES_DIR / "profiles_layer.json")
        package = WizardDataPackage(self.hw, None, None, exposure_image, ep, lp)
        self.manager = ActionManager()
        self.printer = Printer(self.hw, self.manager)
        self.printer0 = Printer0(self.printer)
        bus = SystemBus()
        # pylint: disable = no-member
        self.printer0_dbus = bus.publish(
                Printer0.__INTERFACE__,
                (None, weakref.proxy(self.printer0), self.printer0.dbus))
        self.standard0_dbus = bus.publish(Standard0.__INTERFACE__, Standard0(self.printer))
        self.pickler = ExposurePickler(package)


    def tearDown(self):
        self.standard0_dbus.unpublish()
        self.printer0_dbus.unpublish()
        # This fixes symptoms of a bug in pydbus. Drop circular dependencies.
        if self.printer0 in Printer0.PropertiesChanged.map:  # pylint: disable = no-member
            del Printer0.PropertiesChanged.map[self.printer0]  # pylint: disable = no-member
        if self.printer0 in Printer0.exception.map:  # pylint: disable = no-member
            del Printer0.exception.map[self.printer0]  # pylint: disable = no-member
        # Make sure we are not leaving these behind.
        # Base test tear down checks this does not happen.
        del self.printer0
        self.manager.exit()
        super().tearDown()


    def test_Printer0_signals(self):
        uri = "cz.prusa3d.sl1.printer0"
        printer0: Printer0 = SystemBus().get(uri)
        receiver = Mock()
        printer0.onPropertiesChanged = receiver.receive

        # ActionManager.exposure_changed
        exposure = self.manager.new_exposure(self.pickler, TestExposureSignals.PROJECT)
        sleep(.1)
        receiver.receive.assert_called_with(uri, {'current_exposure': '/cz/prusa3d/sl1/exposures0/0'}, [])
        self.manager.reprint_exposure(self.pickler, exposure)
        sleep(.1)
        receiver.receive.assert_called_with(uri, {'current_exposure': '/cz/prusa3d/sl1/exposures0/1'}, [])
        self.pickler.save(exposure)
        self.manager.exit()
        self.manager = ActionManager()
        self.manager.load_exposure(self.pickler)
        sleep(.1)
        receiver.receive.assert_called_with(uri, {'current_exposure': '/cz/prusa3d/sl1/exposures0/1'}, [])
        # TODO more


    def test_Standard0_signals(self):
        uri = "cz.prusa3d.sl1.standard0"
        standard0: Standard0 = SystemBus().get(uri)
        receiver = Mock()
        standard0.onLastErrorOrWarn = receiver.receive

        # Standard0._on_exposure_values_changed
        self.manager.new_exposure(self.pickler, TestExposureSignals.PROJECT)
        self.manager.exposure.data.resin_warn = True
        sleep(.1)
        receiver.receive.assert_called_with(PrinterWarning.as_dict(ResinLow()))
        self.manager.exposure.data.resin_warn = False
        sleep(.1)
        receiver.receive.assert_called_with(PrinterWarning.as_dict(None))
        self.manager.exposure.data.warning = AmbientTemperatureOutOfRange(128.48)
        sleep(.1)
        receiver.receive.assert_called_with(PrinterWarning.as_dict(AmbientTemperatureOutOfRange(128.48)))
        # TODO more

    def test_Exposure0_signals(self):
        self.manager.new_exposure(self.pickler, TestExposureSignals.PROJECT)
        # test on recreated Exposure object
        self.manager.reprint_exposure(self.pickler, self.manager.exposure)

        uri = "cz.prusa3d.sl1.exposure0"
        exposure0: Exposure0 = SystemBus().get(uri, "/cz/prusa3d/sl1/exposures0/1")
        receiver = Mock()
        exposure0.onPropertiesChanged = receiver.receive

        # project changes
        with time_machine.travel(datetime.fromtimestamp(0)):
            self.manager.exposure.project.data.path = "/nice/path/file.suffix"
            self.manager.exposure.project.exposure_time_ms = 2080
            self.manager.exposure.project.exposure_time_first_ms = 10000
            self.manager.exposure.project.calibrate_regions = 9
            self.manager.exposure.project.calibrate_time_ms = 3000
            self.manager.exposure.project.exposure_profile_by_id = 1
            self.manager.exposure.project.delayed_end_time = datetime.now().timestamp()
            sleep(.1)
            signal_list = [
                call(uri, {"project_file": "/nice/path/file.suffix"}, []),
                call(uri, {"exposure_time_ms": 2080}, []),
                call(uri, {"delayed_end_time": 13}, []),
                call(uri, {"total_time_ms": 13860}, []),
                call(uri, {"exposure_time_first_ms": 10000}, []),
                call(uri, {"delayed_end_time": 30}, []),
                call(uri, {"total_time_ms": 30860}, []),
                call(uri, {"calibration_regions": 9}, []),
                call(uri, {"delayed_end_time": 46}, []),
                call(uri, {"total_time_ms": 46860}, []),
                call(uri, {"exposure_time_calibrate_ms": 3000}, []),
                call(uri, {"delayed_end_time": 78}, []),
                call(uri, {"total_time_ms": 78860}, []),
                call(uri, {"user_profile": 1}, []),
                call(uri, {"total_time_ms": 89860}, []),
                call(uri, {"delayed_end_time": 0}, []),
            ]

            receiver.receive.assert_has_calls(signal_list)

        # exposure changes
        now = datetime.now(tz=timezone.utc)
        then = now + timedelta(hours=1)
        receiver.receive.reset_mock()
        self.manager.exposure.state = ExposureState.PRINTING
        self.manager.exposure.data.resin_count_ml = 2.0
        self.manager.exposure.data.resin_remain_ml = 1.0
        self.manager.exposure.data.resin_warn = True
        self.manager.exposure.data.resin_low = True
        self.manager.exposure.data.remaining_wait_sec = 5
        self.manager.exposure.data.estimated_total_time_ms = 23755
        self.manager.exposure.data.print_start_time = now
        self.manager.exposure.data.print_end_time = then
        self.manager.exposure.data.exposure_end = then
        self.manager.exposure.data.check_results[ExposureCheck.FAN] = ExposureCheckResult.RUNNING
        self.manager.exposure.data.warning = AmbientTooCold(-273.15)
        self.manager.exposure.data.fatal_error = FanFailed(0)
        sleep(.1)
        signal_list = [
                call(uri, {"state": Exposure0State.PRINTING.value}, []),
                call(uri, {"resin_used_ml": 2.0}, []),
                call(uri, {"resin_remaining_ml": 1.0}, []),
                call(uri, {"resin_warn": True}, []),
                call(uri, {"resin_low": True}, []),
                call(uri, {"remaining_wait_sec": 5}, []),
                call(uri, {"total_time_ms": 23755}, []),
                call(uri, {"print_start_timestamp": now.timestamp()}, []),
                call(uri, {"print_end_timestamp": then.timestamp()}, []),
                call(uri, {"exposure_end": then.timestamp()}, []),
                call(uri, {"checks_state": {ExposureCheck.FAN.value: ExposureCheckResult.RUNNING.value}}, []),
                call(uri, {"exposure_warning": PrinterWarning.as_dict(AmbientTooCold(-273.15))}, []),
                call(uri, {"failure_reason": PrinterException.as_dict(FanFailed(0))}, []),
        ]
        receiver.receive.assert_has_calls(signal_list)
        # exposure changes multi
        receiver.receive.reset_mock()
        self.manager.exposure.data.actual_layer = 2
        sleep(.1)
        expected_args = {
               "current_layer": 2,
               "progress": 50.0,
               "position_nm": 0,
               "time_remain_ms": 0,
               }
        args = receiver.receive.call_args.args[1]
        args.pop("expected_finish_timestamp")
        self.assertEqual(expected_args, args)


if __name__ == "__main__":
    unittest.main()
