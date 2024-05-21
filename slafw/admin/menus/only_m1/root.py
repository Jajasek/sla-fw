# This file is part of the SLA firmware
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw.libPrinter import Printer
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminLabel
from slafw.admin.menu import AdminMenu


class OnlyM1Root(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control, printer)
        self.add_back()
        self.add_item(AdminLabel("Only M1 feature", ""))
