# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import re
from abc import ABC, abstractmethod
from enum import unique, Enum
from typing import List, Dict


def parse_axis(text: str, axis: str) -> int:
    try:
        mm, dec = re.search(fr"(?<={axis}:)([0-9]*)\.([0-9]*)", text).groups()
        nm = int(mm) * 1000 * 1000
        for i, c in enumerate(dec):
            if i <= 5:
                nm += int(c) * 10 ** (5 - i)
    except Exception as exception:
        raise ValueError from exception

    return nm


def format_axis(position_nm: int) -> str:
    return f"{position_nm // 1000000}.{position_nm % 1000000}"


class AxisProfileBase:  # pylint: disable = too-few-public-methods
    """Base for axis profile enums. Important for type checking"""


@unique
class AxisProfile(AxisProfileBase, Enum):
    temp = -1


@unique
class Axis(Enum):
    TOWER = 0
    TILT = 1


class Axis(ABC):

########## position/movement ##########

    @property
    @abstractmethod
    def max(self) -> int:
        """return max axis position"""

    @property
    @abstractmethod
    def min(self) -> int:
        """return min axis position"""

    @property
    @abstractmethod
    def position(self) -> int:
        """get current position of the axis"""

    @position.setter
    @abstractmethod
    def position(self, position_ustep: int):
        """set current position of the axis"""

    @property
    @abstractmethod
    def target_position(self) -> int:
        """return last target position which has to be set before every move"""

    @property
    @abstractmethod
    def on_target_position(self) -> bool:
        """return if axis has completed the movement and is on expected position"""

    @property
    @abstractmethod
    def moving(self) -> bool:
        """determine if axis is moving at the moment"""

    @abstractmethod
    def move_absolute(self, position) -> bool:
        """initiate movement of the axis"""

    @abstractmethod
    def move(self, speed: int, set_profiles: bool = True, fullstep=False) -> bool:
        """high level movement of the axis with predefined properties"""

    @abstractmethod
    def stop(self):
        """stop movement of the axis (do not release)"""

########## homing ##########

    @property
    @abstractmethod
    def synced(self) -> bool:
        """basic check if axis is synchronized (homing has succesfully finished)"""

    @property
    @abstractmethod
    def homing_status(self) -> int:
        """get actual state of axis homing"""

    @abstractmethod
    def sync(self) -> bool:
        """start axis homing"""

    def sync_wait(self, retries: int = 2) -> None:
        """blocking method for axis homing. retries = number of additional tries when homing fails"""
        asyncio.run(self.sync_wait_async(retries=retries))

    @abstractmethod
    async def sync_wait_async(self, retries: int = 2) -> None:
        """blocking method for axis homing. retries = number of additional tries when homing fails"""

########## profiles ##########

    @property
    @abstractmethod
    def profile_names(self) -> List[str]:
        """list of all profile names of given axis"""

    @property
    @abstractmethod
    def profile_id(self) -> AxisProfileBase:
        """return selected profile"""

    @profile_id.setter
    @abstractmethod
    def profile_id(self, profile_id: AxisProfileBase):
        """select profile"""

    @property
    @abstractmethod
    def profile(self) -> List[int]:
        """get values of currently selected profile in MC"""

    @profile.setter
    @abstractmethod
    def profile(self, profile: List[int]):
        """update values of currently selected profile in MC"""

    @property
    @abstractmethod
    def profiles(self) -> List[List[int]]:
        """get all profiles from MC"""

    @profiles.setter
    @abstractmethod
    def profiles(self, profiles: List[List[int]]):
        """save all profiles to MC"""

    @property
    @abstractmethod
    def sensitivity_dict(self) -> Dict[str, List[List[int]]]:
        """return dict with axis sensitivity values"""
