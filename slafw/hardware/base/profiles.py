# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path
from typing import Optional, Callable
from functools import cache # type: ignore
from abc import abstractmethod

from slafw.configs.value import ValueConfig
from slafw.configs.json import JsonConfig
from slafw.configs.writer import ConfigWriter
from slafw.errors.errors import ConfigException


class SingleProfile(ValueConfig):
    @property
    @abstractmethod
    def __definition_order__(self) -> tuple:
        """defined items order"""

    def __init__(self):
        super().__init__(is_master=True)
        self.name: Optional[str] = None
        self.idx: Optional[int] = None
        self.saver: Optional[Callable] = None

    def __iter__(self):
        for name in self.__definition_order__:
            if not name.startswith("_"):
                yield self._values[name]

    def __eq__(self, other):
        if isinstance(other, SingleProfile):
            return list(self.dump()) == list(other.dump())
        if isinstance(other, list):
            return list(self.dump()) == other
        return False

    def dump(self):
        for value in self:
            yield value.value_getter(self)

    def get_writer(self) -> ConfigWriter:
        return ConfigWriter(self)

    def write(self, file_path: Optional[Path]=None, factory: bool=False, nondefault: bool=False) -> None:
        if not callable(self.saver):
            raise ConfigException("Write fuction not defined")
        self.saver(file_path, factory, nondefault)  # pylint: disable=not-callable

    @property
    def is_modified(self):
        for val in self._values.values():
            if val.get_factory_value(self) is not None:
                return True
        return False


class ProfileSet(JsonConfig):
    @property
    @abstractmethod
    def __definition_order__(self) -> tuple:
        """defined items order"""

    @property
    @abstractmethod
    def name(self) -> str:
        """profile set name"""

    def __init__(
            self,
            file_path: Optional[Path]=None,
            factory_file_path: Optional[Path]=None,
            default_file_path: Optional[Path]=None
    ):
        self._apply_profile: Optional[Callable] = None
        super().__init__(
                file_path=file_path,
                factory_file_path=factory_file_path,
                default_file_path=default_file_path,
                is_master=True
        )
        self.read_file()
        idx = 0
        for name in self.__definition_order__:
            if not name.startswith("_"):
                profile = getattr(self, name)
                if profile is None:
                    raise ConfigException(f"Missing data for profile <{name}>")
                for value in profile:
                    if value.value_getter(profile) is None:
                        raise ConfigException(f"Missing data for value <{value.key}> in profile <{name}>")
                profile.name = name
                profile.idx = idx
                profile.saver = self.write
                idx += 1

    def __iter__(self):
        for name in self.__definition_order__:
            if not name.startswith("_"):
                yield getattr(self, name)

    @cache
    def __getitem__(self, key):
        for profile in self:
            if profile.idx == key:
                return profile
        raise IndexError

    def apply_all(self):
        if callable(self._apply_profile):
            for profile in self:
                self._apply_profile(profile)

    @property
    def apply_profile(self) -> Callable:
        return self._apply_profile

    @apply_profile.setter
    def apply_profile(self, callback: Callable):
        self._apply_profile = callback
