# part of SL1 firmware
# 2014-2018 Futur3d - www.futur3d.net
# 2018-2019 Prusa Research s.r.o. - www.prusa3d.com

import os
import logging
from time import time, sleep
import toml

from sl1fw import defines


class Printer(object):

    def __init__(self, debugDisplay=None):
        startTime = time()

        self.logger = logging.getLogger(__name__)
        self.logger.info("SL1 firmware started - version %s", defines.swVersion)

        from sl1fw import libConfig
        try:
            with open(defines.hwConfigFactoryDefaultsFile, "r") as factory:
                factory_defaults = toml.load(factory)
            #endwith
        except:
            self.logger.exception("Failed to load factory defaults")
            factory_defaults = {}
        #endtry
        self.hwConfig = libConfig.HwConfig(defines.hwConfigFile, defaults = factory_defaults)
        self.hwConfig.logAllItems()
        self.config = libConfig.PrintConfig(self.hwConfig)

        from sl1fw.libHardware import Hardware
        self.hw = Hardware(self.hwConfig, self.config)

        from sl1fw.libInternet import Internet
        self.inet = Internet()

        from sl1fw.libQtDisplay import QtDisplay
        qtdisplay = QtDisplay()

        from sl1fw.libWebDisplay import WebDisplay
        webdisplay = WebDisplay()

        devices = list((qtdisplay, webdisplay))

        from sl1fw.libScreen import Screen
        self.screen = Screen(self.hwConfig)

        from sl1fw.libPages import PageWait
        from sl1fw.pages.start import PageStart
        from sl1fw.libDisplay import Display
        self.display = Display(self.hwConfig, self.config, devices, self.hw, self.inet, self.screen)

        self.hw.connectMC(PageWait(self.display), PageStart(self.display))

        self.inet.startNetMonitor(self.display.assignNetActive)

        self.logger.info("Start time: %f secs", time() - startTime)
    #endclass


    def __del__(self):
        self.exit()
    #enddef


    def exit(self):
        self.screen.exit()
        self.display.exit()
        self.inet.exit()
        self.hw.exit()
    #enddef


    def start(self):
        from sl1fw.libExposure import Exposure
        firstRun = True

        try:
            while True:
                self.hw.uvLed(False)
                self.hw.powerLed("normal")

                self.expo = Exposure(self.hwConfig, self.config, self.display, self.hw, self.screen)
                self.display.initExpo(self.expo)
                self.screen.cleanup()

                if self.hw.checkFailedBoot():
                    self.display.pages['error'].setParams(
                        text=_(
                            "The printer has booted to an alernative boot slot due to a failed boot attempts using the "
                            "primary slot. This can happen after a failed update or due to hardware failure. Printer "
                            "settings may have been reset to factory defaults."))
                    self.display.doMenu("error")
                #endif

                if firstRun:
                    if not self.hwConfig.defaultsSet():
                        self.display.pages['error'].setParams(
                            text=_("Failed to load fans and LEDS factory calibration."))
                        self.display.doMenu("error")
                    #endif

                    if self.hwConfig.showUnboxing:
                        self.hw.beepRepeat(1)
                        self.display.doMenu("unboxing1")
                        sleep(0.5)
                    elif self.hwConfig.showWizard:
                        self.hw.beepRepeat(1)
                        self.display.doMenu("wizard1")
                        sleep(0.5)
                    #endif
                #endif

                self.display.pages['home'].readyBeep = True
                self.display.doMenu("home")
                firstRun = False
            #endwhile

        except Exception:
            self.logger.exception("run() exception:")
            self.hw.powerLed("error")
            self.display.pages['exception'].setParams(text =
                    "An unexpected error has occured :-(.\n\n"
                    "The SL1 will finish the print if you are currently printing.\n\n"
                    "You can turn the printer off by pressing the front power button.\n\n"
                    "Please follow the instructions in Chapter 3.1 in the handbook to learn how to save a log file. Please send the log to us and help us improve the printer.\n\n"
                    "Thank you!")
            self.display.forcePage("exception")
            if hasattr(self, 'expo') and self.expo.inProgress():
                self.expo.waitDone()
            #endif
            self.hw.uvLed(False)
            self.hw.stopFans()
            self.hw.motorsRelease()
            while not self.display.hw.getPowerswitchState():
                sleep(0.5)
            #endwhile
            self.display.shutDown(True)
        #endtry

    #enddef

#endclass
