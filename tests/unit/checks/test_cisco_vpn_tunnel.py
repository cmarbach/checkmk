import pytest

pytestmark = pytest.mark.checks

_STRING_TABLE = [
    [
        ["761856", "211.26.203.53", "6048", "6080"],
        ["12509184", "158.244.78.71", "77536", "77632"],
        ["13746176", "110.173.49.157", "57872", "60680"],
        ["22503424", "237.39.169.243", "618480", "619920"],
        ["43585536", "88.40.117.192", "4720", "4720"],
        ["45854720", "99.155.108.155", "18944", "18992"],
        ["55197696", "107.36.151.171", "13120", "13120"],
        ["67805184", "211.167.210.107", "1564", "1600"],
        ["81604608", "62.111.62.165", "1828836", "540776"],
        ["89939968", "158.8.11.214", "86240", "86720"],
        ["100876288", "176.210.155.217", "3176", "2424"],
        ["107544576", "13.232.54.46", "12400", "12464"],
    ],
    [
        ["221540352", "1", "29603616", "29606724"],
        ["13746176", "1", "4275671278", "552070119"],
        ["181399552", "1", "34440168", "265351058"],
        ["248475648", "1", "971342856", "972010160"],
        ["81604608", "1", "418226309", "2404964353"],
        ["12509184", "1", "1445263205", "1124929982"],
        ["253952000", "1", "356940563", "861342895"],
        ["242581504", "1", "103816", "34333876"],
        ["242581504", "1", "1951457951", "1352517430"],
        ["242581504", "1", "2260468", "3172212"],
        ["242581504", "1", "879749", "1769163"],
        ["89939968", "1", "8302751", "85269964"],
        ["89939968", "1", "836794", "1016956"],
        ["107544576", "1", "729386986", "181978684"],
        ["146874368", "1", "20042695", "139631395"],
        ["190656512", "1", "1632632", "2622595"],
        ["175759360", "1", "1190381852", "2072225340"],
        ["175759360", "1", "6456504", "9433584"],
        ["175759360", "1", "2037804", "2062476"],
        ["175759360", "1", "2558867", "2271498"],
        ["175759360", "1", "2618100", "3383666"],
        ["190656512", "1", "51552982", "1464267"],
        ["183275520", "1", "368040", "7596836"],
        ["22503424", "1", "2911153", "2849138"],
        ["22503424", "1", "2815031", "2755928"],
        ["22503424", "1", "4583776", "72612782"],
        ["22503424", "1", "5580736", "5342356"],
        ["221634560", "1", "995702379", "1060325044"],
        ["221634560", "1", "9778928", "8595392"],
        ["221634560", "1", "542364", "542364"],
        ["234635264", "1", "3169086", "10990082"],
        ["176361472", "1", "4133255", "334298"],
        ["100876288", "1", "805509", "996792"],
        ["55197696", "1", "0", "0"],
        ["202616832", "1", "328", "212"],
        ["45854720", "1", "0", "0"],
        ["242376704", "1", "528", "720"],
        ["81604608", "1", "0", "0"],
        ["195731456", "1", "0", "0"],
        ["761856", "1", "0", "0"],
        ["761856", "1", "0", "0"],
        ["179777536", "1", "120", "156"],
        ["43585536", "1", "0", "0"],
        ["242581504", "1", "0", "0"],
    ],
]

_SECTION = {
    "110.173.49.157": {
        "phase_1": (57872.0, 60680.0),
        "phase_2": (4275671278.0, 552070119.0),
    },
    "211.167.210.107": {
        "phase_1": (1564.0, 1600.0)
    },
    "176.210.155.217": {
        "phase_1": (3176.0, 2424.0),
        "phase_2": (805509.0, 996792.0),
    },
    "62.111.62.165": {
        "phase_1": (1828836.0, 540776.0),
        "phase_2": (418226309.0, 2404964353.0),
    },
    "158.244.78.71": {
        "phase_1": (77536.0, 77632.0),
        "phase_2": (1445263205.0, 1124929982.0),
    },
    "107.36.151.171": {
        "phase_1": (13120.0, 13120.0),
        "phase_2": (0.0, 0.0),
    },
    "13.232.54.46": {
        "phase_1": (12400.0, 12464.0),
        "phase_2": (729386986.0, 181978684.0),
    },
    "158.8.11.214": {
        "phase_1": (86240.0, 86720.0),
        "phase_2": (9139545.0, 86286920.0),
    },
    "237.39.169.243": {
        "phase_1": (618480.0, 619920.0),
        "phase_2": (15890696.0, 83560204.0),
    },
    "99.155.108.155": {
        "phase_1": (18944.0, 18992.0),
        "phase_2": (0.0, 0.0),
    },
    "88.40.117.192": {
        "phase_1": (4720.0, 4720.0),
        "phase_2": (0.0, 0.0),
    },
    "211.26.203.53": {
        "phase_1": (6048.0, 6080.0),
        "phase_2": (0.0, 0.0),
    },
}


def test_parse_cisco_vpn_tunnel(check_manager):
    assert check_manager.get_check("cisco_vpn_tunnel").run_parse(_STRING_TABLE) == _SECTION


def test_inventory_cisco_vpn_tunnel(check_manager):
    assert sorted(check_manager.get_check("cisco_vpn_tunnel").run_discovery(_SECTION)) == [(
        ip,
        {},
    ) for ip in sorted(_SECTION)]


@pytest.mark.parametrize(
    "item, params, expected_result",
    [
        pytest.param(
            "110.173.49.157",
            {},
            (
                0,
                "Phase 1: in: 0 B/s, out: 0 B/s, Phase 2: in: 0 B/s, out: 0 B/s",
                [("if_in_octets", 0.0), ("if_out_octets", 0.0)],
            ),
            id="standard case",
        ),
        pytest.param(
            "211.167.210.107",
            {},
            (
                0,
                "Phase 1: in: 0 B/s, out: 0 B/s, Phase 2 missing",
                [("if_in_octets", 0.0), ("if_out_octets", 0.0)],
            ),
            id="phase 2 missing",
        ),
        pytest.param(
            "110.173.49.157",
            {
                "tunnels": [
                    ("110.173.49.157", "herbert", 1),
                    ("110.173.49.157", "hansi", 2),
                    ("158.244.78.71", "fritz", 3),
                ],
            },
            (
                0,
                "[herbert] [hansi] Phase 1: in: 0 B/s, out: 0 B/s, Phase 2: in: 0 B/s, out: 0 B/s",
                [("if_in_octets", 0.0), ("if_out_octets", 0.0)],
            ),
            id="with aliases",
        ),
        pytest.param(
            "1.2.3.4",
            {},
            (
                2,
                "Tunnel is missing",
                [("if_in_octets", 0), ("if_out_octets", 0)],
            ),
            id="tunnel missing, no params",
        ),
        pytest.param(
            "1.2.3.4",
            {"state": 3},
            (
                3,
                "Tunnel is missing",
                [("if_in_octets", 0), ("if_out_octets", 0)],
            ),
            id="tunnel missing, default missing state configured",
        ),
        pytest.param(
            "1.2.3.4",
            {
                "tunnels": [
                    ("110.173.49.157", "herbert", 1),
                    ("1.2.3.4", "annegret", 1),
                ],
                "state": 3,
            },
            (
                1,
                "[annegret] Tunnel is missing",
                [("if_in_octets", 0), ("if_out_octets", 0)],
            ),
            id="tunnel missing, default and tunnel-specific missing state configured",
        ),
    ],
)
def test_check_cisco_vpn_tunnel(
        check_manager,
        item,
        params,
        expected_result,
):
    assert check_manager.get_check("cisco_vpn_tunnel").run_check(
        item,
        params,
        _SECTION,
    ) == expected_result
