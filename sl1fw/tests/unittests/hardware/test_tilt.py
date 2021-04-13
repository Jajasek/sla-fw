# This file is part of the SL1 firmware
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2021 Prusa Research a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
from time import sleep
from typing import Optional

from sl1fw.tests.base import Sl1fwTestCase
from sl1fw import defines
from sl1fw.configs.hw import HwConfig
from sl1fw.libHardware import Hardware
from sl1fw.errors.errors import TiltPositionFailed
from sl1fw.hardware.tilt import TiltProfile


class TestTilt(Sl1fwTestCase):
    # pylint: disable=too-many-public-methods

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hw_config = None
        self.config = None
        self.hw: Optional[Hardware] = None

    def setUp(self):
        super().setUp()
        defines.cpuSNFile = str(self.SAMPLES_DIR / "nvmem")
        defines.cpuTempFile = str(self.SAMPLES_DIR / "cputemp")
        defines.factoryConfigPath = str(self.SL1FW_DIR / ".." / "factory/factory.toml")
        defines.counterLog = str(self.TEMP_DIR / "uvcounter-log.json")

        self.hw_config = HwConfig(file_path=self.SAMPLES_DIR / "hardware.cfg")
        self.hw = Hardware(self.hw_config)

        try:
            self.hw.connect()
            self.hw.start()
        except Exception as exception:
            self.tearDown()
            raise exception

    def tearDown(self):
        self.hw.exit()
        if self.EEPROM_FILE.exists():
            self.EEPROM_FILE.unlink()
        super().tearDown()

    def test_limits(self):
        self.assertEqual(self.hw_config.tiltMax, self.hw.tilt.max)
        self.assertEqual(self.hw_config.tiltMin, self.hw.tilt.min)

    def test_position(self):
        positions = [10000, 0]
        for position in positions:
            self.hw.tilt.position = position
            self.assertEqual(position, self.hw.tilt.position)
        self.hw.tilt.moveAbsolute(self.hw.tilt.max)
        with self.assertRaises(TiltPositionFailed):
            self.hw.tilt.position = position

    def test_movement(self):
        self.assertFalse(self.hw.tilt.moving)
        self.hw.tilt.moveAbsolute(self.hw.tilt.max)
        self.assertTrue(self.hw.tilt.moving)
        while self.hw.tilt.moving:
            sleep(0.1)
        self.assertFalse(self.hw.tilt.moving)
        self.assertTrue(self.hw.tilt.onTargetPosition)
        self.assertEqual(self.hw.tilt.max, self.hw.tilt.position)

    #TODO: test all possible scenarios
    def test_move(self):
        # nothing
        self.hw.tilt.position = 0
        self.hw.tilt.profileId = TiltProfile.temp
        self.hw.tilt.move(speed=0, set_profiles=False, fullstep=False)
        self.assertFalse(self.hw.tilt.moving)
        self.assertEqual(0, self.hw.tilt.position)
        self.assertEqual(TiltProfile.temp, self.hw.tilt.profileId)
        self.hw.tilt.stop()

        # move up without profile change
        self.hw.tilt.position = 0
        self.hw.tilt.profileId = TiltProfile.temp
        self.hw.tilt.move(speed=1, set_profiles=False, fullstep=False)
        self.assertTrue(self.hw.tilt.moving)
        self.assertLess(0, self.hw.tilt.position)
        self.assertEqual(TiltProfile.temp, self.hw.tilt.profileId)
        self.hw.tilt.stop()

        # move up slow with profile change
        self.hw.tilt.position = 0
        self.hw.tilt.profileId = TiltProfile.temp
        self.hw.tilt.move(speed=1, set_profiles=True, fullstep=False)
        self.assertTrue(self.hw.tilt.moving)
        self.assertLess(0, self.hw.tilt.position)
        self.assertEqual(TiltProfile.moveSlow, self.hw.tilt.profileId)
        self.hw.tilt.stop()

        # move up fast with profile change
        self.hw.tilt.position = 0
        self.hw.tilt.profileId = TiltProfile.temp
        self.hw.tilt.move(speed=2, set_profiles=True, fullstep=False)
        self.assertTrue(self.hw.tilt.moving)
        self.assertLess(0, self.hw.tilt.position)
        self.assertEqual(TiltProfile.homingFast, self.hw.tilt.profileId)
        self.hw.tilt.stop()

        # move up, stop and go to fullstep
        self.hw.tilt.position = 0
        self.hw.tilt.move(speed=1, set_profiles=True, fullstep=False)
        sleep(0.3)
        self.assertTrue(self.hw.tilt.moving)
        self.assertLess(0, self.hw.tilt.position)
        self.hw.tilt.stop()
        position = self.hw.tilt.position
        self.hw.tilt.move(speed=0, set_profiles=True, fullstep=True)
        self.assertLessEqual(position, self.hw.tilt.position)
        # TODO: ensure tilt is in fullstep

    def test_sensitivity(self):
        #pylint: disable=protected-access
        with self.assertRaises(ValueError):
            self.hw.tilt.sensitivity(-3)
        with self.assertRaises(ValueError):
            self.hw.tilt.sensitivity(3)
        sensitivities = [-2, -1, 0, 1, 2]
        originalProfiles = self.hw.tilt.profiles
        homingFast = originalProfiles[TiltProfile.homingFast.value]
        homingSlow = originalProfiles[TiltProfile.homingSlow.value]
        for sensitivity in sensitivities:
            self.hw.tilt.sensitivity(sensitivity)
            homingFast[4] = self.hw.tilt._tiltAdjust[TiltProfile.homingFast][sensitivity + 2][0]
            homingFast[5] = self.hw.tilt._tiltAdjust[TiltProfile.homingFast][sensitivity + 2][1]
            homingSlow[4] = self.hw.tilt._tiltAdjust[TiltProfile.homingSlow][sensitivity + 2][0]
            homingSlow[5] = self.hw.tilt._tiltAdjust[TiltProfile.homingSlow][sensitivity + 2][1]
            newProfiles = self.hw.tilt.profiles
            self.assertEqual(homingFast, newProfiles[TiltProfile.homingFast.value])
            self.assertEqual(homingSlow, newProfiles[TiltProfile.homingSlow.value])

    #FIXME: test goToFullstep. Simulator behaves differently from real HW ()

    def test_stir_resin(self):
        self.hw.tilt.stirResin()
        self.assertTrue(self.hw.tilt.synced)
        self.assertEqual(0, self.hw.tilt.position)

    def test_sync(self):
        self.hw.tilt.sync()
        self.assertLess(0, self.hw.tilt.homingStatus)
        for _ in range(1, 100):
            if self.hw.tilt.synced:
                break
            sleep(0.1)
        self.assertEqual(0, self.hw.tilt.homingStatus)
        self.assertTrue(self.hw.tilt.synced)
        self.hw.motorsRelease()
        self.assertFalse(self.hw.tilt.synced)

    def test_sync_wait(self):
        self.hw.tilt.syncWait()
        self.assertTrue(self.hw.tilt.synced)
        self.assertEqual(0, self.hw.tilt.position)
        self.assertTrue(self.hw.tilt.onTargetPosition)

    def test_profileNames(self):
        self.assertEqual(
            [
                "temp",
                "homingFast",
                "homingSlow",
                "moveFast",
                "moveSlow",
                "layerMoveSlow",
                "layerRelease",
                "layerMoveFast",
                "reserved2",
            ],
            self.hw.tilt.profileNames,
        )

    def test_profileId(self):
        profiles = [TiltProfile.layerMoveFast, TiltProfile.layerMoveSlow]
        for profile in profiles:
            self.hw.tilt.profileId = profile
            self.assertEqual(profile, self.hw.tilt.profileId)

    def test_profile(self):
        testProfile = [12345, 23456, 234, 345, 28, 8, 1234]
        self.hw.tilt.profileId = TiltProfile.reserved2
        self.assertNotEqual(testProfile, self.hw.tilt.profile)
        self.hw.tilt.profile = testProfile
        self.assertEqual(testProfile, self.hw.tilt.profile)

    def test_profiles(self):
        profiles = self.hw.tilt.profiles
        self.assertEqual(type([]), type(profiles))
        self.assertEqual(8, len(profiles)) # all except temp
        for profile in profiles:
            self.assertEqual(7, len(profile))
            self.assertEqual(type([int]), type(profile))
        for profileId, data in enumerate(profiles):
            self.hw.tilt.profileId = TiltProfile(profileId)
            self.assertEqual(TiltProfile(profileId), self.hw.tilt.profileId)
            self.assertEqual(data, self.hw.tilt.profile)

    def test_home(self):
        self.hw.tilt.homeCalibrateWait()
        while self.hw.tilt.moving:
            sleep(0.1)
        self.assertEqual(0, self.hw.tilt.position)
        self.assertTrue(self.hw.tilt.synced)

    def test_stop(self):
        self.hw.tilt.position = 0
        self.hw.tilt.moveAbsolute(self.hw_config.tiltMax)
        self.hw.tilt.stop()
        self.assertFalse(self.hw.tilt.moving)
        self.assertLess(0, self.hw.tilt.position)
        self.assertGreater(self.hw_config.tiltMax, self.hw.tilt.position)
        self.assertFalse(self.hw.tilt.onTargetPosition)

    def test_up(self):
        self.hw.tilt.moveUp()
        while self.hw.tilt.moving:
            sleep(0.1)
        self.assertTrue(self.hw.tilt.onTargetPosition)

    def test_up_wait(self):
        self.hw.tilt.moveUpWait()
        self.assertTrue(self.hw.tilt.onTargetPosition)

    def test_down(self):
        self.hw.tilt.moveDown()
        while self.hw.tilt.moving:
            sleep(0.1)
        self.assertTrue(self.hw.tilt.onTargetPosition)

    def test_down_wait(self):
        self.hw.tilt.moveDownWait()
        self.assertTrue(self.hw.tilt.onTargetPosition)

    def test_layer_up(self):
        self.hw.tilt.layerUpWait()

    def test_layer_down(self):
        self.hw.tilt.layerDownWait()

if __name__ == "__main__":
    unittest.main()