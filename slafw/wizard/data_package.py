# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass
import weakref

from slafw.hardware.base.hardware import BaseHardware
from slafw.configs.writer import ConfigWriter
from slafw.configs.runtime import RuntimeConfig
from slafw.image.exposure_image import ExposureImage


@dataclass
class WizardDataPackage:
    """
    Data getting passed to the wizards, wizard groups and wizard checks for their initialization
    """

    hw: BaseHardware = None
    config_writer: ConfigWriter = None
    runtime_config: RuntimeConfig = None
    exposure_image: ExposureImage = None


def fill_wizard_data_package(printer) -> WizardDataPackage:
    return WizardDataPackage(
        hw=printer.hw,
        config_writer=printer.hw.config.get_writer(),
        runtime_config=printer.runtime_config,
        exposure_image=weakref.proxy(printer.exposure_image),
    )
