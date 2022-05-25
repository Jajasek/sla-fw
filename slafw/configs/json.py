# This file is part of the SLA firmware
# Copyright (C) 2014-2018 Futur3d - www.futur3d.net
# Copyright (C) 2018-2019 Prusa Research s.r.o. - www.prusa3d.com
# Copyright (C) 2020-2022 Prusa Development a.s. - www.prusa3d.com
# SPDX-License-Identifier: GPL-3.0-or-later

import json

from slafw.configs.common import ValueConfigCommon
from slafw.errors.errors import ConfigException


class JsonConfig(ValueConfigCommon):
    """
    Main config class based on JSON files.

    Inherit this to create a JSON configuration
    """

    def read_text(self, text: str, factory: bool = False, defaults: bool = False) -> None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exception:
            raise ConfigException("Failed to decode config content:\n %s" % text) from exception
        self._fill_from_dict(self, self._values.values(), data, factory, defaults)

    def _dump_for_save(self, factory: bool = False) -> str:
        return json.dumps(self.as_dictionary(nondefault=False, factory=factory), indent=4)
