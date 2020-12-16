# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=no-else-return

import json
import logging
import threading
from time import sleep
from abc import ABC, abstractmethod

from sl1fw import defines
from sl1fw.libConfig import RuntimeConfig
from sl1fw.libHardware import Hardware
from sl1fw.libNetwork import Network
from sl1fw.slicer.profile_downloader import ProfileDownloader
from sl1fw.slicer.profile_parser import ProfileParser
from sl1fw.slicer.slicer_profile import SlicerProfile
from sl1fw.screen.printer_model import PrinterModel


class BackgroundNetworkCheck(ABC):
    def __init__(self, inet: Network, name: str):
        self.logger = logging.getLogger(name)
        self.inet = inet
        self.change_trigger = True
        self.logger.info("Registering net change handler")
        self.inet.net_change.connect(self.connection_changed)

    def connection_changed(self, value):
        if value and self.change_trigger:
            self.logger.info("Starting background network check thread")
            threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        while True:
            run_after = self.check()
            if run_after is None:
                self.logger.warning("Check returned error, waiting for next connection change.")
                break
            self.change_trigger = False
            if not run_after:
                self.logger.debug("Check returned no repeat, exiting thread.")
                break
            self.logger.debug("Check returned repeat after %d secs, sleeping.", run_after)
            sleep(run_after)

    @abstractmethod
    def check(self):
        ...


class AdminCheck(BackgroundNetworkCheck):
    def __init__(self, config: RuntimeConfig, hw: Hardware, inet: Network):
        self.config = config
        self.hw = hw
        super().__init__(inet, "sl1fw.AdminCheck")

    def check(self):
        self.logger.info("Querying admin enabled")
        query_url = defines.admincheckURL + "/?serial=" + self.hw.cpuSerialNo
        try:
            self.inet.download_url(query_url, defines.admincheckTemp)
        except Exception:
            self.logger.exception("download_url exception:")
            return None
        with open(defines.admincheckTemp, "r") as file:
            admin_check = json.load(file)
            result = admin_check.get("result", None)
            if result is None:
                self.logger.warning("Error querying admin enabled")
                return None
            elif result:
                self.config.show_admin = True
                self.logger.info("Admin enabled")
            else:
                self.logger.info("Admin not enabled")
        return 0


class SlicerProfileUpdater(BackgroundNetworkCheck):
    def __init__(self, inet: Network, profile: SlicerProfile, printer_model: PrinterModel):
        self.profile = profile
        self.printer_model = printer_model
        super().__init__(inet, "sl1fw.SlicerProfileUpdater")

    def check(self):
        self.logger.info("Checking slicer profiles update")
        downloader = ProfileDownloader(self.inet, self.profile.vendor)
        new_version = downloader.checkUpdates()
        retc = defines.slicerProfilesCheckOK
        if new_version is None:
            retc = defines.slicerProfilesCheckProblem
        elif new_version:
            f = downloader.download(new_version)
            new_profile = ProfileParser(self.printer_model).parse(f)
            if new_profile and new_profile.save(filename = defines.slicerProfilesFile):
                self.profile.data = new_profile.data
            else:
                self.logger.info("Problem with new profile file, giving up")
                retc = defines.slicerProfilesCheckProblem
        else:
            self.logger.info("No new version of slicer profiles available")
        return retc