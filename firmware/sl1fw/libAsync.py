# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import threading
import json

import distro

from sl1fw import defines
from sl1fw.libDisplay import Display
from sl1fw.libNetwork import Network


class Admin_check_thread(threading.Thread):

    def __init__(self, display: Display, inet: Network):
        super(Admin_check_thread, self).__init__()
        self.display = display
        self.inet = inet
        self.stop_request = threading.Event()
        self.changed_request = threading.Event()
        self.logger = logging.getLogger(__name__)
    #enddef


    def join(self, timeout = None):
        self.stop_request.set()
        super(Admin_check_thread, self).join(timeout)
    #enddef


    def connection_changed(self, value):
        if value:
            self.changed_request.set()
        #endif
    #enddef


    def run(self):
        #self.logger.debug("thread started")
        while not self.stop_request.is_set():
            if self.changed_request.wait(0.1):
                self.changed_request.clear()
                self.logger.info("the network is avaiable, querying admin enabled")
                try:
                    query_url = defines.admincheckURL + "/?serial=" + self.display.hw.cpuSerialNo
                    self.inet.download_url(query_url, defines.admincheckTemp, distro.version(), self.display.hw.cpuSerialNo)

                    with open(defines.admincheckTemp, 'r') as file:
                        admin_check = json.load(file)
                        if not admin_check['result']:
                            raise Exception("Admin not enabled")
                        #endif
                    #endwith
                    self.display.show_admin = True
                    self.logger.warning("Admin enabled")
                except:
                    self.logger.exception("Admin accesibility check exception")
                #endexcept
            #endif
        #endwhile
        #self.logger.debug("thread ended")
    #enddef

#endclass


class Admin_check:

    def __init__(self, display, inet):
        self.logger = logging.getLogger(__name__)
        self.check_thread = Admin_check_thread(display, inet)
        self.check_thread.start()
        inet.register_net_change_handler(self.check_thread.connection_changed)
    #enddef


    def exit(self):
        self.check_thread.join()
    #enddef

#endclass
