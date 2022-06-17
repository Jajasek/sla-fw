# This file is part of the SLA firmware
# Copyright (C) 2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
from time import sleep
from pathlib import Path
from typing import List

from slafw import defines
from slafw.configs.hw import HwConfig
from slafw.configs.unit import Ustep
from slafw.configs.value import DictOfConfigs
from slafw.errors.errors import TiltPositionFailed
from slafw.hardware.printer_model import PrinterModel
from slafw.hardware.axis import HomingStatus
from slafw.hardware.power_led import PowerLed
from slafw.hardware.sl1.tower import TowerSL1
from slafw.hardware.sl1.axis import SingleProfileSL1, AxisSL1
from slafw.hardware.tilt import MovingProfilesTilt, Tilt
from slafw.motion_controller.controller import MotionController


TILT_CFG_LOCAL = defines.configDir / "profiles_tilt.json"

class MovingProfilesTiltSL1(MovingProfilesTilt):
    # pylint: disable=too-many-ancestors
    homingFast = DictOfConfigs(SingleProfileSL1)      # type: ignore
    homingSlow = DictOfConfigs(SingleProfileSL1)      # type: ignore
    moveFast = DictOfConfigs(SingleProfileSL1)        # type: ignore
    moveSlow = DictOfConfigs(SingleProfileSL1)        # type: ignore
    layerMoveSlow = DictOfConfigs(SingleProfileSL1)   # type: ignore
    layerRelease = DictOfConfigs(SingleProfileSL1)    # type: ignore
    layerMoveFast = DictOfConfigs(SingleProfileSL1)   # type: ignore
    reserved = DictOfConfigs(SingleProfileSL1)        # type: ignore
    __definition_order__ = tuple(locals())


class TiltSL1(Tilt, AxisSL1):
    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-public-methods
    # pylint: disable=too-many-arguments

    def __init__(self, mcc: MotionController, config: HwConfig,
                 power_led: PowerLed, tower: TowerSL1, printer_model: PrinterModel):
        super().__init__(config, power_led)
        self._mcc = mcc
        self._tower = tower
        defaults = Path(defines.dataPath) / printer_model.name / f"default_profiles_{self.name}.json" # type: ignore[attr-defined]
        self._profiles = MovingProfilesTiltSL1(factory_file_path=TILT_CFG_LOCAL, default_file_path=defaults)
        self._sensitivity = {
            #                -2       -1        0        +1       +2
            "homingFast": [[20, 5], [20, 6], [20, 7], [21, 9], [22, 12]],
            "homingSlow": [[16, 3], [16, 5], [16, 7], [16, 9], [16, 11]],
        }

    def start(self):
        self.actual_profile = self._profiles.homingFast    # type: ignore
        try:
            self.set_stepper_sensitivity(self.sensitivity)
        except RuntimeError as e:
            self._logger.error("%s - ignored", e)
        self.apply_all_profiles()

    @property
    def position(self) -> Ustep:
        return Ustep(self._mcc.doGetInt("?tipo"))

    @position.setter
    def position(self, position: Ustep) -> None:
        self._check_units(position, Ustep)
        if self.moving:
            raise TiltPositionFailed("Failed to set tilt position since its moving")
        self._mcc.do("!tipo", int(position))
        self._target_position = position
        self._logger.debug("Position set to: %d ustep", self._target_position)

    @property
    def moving(self):
        if self._mcc.doGetInt("?mot") & 2:
            return True
        return False

    def move(self, position):
        self._check_units(position, Ustep)
        self._mcc.do("!tima", int(position))
        self._target_position = position
        self._logger.debug("Move initiated. Target position: %d ustep",
                           self._target_position)

    def stop(self):
        axis_moving = self._mcc.doGetInt("?mot")
        self._mcc.do("!mot", axis_moving & ~2)
        self._target_position = self.position
        self._logger.debug("Move stopped. Rewriting target position to: %d ustep",
                           self._target_position)

    def go_to_fullstep(self, go_up: bool):
        self._mcc.do("!tigf", int(go_up))

    async def layer_down_wait_async(self, slowMove: bool = False) -> None:
        profile = self._config.tuneTilt[0] if slowMove else self._config.tuneTilt[1]
        # initial release movement with optional sleep at the end
        self.actual_profile = self._profiles[profile[0]]
        if profile[1] > 0:
            self.move(self.position - Ustep(profile[1]))
            while self.moving:
                await asyncio.sleep(0.1)
        await asyncio.sleep(profile[2] / 1000.0)
        # next movement may be splited
        self.actual_profile = self._profiles[profile[3]]
        movePerCycle = self.position // profile[4]
        for _ in range(profile[4]):
            self.move(self.position - movePerCycle)
            while self.moving:
                await asyncio.sleep(0.1)
            await asyncio.sleep(profile[5] / 1000.0)
        tolerance = Ustep(defines.tiltHomingTolerance)
        # if not already in endstop ensure we end up at defined bottom position
        if not self._mcc.checkState("endstop"):
            self.move(-tolerance)
            # tilt will stop moving on endstop OR by stallguard
            while self.moving:
                await asyncio.sleep(0.1)
        # check if tilt is on endstop and within tolerance
        if self._mcc.checkState("endstop") and -tolerance <= self.position <= tolerance:
            return
        # unstuck
        self._logger.warning("Tilt unstucking")
        self.actual_profile = self._profiles.layerRelease   # type: ignore
        count = Ustep(0)
        step = Ustep(128)
        while count < self._config.tiltMax and not self._mcc.checkState("endstop"):
            self.position = step
            self.move(self.home_position)
            while self.moving:
                await asyncio.sleep(0.1)
            count += step
        await self.sync_ensure_async(retries=0)

    def layer_up_wait(self, slowMove: bool = False, tiltHeight: Ustep = Ustep(0)) -> None:
        if tiltHeight == self.home_position: # use self._config.tiltHeight by default
            _tiltHeight = self.config_height_position
        else: # in case of calibration there is need to force new unstored tiltHeight
            _tiltHeight = tiltHeight
        profile = self._config.tuneTilt[2] if slowMove else self._config.tuneTilt[3]

        self.actual_profile = self._profiles[profile[0]]
        self.move(_tiltHeight - Ustep(profile[1]))
        while self.moving:
            sleep(0.1)
        sleep(profile[2] / 1000.0)
        self.actual_profile = self._profiles[profile[3]]

        # finish move may be also splited in multiple sections
        movePerCycle = (_tiltHeight - self.position) // profile[4]
        for _ in range(profile[4]):
            self.move(self.position + movePerCycle)
            while self.moving:
                sleep(0.1)
            sleep(profile[5] / 1000.0)

    def release(self) -> None:
        axis_enabled = self._mcc.doGetInt("?ena")
        self._mcc.do("!ena", axis_enabled & ~2)

    async def stir_resin_async(self) -> None:
        for _ in range(self._config.stirringMoves):
            self.actual_profile = self._profiles.homingFast # type: ignore
            # do not verify end positions
            self.move(self._config.tiltHeight)
            while self.moving:
                sleep(0.1)
            self.move(self.home_position)
            while self.moving:
                sleep(0.1)
            await self.sync_ensure_async()

    @property
    def homing_status(self) -> HomingStatus:
        return HomingStatus(self._mcc.doGetInt("?tiho"))

    def sync(self) -> None:
        self._mcc.do("!tiho")
        sleep(0.2)  #FIXME: mc-fw does not start the movement immediately -> wait a bit

    async def home_calibrate_wait_async(self):
        self._mcc.do("!tihc")
        await super().home_calibrate_wait_async()
        self.position = self.home_position

    async def verify_async(self) -> None:
        if not self.synced:
            while self._tower.moving:
                await asyncio.sleep(0.25)
            await self.sync_ensure_async()
        self.actual_profile = self._profiles.moveFast   # type: ignore
        await self.move_ensure_async(self._config.tiltHeight)

    @property
    def profiles(self) -> MovingProfilesTiltSL1:
        return self._profiles

    def _read_profile_id(self) -> int:
        return self._mcc.doGetInt("?tics")

    def _read_profile_data(self) -> List[int]:
        return self._mcc.doGetIntList("?ticf")

    def _write_profile_id(self, profile_id: int):
        self._mcc.do("!tics", profile_id)

    def _write_profile_data(self):
        self._mcc.do("!ticf", *self._actual_profile.dump())
