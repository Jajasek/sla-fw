# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable=too-few-public-methods

from unittest.mock import Mock

from PySignal import Signal


class Network:
    def __init__(self):
        self.ip = "1.2.3.4"
        self.devices = {"eth0": "1.2.3.4"}
        self.hostname = "test_hostname"
        self.net_change = Signal()

    def start_net_monitor(self):
        pass


def fake_network_system_bus():
    mock = Mock()
    get_mock = Mock()
    get_mock.AddressData = [{"address": "1.2.3.4"}]
    mock.get.return_value = get_mock
    return mock