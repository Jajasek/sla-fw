# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# TODO: Fix following pylint problems
# pylint: disable=inconsistent-return-statements

import os
import numpy
from PIL import Image
from prusaerrors.sl1.codes import Sl1Codes

from sl1fw import defines
from sl1fw.pages import page
from sl1fw.pages.base import Page
from sl1fw.libConfig import TomlConfigStats

@page
class PageService(Page):
    Name = "service"

    def __init__(self, display):
        super(PageService, self).__init__(display)
        self.pageUI = "admin"
        self.pageTitle = "Service"
    #enddef


    def show(self):
        stats = TomlConfigStats(defines.statsData, self.display.hw)
        stats.load()
        minutes = stats['total_seconds'] // 60
        self.items.update({
                'button1' : "TODO",

                'button6' : "Started projects: %d" % stats['started_projects'],
                'button7' : "Layers: %d" % stats['layers'],
                'button8' : "Total time: %(hour)dh%(minute)02dm" % {'hour' : minutes // 60, 'minute' : minutes % 60},
                'button9' : "Total resin: %.3fml" % stats['total_resin'],
                'button10' : "Display usage heatmap",
                'button11' :"Finished projects: %d" % stats['finished_projects'],

                })
        super(PageService, self).show()
    #enddef


    @staticmethod
    def button10ButtonRelease():
        return "displayusage"
    #enddef

#endclass


@page
class PageDisplayUsage(Page):
    Name = "displayusage"

    def __init__(self, display):
        super(PageDisplayUsage, self).__init__(display)
        self.pageUI = "picture"
        self.pageTitle = "Display usage heatmap"
        self.palette = None
        try:
            paletteBytes = bytes()
            with open(defines.displayUsagePalette, "r") as f:
                for line in f:
                    paletteBytes += bytes.fromhex(line.strip()[1:])
                #endfor
            #endwith
            self.palette = list(paletteBytes)
        except Exception:
            self.logger.exception("load palette failed")
        #endtry
    #enddef


    def prepare(self):
        try:
            with numpy.load(defines.displayUsageData) as npzfile:
                savedData = npzfile['display_usage']
            #endwith
        except Exception:
            self.logger.exception("load display usage failed")
            savedData = None
        #endtry

        if savedData is None:
            self.logger.error("No display suage data to show")
            self.display.pages['error'].setParams(code=Sl1Codes.NO_DISPLAY_USAGE_DATA.raw_code)
            return "error"
        #endif

        if savedData.shape != defines.display_usage_size:
            self.logger.warning("Wrong saved data shape: %s", savedData.shape)
            self.display.pages['error'].setParams(code=Sl1Codes.NO_DISPLAY_USAGE_DATA.raw_code)
            return "error"
        #endif

        imagePath = os.path.join(defines.ramdiskPath, "displayhm.png")
        self.generateDisplayUsageHeatmap(imagePath, savedData)
        self.setItems(image_path = "file://%s" % imagePath)
    #enddef


    def generateDisplayUsageHeatmap(self, filename, data):
        maxValue = data.max()
        # 0-255 range
        data = data * 255 / maxValue
        image = Image.fromarray(data.astype('int8'), 'P')
        if self.palette:
            image.putpalette(self.palette)
        #endif
        trans = image.transpose(Image.ROTATE_270)
        trans.save(filename)
    #enddef


    @staticmethod
    def _EXIT_():
        return "_EXIT_"
    #enddef


    @staticmethod
    def _BACK_():
        return "_BACK_"
    #enddef

#endclass
