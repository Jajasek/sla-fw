# This file is part of the SL1 firmware
# Copyright (C) 2020 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from collections import OrderedDict
from functools import partial
from typing import Dict, Optional

from PySignal import Signal

from sl1fw.admin.base_menu import AdminMenuBase
from sl1fw.admin.control import AdminControl
from sl1fw.admin.items import (
    AdminItem,
    AdminValue,
    AdminAction,
    AdminLabel,
)


def part(func, *args, **kwargs):
    """
    None aware partial function

    :param func: Function, can be None
    :param obj: Parameters
    :return: Function with params fixed or None if no input function
    """
    if not func:
        return func

    return partial(func, *args, **kwargs)


class AdminMenu(AdminMenuBase):
    def __init__(self, control: AdminControl):
        self.logger = logging.getLogger(__name__)
        self._control = control
        self.items_changed = Signal()
        self.value_changed = Signal()
        self._items: Dict[str, AdminItem] = OrderedDict()

    @property
    def items(self) -> Dict[str, AdminItem]:
        return self._items

    def enter(self, menu: AdminMenuBase):
        self._control.enter(menu)

    def exit(self):
        self._control.exit()

    def add_item(self, item: AdminItem):
        if isinstance(item, AdminValue):
            item.changed.connect(self.value_changed.emit)
        self._items[item.name] = item
        self.items_changed.emit()

    def add_label(self, initial_text: Optional[str] = None):
        label = AdminLabel(initial_text)
        self.add_item(label)
        return label

    def add_back(self, bold=True):
        text = "<b>Back</b>" if bold else "Back"
        self.add_item(AdminAction(text, self._control.pop))

    def del_item(self, item: AdminItem):
        del self._items[item.name]
        self.items_changed.emit()
