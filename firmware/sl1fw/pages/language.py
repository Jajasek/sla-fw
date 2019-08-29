# part of SL1 firmware
# 2014-2018 Futur3d - www.futur3d.net
# 2018-2019 Prusa Research s.r.o. - www.prusa3d.com

import pydbus

from sl1fw.pages import page
from sl1fw.libPages import Page


@page
class PageSetLanguage(Page):
    Name = "setlanguage"

    def __init__(self, display):
        super(PageSetLanguage, self).__init__(display)
        self.pageUI = "setlanguage"
        self.pageTitle = N_("Set Language")
        self._locale = None
    #enddef


    @property
    def locale(self):
        if not self._locale:
            self._locale = pydbus.SystemBus().get("org.freedesktop.locale1")
        #endif
        return self._locale
    #enddef


    def fillData(self):
        try:
            locale = str(self.locale.Locale)
            lang = re.match(".*'LANG=(.*)'.*", locale).groups()[0]
        except:
            lang = ""

        return {
            'locale' : lang,
        }
    #enddef


    def show(self):
        self.items.update(self.fillData())
        super(PageSetLanguage, self).show()
    #enddef


    def setlocaleButtonSubmit(self, data):
        try:
            self.locale.SetLocale([data['locale']], False)
        except:
            self.logger.error("Setting locale failed")
        #endtry

        return "_BACK_"
    #enddef

#endclass