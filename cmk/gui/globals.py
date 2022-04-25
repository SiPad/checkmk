#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from __future__ import annotations

import logging
from functools import partial
from typing import Any, TYPE_CHECKING

from werkzeug.local import LocalProxy

from cmk.gui.ctx_stack import _lookup_app_object, request_local_attr

#####################################################################
# a namespace for storing data during an application context

if TYPE_CHECKING:
    # Import cycles
    from cmk.gui import htmllib, http


######################################################################
# TODO: This should live somewhere else...
class PrependURLFilter(logging.Filter):
    def filter(self, record):
        if record.levelno >= logging.ERROR:
            record.msg = "%s %s" % (request.requested_url, record.msg)
        return True


# From app context
current_app = LocalProxy(partial(_lookup_app_object, "app"))
g: Any = LocalProxy(partial(_lookup_app_object, "g"))


# NOTE: All types FOO below are actually a Union[Foo, LocalProxy], but
# LocalProxy is meant as a transparent proxy, so we leave it out to de-confuse
# mypy. LocalProxy uses a lot of reflection magic, which can't be understood by
# tools in general.

# From request context
request: http.Request = request_local_attr("request")
response: http.Response = request_local_attr("response")

html: htmllib.html = request_local_attr("html")
