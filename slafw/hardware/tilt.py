# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
from abc import abstractmethod
from functools import cached_property

from slafw.configs.unit import Ustep
from slafw.errors.errors import TiltMoveFailed, TiltHomeFailed
from slafw.hardware.axis import Axis
from slafw.hardware.base.profiles import SingleProfile, ProfileSet


class MovingProfilesTilt(ProfileSet):
    name = "tilt moving profiles"

    @property
    @abstractmethod
    def homingFast(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def homingSlow(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def moveFast(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def moveSlow(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def layerMoveSlow(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def layerRelease(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def layerMoveFast(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def reserved(self) -> SingleProfile:
        pass


class Tilt(Axis):

    @property
    def name(self) -> str:
        return "tilt"

    @cached_property
    def sensitivity(self) -> int:
        return self._config.tiltSensitivity

    @cached_property
    def home_position(self) -> Ustep:
        return Ustep(0)

    @cached_property
    def config_height_position(self) -> Ustep:
        return self._config.tiltHeight

    @cached_property
    def minimal_position(self) -> Ustep:
        return self.home_position

    @abstractmethod
    def get_tune_profile_up(self, slow_move: bool) -> SingleProfile:
        """get profile for up move"""

    @abstractmethod
    def get_tune_profile_down(self, slow_move: bool) -> SingleProfile:
        """get profile for up move"""

    @abstractmethod
    def layer_up_wait(self, profile: SingleProfile=None, tiltHeight: Ustep=Ustep(0)) -> None:
        """tilt up during the print"""

    def layer_down_wait(self, profile: SingleProfile=None) -> None:
        asyncio.run(self.layer_down_wait_async(profile=profile))

    @abstractmethod
    async def layer_down_wait_async(self, profile: SingleProfile=None) -> None:
        """tilt up during the print"""

    def stir_resin(self) -> None:
        asyncio.run(self.stir_resin_async())

    @abstractmethod
    async def stir_resin_async(self) -> None:
        """stiring moves of tilt."""

    def _move_api_min(self) -> None:
        self.move(self.home_position)

    def _move_api_max(self) -> None:
        self.move(self._config.tiltMax)

    @staticmethod
    def _raise_move_failed():
        raise TiltMoveFailed()

    @staticmethod
    def _raise_home_failed():
        raise TiltHomeFailed()

    @property
    @abstractmethod
    def profiles(self) -> MovingProfilesTilt:
        """all tilt profiles"""

    @property
    @abstractmethod
    def tune(self) -> ProfileSet:
        """tilt tune profiles"""
