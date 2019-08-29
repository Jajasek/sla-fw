# part of SL1 firmware
# 2014-2018 Futur3d - www.futur3d.net
# 2018-2019 Prusa Research s.r.o. - www.prusa3d.com

from sl1fw.pages import page
from sl1fw.libPages import Page, PageWait


@page
class PageControl(Page):
    Name = "control"

    def __init__(self, display):
        super(PageControl, self).__init__(display)
        self.pageUI = "control"
        self.pageTitle = N_("Control")
    #enddef


    def show(self):
        self.moving = False
        super(PageControl, self).show()
    #enddef


    def topButtonRelease(self):
        self.display.hw.powerLed("warn")
        pageWait = PageWait(self.display, line1 = _("Moving platform to the top"))
        pageWait.show()
        retc = self._syncTower(pageWait)
        self.display.hw.motorsHold()
        self.display.hw.powerLed("normal")
        return retc
    #enddef


    def tankresButtonRelease(self):
        self.display.hw.powerLed("warn")
        pageWait = PageWait(self.display, line1 = _("Tank reset"))
        pageWait.show()
        # assume tilt is up (there may be error from print)
        self.display.hw.setTiltPosition(self.display.hw._tiltEnd)
        self.display.hw.tiltLayerDownWait(True)
        self.display.hw.tiltSyncWait()
        self.display.hw.tiltLayerUpWait()
        self.display.hw.motorsHold()
        self.display.hw.powerLed("normal")
        return "_SELF_"
    #enddef


    def disablesteppersButtonRelease(self):
        self.display.hw.motorsRelease()
    #enddef

#endclass