# This file is part of the SLA firmware
# Copyright (C) 2022 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import unittest

from slafw.errors.errors import ConfigException
from slafw.tests.base import SlafwTestCase

from slafw.hardware.base.profiles import SingleProfile, ProfileSet
from slafw.hardware.sl1.tilt import MovingProfilesTiltSL1
from slafw.hardware.sl1.tower import MovingProfilesTowerSL1
from slafw.configs.value import IntValue, DictOfConfigs


class DummySingleProfile(SingleProfile):
    first_value = IntValue(888, minimum=0, maximum=999, factory=True)
    second_value = IntValue(777, minimum=0, maximum=999, factory=True)
    third_value = IntValue(666, minimum=0, maximum=999, factory=True)
    __definition_order__ = tuple(locals())

class ErrorSingleProfile(SingleProfile):
    first = IntValue(minimum=0, maximum=999, factory=True)
    __definition_order__ = tuple(locals())

class DummyProfileSet(ProfileSet):
    first_profile = DictOfConfigs(DummySingleProfile)
    second_profile = DictOfConfigs(DummySingleProfile)
    third_profile = DictOfConfigs(DummySingleProfile)
    __definition_order__ = tuple(locals())

class ErrorProfileSet1(ProfileSet):
    first_profile = DictOfConfigs(ErrorSingleProfile)
    second_profile = DictOfConfigs(ErrorSingleProfile)
    third_profile = DictOfConfigs(ErrorSingleProfile)
    __definition_order__ = tuple(locals())

class ErrorProfileSet2(ProfileSet):
    first = DictOfConfigs(DummySingleProfile)
    __definition_order__ = tuple(locals())

class TestProfileSet(SlafwTestCase):
    def setUp(self):
        super().setUp()
        self.infile = self.SAMPLES_DIR / "test_profile_set.json"
        self.outfile = self.TEMP_DIR / "test_out.json"

    def test_errors(self):
        with self.assertRaises(ConfigException):
            ErrorProfileSet1(self.infile)
        with self.assertRaises(ConfigException):
            ErrorProfileSet2(self.infile)

    def test_write_changed(self):
        test_profiles = DummyProfileSet(factory_file_path=self.outfile, default_file_path=self.infile)
        test_profiles.first_profile.first_value = 999
        test_profiles.write_factory()
        with open(self.outfile, encoding="utf-8") as o:
            self.assertEqual({'first_profile': {'first_value': 999}}, json.load(o))

    def test_write_unchanged(self):
        test_profiles = DummyProfileSet(factory_file_path=self.outfile, default_file_path=self.infile)
        test_profiles.write_factory()
        with open(self.outfile, encoding="utf-8") as o:
            self.assertFalse(len(json.load(o)))

    def test_writer(self):
        test_profiles = DummyProfileSet(factory_file_path=self.outfile, default_file_path=self.infile)
        writer = test_profiles.second_profile.get_writer()
        writer.second_value = 555
        writer.third_value = 999
        writer.commit(factory=True)
        with open(self.outfile, encoding="utf-8") as o:
            self.assertEqual({'second_profile': {'second_value': 555, 'third_value': 999}}, json.load(o))

    def test_load_as_defaults(self):
        test_profiles = DummyProfileSet(factory_file_path=self.infile)
        fp = test_profiles.first_profile
        self.assertEqual(888, fp.get_values()["first_value"].get_default_value(fp))
        self.assertEqual(777, fp.get_values()["second_value"].get_default_value(fp))
        self.assertEqual(666, fp.get_values()["third_value"].get_default_value(fp))
        sp = test_profiles.second_profile
        self.assertEqual(888, sp.get_values()["first_value"].get_default_value(sp))
        tp = test_profiles.third_profile
        self.assertEqual(888, tp.get_values()["first_value"].get_default_value(tp))
        test_profiles = DummyProfileSet(default_file_path=self.infile)
        fp = test_profiles.first_profile
        self.assertEqual(1, fp.get_values()["first_value"].get_default_value(fp))
        self.assertEqual(2, fp.get_values()["second_value"].get_default_value(fp))
        self.assertEqual(3, fp.get_values()["third_value"].get_default_value(fp))
        sp = test_profiles.second_profile
        self.assertEqual(11, sp.get_values()["first_value"].get_default_value(sp))
        self.assertEqual(22, sp.get_values()["second_value"].get_default_value(sp))
        self.assertEqual(33, sp.get_values()["third_value"].get_default_value(sp))
        tp = test_profiles.third_profile
        self.assertEqual(111, tp.get_values()["first_value"].get_default_value(tp))
        self.assertEqual(222, tp.get_values()["second_value"].get_default_value(tp))
        self.assertEqual(333, tp.get_values()["third_value"].get_default_value(tp))

    def test_is_modified(self):
        test_profiles = DummyProfileSet(default_file_path=self.infile)
        self.assertFalse(test_profiles.first_profile.is_modified)
        test_profiles = DummyProfileSet(factory_file_path=self.infile)
        self.assertTrue(test_profiles.first_profile.is_modified)

    def test_factory_reset(self):
        test_profiles = DummyProfileSet(self.infile)
        test_profiles.factory_reset()
        self.assertEqual(888, test_profiles.first_profile.first_value)
        self.assertEqual(777, test_profiles.first_profile.second_value)
        self.assertEqual(666, test_profiles.first_profile.third_value)
        test_profiles.write_factory(self.outfile)
        with open(self.outfile, encoding="utf-8") as o:
            self.assertEqual({}, json.load(o))
        test_profiles = DummyProfileSet(factory_file_path=self.infile)
        test_profiles.factory_reset(True)
        self.assertEqual(888, test_profiles.first_profile.first_value)
        self.assertEqual(777, test_profiles.first_profile.second_value)
        self.assertEqual(666, test_profiles.first_profile.third_value)
        test_profiles.write_factory(self.outfile)
        with open(self.outfile, encoding="utf-8") as o:
            self.assertEqual({}, json.load(o))

class TestMovingProfilesSL1(SlafwTestCase):
    def test_tilt_profiles(self):
        profiles = MovingProfilesTiltSL1(factory_file_path=self.SAMPLES_DIR / "profiles_tilt.json")
        self.assertEqual(2560, profiles.homingFast.starting_steprate)
        self.assertEqual(1500, profiles.homingSlow.maximum_steprate)
        self.assertEqual(0, profiles.moveFast.acceleration)
        self.assertEqual(80, profiles.moveSlow.deceleration)
        self.assertEqual(44, profiles.layerMoveSlow.current)
        self.assertEqual(63, profiles.layerRelease.stallguard_threshold)
        self.assertEqual(2000, profiles.layerMoveFast.coolstep_threshold)
        self.assertEqual(3840, profiles.reserved.starting_steprate)

    def test_tower_profiles(self):
        profiles = MovingProfilesTowerSL1(factory_file_path=self.SAMPLES_DIR / "profiles_tower.json")
        self.assertEqual(2500, profiles.homingFast.starting_steprate)
        self.assertEqual(7500, profiles.homingSlow.maximum_steprate)
        self.assertEqual(250, profiles.moveFast.acceleration)
        self.assertEqual(50, profiles.moveSlow.deceleration)
        self.assertEqual(34, profiles.layer.current)
        self.assertEqual(6, profiles.layerMove.stallguard_threshold)
        self.assertEqual(500, profiles.superSlow.coolstep_threshold)
        self.assertEqual(2500, profiles.resinSensor.starting_steprate)

    def test_profile_overlay(self):
        profiles = MovingProfilesTowerSL1(
                factory_file_path=self.SAMPLES_DIR / "profiles_tower_overlay.json",
                default_file_path=self.SAMPLES_DIR / "profiles_tower.json")
        self.assertEqual(2499, profiles.homingFast.starting_steprate)
        self.assertEqual(7500, profiles.homingSlow.maximum_steprate)


if __name__ == '__main__':
    unittest.main()
