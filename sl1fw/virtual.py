#!/usr/bin/env python

# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

"""
This module is used to run a virtual printer. Virtual printer encompasses some of the real printer and parts of the
integration test mocks. All in all this launches the printer (similar to the one launched by main.py) that can run on
a desktop computer without motion controller connected. This mode is intended for GUI testing.
"""

import asyncio
import builtins
import concurrent
import gettext
import logging
import os
import signal
import tempfile
import warnings
from pathlib import Path
from shutil import copyfile
from threading import Thread
from unittest.mock import patch, Mock

import pydbus
from gi.repository import GLib

import sl1fw.tests.mocks.mc_port
from sl1fw import defines, test_runtime
from sl1fw import libPrinter
from sl1fw.admin.manager import AdminManager
from sl1fw.api.admin0 import Admin0
from sl1fw.api.printer0 import Printer0
from sl1fw.api.standard0 import Standard0
from sl1fw.tests import samples
from sl1fw.tests.mocks.dbus.rauc import Rauc

# use system locale settings for translation
gettext.install("sl1fw", defines.localedir, names=("ngettext",))
builtins.N_ = lambda x: x

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s", level=logging.DEBUG)


# Display warnings only once
warnings.simplefilter("once")

temp_dir_obj = tempfile.TemporaryDirectory()
TEMP_DIR = Path(temp_dir_obj.name)
SAMPLES_DIR = Path(samples.__file__).parent
SL1FW_DIR = Path(sl1fw.__file__).parent
HARDWARE_FILE = TEMP_DIR / "sl1fw.hardware.cfg"
copyfile(SAMPLES_DIR / "hardware-virtual.cfg", HARDWARE_FILE)


def change_dir(path):
    return os.path.join(defines.previousPrints, os.path.basename(path))


defines.hwConfigPath = HARDWARE_FILE
defines.factoryConfigPath = str(SL1FW_DIR / ".." / "factory" / "factory.toml")
defines.hwConfigPathFactory = str(SAMPLES_DIR / "hardware.toml")
defines.templates = str(SL1FW_DIR / "intranet" / "templates")
test_runtime.testing = True
test_runtime.hard_exceptions = False
defines.truePoweroff = False
defines.cpuSNFile = str(SAMPLES_DIR / "nvmem")
defines.cpuTempFile = str(SAMPLES_DIR / "cputemp")
defines.multimediaRootPath = str(SL1FW_DIR / "multimedia")
defines.internalProjectPath = str(SAMPLES_DIR)
defines.ramdiskPath = str(TEMP_DIR)
defines.octoprintAuthFile = str(SAMPLES_DIR / "slicer-upload-api.key")
defines.livePreviewImage = str(Path(defines.ramdiskPath) / "live.png")
defines.displayUsageData = str(Path(defines.ramdiskPath) / "display_usage.npz")
defines.serviceData = str(Path(defines.ramdiskPath) / "service.toml")
defines.statsData = str(Path(defines.ramdiskPath) / "stats.toml")
defines.fan_check_override = True
defines.mediaRootPath = str(SAMPLES_DIR)
prev_prints = TEMP_DIR / "previous_prints"
prev_prints.mkdir(exist_ok=True)
defines.previousPrints = str(prev_prints)
defines.lastProjectHwConfig = change_dir(defines.lastProjectHwConfig)
defines.lastProjectFactoryFile = change_dir(defines.lastProjectFactoryFile)
defines.lastProjectConfigFile = change_dir(defines.lastProjectConfigFile)
defines.lastProjectPickler = change_dir(defines.lastProjectPickler)
defines.uvCalibDataPath = str(Path(defines.ramdiskPath) / defines.uvCalibDataFilename)
defines.slicerProfilesFile = TEMP_DIR / defines.profilesFile
defines.loggingConfig = TEMP_DIR / "logging_config.json"
defines.last_job = Path(defines.ramdiskPath) / "last_job"
defines.last_log_token = Path(defines.ramdiskPath) / "last_log_token"
defines.printer_summary = Path(defines.ramdiskPath) / "printer_summary"
defines.firmwareListTemp = str(Path(defines.ramdiskPath) / "updates.json")
defines.slicerProfilesFile = str(Path(defines.ramdiskPath) / "slicer_profiles.toml")
defines.firmwareTempFile = str(Path(defines.ramdiskPath) / "update.raucb")


class Virtual:
    def __init__(self):
        self.printer = None
        self.rauc_mocks = None
        self.glib_loop = None
        self.printer0 = None
        self.standard0 = None
        self.admin_manager = None
        self.admin0_dbus = None

    def __call__(self):
        signal.signal(signal.SIGINT, self.tear_down)
        signal.signal(signal.SIGTERM, self.tear_down)

        with patch("sl1fw.motion_controller.controller.serial", sl1fw.tests.mocks.mc_port), patch(
            "sl1fw.libUvLedMeterMulti.serial", sl1fw.tests.mocks.mc_port
        ), patch("sl1fw.motion_controller.controller.UInput", Mock()), patch(
            "sl1fw.motion_controller.controller.gpio", Mock()
        ), patch("sl1fw.functions.files.get_save_path", self.fake_save_path), patch(
            "sl1fw.screen.screen.Wayland", Mock()):
            print("Resolving system bus")
            bus = pydbus.SystemBus()
            print("Publishing Rauc mock")
            self.rauc_mocks = bus.publish(Rauc.__OBJECT__, ("/", Rauc()))

            print("Running glib mainloop")
            self.glib_loop = GLib.MainLoop()
            Thread(target=self.glib_loop.run, daemon=True).start()

            print("Initializing printer")
            self.printer = libPrinter.Printer()

            print("Overriding printer settings")
            self.printer.hwConfig.calibrated = True
            self.printer.hwConfig.fanCheck = False
            self.printer.hwConfig.coverCheck = False
            self.printer.hwConfig.resinSensor = False

            print("Publishing printer on D-Bus")
            self.printer0 = bus.publish(Printer0.__INTERFACE__, Printer0(self.printer))
            self.standard0 = bus.publish(Standard0.__INTERFACE__, Standard0(self.printer))
            self.admin_manager = AdminManager()
            self.admin0_dbus = bus.publish(Admin0.__INTERFACE__, Admin0(self.admin_manager, self.printer))
            print("Running printer")
            self.printer.run()

            print("Unpublishing Rauc mock")
            self.rauc_mocks.unpublish()

    def tear_down(self, signum, _):
        if signum != signal.SIGTERM:
            return

        print("Running virtual printer tear down")
        asyncio.run(self.async_tear_down())
        print("Virtual printer teardown finished")

    @staticmethod
    def fake_save_path():
        return Path(TEMP_DIR)

    async def async_tear_down(self):
        loop = asyncio.get_running_loop()
        # Run all teardown parts in parallel. Some may block or fail
        with concurrent.futures.ThreadPoolExecutor() as pool:
            tasks = [
                loop.run_in_executor(pool, self.printer.exit),
                loop.run_in_executor(pool, self.rauc_mocks.unpublish),
                loop.run_in_executor(pool, self.glib_loop.quit),
                loop.run_in_executor(pool, self.printer0.unpublish),
                loop.run_in_executor(pool, self.standard0.unpublish),
                loop.run_in_executor(pool, self.admin0_dbus.unpublish),
            ]
        await asyncio.gather(*tasks)


def run_virtual():
    Virtual()()


if __name__ == "__main__":
    run_virtual()