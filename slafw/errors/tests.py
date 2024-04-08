# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2020 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import inspect
from typing import Collection, Tuple

from slafw.errors import errors, warnings
from slafw.motion_controller.trace import Trace
from slafw.states.printer import PrinterState

FAKE_ARGS = {
    "url: str": "http://example.com",
    "total_bytes: int": 0,
    "completed_bytes: int": 0,
    "failed_fans: List[int]": [1],
    "failed_fans: List": [1],
    "failed_fan_names: List[str]": "UV Fan",
    "failed_fan_names: List": "UV Fan",
    "volume: float": 12.3,
    "volume_ml: float": 12.3,
    "failed_sensors: List[int]": [2],
    "failed_sensor_names: List[str]": ["UV LED temperature"],
    "message: str": "Error occurred",
    "trace: slafw.motion_controller.trace.Trace = None": Trace(10),
    "current_state: enum.Enum": PrinterState.PRINTING,
    "allowed_states: List[enum.Enum]": [PrinterState.PRINTING],
    "ambient_temperature: float": 42,
    "actual_model: str": "Some other printer",
    "actual_variant: str": "Some other variant",
    "printer_variant: str": "default",
    "project_variant: str": "something_else",
    "changes: Dict[str, Tuple[Any, Any]]": {"exposure": (10, 20)},
    "changes: Dict": {"exposure": (10, 20)},
    "measured_resin_ml: float": 12.3,
    "required_resin_ml: float": 23.4,
    "warning: Warning": warnings.AmbientTooHot(ambient_temperature=42.0),  # type: ignore
    "name: str": "fan1",
    "fan: str": "fan1",
    "rpm: Union[int, NoneType]": 1234,
    "rpm: Optional[int]": 1234,
    "rpm: Optional": 1234,
    "avg: Union[int, NoneType]": 1234,
    "avg: Optional[int]": 1234,
    "avg: Optional": 1234,
    "fanError: Dict[int, bool]": {0: False, 1: True, 2: False},
    "fanError: Dict": {0: False, 1: True, 2: False},
    "uv_temp_deg_c: float": 42.42,
    "position_nm: int": 123450,
    "position: int": 12345,
    "position_mm: float": 48.128,
    "tilt_position: Union[int, NoneType]": 5000,
    "tilt_position: Optional[int]": 5000,
    "tilt_position: Optional": 5000,
    "tower_position_nm: int": 100000000,
    "sn: str": "123456789",
    "min_resin_ml: float": 10,
    "failed_fans_text: str": "UV LED Fan",
    "fans: List[str]": ["UV LED Fan"],
    "found: float": 240,
    "allowed: float": 250,
    "intensity: float": 150,
    "threshold: float": 125,
    "nonprusa_code: int": 42,
    "temperature: float": 36.8,
    "sensor: str": "Ambient temperature",
    "message: str = ''": "Exception message string",
    "reason: str": "Everything is broken",
    "pwm: int": 142,
    "pwm_min: int": 150,
    "pwm_max: int": 250,
    "transmittance: float": -1,
    "counter_h: int": 500,
    "fan__map_HardwareDeviceId: int": 2000,
    "sensor__map_HardwareDeviceId: int": 1000,
    "min: float": 5.0,
    "max: float": 55.0,
    "min_rpm: int": 1000,
    "max_rpm: int": 5000,
    "avg_rpm: int": 500,
    "lower_bound_rpm: int": 1200,
    "upper_bound_rpm: int": 1800,
    "error: int": 1,
}

IGNORED_ARGS = {"self", "args", "kwargs"}


def get_classes(get_errors: bool = False, get_warnings: bool = False) -> Collection[Tuple[str, Exception]]:
    classes = []
    if get_errors:
        classes.extend(inspect.getmembers(errors))
    if get_warnings:
        classes.extend(inspect.getmembers(warnings))

    for name, cls in classes:
        if not isinstance(cls, type):
            continue

        if not issubclass(cls, Exception):
            continue

        yield name, cls


def get_instance(cls):
    parameters = inspect.signature(cls.__init__).parameters
    args = [FAKE_ARGS[str(param)] for name, param in parameters.items() if name not in IGNORED_ARGS]
    return cls(*args)


def get_instance_by_code(code: str):
    for _, cls in get_classes(get_errors=True, get_warnings=True):
        if getattr(cls, "CODE", None).code == code:
            return get_instance(cls)
    raise ValueError(f"Unknown exception code to inject {code}")
