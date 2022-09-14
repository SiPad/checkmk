#!/usr/bin/env python3
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from collections.abc import Sequence

import pytest

from tests.unit.conftest import FixRegister

from cmk.utils.type_defs import CheckPluginName, SectionName

from cmk.base import item_state
from cmk.base.api.agent_based.type_defs import StringTable
from cmk.base.api.agent_based.utils import GetRateError
from cmk.base.plugins.agent_based.agent_based_api.v1 import Service

STRING_TABLE = [
    [
        '[{"Id":',
        '"id_10_VolumeReadOps",',
        '"Label":',
        '"123",',
        '"Timestamps":',
        "[],",
        '"Values":',
        "[[0.0030055,",
        "null]],",
        '"StatusCode":',
        '"Complete"},',
        '{"Id":',
        '"id_10_VolumeWriteOps",',
        '"Label":',
        '"123",',
        '"Timestamps":',
        "[],",
        '"Values":',
        "[[0.0030055,",
        "null]],",
        '"StatusCode":',
        '"Complete"},',
        '{"Id":',
        '"id_10_VolumeReadBytes",',
        '"Label":',
        '"123",',
        '"Timestamps":',
        "[],",
        '"Values":',
        "[[0.0030055,",
        "null]],",
        '"StatusCode":',
        '"Complete"},',
        '{"Id":',
        '"id_10_VolumeWriteBytes",',
        '"Label":',
        '"123",',
        '"Timestamps":',
        "[],",
        '"Values":',
        "[[0.0030055,",
        "null]],",
        '"StatusCode":',
        '"Complete"},',
        '{"Id":',
        '"id_10_VolumeQueueLength",',
        '"Label":',
        '"123",',
        '"Timestamps":',
        "[],",
        '"Values":',
        "[[0.0030055,",
        "null]],",
        '"StatusCode":',
        '"Complete"},',
        '{"Id":',
        '"id_10_BurstBalance",',
        '"Label":',
        '"123",',
        '"Timestamps":',
        "[],",
        '"Values":',
        "[[0.0030055,",
        "null]],",
        '"StatusCode":',
        '"Complete"}',
        "]",
    ]
]


@pytest.mark.parametrize(
    "string_table, discovery_result",
    [
        pytest.param(
            STRING_TABLE,
            [Service(item="123")],
            id="For every disk in the section a Service is discovered.",
        ),
        pytest.param(
            [],
            [],
            id="If the section is empty, no Services are discovered.",
        ),
    ],
)
def test_aws_ebs_discovery(
    string_table: StringTable,
    discovery_result: Sequence[Service],
    fix_register: FixRegister,
) -> None:
    check = fix_register.check_plugins[CheckPluginName("aws_ebs")]
    parse_function = fix_register.agent_sections[SectionName("aws_ebs")].parse_function

    assert list(check.discovery_function(parse_function(string_table))) == discovery_result


def test_check_aws_ebs_raise_get_rate_error(fix_register: FixRegister) -> None:
    check = fix_register.check_plugins[CheckPluginName("aws_ebs")]
    parse_function = fix_register.agent_sections[SectionName("aws_ebs")].parse_function
    with pytest.raises(GetRateError):
        list(
            check.check_function(
                item="123",
                params={},
                section=parse_function(STRING_TABLE),
            )
        )


def test_check_aws_ebs(fix_register: FixRegister) -> None:
    for metric in [
        "aws_ebs_disk_io_read_ios",
        "aws_ebs_disk_io_write_ios",
        "aws_ebs_disk_io_read_throughput",
        "aws_ebs_disk_io_write_throughput",
        "aws_ebs_disk_io_queue_len",
    ]:
        item_state.set_item_state(f"{metric}.123", (0, 0))
    check = fix_register.check_plugins[CheckPluginName("aws_ebs")]
    parse_function = fix_register.agent_sections[SectionName("aws_ebs")].parse_function
    check_result = check.check_function(item="123", params={}, section=parse_function(STRING_TABLE))
    assert len(list(check_result)) == 10
