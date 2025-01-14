#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info
from cmk.base.plugins.agent_based.agent_based_api.v1 import SNMPTree, startswith


def parse_atto_fibrebridge_sas(string_table):
    phy_operstates = {
        -1: "unknown",
        1: "online",
        2: "offline",
    }

    sas_operstates = {
        -1: "unknown",
        1: "online",
        2: "offline",
        # From the MIB: "Degraded state is entered when fewer than all four PHYs are online."
        3: "degraded,",
    }

    sas_adminstates = {
        -1: "unknown",
        1: "disabled",
        2: "enabled",
    }

    parsed = {}
    for line in string_table:
        port_info = {}
        port_info["oper_state"] = sas_operstates[int(line[1])]
        port_info["admin_state"] = sas_adminstates[int(line[6])]

        for port_number, line_index in enumerate(range(2, 6)):
            port_info["state_phy_%d" % (port_number + 1)] = phy_operstates[int(line[line_index])]

        parsed[line[0]] = port_info

    return parsed


def inventory_atto_fibrebridge_sas(parsed):
    for item, port_info in parsed.items():
        if port_info["admin_state"] == "enabled":
            yield item, None


def check_atto_fibrebridge_sas(item, _no_params, parsed):
    port_info = parsed[item]
    oper_state = port_info["oper_state"]

    operstate_severities = {
        "unknown": 3,
        "online": 0,
        "degraded": 1,
        "offline": 2,
    }

    yield operstate_severities[oper_state], "Operational state: " + oper_state

    for phy_index in range(1, 5):
        yield 0, "PHY%d operational state: %s" % (phy_index, port_info["state_phy_%d" % phy_index])


check_info["atto_fibrebridge_sas"] = LegacyCheckDefinition(
    detect=startswith(".1.3.6.1.2.1.1.2.0", ".1.3.6.1.4.1.4547"),
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.4547.2.3.3.3.1",
        oids=["2", "3", "4", "5", "6", "7", "8"],
    ),
    parse_function=parse_atto_fibrebridge_sas,
    service_name="SAS Port %s",
    discovery_function=inventory_atto_fibrebridge_sas,
    check_function=check_atto_fibrebridge_sas,
)
