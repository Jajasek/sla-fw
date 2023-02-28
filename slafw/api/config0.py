# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import functools
from typing import Any, Dict
from typing import TYPE_CHECKING

from pydbus.generic import signal

from slafw.api.decorators import auto_dbus, dbus_api, wrap_dict_data_recursive
from slafw.configs.hw import HwConfig
from slafw.configs.value import Value, NumericValue, ListValue, TextValue

if TYPE_CHECKING:
    from slafw.hardware.hardware import BaseHardware


def wrap_hw_config(cls: Config0):
    """
    This is a custom decorator that adds properties to target class that map to HWConfig properties

    :param cls: Target class, Has to be config compatible
    :return: Modified class with properties added
    """
    for val in vars(HwConfig):
        if val.startswith("raw_"):
            continue

        if not isinstance(getattr(HwConfig, val), property):
            continue

        def func():
            pass

        func.__name__ = val
        setattr(cls, val, auto_dbus(wrap_property()(func)))
        if val not in cls.CHANGED_MAP:
            cls.CHANGED_MAP[val] = set()
        cls.CHANGED_MAP[val].add(val)
    return cls


def wrap_property(func_name=None):
    """
    Parametric decorator to turn a function into a property mapping to HWConfig property

    :param func_name: Input function
    :return: mapped property
    """

    def decor(func):
        if func_name is None:
            name = func.__name__
        else:
            name = func_name
        f = getattr(HwConfig, name)
        assert isinstance(f, property)

        @functools.wraps(f.fget)
        def getter(self):
            return getattr(self.config, name)

        getter.__name__ = func.__name__
        getter.__doc__ = f.__doc__

        if f.fset:
            @functools.wraps(f.fset)
            def setter(self, value):
                setattr(self.config, name, value)

            return property(fget=getter, fset=setter)

        return property(fget=getter)

    return decor


@dbus_api
@wrap_hw_config
class Config0:
    """
    This class provides automatic mapping to HwConfig properties

    The content is generated by a decorator based on the current HwConfig specification. This allows us to expose new
    HwConfig properties automatically. Simple on change mapping is added automatically hwconfig.name -> Config0.name.
    This one can be extended by putting custom mapping to CHANGED_MAP.
    """

    __INTERFACE__ = "cz.prusa3d.sl1.config0"

    PropertiesChanged = signal()

    def __init__(self, config: HwConfig):
        self.config = config
        self.config.add_onchange_handler(self._on_change)

    @auto_dbus
    def save(self) -> None:
        """
        Save the configuration

        :return: None
        """
        self.config.write()

    @auto_dbus
    @property
    def constraints(self) -> Dict[str, Dict[str, Any]]:
        """
        Configuration constraints

        Provides dictionary containing configuration value constraints. The dictionary is uses value names as keys and
        values are dictionaries holding constraint names as keys and constraint values as values. Example:

        .. highlight:: python
        .. code-block:: python

            {
                'stirring_moves': {'min': 1, 'max': 10},
                'stirring_delay_ms': {'max': 300000},
                'towerSensitivity': {'min': -2, 'max': 2},
                ...
            }

        :return: Config settings constraints as dictionary
        """
        values = self.config.get_values()
        return wrap_dict_data_recursive({
            name: self._process_value(value)
            for name, value in values.items()
            if not name.startswith("raw_") and self._process_value(value)
        })

    @staticmethod
    def _process_value(value: Value):
        ret = {}
        if isinstance(value, NumericValue):
            if value.min:
                ret["min"] = value.min
            if value.max:
                ret["max"] = value.max
        if isinstance(value, ListValue):
            ret["length"] = value.length
        if isinstance(value, TextValue):
            ret["regex"] = value.regex.pattern
        return ret

    def _on_change(self, key: str, _: Any):
        if key in self.CHANGED_MAP:
            for changed in self.CHANGED_MAP[key]:
                self.PropertiesChanged(self.__INTERFACE__, {changed: getattr(self.config, changed)}, [])

    CHANGED_MAP = {
        "screwMm": {"microStepsMM"},
        "raw_calibrated": {"calibrated"},
        "tiltHeight": {"calibrated"},
        "limit4fast": {"limit4fast"},
        "tankCleaningExposureTime": {"tankCleaningExposureTime"}
    }
