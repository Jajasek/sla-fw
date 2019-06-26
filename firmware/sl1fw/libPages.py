# part of SL1 firmware
# -*- coding: utf-8 -*-
# 2014-2018 Futur3d - www.futur3d.net
# 2018-2019 Prusa Research s.r.o. - www.prusa3d.com

import os
import logging
from time import time, sleep
import toml
import subprocess
import glob

# Python 2/3 imports
try:
    from urllib.parse import urlparse, urlencode
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
except ImportError:
    # TODO: Remove once we accept Python 3
    from urlparse import urlparse
    from urllib import urlencode
    from urllib2 import urlopen, Request, HTTPError
#endtry

from sl1fw import defines
from sl1fw import libConfig


class PageRegistry(object):
    def __init__(self):
        self._pages = {}

    def __call__(self, page_class):
        self._pages[page_class.Name] = page_class
        return page_class
    #enddef

    def getpages(self):
        return self._pages
    #enddef

#endclass


page = PageRegistry()


class Page(object):

    def __init__(self, display):
        self.pageUI = "splash"
        self.pageTitle = ""
        self.logger = logging.getLogger(__name__)
        self.display = display
        self.autorepeat = {}
        self.stack = True
        self.items = dict()

        self.updateDataPeriod = None

        # callback options
        self.callbackPeriod = 0.5
        self.checkPowerbutton = True
        self.checkCover = False
        self.checkCoverOveride = False   # to force off when exposure is in progress
        self.checkCooling = False

        # vars for checkCoverCallback()
        self.checkCoverBeepDelay = 2
        self.checkCoverWarnOnly = True
        self.checkCoverUVOn = False
        # vars for powerButtonCallback()
        self.powerButtonCount = 0
        # vars for checkCoolingCallback()
        self.checkCooligSkip = 20   # 10 sec
        self.checkOverTempSkip = 20   # 10 sec
    #enddef


    @property
    def octoprintAuth(self):
        try:
            with open(defines.octoprintAuthFile, "r") as f:
                return f.read()
            #endwith
        except IOError as e:
            self.logger.exception("octoprintAuthFile exception: %s" % str(e))
            return None
        #endtry
    #enddef


    def prepare(self):
        pass
    #enddef


    def leave(self):
        '''Override this to modify page this page is left for.'''
        pass
    #enddef


    def show(self):
        # renew save path every time when page is shown, it may change
        self.items.update({
            'save_path' : self.getSavePath(),
            'image_version' : "%s%s" % (self.display.hwConfig.os.versionId, _(" (factory mode)") if self.display.hwConfig.factoryMode else ""),
            'page_title' : _(self.pageTitle),
            })

        for device in self.display.devices:
            device.setPage(self.pageUI)
            device.setItems(self.items)
            device.showPage()
        #endfor
    #enddef


    def showItems(self, **kwargs):
        self.items.update(kwargs)
        for device in self.display.devices:
            device.showItems(kwargs)
        #endfor
    #enddef


    def setItems(self, **kwargs):
        self.items.update(kwargs)
    #enddef


    def emptyButton(self):
        self.logger.debug("emptyButton() called")
    #enddef


    def emptyButtonRelease(self):
        self.logger.debug("emptyButtonRelease() called")
    #enddef


    def backButtonRelease(self):
        return "_BACK_"
    #enddef


    def wifiButtonRelease(self):
        return "netinfo"
    #enddef


    def infoButtonRelease(self):
        return "about"
    #enddef


    def turnoffButtonRelease(self):
        self.display.pages['yesno'].setParams(
                yesFce = self.turnoffContinue,
                text = _("Do you really want to turn off the printer?"))
        return "yesno"
    #enddef


    def turnoffContinue(self):
        self.display.shutDown(True)
    #enddef


    def netChange(self):
        pass
    #enddef


    # List paths to successfully mounted partitions found on currently attached removable storage devices.
    def getSavePaths(self):
        return [p for p in glob.glob(os.path.join(defines.mediaRootPath, '*')) if os.path.ismount(p)]
    #enddef

    # Dynamic USB path, first usb device or None
    def getSavePath(self):
        usbs = self.getSavePaths()
        if len(usbs) == 0:
            self.logger.debug("getSavePath returning None, no media seems present")
            return None
        #endif
        return usbs[0]
    #enddsef


    def downloadURL(self, url, dest, title=None, timeout_sec=10):
        """Fetches file specified by url info destination while displaying progress. This is implemented as chunked
        copy from source file descriptor to the deestination file descriptor. The progress is updated once the cunk is
        copied. The source file descriptor is either standard file when the source is mounted USB drive or urlopen
        result."""

        if not title:
            title = _("Fetching")
        #endif
        pageWait = PageWait(self.display, line1=title, line2="0%")
        pageWait.show()

        self.logger.info("Downloading %s" % url)

        if url.startswith("http://") or url.startswith("https://"):
            # URL is HTTP, source is url
            req = Request(url)
            req.add_header('User-Agent', 'Prusa-SL1')
            req.add_header('Prusa-SL1-version', self.display.hwConfig.os.versionId)
            req.add_header('Prusa-SL1-serial', self.display.hw.cpuSerialNo)
            source = urlopen(req, timeout=timeout_sec)

            # Default files size (sometimes HTTP server does not know size)
            file_size = None

            # Try to read header using Python 3 API
            try:
                file_size = int(source.info().get("Content-Length"))
            except:
                self.logger.exception("Failed to read file content length header Python 3 way")

                # Try to header read using Python 2 API
                try:
                    # TODO: Remove once we accept Python3
                    file_size = int(source.info().getheaders("Content-Length")[0])
                except:
                    self.logger.exception("Failed to read file content length header Python 2 way")
                #endtry
            #endtry

            block_size = 8 * 1024
        else:
            # URL is file, source is file
            self.logger.info("Copying firmware %s" % url)
            source = open(url, "rb")
            file_size = os.path.getsize(url)
            block_size = 1024 * 1024
        #endif

        with open(dest, 'wb') as file:
            old_progress = 0
            while True:
                buffer = source.read(block_size)
                if not buffer or buffer == '':
                    break
                #endif
                file.write(buffer)

                if file_size is not None:
                    progress = int(100 * file.tell() / file_size)
                else:
                    progress = 0
                #endif

                if progress != old_progress:
                    pageWait.showItems(line2="%d%%" % progress)
                    old_progress = progress
                #endif
            #endwhile

            if file_size and file.tell() != file_size:
                raise Exception("Download of %s failed to read whole file %d != %d", url, file_size, file.tell())
            #endif
        #endwith

        source.close()
    #enddef


    def ensureCoverIsClosed(self):
        if not self.display.hwConfig.coverCheck or self.display.hw.isCoverClosed():
            return
        #endif
        self.display.hw.powerLed("warn")
        pageWait = PageWait(self.display,
                line1 = _("Close the orange cover."),
                line2 = _("If the cover is closed, please check the connection of the cover switch."))
        pageWait.show()
        self.display.hw.beepAlarm(3)
        #endif
        while not self.display.hw.isCoverClosed():
            sleep(0.5)
        #endwhile
        self.display.hw.powerLed("normal")
    #enddef


    def saveLogsToUSB(self):
        save_path = self.getSavePath()
        if save_path is None:
            self.display.pages['error'].setParams(text=_("No USB storage present"))
            return "error"
        #endif

        pageWait = PageWait(self.display, line1=_("Saving logs"))
        pageWait.show()

        timestamp = str(int(time()))
        serial = self.display.hw.cpuSerialNo
        log_file = os.path.join(save_path, "log.%s.%s.txt.gz" % (serial, timestamp))

        try:
            subprocess.check_call(
                ["/bin/sh", "-c", "journalctl | gzip > %s; sync" % log_file])
        except subprocess.CalledProcessError as e:
            self.display.pages['error'].setParams(text=_("Log save failed"))
            return "error"
        #endexcept

        return "_BACK_"
    #enddef


    def writeToFactory(self, saveFce):
        try:
            self.logger.info("Remounting factory partition rw")
            subprocess.check_call(["/usr/bin/mount", "-o", "remount,rw", defines.factoryMountPoint])
            saveFce()
        except:
            self.logger.exception("Failed to save to factory partition")
            return False
        finally:
            try:
                self.logger.info("Remounting factory partition ro")
                subprocess.check_call(["/usr/bin/mount", "-o", "remount,ro", defines.factoryMountPoint])
            except:
                self.logger.exception("Failed to remount factory partion ro")
            #endtry
        #endtry
        return True
    #enddef


    def saveDefaultsFile(self):
        defaults = {
            'fan1pwm': self.display.hwConfig.fan1Pwm,
            'fan2pwm': self.display.hwConfig.fan2Pwm,
            'fan3pwm': self.display.hwConfig.fan3Pwm,
            'uvpwm': self.display.hwConfig.uvPwm,
        }

        with open(defines.hwConfigFactoryDefaultsFile, "w") as file:
            toml.dump(defaults, file)
        #endwith

        self.display.hwConfig._defaults = defaults
    #enddef


    def _onOff(self, temp, changed, index, val):
        if isinstance(temp[val], libConfig.MyBool):
            temp[val].inverse()
        else:
            temp[val] = not temp[val]
        #endif
        changed[val] = str(temp[val])
        self.showItems(**{ 'state1g%d' % (index + 1) : int(temp[val]) })
    #enddef


    def _value(self, temp, changed, index, val, valmin, valmax, change, strFce = str):
        if valmin <= temp[val] + change <= valmax:
            temp[val] += change
            changed[val] = str(temp[val])
            self.showItems(**{ 'value2g%d' % (index + 1) : strFce(temp[val]) })
        else:
            self.display.hw.beepAlarm(1)
        #endif
    #enddef


    def _setItem(self, items, oldValues, index, value):
        if oldValues.get(index, None) != value:
            if isinstance(value, bool):
                items[index] = int(value)
            elif isinstance(value, dict):
                items[index] = value
            else:
                items[index] = str(value)
            #endif
            oldValues[index] = value
        #endif
    #enddef


    def _syncTower(self, pageWait):
        self.display.hw.towerSync()
        while not self.display.hw.isTowerSynced():
            sleep(0.25)
            pageWait.showItems(line2 = self.display.hw.getTowerPosition())
        #endwhile
        if self.display.hw.towerSyncFailed():
            self.display.pages['error'].setParams(
                    text = _("Tower homing failed!\n\n"
                        "Check the printer's hardware."))
            return "error"
        #endif
        return "_SELF_"
    #enddef


    def _syncTilt(self):
        if not self.display.hw.tiltSyncWait(retries = 2):
            self.display.pages['error'].setParams(
                    text = _("Tilt homing failed!\n\n"
                        "Check the printer's hardware."))
            return "error"
        #endif
        return "_SELF_"
    #enddef


    def _strZHop(self, value):
        return "%.3f" % self.display.hwConfig.calcMM(value)
    #enddef


    def _strOffset(self, value):
        return "%+.3f" % self.display.hwConfig.calcMM(value)
    #enddef


    def _strTenth(self, value):
        return "%.1f" % (value / 10.0)
    #enddef


    def countRemainTime(self, actualLayer, slowLayers):
        config = self.display.config
        hwConfig = self.display.hwConfig
        timeRemain = 0
        fastLayers = config.totalLayers - actualLayer - slowLayers
        # first 3 layers with expTimeFirst
        long1 = 3 - actualLayer
        if long1 > 0:
            timeRemain += long1 * (config.expTimeFirst - config.expTime)
        #endif
        # fade layers (approx)
        long2 = config.fadeLayers + 3 - actualLayer
        if long2 > 0:
            timeRemain += long2 * ((config.expTimeFirst - config.expTime) / 2 - config.expTime)
        #endif
        timeRemain += fastLayers * hwConfig.tiltFastTime
        timeRemain += slowLayers * hwConfig.tiltSlowTime

        # FIXME slice2 and slice3
        timeRemain += (fastLayers + slowLayers) * (
                config.calibrateRegions * config.calibrateTime
                + self.display.hwConfig.calcMM(config.layerMicroSteps) * 5  # tower move
                + config.expTime
                + hwConfig.delayBeforeExposure
                + hwConfig.delayAfterExposure)
        self.logger.debug("timeRemain: %f", timeRemain)
        return int(round(timeRemain / 60))
    #enddef


    def callback(self):

        state = False
        if self.checkPowerbutton:
            state = True
            retc = self.powerButtonCallback()
            if retc:
                return retc
            #endif
        #endif

        expoInProgress = self.display.expo.inProgress()

        if not self.checkCoverOveride and (self.checkCover or expoInProgress):
            state = True
            self.checkCoverCallback()
        #endif

        if self.checkCooling or (expoInProgress and self.display.checkCoolingExpo):
            state = True
            retc = self.checkCoolingCallback(expoInProgress)
            if retc:
                return retc
            #endif
        #endif

        # always check the over temp
        self.checkOverTempCallback()

        if not state:
            # just read status from the MC to prevent the power LED pulsing
            self.display.hw.getPowerswitchState()
        #endif
    #enddef


    def powerButtonCallback(self):
        if not self.display.hw.getPowerswitchState():
            if self.powerButtonCount:
                self.powerButtonCount = 0
                self.display.hw.powerLed("normal")
            #endif
            return
        #endif

        if self.powerButtonCount > 0:
            self.display.hw.powerLed("normal")
            self.display.hw.beepEcho()
            return self.turnoffButtonRelease()
        #endif

        if not self.powerButtonCount:
            self.display.hw.powerLed("off")
            self.display.hw.beepEcho()
        #endif

        self.powerButtonCount += 1
    #enddef


    def checkCoverCallback(self):
        if not self.display.hwConfig.coverCheck or self.display.hw.isCoverClosed():
            self.checkCoverBeepDelay = 2
            return
        #endif

        if self.checkCoverWarnOnly:
            if self.checkCoverBeepDelay > 1:
                self.display.hw.beepAlarm(2)
                self.checkCoverBeepDelay = 0
            else:
                self.checkCoverBeepDelay += 1
            #endif
        else:
            self.display.hw.uvLed(False)
            self.display.hw.powerLed("warn")
            pageWait = PageWait(self.display, line1 = _("Close the orange cover."))
            pageWait.show()
            self.display.hw.beepAlarm(3)
            while not self.display.hw.isCoverClosed():
                sleep(0.5)
            #endwhile
            self.display.hw.powerLed("normal")
            self.show()
            if self.checkCoverUVOn:
                self.display.hw.uvLed(True)
            #endif
        #endif
    #enddef


    def checkCoolingCallback(self, expoInProgress):
        if self.checkCooligSkip < 20:
            self.checkCooligSkip += 1
            return
        #endif
        self.checkCooligSkip = 0

        # UV LED temperature test
        temp = self.display.hw.getUvLedTemperature()
        if temp < 0:
            if expoInProgress:
                self.display.expo.doPause()
                self.display.checkCoolingExpo = False
                backFce = self.exitPrint
                addText = _("Actual job will be canceled.")
            else:
                self.display.hw.uvLed(False)
                backFce = self.backButtonRelease
                addText = ""
            #endif

            self.display.pages['error'].setParams(
                    backFce = backFce,
                    text = _("Reading of UV LED temperature has failed!\n\n"
                        "This value is essential for the UV LED lifespan and printer safety.\n\n"
                        "Please contact tech support!\n\n"
                        "%s") % addText)
            return "error"
        #endif

        if temp > defines.maxUVTemp:
            if expoInProgress:
                self.display.expo.doPause()
            else:
                self.display.hw.uvLed(False)
            #enddef
            self.display.hw.powerLed("error")
            pageWait = PageWait(self.display, line1 = _("UV LED OVERHEAT!"), line2 = _("Cooling down"))
            pageWait.show()
            self.display.hw.beepAlarm(3)
            while(temp > defines.maxUVTemp - 10): # hystereze
                pageWait.showItems(line3 = _("Temperature is %.1f C") % temp)
                sleep(10)
                temp = self.display.hw.getUvLedTemperature()
            #endwhile
            self.display.hw.powerLed("normal")
            self.show()
            if expoInProgress:
                self.display.expo.doContinue()
            #enddef
        #endif

        # fans test
        if not self.display.hwConfig.fanCheck or self.display.fanErrorOverride:
            return
        #endif

        fansState = self.display.hw.getFansError()
        if any(fansState):
            failedFans = []
            for num, state in enumerate(fansState):
                if state:
                    failedFans.append(self.display.hw.getFanName(num))
                #endif
            #endfor

            self.display.fanErrorOverride = True

            if expoInProgress:
                backFce = self.exitPrint
                addText = _("Expect overheating, but the print may continue.\n\n"
                        "If you don't want to continue, please press the Back button on top of the screen and the actual job will be canceled.")
            else:
                backFce = self.backButtonRelease
                addText = ""
            #endif

            self.display.pages['confirm'].setParams(
                    backFce = backFce,
                    continueFce = self.backButtonRelease,
                    beep = True,
                    text = _("Failed: %(what)s\n\n"
                        "Please contact tech support!\n\n"
                        "%(addText)s") % { 'what' : ", ".join(failedFans), 'addText' : addText })
            return "confirm"
        #endif
    #enddef


    def checkOverTempCallback(self):
        if self.checkOverTempSkip < 20:
            self.checkOverTempSkip += 1
            return
        #endif
        self.checkOverTempSkip = 0

        A64temperature = self.display.hw.getCpuTemperature()
        if A64temperature > defines.maxA64Temp - 10: # 60 C
            self.logger.warning("Printer is overheating! Measured %.1f °C on A64.", A64temperature)
            self.display.hw.startFans()
            #self.checkCooling = True #shouldn't this start the fan check also?
        #endif
        '''
        do not shut down the printer for now
        if A64temperature > defines.maxA64Temp: # 70 C
            self.logger.warning("Printer is shuting down due to overheat! Measured %.1f °C on A64.", A64temperature)
            self.display.pages['error'].setParams(
                text = _("Printers temperature is too high. Measured: %.1f °C!\n\n"
                    "Shutting down in 10 seconds") % A64temperature)
            self.display.pages['error'].show()
            for i in range(10):
                self.display.hw.beepAlarm(3)
                sleep(1)
            #endfor
            self.display.shutDown(True)
            return "error"
        #endif
        '''
    #enddef


    def exitPrint(self):
        self.display.expo.doExitPrint()
        self.display.expo.canceled = True
        self.display.setWaitPage(line1 = _("Job will be canceled after layer finish"))
        return "_SELF_"
    #enddef


    def ramdiskCleanup(self):
        project_files = []
        for ext in defines.projectExtensions:
            project_files.extend(glob.glob(defines.ramdiskPath + "/*" + ext))
        #endfor
        for project_file in project_files:
            self.logger.debug("removing '%s'", project_file)
            try:
                os.remove(project_file)
            except Exception as e:
                self.logger.exception("ramdiskCleanup() exception:")
            #endtry
        #endfor
    #enddef


    def allOff(self):
        self.display.screen.getImgBlack()
        self.display.hw.uvLed(False)
        self.display.hw.stopFans()
        self.display.hw.motorsRelease()
    #enddef


    def getMeasPwms(self):
        br = self.display.hw.mcBoardRevisionBin
        if br[0] >= 6 and br[1] >= 2:
            self.measMinPwm = defines.uvLedMeasMinPwm500k
            self.measMaxPwm = defines.uvLedMeasMaxPwm500k
        else:
            self.measMinPwm = defines.uvLedMeasMinPwm
            self.measMaxPwm = defines.uvLedMeasMaxPwm
        #endif
    #enddef

#endclass


@page
class PageWait(Page):
    Name = "wait"

    def __init__(self, display, **kwargs):
        super(PageWait, self).__init__(display)
        self.pageUI = "wait"
        self.pageTitle = N_("Please wait")
        self.items.update(kwargs)
    #enddef


    def fill(self, **kwargs):
        self.items = kwargs
    #enddef

#endclass
