#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (C) 2019 tribe29 GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import pytest

from cmk.base.plugins.agent_based.agent_based_api.v1 import TableRow
from cmk.base.plugins.agent_based.inventory_lnx_ip_r import inventory_lnx_ip_r, parse_lnx_ip_r


@pytest.mark.parametrize(
    "string_table, expected_result",
    [
        ([], []),
        (
            [
                [
                    "default",
                    "via",
                    "10.10.0.1",
                    "dev",
                    "wlan",
                    "proto",
                    "static",
                ],
                [
                    "10.10.0.0/16",
                    "dev",
                    "wlan0",
                    "proto",
                    "kernel",
                    "scope",
                    "link",
                    "src",
                    "10.10.0.41",
                    "metric",
                    "9",
                ],
            ],
            [
                TableRow(
                    path=["networking", "routes"],
                    key_columns={
                        "target": "0.0.0.0/0",
                    },
                    inventory_columns={
                        "type": "gateway",
                        "device": "wlan",
                        "gateway": "10.10.0.1",
                    },
                    status_columns={},
                ),
                TableRow(
                    path=["networking", "routes"],
                    key_columns={
                        "target": "10.10.0.0/16",
                    },
                    inventory_columns={
                        "type": "local",
                        "device": "wlan0",
                        "gateway": None,
                    },
                    status_columns={},
                ),
            ],
        ),
    ],
)
def test_lnx_ip_r(string_table, expected_result):
    assert list(inventory_lnx_ip_r(parse_lnx_ip_r(string_table))) == expected_result
