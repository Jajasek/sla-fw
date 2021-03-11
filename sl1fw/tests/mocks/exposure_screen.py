# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest.mock import Mock

from sl1fw.hardware.printer_model import PrinterModel


class ExposureScreen:
    # pylint: disable = too-few-public-methods
    def __init__(self):
        self.parameters = PrinterModel.SL1.exposure_screen_parameters

        self.start = Mock(return_value=PrinterModel.SL1)
        self.exit = Mock()
        self.show = Mock()
        self.sync = Mock()