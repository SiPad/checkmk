#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from tests.testlib.site import Site


def test_load_openapi_plugin(site: Site) -> None:
    with site.copy_file(
        "openapi_plugin.py", "local/lib/check_mk/gui/plugins/openapi/test_plugin.py"
    ):
        assert (
            site.python_helper("helper_test_load_openapi_plugin.py").check_output().rstrip()
            == "True"
        )
