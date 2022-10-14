# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from slafw import defines
from slafw.configs.value import DictOfConfigs, BoolValue, IntValue, ProfileIndex
from slafw.configs.unit import Ustep, Nm, Ms
from slafw.hardware.base.profiles import SingleProfile, ProfileSet
from slafw.hardware.sl1.tilt_profiles import MovingProfilesTiltSL1
from slafw.hardware.sl1.tower_profiles import MovingProfilesTowerSL1


LAYER_PROFILES_DEFAULT_NAME = "default_layer_profiles.json"
LAYER_PROFILES_LOCAL = defines.configDir / "profiles_layer.json"
EXPOSURE_PROFILES_DEFAULT_NAME = "default_exposure_profiles.json"
EXPOSURE_PROFILES_LOCAL = defines.configDir / "profiles_exposure.json"

class SingleLayerProfileSL1(SingleProfile):
    delay_before_exposure_ms = IntValue(
            minimum=0,
            maximum=30_000,
            unit=Ms,
            factory=True,
            doc="Delay between tear off and exposure.")
    delay_after_exposure_ms = IntValue(
            minimum=0,
            maximum=30_000,
            unit=Ms,
            factory=True,
            doc="Delay between exposure and tear off.")
    tower_hop_height_nm = IntValue(
            minimum=0,
            maximum=100_000_000,
            unit=Nm,
            factory=True,
            doc="How much to raise the tower during layer change.")
    tower_profile = ProfileIndex(
            MovingProfilesTowerSL1,
            factory=True,
            doc="The tower moving profile.")
    use_tilt = BoolValue(
            factory=True,
            doc="Use the tilt to tear off the layers.")
    # tilt down settings
    tilt_down_initial_profile = ProfileIndex(
            MovingProfilesTiltSL1,
            factory=True,
            doc="The tilt profile for first move down.")
    tilt_down_offset_steps = IntValue(
            minimum=0,
            maximum=10000,
            unit=Ustep,
            factory=True,
            doc="How many steps to perform in first move down.")
    tilt_down_offset_delay_ms = IntValue(
            minimum=0,
            maximum=20000,
            unit=Ms,
            factory=True,
            doc="Waiting time after first move down.")
    tilt_down_finish_profile = ProfileIndex(
            MovingProfilesTiltSL1,
            factory=True,
            doc="The tilt profile for remaining moves down.")
    tilt_down_cycles = IntValue(
            minimum=0,
            maximum=10,
            factory=True,
            doc="How many parts should the remaining distance be made up of.")
    tilt_down_delay_ms = IntValue(
            minimum=0,
            maximum=20000,
            unit=Ms,
            factory=True,
            doc="Waiting time after every part.")
    # tilt up settings
    tilt_up_initial_profile = ProfileIndex(
            MovingProfilesTiltSL1,
            factory=True,
            doc="The tilt profile for first move up.")
    tilt_up_offset_steps = IntValue(
            minimum=0,
            maximum=10000,
            unit=Ustep,
            factory=True,
            doc="How many steps to perform in first move up.")
    tilt_up_offset_delay_ms = IntValue(
            minimum=0,
            maximum=20_000,
            unit=Ms,
            factory=True,
            doc="Waiting time after first move up.")
    tilt_up_finish_profile = ProfileIndex(
            MovingProfilesTiltSL1,
            factory=True,
            doc="The tilt profile for remaining moves up.")
    tilt_up_cycles = IntValue(
            minimum=0,
            maximum=10,
            factory=True,
            doc="How many parts should the remaining distance be made up of.")
    tilt_up_delay_ms = IntValue(
            minimum=0,
            maximum=20_000,
            unit=Ms,
            factory=True,
            doc="Waiting time after every part.")
    # this should be measured by printer
    moves_time_ms = IntValue(
            minimum=0,
            maximum=600_000,
            unit=Ms,
            factory=True,
            doc="Time necessary to perform all layer change moves.")
    __definition_order__ = tuple(locals())


class LayerProfilesSL1(ProfileSet):
    super_fast = DictOfConfigs(SingleLayerProfileSL1)
    fast = DictOfConfigs(SingleLayerProfileSL1)
    slow = DictOfConfigs(SingleLayerProfileSL1)
    super_slow = DictOfConfigs(SingleLayerProfileSL1)
    __definition_order__ = tuple(locals())
    _add_dict_type = SingleLayerProfileSL1   # type: ignore
    name = "layer change profiles"


class SingleExposureProfileSL1(SingleProfile):
    small_fill_layer_profile = ProfileIndex(
            LayerProfilesSL1,
            factory=True,
            doc="Layer profile for printed area smaller than <limit4fast>")
    large_fill_layer_profile = ProfileIndex(
            LayerProfilesSL1,
            factory=True,
            doc="Layer profile for printed area greater than <limit4fast>")
    __definition_order__ = tuple(locals())


class ExposureProfilesSL1(ProfileSet):
    default = DictOfConfigs(SingleExposureProfileSL1)
    safe = DictOfConfigs(SingleExposureProfileSL1)
    high_viscosity = DictOfConfigs(SingleExposureProfileSL1)
    __definition_order__ = tuple(locals())
    _add_dict_type = SingleExposureProfileSL1   # type: ignore
    name = "exposure profiles"
