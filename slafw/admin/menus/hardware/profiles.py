# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Collection
from pathlib import Path
from time import sleep

from slafw.defines import dataPath
from slafw.libPrinter import Printer
from slafw.hardware.base.profiles import SingleProfile, ProfileSet
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminItem, AdminLabel, AdminAction, AdminIntValue, AdminSelectionValue
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.admin.menu import AdminMenu
from slafw.admin.menus.dialogs import Info, Wait, Error
from slafw.hardware.axis import Axis
from slafw.hardware.tower import MovingProfilesTower
from slafw.hardware.tilt import MovingProfilesTilt
from slafw.hardware.sl1.tilt import TuneTiltSL1
from slafw.hardware.power_led_action import WarningAction
from slafw.functions.files import get_save_path, usb_remount, get_export_file_name
from slafw.functions.system import get_configured_printer_model
from slafw.errors.errors import NoExternalStorage, TiltHomeFailed
from slafw.configs.value import ProfileIndex


class Profiles(SafeAdminMenu):
    def __init__(self, control: AdminControl, printer: Printer, axis: Axis, pset: ProfileSet):
        super().__init__(control)
        self._printer = printer
        self._pset = pset

        self.add_back()
        self.add_items(
            (
                AdminAction(
                    f"Edit {pset.name}",
                    lambda: self.enter(EditProfiles(self._control, printer, axis, pset)),
                    "edit_white"
                ),
                AdminAction(
                    f"Import {pset.name}",
                    lambda: self.enter(ImportProfiles(self._control, pset)),
                    "save_color"
                ),
                AdminAction(f"Save {pset.name} to USB drive", self.save_to_usb, "usb_color"),
                AdminAction(f"Restore to factory {pset.name}", self.factory_profiles, "factory_color"),
            )
        )

    @SafeAdminMenu.safe_call
    def save_to_usb(self):
        save_path = get_save_path()
        if save_path is None or not save_path.parent.exists():
            raise NoExternalStorage()
        usb_remount(str(save_path))
        model_name = get_configured_printer_model().name    # type: ignore[attr-defined]
        fn = f"{self._pset.name.replace(' ', '_')}-{model_name}.{get_export_file_name(self._printer.hw)}.json"
        self._pset.write_factory(save_path / fn, nondefault=True)
        self._control.enter(Info(self._control, headline=f"{self._pset.name.capitalize()} saved to:", text=fn))

    @SafeAdminMenu.safe_call
    def factory_profiles(self):
        self._pset.factory_reset(True)
        self._pset.write_factory()
        self._pset.apply_all()
        self._control.enter(Info(self._control, text=f"{self._pset.name.capitalize()} restored"))


class EditProfiles(AdminMenu):
    def __init__(self, control: AdminControl, printer: Printer, axis: Axis, pset: ProfileSet):
        super().__init__(control)
        self.add_back()
        self.add_items(self._get_items(printer, axis, pset))

    def _get_items(self, printer: Printer, axis: Axis, pset: ProfileSet) -> Collection[AdminItem]:
        if isinstance(pset, (MovingProfilesTilt, MovingProfilesTower)):
            icon = "steppers_color"
        elif isinstance(pset, TuneTiltSL1):
            icon = "tilt_sensivity_color"
        else:
            icon = ""
        for profile in pset:
            yield AdminAction(profile.name, self._get_callback(printer, axis, pset, profile), icon)

    def _get_callback(self, printer: Printer, axis: Axis, pset: ProfileSet, profile: SingleProfile):
        return lambda: self._control.enter(EditProfileItems(self._control, printer, axis, pset, profile))


class EditProfileItems(SafeAdminMenu):
    # pylint: disable = too-many-arguments
    def __init__(self, control: AdminControl, printer: Printer, axis: Axis, pset: ProfileSet, profile: SingleProfile):
        super().__init__(control)
        self._printer = printer
        self._axis = axis
        self._pset = pset
        self._profile = profile
        self._temp_profile = None
        self._temp = profile.get_writer()
        self.add_back()
        self.add_item(AdminAction("Test profile", self.test_profile, "touchscreen-icon"))
        self.add_items(self._get_items(profile))

    def _get_items(self, profile: SingleProfile) -> Collection[AdminItem]:
        for value in profile:
            if isinstance(value, ProfileIndex):
                yield AdminSelectionValue.from_value(value.key, self._temp, value.key, value.options, True, "edit_white")
            else:
                yield AdminIntValue.from_value(value.key, self._temp, value.key, 1, "edit_white", unit=value.unit)

    def on_leave(self):
        self._temp.commit(factory=True)
        self._pset.apply_all()

    @SafeAdminMenu.safe_call
    def test_profile(self):
        self._temp_profile = type(self._pset[self._profile.idx])()
        self._temp_profile.name = "temporary"
        self._temp_profile.idx = -1
        for val in self._temp_profile.get_values().values():
            val.set_value(self._temp_profile, getattr(self._temp, val.key))
        if isinstance(self._pset, (MovingProfilesTilt, MovingProfilesTower)):
            self._axis.actual_profile = self._temp_profile
            getattr(self._control, f"{self._axis.name}_moves")()
        elif isinstance(self._pset, TuneTiltSL1):
            if self._profile.name.find("_down_") != -1:
                self._control.enter(Wait(self._control, self._do_tune_test_down))
            elif self._profile.name.find("_up_") != -1:
                self._control.enter(Wait(self._control, self._do_tune_test_up))
            else:
                raise RuntimeError(f"Unknown profile direction: {self._profile.name}")
        else:
            raise RuntimeError(f"Unknown profiles type: {type(self._pset)}")

    def _sync(self):
        if not self._axis.synced:
            self._axis.actual_profile = self._axis.profiles.homingFast    # type: ignore
            try:
                self._axis.sync_ensure()
            except TiltHomeFailed:
                self._control.enter(Error(self._control, text=f"Failed to home {self._axis.name}"))
                return False
        self._axis.actual_profile = self._axis.profiles.moveFast    # type: ignore
        return True

    def _do_tune_test_down(self, status: AdminLabel):
        status.set(f"Testing {self._profile.name}")
        with WarningAction(self._printer.hw.power_led):
            if self._sync():
                self._axis.move_ensure(self._axis.config_height_position)
                self._printer.hw.beepEcho()
                sleep(1)
                self._printer.hw.tilt.layer_down_wait(self._temp_profile)
                self._printer.hw.beepEcho()
                sleep(1)

    def _do_tune_test_up(self, status: AdminLabel):
        status.set(f"Testing {self._profile.name}")
        with WarningAction(self._printer.hw.power_led):
            if self._sync():
                self._axis.move_ensure(self._axis.minimal_position)
                self._printer.hw.beepEcho()
                sleep(1)
                self._printer.hw.tilt.layer_up_wait(self._temp_profile)
                self._printer.hw.beepEcho()
                sleep(1)


class ImportProfiles(SafeAdminMenu):
    def __init__(self, control: AdminControl, pset: ProfileSet):
        super().__init__(control)
        self._pset = pset
        self.add_back()
        usb_path = get_save_path()
        basename = self._pset.name.replace(' ', '_')
        if usb_path is None:
            self.add_label("USB not present. To get files from USB, plug the USB\nand re-enter.", "error_small_white")
        else:
            self.add_label("<b>USB</b>", "usb_color")
            self.list_files(usb_path, [f"**/*{basename}*.json"], self._import_profile, "usb_color")
        self.add_label("<b>Internal</b>", "factory_color")
        self.list_files(Path(dataPath), [f"**/*{basename}*.json"], self._import_profile, "factory_color")

    @SafeAdminMenu.safe_call
    def _import_profile(self, path: Path, name: str):
        fullname = path / name
        if not fullname.exists():
            raise FileNotFoundError(f"Profiles file not found: {name}")
        self._pset.read_file_raw(fullname, factory=True)
        self._pset.write_factory()
        self._pset.apply_all()
        self._control.enter(Info(self._control, text="Profiles loaded", pop=2))
