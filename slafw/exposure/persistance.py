# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import pickle
from asyncio import Task
from queue import Queue
from threading import Thread, Lock, Event
from zipfile import ZipFile
from logging import Logger

from PySignal import Signal

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.configs.project import ProjectConfig
from slafw.hardware.base.hardware import BaseHardware
from slafw.image.exposure_image import ExposureImage
from slafw.utils.traceable_collections import TraceableDict, TraceableList
from slafw.exposure.profiles import (
    SingleExposureProfileSL1,
    ExposureProfilesSL1,
    SingleLayerProfileSL1,
    LayerProfilesSL1,
)

LAST_PROJECT_HW_CONFIG = defines.previousPrints / defines.hwConfigFileName
LAST_PROJECT_FACTORY_FILE = defines.previousPrints / defines.hwConfigFileNameFactory
LAST_PROJECT_CONFIG_FILE = defines.previousPrints / defines.configFile
LAST_PROJECT_PICKLER = defines.previousPrints / "last_project.pck"

class ExposurePickler(pickle.Pickler):
    IGNORED_CLASSES = (
        Signal,
        BaseHardware,
        ExposureImage,
        Thread,
        TraceableDict,
        TraceableList,
        Queue,
        ZipFile,
        Event,
        type(Lock()),
        Task,
        ExposureProfilesSL1,
        LayerProfilesSL1,
        SingleLayerProfileSL1,
    )

    def persistent_id(self, obj):
        if isinstance(obj, self.IGNORED_CLASSES):
            return ("ignore", None)
        if isinstance(obj, HwConfig):
            obj.write(LAST_PROJECT_HW_CONFIG)
            obj.write_factory(LAST_PROJECT_FACTORY_FILE)
            return ("HwConfig", None)
        if isinstance(obj, ProjectConfig):
            obj.write(LAST_PROJECT_CONFIG_FILE)
            return ("ProjectConfig", None)
        if isinstance(obj, SingleExposureProfileSL1):
            return ("ExposureProfileId", obj.idx)
        return None


class ExposureUnpickler(pickle.Unpickler):
    def __init__(self,
                 pickle_io,
                 hw: BaseHardware,
                 exposure_profiles: ExposureProfilesSL1,
                 layer_profiles: LayerProfilesSL1):

        super().__init__(pickle_io)
        self._hw = hw
        self._exposure_profiles = exposure_profiles
        self._layer_profiles = layer_profiles
        assert hw is not None
        assert exposure_profiles is not None
        assert layer_profiles is not None

    def load(self) -> "Exposure":
        # FIXME bad practise
        # pylint: disable=protected-access
        """ The Exposure object and its member Project are recovered broken, this wrapper is here to fix them """
        exposure = super().load()

        # Necessary preconditions
        assert exposure is not None
        assert exposure.project is not None

        # Reconstruct the unpickled Exposure object to usable state
        exposure.change = Signal()
        exposure.hw = self._hw
        exposure.exposure_profiles = self._exposure_profiles
        exposure.layer_profiles = self._layer_profiles

        # Exposure.project is also unpickled in an invalid state, fix it!
        # This is awkward because it touches its private variables. It's still slightly better than creating a new one
        # and picking which members to copy.
        if exposure.project._hw is None:
            exposure.project._hw = self._hw
        if exposure.project._layer_profiles is None:
            exposure.project._layer_profiles = self._layer_profiles
        return exposure

    def persistent_load(self, pid):
        key, val = pid
        if key == "ignore":
            return None
        if key == "HwConfig":
            hw_config = HwConfig(
                file_path=LAST_PROJECT_HW_CONFIG,
                factory_file_path=LAST_PROJECT_FACTORY_FILE,
                is_master=False,
            )
            hw_config.read_file()
            return hw_config
        if key == "ProjectConfig":
            project_config = ProjectConfig()
            project_config.read_file(file_path=LAST_PROJECT_CONFIG_FILE)
            return project_config
        if key == "ExposureProfileId":
            return self._exposure_profiles[val]
        raise pickle.UnpicklingError(f"unsupported persistent object {str(key)}")


def cleanup_last_data(logger: Logger, clear_all=False) -> None:
    if clear_all:
        files = list(defines.previousPrints.glob("*"))
    else:
        files = [
            LAST_PROJECT_HW_CONFIG,
            LAST_PROJECT_FACTORY_FILE,
            LAST_PROJECT_CONFIG_FILE,
            LAST_PROJECT_PICKLER,
        ]
    for project_file in files:
        logger.debug("removing '%s'", project_file)
        try:
            project_file.unlink()
        except FileNotFoundError:
            logger.debug("No such file '%s'", project_file)
        except Exception:
            logger.exception("cleanup_last_data() exception:")
