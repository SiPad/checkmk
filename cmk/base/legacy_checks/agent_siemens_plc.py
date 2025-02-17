#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from typing import Any, Mapping, Optional, Sequence

from cmk.base.config import special_agent_info


def agent_siemens_plc_arguments(
    params: Mapping[str, Any], hostname: str, ipaddress: Optional[str]
) -> Sequence[str]:
    args = []

    if "timeout" in params:
        args += ["--timeout", params["timeout"]]

    for device in params["devices"]:
        dev_args = device["host_name"]
        dev_args += ";%s" % device["host_address"]
        dev_args += ";%d" % device["rack"]
        dev_args += ";%d" % device["slot"]
        dev_args += ";%d" % device["tcp_port"]

        for value in params["values"] + device["values"]:
            v = []
            for part in value:
                if isinstance(part, tuple):
                    v.append(":".join(map(str, part)))
                else:
                    v.append(str(part))
            dev_args += ";%s" % ",".join(v)

        args.append("--hostspec")
        args.append(dev_args)

    return args


special_agent_info["siemens_plc"] = agent_siemens_plc_arguments
