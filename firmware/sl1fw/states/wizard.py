# This file is part of the SL1 firmware
# Copyright (C) 2020 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

from enum import unique, Enum


@unique
class WizardState(Enum):
    INIT = 0
    RUNNING = 1
    DONE = 2
    FAILED = 3
    CANCELED = 4
    STOPPED = 5

    # Group enter states - user printer reconfiguration
    PREPARE_WIZARD_PART_1 = 1000
    PREPARE_WIZARD_PART_2 = 1001
    PREPARE_WIZARD_PART_3 = 1002
    PREPARE_CALIBRATION_PLATFORM_INSERT = 1010
    PREPARE_DISPLAYTEST = 1011
    PREPARE_CALIBRATION_TANK_PLACEMENT = 1012
    PREPARE_CALIBRATION_TILT_ALIGN = 1013
    PREPARE_CALIBRATION_PLATFORM_ALIGN = 1014
    PREPARE_CALIBRATION_FINISH = 1015

    # User action required states
    CLOSE_COVER = 2000
    TEST_DISPLAY = 2001
    TEST_AUDIO = 2002
    LEVEL_TILT = 2003

    OPEN_COVER = 2100
    REMOVE_SAFETY_STICKER = 2101
    REMOVE_SIDE_FOAM = 2102
    REMOVE_TANK_FOAM = 2103  # Remove resin tank
    REMOVE_DISPLAY_FOIL = 2104  # Peel off exposure display foil

    @staticmethod
    def finished_states():
        return [WizardState.FAILED, WizardState.DONE, WizardState.CANCELED]


@unique
class WizardId(Enum):
    UNKNOWN = 0
    THE_WIZARD = 1
    CALIBRATION = 2
    DISPLAY = 3
    COMPLETE_UNBOXING = 4
    KIT_UNBOXING = 5


@unique
class WizardCheckState(Enum):
    WAITING = 0
    RUNNING = 1
    SUCCESS = 2
    FAILURE = 3
    WARNING = 4
    USER = 5
    CANCELED = 6