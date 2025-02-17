#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from typing import Any, Mapping, Optional, Sequence, Union

from cmk.base.check_api import passwordstore_get_cmdline
from cmk.base.config import special_agent_info


def agent_3par_arguments(
    params: Mapping[str, Any], hostname: str, ipaddress: Optional[str]
) -> Sequence[Union[str, tuple[str, str, str]]]:
    args = [
        "--user",
        params["user"],
        "--password",
        passwordstore_get_cmdline("%s", params["password"]),
        "--port",
        params["port"],
    ]
    if not params.get("verify_cert", False):
        args.append("--no-cert-check")

    if "values" in params:
        args += ["--values", ",".join(params["values"])]

    args.append(ipaddress or hostname)

    return args


special_agent_info["3par"] = agent_3par_arguments
