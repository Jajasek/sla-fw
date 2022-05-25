# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Collection

from slafw.hardware.base.profiles import ProfileSet, SingleProfile
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminItem, AdminAction, AdminIntValue
from slafw.admin.menu import AdminMenu


class ProfilesList(AdminMenu):
    def __init__(self, control: AdminControl, profiles: ProfileSet):
        super().__init__(control)
        self._profiles = profiles
        self.add_back()
        self.add_items(self._get_items())

    def _get_items(self) -> Collection[AdminItem]:
        for profile in self._profiles:
            yield AdminAction(profile.name, self._get_callback(profile), "steppers_color")

    def _get_callback(self, profile: SingleProfile):
        return lambda: self._control.enter(ProfileItems(self._control, profile))


class ProfileItems(AdminMenu):
    def __init__(self, control: AdminControl, profile: SingleProfile):
        super().__init__(control)
        self._profile = profile
        self._temp = profile.get_writer()
        self.add_back()
        self.add_items(self._get_items())

    def _get_items(self) -> Collection[AdminItem]:
        for value in self._profile:
            yield AdminIntValue.from_value(value.key, self._temp, value.key, 1, "edit_white")

    def on_leave(self):
        self._temp.commit(factory=True)
