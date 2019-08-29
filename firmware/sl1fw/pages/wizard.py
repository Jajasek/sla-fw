# part of SL1 firmware
# -*- coding: utf-8 -*-
# 2014-2018 Futur3d - www.futur3d.net
# 2018-2019 Prusa Research s.r.o. - www.prusa3d.com

import re
from time import sleep
from gettext import ngettext
import pygame

from sl1fw import defines
from sl1fw import libConfig
from sl1fw.pages import page
from sl1fw.libPages import Page, PageWait


@page
class PageWizardInit(Page):
    Name = "wizardinit"

    def __init__(self, display):
        super(PageWizardInit, self).__init__(display)
        self.pageUI = "confirm"
        self.pageTitle = N_("Setup wizard step 1/10")
    #enddef


    def show(self):
        self.items.update({
            'text' : _("Welcome to the setup wizard.\n\n"
                "This procedure is mandatory and it will help you to set up the printer.")})
        super(PageWizardInit, self).show()
    #enddef


    def contButtonRelease(self):
        # check serial numbers
        if (not re.match(r"CZPX\d{4}X009X[C|K]\d{5}", self.display.hw.cpuSerialNo) or
        not re.match(r"CZPX\d{4}X012X[C|K|0|1]\d{5}", self.display.hw.mcSerialNo)):
# FIXME we don't want cut off betatesters with MC without serial number
            self.display.pages['error'].setParams(
                backFce = self.justContinue, # use as confirm
                text = _("Serial numbers in wrong format!\n\n"
                    "A64: %(a64)s\n"
                    "MC: %(mc)s\n"
                    "Please contact tech support!"
                    % {'a64' : self.display.hw.cpuSerialNo, 'mc' : self.display.hw.mcSerialNo}))
            return "error"

        #endif
        return self.justContinue() # only for confirm, join with contButtonContinue() when changed to error
    #enddef


    def justContinue(self):
        self.display.hw.powerLed("warn")
        homeStatus = 0

        #tilt home check
        pageWait = PageWait(self.display, line1 = _("Tilt home check"))
        pageWait.show()
        for i in range(3):
            self.display.hw.mcc.do("!tiho")
            while self.display.hw.mcc.doGetInt("?tiho") > 0:
                sleep(0.25)
            #endwhile
            homeStatus = self.display.hw.mcc.doGetInt("?tiho")
            if homeStatus == -2:
                self.display.pages['error'].setParams(
                    text = _("Tilt endstop not reached!\n\n"
                        "Please check if the tilt motor and optical endstop are connected properly."))
                return "error"
            elif homeStatus == 0:
                self.display.hw.tiltHomeCalibrateWait()
                self.display.hw.setTiltPosition(0)
                break
            #endif
        #endfor
        if homeStatus == -3:
            self.display.pages['error'].setParams(
                text = _("Tilt home check failed!\n\n"
                    "Please contact tech support!\n\n"
                    "Tilt profiles need to be changed."))
            return "error"
        #endif

        #tilt length measure
        pageWait.showItems(line1 = _("Tilt axis check"))
        self.display.hw.setTiltProfile("homingFast")
        self.display.hw.tiltMoveAbsolute(self.display.hw._tiltEnd)
        while self.display.hw.isTiltMoving():
            sleep(0.25)
        #endwhile
        self.display.hw.tiltMoveAbsolute(512)   # go down fast before endstop
        while self.display.hw.isTiltMoving():
            sleep(0.25)
        #endwhile
        self.display.hw.setTiltProfile("homingSlow")    #finish measurement with slow profile (more accurate)
        self.display.hw.tiltMoveAbsolute(self.display.hw._tiltMin)
        while self.display.hw.isTiltMoving():
            sleep(0.25)
        #endwhile
        #TODO make MC homing more accurate
        if self.display.hw.getTiltPosition() < -defines.tiltHomingTolerance or self.display.hw.getTiltPosition() > defines.tiltHomingTolerance:
            self.display.pages['error'].setParams(
                text = _("Tilt axis check failed!\n\n"
                    "Current position: %d\n\n"
                    "Please check if the tilting mechanism can move smoothly in its entire range.") % self.display.hw.getTiltPosition())
            return "error"
        #endif
        self.display.hw.setTiltProfile("homingFast")
        self.display.hw.tiltMoveAbsolute(defines.defaultTiltHeight)
        while self.display.hw.isTiltMoving():
            sleep(0.25)
        #endwhile

        #tower home check
        pageWait.showItems(line1 = _("Tower home check"))
        towerSensitivity = -1    # use default sesnsitivity first, then try from 0
        i = 0
        while True:
            self.display.hw.mcc.do("!twho")
            while self.display.hw.mcc.doGetInt("?twho") > 0:
                sleep(0.25)
            #endwhile
            homeStatus = self.display.hw.mcc.doGetInt("?twho")
            if homeStatus == 0:
                i += 1
                if i > 3:
                    break
                #endif
            elif homeStatus == -2:
                self.display.pages['error'].setParams(
                    text = _("Tower endstop not reached!\n\n"
                        "Please check if the tower motor is connected properly."))
                return "error"
            elif homeStatus == -3:  #if homing failed try different tower homing profiles (only positive values of motor sensitivity)
                towerSensitivity += 1   #try next motor sensitivity
                self.logger.debug("tower sensitivity: %d", towerSensitivity)
                if towerSensitivity >= len(self.display.hw.towerAdjust['homingFast']) - 2:
                    self.display.pages['error'].setParams(
                        text = _("Tower home check failed!\n\n"
                            "Please contact tech support!\n\n"
                            "Tower profiles need to be changed."))
                    return "error"
                self.display.hw.updateMotorSensitivity(self.display.hwConfig.tiltSensitivity, towerSensitivity)
                i = 0   #start over tower home check
                continue
            #endif
        #endwhile
        self.display.hwConfig.towerSensitivity = towerSensitivity
        self.display.hw.towerHomeCalibrateWait()
        self.display.hw.setTowerPosition(self.display.hw._towerEnd)
        self.display.wizardData.update(
            towerSensitivity = self.display.hwConfig.towerSensitivity)
        self.display.hwConfig.update(
            towerSensitivity = self.display.hwConfig.towerSensitivity)
        if not self.display.hwConfig.writeFile():
            self.display.pages['error'].setParams(
                text = _("Cannot save wizard configuration"))
            return "error"
        #endif

        # temperature check
        pageWait.showItems(line1 = _("A64 temperature check"))
        A64temperature = self.display.hw.getCpuTemperature()
        if A64temperature > defines.maxA64Temp:
            self.display.pages['error'].setParams(
                text = _("A64 temperature is too high. Measured: %.1f °C!\n\n"
                    "Shutting down in 10 seconds...") % A64temperature)
            self.display.pages['error'].show()
            for i in range(10):
                self.display.hw.beepAlarm(3)
                sleep(1)
            #endfor
            self.display.shutDown(True)
            return "error"
        #endif

        pageWait.showItems(line1 = _("Thermistors temperature check"))
        temperatures = self.display.hw.getMcTemperatures()
        for i in range(2):
            if temperatures[i] < 0:
                self.display.pages['error'].setParams(
                    text = _("Can't read %s\n\n"
                        "Please check if temperature sensors are connected correctly.") % self.display.hw.getSensorName(i))
                return "error"
            #endif
            if i == 0:
                maxTemp = defines.maxUVTemp
            else:
                maxTemp = defines.maxAmbientTemp
            #endif
            if not defines.minAmbientTemp < temperatures[i] < maxTemp:
                self.display.pages['error'].setParams(
                    text = _("%(sensor)s not in range!\n\n"
                        "Measured temperature: %(temp).1f °C.\n\n"
                        "Keep the printer out of direct sunlight at room temperature (18 - 32 °C).")
                    % { 'sensor' : self.display.hw.getSensorName(i), 'temp' : temperatures[i] })
                return "error"
            #endif
        #endfor
        self.display.wizardData.update(
                wizardTempA64 = A64temperature,
                wizardTempUvInit = temperatures[0],
                wizardTempAmbient = temperatures[1])
        self.display.hw.powerLed("normal")

        return "fantest"
    #enddef


    def backButtonRelease(self):
        return "wizardskip"
    #enddef


    def _BACK_(self):
        return "wizarduvled"
    #enddef


    def _EXIT_(self):
        self.allOff()
        return "_EXIT_"
    #enddef

#endclass


@page
class PageWizardUvLed(Page):
    Name = "wizarduvled"

    def __init__(self, display):
        super(PageWizardUvLed, self).__init__(display)
        self.pageUI = "confirm"
        self.pageTitle = N_("Setup wizard step 2/10")
    #enddef


    def show(self):
        self.items.update({
            'imageName' : "19_remove_tank.jpg",
            'text' : _("Please unscrew and remove the resin tank.")})
        super(PageWizardUvLed, self).show()
    #enddef

    def contButtonRelease(self):
        self.display.pages['confirm'].setParams(
            continueFce = self.continueCloselid,
            backFce = self.backButtonRelease,
            pageTitle = N_("Setup wizard step 3/10"),
            imageName = "09_remove_platform.jpg",
            text = _("Loosen the black knob and remove the platform."))
        return "confirm"
    #enddef


    def continueCloselid(self):
        self.display.pages['confirm'].setParams(
            continueFce = self.continueUvCheck,
            backFce = self.backButtonRelease,
            pageTitle = N_("Setup wizard step 4/10"),
            imageName = "18_close_cover_no_tank.jpg",
            text = _("Please close the orange lid."))
        return "confirm"
    #enddef


    def continueUvCheck(self):
        self.ensureCoverIsClosed()
        self.display.hw.startFans()
        # UV LED voltage comparation
        pageWait = PageWait(self.display, line1 = _("UV LED check"))
        pageWait.show()
        self.display.hw.uvLedPwm = 0
        self.display.hw.uvLed(True)
        br = self.display.hw.mcBoardRevisionBin
        if br[0] >= 6 and br[1] >= 2:
            uvPwms = [40, 122, 243, 250]    # board rev 0.6c+
        else:
            uvPwms = [31, 94, 188, 219]     # board rev. < 0.6c
        #endif
        diff = 0.55    # [mV] voltages in all rows cannot differ more than this limit
        row1 = list()
        row2 = list()
        row3 = list()
        for i in range(3):
            self.display.hw.uvLedPwm = uvPwms[i]
            if self.display.hw.mcFwRevision < 6:
                sleep(10)   # wait to refresh all voltages (board rev. 0.5)
            else:
                sleep(5)    # wait to refresh all voltages (board rev. 0.6+)
            volts = self.display.hw.getVoltages()
            del volts[-1]   # delete power supply voltage
            if max(volts) - min(volts) > diff:
                self.display.hw.uvLed(False)
                self.display.pages['error'].setParams(
                    text = _("UV LED voltages differ too much!\n\n"
                        "Please check if the UV LED panel is connected properly.\n\n"
                        "Data: %(pwm)d, %(value)s V") % { 'pwm' : uvPwms[i], 'value' : volts})
                return "error"
            #endif
            row1.append(int(volts[0] * 1000))
            row2.append(int(volts[1] * 1000))
            row3.append(int(volts[2] * 1000))
        #endfor
        self.display.wizardData.update(
                wizardUvVoltageRow1 = row1,
                wizardUvVoltageRow2 = row2,
                wizardUvVoltageRow3 = row3)

        # UV LED temperature check
        pageWait.showItems(line1 = _("UV LED warmup check"))
        self.display.hw.uvLedPwm = uvPwms[3]
        for countdown in range(120, 0, -1):
            pageWait.showItems(line2 = ngettext("Remaining %d second" % countdown,
                    "Remaining %d seconds" % countdown, countdown))
            sleep(1)
            temp = self.display.hw.getUvLedTemperature()
            if temp > defines.maxUVTemp:
                self.display.hw.uvLed(False)
                self.display.pages['error'].setParams(
                    text = _("UV LED too hot!\n\n"
                        "Please check if the UV LED panel is attached to the heatsink.\n\n"
                        "Temperature data: %s") % temp)
                return "error"
            #endif
        #endfor
        self.display.wizardData.update(wizardTempUvWarm = temp)
        self.display.hw.uvLedPwm = self.display.hwConfig.uvPwm
        self.display.hw.powerLed("normal")

        return "displaytest"
    #enddef


    def backButtonRelease(self):
        return "wizardskip"
    #enddef


    def _OK_(self):
        return "wizardtoweraxis"
    #enddef


    def _EXIT_(self):
        self.allOff()
        return "_EXIT_"
    #enddef

#endclass


@page
class PageWizardTowerAxis(Page):
    Name = "wizardtoweraxis"

    def __init__(self, display):
        super(PageWizardTowerAxis, self).__init__(display)
        self.pageUI = "confirm"
        self.pageTitle = N_("Setup wizard step 5/10")
    #enddef


    def show(self):
        self.items.update({
            'imageName' : "04_tighten_screws.jpg",
            'text' : _("Secure the resin tank with resin tank screws.\n\n"
                "Make sure the tank is empty and clean.")})
        super(PageWizardTowerAxis, self).show()
    #enddef


    def contButtonRelease(self):
        self.display.pages['confirm'].setParams(
            continueFce = self.continueTowerCheck,
            backFce = self.backButtonRelease,
            pageTitle = N_("Setup wizard step 6/10"),
            imageName = "12_close_cover.jpg",
            text = _("Please close the orange lid."))
        return "confirm"
    #enddef

    def continueTowerCheck(self):
        self.ensureCoverIsClosed()

        self.display.hw.powerLed("warn")
        pageWait = PageWait(self.display, line1 = _("Tower axis check"))
        pageWait.show()
        self.display.hw.setTowerProfile("homingFast")
        self.display.hw.towerMoveAbsolute(0)
        while self.display.hw.isTowerMoving():
            sleep(0.25)
        #endwhile
        if self.display.hw.getTowerPositionMicroSteps() == 0:
            #stop 10 mm before endstop to change sensitive profile
            self.display.hw.towerMoveAbsolute(self.display.hw._towerEnd - 8000)
            while self.display.hw.isTowerMoving():
                sleep(0.25)
            #endwhile
            self.display.hw.setTowerProfile("homingSlow")
            self.display.hw.towerMoveAbsolute(self.display.hw._towerMax)
            while self.display.hw.isTowerMoving():
                sleep(0.25)
            #endwhile
        #endif
        position = self.display.hw.getTowerPositionMicroSteps()
        #MC moves tower by 1024 steps forward in last step of !twho
        if position < self.display.hw._towerEnd or position > self.display.hw._towerEnd + 1024 + 127: #add tolerance half fullstep
            self.display.pages['error'].setParams(
                text = _("Tower axis check failed!\n\n"
                    "Current position: %d\n\n"
                    "Please check if the ballscrew can move smoothly in its entire range.") % position)
            return "error"
        #endif
        return "wizardresinsensor"
    #enddef


    def backButtonRelease(self):
        return "wizardskip"
    #enddef


    def _EXIT_(self):
        self.allOff()
        return "_EXIT_"
    #enddef

#endclass


@page
class PageWizardResinSensor(Page):
    Name = "wizardresinsensor"

    def __init__(self, display):
        super(PageWizardResinSensor, self).__init__(display)
        self.pageUI = "confirm"
        self.pageTitle = N_("Setup wizard step 7/10")
    #enddef


    def show(self):
        self.items.update({
            'imageName' : "11_insert_platform_60deg.jpg",
            'text' : _("Insert the platform at a 60-degree angle, exactly like in the picture. The platform must hit the edges of the tank on its way down.")})
        super(PageWizardResinSensor, self).show()
    #enddef


    def contButtonRelease(self):
        self.display.pages['confirm'].setParams(
            continueFce = self.continueResinCheck,
            backFce = self.backButtonRelease,
            pageTitle = N_("Setup wizard step 8/10"),
            imageName = "12_close_cover.jpg",
            text = _("Please close the orange lid."))
        return "confirm"
    #enddef


    def continueResinCheck(self):
        self.ensureCoverIsClosed()

        self.display.hw.powerLed("warn")
        pageWait = PageWait(self.display,
            line1 = _("Resin sensor check"),
            line2 = _("DO NOT touch the printer"))
        pageWait.show()
        self.display.hw.towerSyncWait()
        self.display.hw.setTowerPosition(self.display.hwConfig.calcMicroSteps(defines.defaultTowerHeight))
        volume = self.display.hw.getResinVolume()
        self.logger.debug("resin volume: %s", volume)
        if not defines.resinWizardMinVolume <= volume <= defines.resinWizardMaxVolume:    #to work properly even with loosen rocker brearing
            self.display.pages['error'].setParams(
                text = _("Resin sensor not working!\n\n"
                    "Please check if the sensor is connected properly and tank is screwed down by both bolts.\n\n"
                    "Measured %d ml.") % volume)
            return "error"
        #endif
        self.display.wizardData.update(wizardResinVolume = volume)
        self.display.hw.towerSync()
        self.display.hw.tiltSyncWait()
        while not self.display.hw.isTowerSynced():
            sleep(0.25)
        #endwhile
        self.display.hw.motorsRelease()
        self.display.hw.stopFans()

        self.display.hwConfig.update(showWizard = "no")
        if not self.display.hwConfig.writeFile():
            self.display.pages['error'].setParams(
                text = _("Cannot save wizard configuration"))
            return "error"
        #endif

        # store data only in factory mode or after first successful run on kit
        if self.display.hwConfig.factoryMode or (self.display.hw.isKit and not self.display.wizardData.wizardDone):
            self.display.wizardData.update(wizardDone = 1)
            if not self.writeToFactory(self.display.wizardData.writeFile):
                self.display.pages['error'].setParams(
                    text = _("!!! Failed to save factory defaults !!!"))
                return "error"
            #endif
        #endif

        self.allOff()
        return "wizardtimezone"
    #enddef


    def backButtonRelease(self):
        return "wizardskip"
    #enddef


    def _EXIT_(self):
        self.allOff()
        return "_EXIT_"
    #enddef

#endclass

@page
class PageWizardTimezone(Page):
    Name = "wizardtimezone"

    def __init__(self, display):
        super(PageWizardTimezone, self).__init__(display)
        self.pageUI = "yesno"
        self.pageTitle = N_("Setup wizard step 9/10")
    #enddef


    def show(self):
        self.items.update({
            'text' : _("Do you want to setup a timezone?")})
        super(PageWizardTimezone, self).show()
    #enddef


    def yesButtonRelease(self):
        return "settimezone"
    #endif


    def noButtonRelease(self):
        return "wizardspeaker"
    #enddef


    def _BACK_(self):
        return "wizardspeaker"
    #enddef


    def _EXIT_(self):
        self.allOff()
        return "_EXIT_"
    #enddef

#endclass


@page
class PageWizardSpeaker(Page):
    Name = "wizardspeaker"

    def __init__(self, display):
        super(PageWizardSpeaker, self).__init__(display)
        self.pageUI = "yesno"
        self.pageTitle = N_("Setup wizard step 10/10")
        pygame.mixer.init(44100, -16, 2, 2048)
        pygame.mixer.music.load(defines.multimediaRootPath + "/chromag_-_the_prophecy.xm")
    #enddef


    def show(self):
        pygame.mixer.music.play(-1)
        self.items.update({
            'text' : _("Can you hear the music?")})
        super(PageWizardSpeaker, self).show()
    #enddef


    def yesButtonRelease(self):
        pygame.mixer.music.stop()
        return "wizardfinish"
    #endif


    def noButtonRelease(self):
        pygame.mixer.music.stop()
        self.display.pages['error'].setParams(
            text = _("Speaker not working.\nPlease check propper connection and wiring of the speaker."))
        return "error"
    #enddef


    def _EXIT_(self):
        self.allOff()
        return "_EXIT_"
    #enddef

#endclass


@page
class PageWizardFinish(Page):
    Name = "wizardfinish"

    def __init__(self, display):
        super(PageWizardFinish, self).__init__(display)
        self.pageUI = "confirm"
        self.pageTitle = N_("Setup wizard done")
    #enddef


    def show(self):
        self.items.update({
            'text' : _("Selftest OK.\n\n"
                "Continue to calibration?")})
        super(PageWizardFinish, self).show()
    #enddef


    def contButtonRelease(self):
        return "calibration1"
    #enddef


    def backButtonRelease(self):
        self.allOff()
        return "_EXIT_"
    #enddef


    def _EXIT_(self):
        self.allOff()
        return "_EXIT_"
    #enddef

#endclass


@page
class PageWizardSkip(Page):
    Name = "wizardskip"

    def __init__(self, display):
        super(PageWizardSkip, self).__init__(display)
        self.pageUI = "yesno"
        self.pageTitle = N_("Skip wizard?")
        self.checkPowerbutton = False
    #enddef


    def show(self):
        self.items.update({
            'text' : _("Do you really want to skip the wizard?\n\n"
                "The machine may not work correctly without finishing this check.")})
        super(PageWizardSkip, self).show()
    #enddef


    def yesButtonRelease(self):
        self.allOff()
        self.display.hwConfig.update(showWizard = "no")
        if not self.display.hwConfig.writeFile():
            self.display.pages['error'].setParams(
                text = _("Cannot save wizard configuration"))
            return "error"
        #endif
        return "_EXIT_"
    #endif


    def noButtonRelease(self):
        return "_NOK_"
    #enddef

#endclass