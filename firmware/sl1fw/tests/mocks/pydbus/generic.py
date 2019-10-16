# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later


def __fake_signal_handler(*args, **kwargs):
    print(f"Signal fired: {args}, {kwargs}")


def signal():
    return __fake_signal_handler
