#!/usr/bin/env bash

# This file is part of the SL1 firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

if [ -n "${1}" ]; then
        LOG_PATH=$1
else
        PATTERN="/run/media/root/*"
        USBS=( ${PATTERN} )
        LOG_PATH=${USBS[0]}/log.emergency.txt.xz
fi;

echo "${LOG_PATH}"

(
        for i in $(journalctl --list-boots | awk '{print $1}'); do
                echo "########## REBOOT: ${i} ##########";
                journalctl --no-pager --boot "${i}";
        done;
) | xz -T0 -0 > "${LOG_PATH}"
sync "${LOG_PATH}"