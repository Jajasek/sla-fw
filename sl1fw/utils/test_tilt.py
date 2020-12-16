#!/usr/bin/env python2

# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from time import sleep

from sl1fw.libConfig import HwConfig
from sl1fw.libHardware import Hardware

logging.basicConfig(format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s", level = logging.DEBUG)


hwConfig = HwConfig()
hw = Hardware(hwConfig)

hw.tiltSyncWait()
hw.tiltMoveAbsolute(5300)
while hw.isTiltMoving():
    sleep(0.1)
#endwhile
profile = [1750, 1750, 0, 0, 58, 26, 2100]
result = dict()
for sgt in range(10, 30):
    profile[5] = sgt
    sgbd = list()
    hw.mcc.do("!tics", 4)
    hw.mcc.do("!ticf", ' '.join(str(num) for num in profile))
    hw.mcc.do("?ticf")
    hw.mcc.do("!sgbd")
    hw.tiltMoveAbsolute(0)
    while hw.isTiltMoving():
        sgbd.extend(hw.getStallguardBuffer())
        sleep(0.1)
    #endwhile
    if hw.getTiltPositionMicroSteps() == 0:
        avg = sum(sgbd) / float(len(sgbd))
        if 200 < avg < 250:
            result[avg] = ' '.join(str(num) for num in profile)

    hw.mcc.do("!tics", 0)
    hw.tiltMoveAbsolute(5300)
    while hw.isTiltMoving():
        sleep(0.1)
    #endwhile

print(result)
hw.mcc.do("!motr")