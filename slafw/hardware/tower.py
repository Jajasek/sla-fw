# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from abc import abstractmethod

from slafw.configs.unit import Nm
from slafw.errors.errors import TowerMoveFailed, TowerHomeFailed
from slafw.hardware.axis import Axis
from slafw.hardware.base.profiles import SingleProfile, ProfileSet


class MovingProfilesTower(ProfileSet):
    name = "tower moving profiles"

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
    def layer(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def layerMove(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def superSlow(self) -> SingleProfile:
        pass

    @property
    @abstractmethod
    def resinSensor(self) -> SingleProfile:
        pass


class Tower(Axis):

    @property
    def name(self) -> str:
        return "tower"

    @property
    def sensitivity(self) -> int:
        return self._config.towerSensitivity

    @property
    def home_position(self) -> Nm:
        return self._config.tower_height_nm

    @property
    def config_height_position(self) -> Nm:
        return self.home_position

    @property
    def minimal_position(self) -> Nm:
        return Nm(0)

    # FIXME: move to the config
    @property
    def min_nm(self) -> Nm:
        return -(self._config.max_tower_height_mm + Nm(5)) * 1_000_000

    # FIXME: move to the config
    @property
    def above_surface_nm(self) -> Nm:
        return -(self._config.max_tower_height_mm - Nm(5)) * 1_000_000

    # FIXME: move to the config
    @property
    def max_nm(self) -> Nm:
        return 2 * self._config.max_tower_height_mm * 1_000_000

    # FIXME: move to the config
    @property
    def end_nm(self) -> Nm:
        return self._config.max_tower_height_mm * 1_000_000

    # FIXME: move to the config
    @property
    def calib_pos_nm(self) -> Nm:  # pylint: disable=no-self-use
        return Nm(1_000_000)

    # FIXME: move to the config
    @property
    def resin_start_pos_nm(self) -> Nm:  # pylint: disable=no-self-use
        return Nm(36_000_000)

    # FIXME: move to the config
    @property
    def resin_end_pos_nm(self) -> Nm:  # pylint: disable=no-self-use
        return Nm(1_000_000)

    def _move_api_min(self) -> None:
        self.move(self._config.calib_tower_offset_nm)

    def _move_api_max(self) -> None:
        self.move(self._config.tower_height_nm)

    @staticmethod
    def _raise_move_failed():
        raise TowerMoveFailed()

    @staticmethod
    def _raise_home_failed():
        raise TowerHomeFailed()

    @property
    @abstractmethod
    def profiles(self) -> MovingProfilesTower:
        """all tower profiles"""
