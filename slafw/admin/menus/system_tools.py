# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import partial
from pathlib import Path

import pydbus

from slafw import defines
from slafw.admin.control import AdminControl
from slafw.admin.items import AdminAction, AdminTextValue, AdminBoolValue, AdminLabel
from slafw.admin.menus.dialogs import Error, Wait
from slafw.admin.safe_menu import SafeAdminMenu
from slafw.errors.errors import FailedUpdateChannelSet
from slafw.functions.system import (
    FactoryMountedRW,
    set_update_channel,
    get_update_channel,
    set_configured_printer_model,
    shut_down, reset_hostname,
)
from slafw.libPrinter import Printer
from slafw.state_actions.examples import Examples
from slafw.hardware.printer_model import PrinterModel


class SystemToolsMenu(SafeAdminMenu):
    SYSTEMD_DBUS = ".systemd1"

    def __init__(self, control: AdminControl, printer: Printer):
        super().__init__(control)
        self._printer = printer
        self.systemd = pydbus.SystemBus().get(self.SYSTEMD_DBUS)

        self.add_back()
        self.add_items(
            (
                AdminAction(
                    "Update channel",
                    lambda: self._control.enter(SetChannelMenu(self._control))
                ),
                AdminBoolValue.from_property(self, SystemToolsMenu.factory_mode),
                AdminBoolValue.from_property(self, SystemToolsMenu.ssh),
                AdminBoolValue.from_property(self, SystemToolsMenu.serial),
                AdminAction("Fake setup", self._fake_setup),
                AdminAction("Download examples", self._download_examples),
            )
        )
        if self._printer.model == PrinterModel.SL1S:
            self.add_item(AdminAction("Switch to M1", self._switch_m1))
        if self._printer.model == PrinterModel.M1:
            self.add_item(AdminAction("Switch to SL1S", self._switch_sl1s))


    @property
    def factory_mode(self) -> bool:
        return self._printer.runtime_config.factory_mode

    @factory_mode.setter
    def factory_mode(self, value: bool):
        with FactoryMountedRW():
            if value:
                defines.factory_enable.touch()
            else:
                if defines.factory_enable.exists():
                    defines.factory_enable.unlink()
                # On factory disable, disable also ssh and serial to ensure
                # end users do not end up with serial, ssh enabled.
                if defines.ssh_service_enabled.exists():
                    defines.ssh_service_enabled.unlink()
                if defines.serial_service_enabled.exists():
                    defines.serial_service_enabled.unlink()

        self._printer.runtime_config.factory_mode = value
        if value:
            self.systemd.Reload()
            self._systemd_enable_service(defines.serial_service_service)
            self._systemd_enable_service(defines.ssh_service_service)

    @property
    def ssh(self) -> bool:
        return defines.ssh_service_enabled.exists()

    @ssh.setter
    def ssh(self, value: bool):
        if self._printer.runtime_config.factory_mode:
            raise ValueError("Already enabled by factory mode")
        self._set_unit(defines.ssh_service_service, defines.ssh_service_enabled, value)

    @property
    def serial(self) -> bool:
        return defines.serial_service_enabled.exists()

    @serial.setter
    def serial(self, value: bool):
        if self._printer.runtime_config.factory_mode:
            raise ValueError("Already enabled by factory mode")
        self._set_unit(defines.serial_service_service, defines.serial_service_enabled, value)

    def _set_unit(self, service: str, enable_file: Path, state: bool):
        if state:
            with FactoryMountedRW():
                enable_file.touch()
            self._systemd_enable_service(service)
        else:
            with FactoryMountedRW():
                enable_file.unlink()
            self._systemd_disable_service(service)

    def _systemd_enable_service(self, service: str):
        state = self.systemd.GetUnitFileState(service)
        if state == "masked":
            self.systemd.UnmaskUnitFiles([service], False)
        self.systemd.Reload()
        self.systemd.StartUnit(service, "replace")

    def _systemd_disable_service(self, service: str):
        self.systemd.Reload()
        self.systemd.StopUnit(service, "replace")

    def _fake_setup(self):
        self.enter(Wait(self._control, self._do_fake_setup))

    @SafeAdminMenu.safe_call
    def _do_fake_setup(self, status: AdminLabel):
        status.set("Saving dummy calibration data")
        writer = self._printer.hw.config.get_writer()
        writer.calibrated = True
        writer.showWizard = False
        writer.showUnboxing = False
        writer.uvPwm = self._printer.hw.uv_led.parameters.safe_default_pwm
        self._printer.hw.uv_led.pwm = writer.uvPwm
        writer.commit()

        status.set("Saving dummy factory data")
        with FactoryMountedRW():
            self._printer.hw.config.write_factory()

        status.set("Done")

    def _download_examples(self):
        self.enter(Wait(self._control, self._do_download_examples))

    @SafeAdminMenu.safe_call
    def _do_download_examples(self, status: AdminLabel):
        status.set("Downloading examples")
        examples = Examples(self._printer.inet, self._printer.model)
        examples.start()
        examples.join()

    def _switch_m1(self):
        self.enter(Wait(self._control, self._do_switch_m1))

    @SafeAdminMenu.safe_call
    def _do_switch_m1(self, status: AdminLabel):
        with FactoryMountedRW():
            defines.printer_m1_enabled.touch()
        self._switch_sl1s_m1(status, PrinterModel.M1, "medic")

    def _switch_sl1s(self):
        self.enter(Wait(self._control, self._do_switch_sl1s))

    @SafeAdminMenu.safe_call
    def _do_switch_sl1s(self, status: AdminLabel):
        with FactoryMountedRW():
            defines.printer_m1_enabled.unlink(missing_ok=True)
        self._switch_sl1s_m1(status, PrinterModel.SL1S, "stable")

    def _switch_sl1s_m1(self, status: AdminLabel, printer_model: PrinterModel, channel: str):
        status.set("Setting update channel")
        try:
            set_update_channel(channel)
        except FailedUpdateChannelSet:
            self.logger.exception("Failed to set update channel")
            self._control.enter(
                Error(self._control, text="Failed to set update channel", pop=2)
            )
        status.set("Setting printer model")
        set_configured_printer_model(printer_model)
        status.set("Setting hostname")
        reset_hostname()
        # new examples remove the old ones
        status.set("Downloading examples")
        examples = Examples(self._printer.inet, printer_model)
        examples.start()
        examples.join()
        shut_down(self._printer.hw, reboot=True)


class SetChannelMenu(SafeAdminMenu):
    def __init__(self, control: AdminControl):
        super().__init__(control)
        self._channel_value = AdminTextValue(
            "Channel",
            lambda: f"Update channel: {get_update_channel()}",
            self._set_update_channel,
        )

        self.add_back()
        self.add_items(
            (
                self._channel_value,
                AdminAction("Switch to stable", partial(self._set_update_channel, "stable")),
                AdminAction("Switch to beta", partial(self._set_update_channel, "beta")),
                AdminAction("Switch to dev", partial(self._set_update_channel, "dev")),
                AdminAction("Switch to medic", partial(self._set_update_channel, "medic")),
            )
        )

    def _set_update_channel(self, channel: str):
        try:
            if channel not in ["stable", "beta", "dev", "medic"]:
                raise ValueError(f'Unsupported update channel: "{channel}"')
            set_update_channel(channel)
        except FailedUpdateChannelSet:
            self.logger.exception("Failed to set update channel")
            self._control.enter(
                Error(self._control, text="Failed to set update channel", pop=2)
            )
        finally:
            self._channel_value.changed.emit()
