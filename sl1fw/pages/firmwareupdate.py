# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from glob import glob
from os import path
from time import sleep

import pydbus
from prusaerrors.sl1.codes import Sl1Codes

from sl1fw import defines
from sl1fw.api.decorators import wrap_exception
from sl1fw.errors.errors import DownloadFailed
from sl1fw.errors.exceptions import get_exception_code
from sl1fw.functions.system import shut_down
from sl1fw.pages import page
from sl1fw.pages.base import Page
from sl1fw.pages.wait import PageWait


@page
class PageFirmwareUpdate(Page):
    Name = "firmwareupdate"

    def __init__(self, display):
        super().__init__(display)
        self.pageUI = "firmwareupdate"
        self.old_items = None
        self.pageTitle = "Firmware update"
        self.rauc = pydbus.SystemBus().get("de.pengutronix.rauc", "/")["de.pengutronix.rauc.Installer"]
        self.updateDataPeriod = 1

    def fillData(self):
        # Get list of available firmware files on USB
        fw_files = glob(path.join(defines.mediaRootPath, "**/*.raucb"))

        # Get Rauc flasher status and progress
        operation = None
        progress = None
        try:
            operation = self.rauc.Operation
            progress = self.rauc.Progress
        except Exception as e:
            self.logger.error("Rauc status read failed: %s", str(e))

        return {
            "firmwares": fw_files,
            "operation": operation,
            "progress": progress,
        }

    def show(self):
        self.items.update(self.fillData())
        super().show()
        self.showItems(**self.items)

    def updateData(self):
        items = self.fillData()
        if self.old_items != items:
            self.showItems(**items)
            self.old_items = items

    def flashButtonSubmit(self, data):
        fw_url = data["firmware"]
        self.display.pages["yesno"].setParams(
            yesFce=self.fetchUpdate, yesParams={"fw_url": fw_url}, text=_("Do you really want to update the firmware?")
        )
        return "yesno"

    def fetchUpdate(self, fw_url):
        try:
            pageWait = PageWait(self.display, line1=_("Fetching firmware"))
            pageWait.show()
            self.display.inet.download_url(fw_url, defines.firmwareTempFile, page=pageWait)
        except DownloadFailed as exception:
            self.logger.exception("Firmware fetch failed")
            self.display.pages["error"].setParams(
                code=get_exception_code(exception).raw_code,
                params=wrap_exception(exception)
            )
            return "error"

        return self.doUpdate(defines.firmwareTempFile)

    def doUpdate(self, fw_file):
        self.logger.info("Flashing: %s", fw_file)
        try:
            rauc = pydbus.SystemBus().get("de.pengutronix.rauc", "/")["de.pengutronix.rauc.Installer"]
            rauc.Install(fw_file)
        except Exception as e:
            self.logger.error("Rauc install call failed: %s", str(e))

        pageWait = PageWait(self.display, line1=_("Updating the firmware"))
        pageWait.show()

        try:
            while True:
                progress = self.rauc.Progress

                pageWait.showItems(line2=progress[1], line3="%d%%" % progress[0])

                # Check progress for update done
                if progress[1] == "Installing done.":
                    pageWait.showItems(line1=_("Update done"), line2=_("Shutting down"))
                    sleep(3)
                    shut_down(self.display.hw, True)

                # Check for operation failure
                if progress[1] == "Installing failed.":
                    raise Exception("Update failed")

                # Wait for a while
                sleep(1)

        except Exception:
            self.logger.exception("Rauc update failed")
            self.display.pages["error"].setParams(code=Sl1Codes.UPDATE_FAILED.raw_code)
            return "error"

    def _eraseProjectsYes(self):
        self.display.pages["factoryreset"].eraseProjects = True
        return "factoryreset"

    def _eraseProjectsNo(self):
        self.display.pages["factoryreset"].eraseProjects = False
        return "factoryreset"

    # Factory reset
    def factoryresetButtonRelease(self): # pylint: disable=no-self-use
        if self.display.runtime_config.factory_mode:
            return self._eraseProjectsNo()
        self.display.pages["yesno"].setParams(pageTitle=_("Erase projects?"),
            text=_("Do you want to erase all projects on Internal storage?\nProjects will be erased during the Factory reset."),
            yesFce=self._eraseProjectsYes,
            noFce=self._eraseProjectsNo)
        return "yesno"
    #enddef