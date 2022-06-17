# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Collection
from pathlib import Path

from slafw.defines import dataPath
from slafw.libPrinter import Printer
from slafw.hardware.base.profiles import SingleProfile
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminItem, AdminAction, AdminIntValue
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.dialogs import Info
from slafw.hardware.axis import Axis
from slafw.functions.files import get_save_path, usb_remount, get_export_file_name
from slafw.functions.system import get_configured_printer_model
from slafw.errors.errors import NoExternalStorage


class Profiles(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer, axis: Axis):
        super().__init__(control)
        self._printer = printer
        self._axis = axis

        self.add_back()
        self.add_items(
            (
                AdminAction(
                    f"Edit {axis.name} profiles",
                    lambda: self.enter(EditProfiles(self._control, axis)),
                    "edit_white"
                ),
                AdminAction(
                    f"Import {axis.name} profiles",
                    lambda: self.enter(ImportProfiles(self._control, axis)),
                    "save_color"
                ),
                AdminAction(f"Save {axis.name} profiles to USB drive", self.save_to_usb, "usb_color"),
                AdminAction(f"Restore to factory {axis.name} profiles", self.factory_profiles, "factory_color"),
            )
        )

    @SafeAdminMenu.safe_call
    def save_to_usb(self):
        save_path = get_save_path()
        if save_path is None or not save_path.parent.exists():
            raise NoExternalStorage()
        usb_remount(str(save_path))
        model_name = get_configured_printer_model().name    # type: ignore[attr-defined]
        fn = f"profiles_{self._axis.name}-{model_name}.{get_export_file_name(self._printer.hw)}.json"
        self._axis.profiles.write_factory(save_path/ fn, nondefault=True)
        self._control.enter(Info(self._control, headline="Profiles saved to:", text=fn))

    @SafeAdminMenu.safe_call
    def factory_profiles(self):
        self._axis.profiles.factory_reset(True)
        self._axis.profiles.write_factory()
        self._axis.apply_all_profiles()
        self._control.enter(Info(self._control, text="Profiles restored"))


class EditProfiles(AdminMenu):
    def __init__(self, control: AdminControl, axis: Axis):
        super().__init__(control)
        self.add_back()
        self.add_items(self._get_items(axis))

    def _get_items(self, axis: Axis) -> Collection[AdminItem]:
        for profile in axis.profiles:
            yield AdminAction(profile.name, self._get_callback(axis, profile), "steppers_color")

    def _get_callback(self, axis: Axis, profile: SingleProfile):
        return lambda: self._control.enter(EditProfileItems(self._control, axis, profile))


class EditProfileItems(AdminMenu):
    def __init__(self, control: AdminControl, axis: Axis, profile: SingleProfile):
        super().__init__(control)
        self._axis = axis
        self._temp = profile.get_writer()
        self.add_back()
        self.add_items(self._get_items(profile))

    def _get_items(self, profile: SingleProfile) -> Collection[AdminItem]:
        for value in profile:
            yield AdminIntValue.from_value(value.key, self._temp, value.key, 1, "edit_white")

    def on_leave(self):
        self._temp.commit(factory=True)
        self._axis.apply_all_profiles()


class ImportProfiles(SafeAdminMenu):
    def __init__(self, control: AdminControl, axis: Axis):
        super().__init__(control)
        self._axis = axis
        self.add_back()
        usb_path = get_save_path()
        if usb_path is None:
            self.add_label("USB not present. To get files from USB, plug the USB\nand re-enter.", "error_small_white")
        else:
            self.add_label("<b>USB</b>", "usb_color")
            self.list_files(usb_path, [f"**/*{axis.name}*.json"], self._import_profile, "usb_color")
        self.add_label("<b>Internal</b>", "factory_color")
        self.list_files(Path(dataPath), [f"**/*{axis.name}*.json"], self._import_profile, "factory_color")

    @SafeAdminMenu.safe_call
    def _import_profile(self, path: Path, name: str):
        fullname = path / name
        if not fullname.exists():
            raise FileNotFoundError(f"Profiles file not found: {name}")
        self._axis.profiles.read_file_raw(fullname, factory=True)
        self._axis.profiles.write_factory()
        self._axis.apply_all_profiles()
        self._control.enter(Info(self._control, text="Profiles loaded", pop=2))
