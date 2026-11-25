"""器官 ``excavation-monitor`` 的判据矩阵（ORGAN-PLAYBOOK §3.0 判据 1 补测）。

补测原则（§3.0 追加要求 2）：**每条规范条款 × ok / rejected 两态 + 边界**。
本文件按「字典项 × 判据 × 两态」「状态迁移表 6×6」「间隔档位 × 四条规则」铺开，
不去重复主文件已经断言过的同一件事（幂等 id、同一算式两次运行一致等在主文件）。

与主文件的分工：
- ``test_excavation_monitor.py``：语义与契约（每条判据一处深测 + 旧仓对账）；
- ``test_excavation_monitor_matrix.py``（本文件）：**逐项铺满**，一个字典项一条用例，
  避免「改了 top_h_disp 顺带坏了 water_level 却没人发现」。

不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数）。
"""

from __future__ import annotations

import importlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from speccalc.core import Basis, Clause, ClauseMissing, ContractError, EXIT_CONTRACT, OK, REJECTED  # noqa: E402
from speccalc.core.data import load as load_data  # noqa: E402
from speccalc.modules import load_builtin  # noqa: E402

load_builtin()
ORGAN = importlib.import_module("speccalc.modules.excavation-monitor")
SLUG = ORGAN.SLUG

BASIS = Basis(
    version="matrix-20261125",
    clauses=(
        Clause(code="GB 50497-2019", clause="alarm-values", version="2019", text="报警值"),
        Clause(code="GB 50497-2019", clause="monitoring-frequency", version="2019", text="监测频率"),
        Clause(code="住房城乡建设部令第 37 号", clause="MOHURD-37", version="2018", text="加密观测"),
    ),
)

DATA = load_data("excavation-monitor.json")
ITEMS = {item["code"]: item for item in DATA["items"]}
DUAL = sorted(code for code, item in ITEMS.items() if item["control_kind"] == "dual")
CUM_ONLY = sorted(code for code, item in ITEMS.items() if item["control_kind"] == "cumulative")


# ---------------------------------------------------------------------------
# 构造器（本文件自足，不跨测试模块 import）
# ---------------------------------------------------------------------------
def _control(value, unit):
    return {"kind": "design_value", "status": "verified", "value": value, "unit": unit,
            "evidence": "设计文件 DK-2026-001"}


def _point(code, item_code, observations, cum=None, rate=None):
    item = ITEMS[item_code]
    control = {}
    if cum is not None:
        control["cumulative"] = _control(cum, item["unit"])
    if rate is not None:
        control["rate"] = _control(rate, "%s/d" % item["unit"])
    return {"code": code, "item_code": item_code, "control": control,
            "observations": list(observations)}


def _obs(round_index, value, missing=False):
    return {"round": round_index, "value": value, "missing": missing}


def _rounds(count, depth=3.0):
    out = []
    for index in range(1, count + 1):
        day = index if index <= 28 else 28
        out.append({"index": index, "observed_on": "2026-01-%02d" % day,
                    "excavation_depth_m": depth})
    return out


def _run(subject, basis=BASIS):
    return tuple(ORGAN.evaluate(subject, basis))


def _one(point, count=1, **extra):
    """跑一次并取**最后一轮**的记录（多轮 subject 上逐轮判一次）。"""
    subject = {"project": "MATRIX", "points": [point], "rounds": _rounds(count)}
    if "rate_window_days" not in extra and point.get("control", {}).get("rate"):
        extra["rate_window_days"] = 5
    if "ratio" in extra:
        extra["prewarning_ratio"] = extra.pop("ratio")
    subject.update(extra)
    records = _run(subject)
    assert records, "没有任何可判行"
    return records[-1]


def _verdict(point, count=1, **extra):
    return _one(point, count, **extra).verdict


def _has_transition(frm, to):
    return to in ORGAN.TRANSITIONS.get(frm, frozenset())


def _freq(subject):
    return tuple(record for record in _run(subject) if record.item_id.startswith("freq."))


def _limit(band_id, days, status="verified"):
    return {"band": band_id, "max_interval_days": days, "kind": "standard_value",
            "status": status, "evidence": "条文核对记录 %s" % band_id}


# ---------------------------------------------------------------------------
# A. 字典 14 项 × 累计量两态（每项用自己的单位，不是同一断言重复 14 次）
# ---------------------------------------------------------------------------
def test_item_top_h_disp_cum_ok():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 9.9)], cum=10.0)) == OK


def test_item_top_h_disp_cum_rejected():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 10.0)], cum=10.0)) == REJECTED


def test_item_top_v_disp_cum_ok():
    assert _verdict(_point("P", "top_v_disp", [_obs(1, 7.0)], cum=8.0)) == OK


def test_item_top_v_disp_cum_rejected():
    assert _verdict(_point("P", "top_v_disp", [_obs(1, 8.5)], cum=8.0)) == REJECTED


def test_item_deep_h_disp_cum_ok():
    assert _verdict(_point("P", "deep_h_disp", [_obs(1, 20.0)], cum=30.0)) == OK


def test_item_deep_h_disp_cum_rejected():
    assert _verdict(_point("P", "deep_h_disp", [_obs(1, 31.0)], cum=30.0)) == REJECTED


def test_item_column_v_disp_cum_ok():
    assert _verdict(_point("P", "column_v_disp", [_obs(1, 2.0)], cum=5.0)) == OK


def test_item_column_v_disp_cum_rejected():
    assert _verdict(_point("P", "column_v_disp", [_obs(1, 5.0)], cum=5.0)) == REJECTED


def test_item_pit_bottom_heave_cum_ok():
    assert _verdict(_point("P", "pit_bottom_heave", [_obs(1, 11.0)], cum=12.0)) == OK


def test_item_pit_bottom_heave_cum_rejected():
    assert _verdict(_point("P", "pit_bottom_heave", [_obs(1, 12.5)], cum=12.0)) == REJECTED


def test_item_prop_force_cum_ok():
    assert _verdict(_point("P", "prop_force", [_obs(1, 300.0)], cum=500.0)) == OK


def test_item_prop_force_cum_rejected():
    assert _verdict(_point("P", "prop_force", [_obs(1, 500.0)], cum=500.0)) == REJECTED


def test_item_anchor_force_cum_ok():
    assert _verdict(_point("P", "anchor_force", [_obs(1, 34.0)], cum=35.0)) == OK


def test_item_anchor_force_cum_rejected():
    assert _verdict(_point("P", "anchor_force", [_obs(1, 36.0)], cum=35.0)) == REJECTED


def test_item_water_level_cum_ok():
    assert _verdict(_point("P", "water_level", [_obs(1, 0.4)], cum=0.5)) == OK


def test_item_water_level_cum_rejected():
    assert _verdict(_point("P", "water_level", [_obs(1, 0.5)], cum=0.5)) == REJECTED


def test_item_ground_v_disp_cum_ok():
    assert _verdict(_point("P", "ground_v_disp", [_obs(1, 4.0)], cum=10.0)) == OK


def test_item_ground_v_disp_cum_rejected():
    assert _verdict(_point("P", "ground_v_disp", [_obs(1, 10.0)], cum=10.0)) == REJECTED


def test_item_building_v_disp_cum_ok():
    assert _verdict(_point("P", "building_v_disp", [_obs(1, 9.0)], cum=10.0)) == OK


def test_item_building_v_disp_cum_rejected():
    assert _verdict(_point("P", "building_v_disp", [_obs(1, 10.1)], cum=10.0)) == REJECTED


def test_item_building_tilt_cum_ok():
    assert _verdict(_point("P", "building_tilt", [_obs(1, 1.9)], cum=2.0)) == OK


def test_item_building_tilt_cum_rejected():
    assert _verdict(_point("P", "building_tilt", [_obs(1, 2.0)], cum=2.0)) == REJECTED


def test_item_pipeline_v_disp_cum_ok():
    assert _verdict(_point("P", "pipeline_v_disp", [_obs(1, 9.0)], cum=10.0)) == OK


def test_item_pipeline_v_disp_cum_rejected():
    assert _verdict(_point("P", "pipeline_v_disp", [_obs(1, 11.0)], cum=10.0)) == REJECTED


def test_item_soil_h_disp_cum_ok():
    assert _verdict(_point("P", "soil_h_disp", [_obs(1, 24.0)], cum=25.0)) == OK


def test_item_soil_h_disp_cum_rejected():
    assert _verdict(_point("P", "soil_h_disp", [_obs(1, 25.0)], cum=25.0)) == REJECTED


def test_item_crack_width_cum_ok():
    assert _verdict(_point("P", "crack_width", [_obs(1, 0.2)], cum=0.3)) == OK


def test_item_crack_width_cum_rejected():
    assert _verdict(_point("P", "crack_width", [_obs(1, 0.35)], cum=0.3)) == REJECTED


# ---------------------------------------------------------------------------
# B. 12 项 dual × 速率两态
# ---------------------------------------------------------------------------
def test_rate_top_h_disp_ok():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 0.0), _obs(2, 4.0)], cum=99.0, rate=5.0), 2) == OK


def test_rate_top_h_disp_rejected():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 0.0), _obs(2, 5.0)], cum=99.0, rate=5.0), 2) == REJECTED


def test_rate_top_v_disp_ok():
    assert _verdict(_point("P", "top_v_disp", [_obs(1, 0.0), _obs(2, 1.9)], cum=99.0, rate=2.0), 2) == OK


def test_rate_top_v_disp_rejected():
    assert _verdict(_point("P", "top_v_disp", [_obs(1, 0.0), _obs(2, 2.0)], cum=99.0, rate=2.0), 2) == REJECTED


def test_rate_deep_h_disp_ok():
    assert _verdict(_point("P", "deep_h_disp", [_obs(1, 0.0), _obs(2, 4.9)], cum=99.0, rate=5.0), 2) == OK


def test_rate_deep_h_disp_rejected():
    assert _verdict(_point("P", "deep_h_disp", [_obs(1, 0.0), _obs(2, 5.5)], cum=99.0, rate=5.0), 2) == REJECTED


def test_rate_column_v_disp_ok():
    assert _verdict(_point("P", "column_v_disp", [_obs(1, 0.0), _obs(2, 0.4)], cum=99.0, rate=0.5), 2) == OK


def test_rate_column_v_disp_rejected():
    assert _verdict(_point("P", "column_v_disp", [_obs(1, 0.0), _obs(2, 0.5)], cum=99.0, rate=0.5), 2) == REJECTED


def test_rate_pit_bottom_heave_ok():
    assert _verdict(_point("P", "pit_bottom_heave", [_obs(1, 0.0), _obs(2, 0.9)], cum=99.0, rate=1.0), 2) == OK


def test_rate_pit_bottom_heave_rejected():
    assert _verdict(_point("P", "pit_bottom_heave", [_obs(1, 0.0), _obs(2, 1.0)], cum=99.0, rate=1.0), 2) == REJECTED


def test_rate_prop_force_ok():
    assert _verdict(_point("P", "prop_force", [_obs(1, 0.0), _obs(2, 99.0)], cum=999.0, rate=100.0), 2) == OK


def test_rate_prop_force_rejected():
    assert _verdict(_point("P", "prop_force", [_obs(1, 0.0), _obs(2, 100.0)], cum=999.0, rate=100.0), 2) == REJECTED


def test_rate_anchor_force_ok():
    assert _verdict(_point("P", "anchor_force", [_obs(1, 0.0), _obs(2, 2.4)], cum=999.0, rate=2.5), 2) == OK


def test_rate_anchor_force_rejected():
    assert _verdict(_point("P", "anchor_force", [_obs(1, 0.0), _obs(2, 2.5)], cum=999.0, rate=2.5), 2) == REJECTED


def test_rate_water_level_ok():
    assert _verdict(_point("P", "water_level", [_obs(1, 0.0), _obs(2, 0.2)], cum=99.0, rate=0.3), 2) == OK


def test_rate_water_level_rejected():
    assert _verdict(_point("P", "water_level", [_obs(1, 0.0), _obs(2, 0.35)], cum=99.0, rate=0.3), 2) == REJECTED


def test_rate_ground_v_disp_ok():
    assert _verdict(_point("P", "ground_v_disp", [_obs(1, 0.0), _obs(2, 1.0)], cum=99.0, rate=1.2), 2) == OK


def test_rate_ground_v_disp_rejected():
    assert _verdict(_point("P", "ground_v_disp", [_obs(1, 0.0), _obs(2, 1.2)], cum=99.0, rate=1.2), 2) == REJECTED


def test_rate_building_v_disp_ok():
    assert _verdict(_point("P", "building_v_disp", [_obs(1, 0.0), _obs(2, 0.4)], cum=99.0, rate=0.5), 2) == OK


def test_rate_building_v_disp_rejected():
    assert _verdict(_point("P", "building_v_disp", [_obs(1, 0.0), _obs(2, 0.6)], cum=99.0, rate=0.5), 2) == REJECTED


def test_rate_pipeline_v_disp_ok():
    assert _verdict(_point("P", "pipeline_v_disp", [_obs(1, 0.0), _obs(2, 1.4)], cum=99.0, rate=1.5), 2) == OK


def test_rate_pipeline_v_disp_rejected():
    assert _verdict(_point("P", "pipeline_v_disp", [_obs(1, 0.0), _obs(2, 1.6)], cum=99.0, rate=1.5), 2) == REJECTED


def test_rate_soil_h_disp_ok():
    assert _verdict(_point("P", "soil_h_disp", [_obs(1, 0.0), _obs(2, 2.9)], cum=99.0, rate=3.0), 2) == OK


def test_rate_soil_h_disp_rejected():
    assert _verdict(_point("P", "soil_h_disp", [_obs(1, 0.0), _obs(2, 3.0)], cum=99.0, rate=3.0), 2) == REJECTED


# ---------------------------------------------------------------------------
# C. 判据适用范围：14 项各自吃哪些判据
# ---------------------------------------------------------------------------
def test_scope_top_h_disp_is_dual():
    assert ORGAN._applicable_bases(ITEMS["top_h_disp"]) == ("cumulative", "rate")


def test_scope_top_v_disp_is_dual():
    assert ORGAN._applicable_bases(ITEMS["top_v_disp"]) == ("cumulative", "rate")


def test_scope_deep_h_disp_is_dual():
    assert ORGAN._applicable_bases(ITEMS["deep_h_disp"]) == ("cumulative", "rate")


def test_scope_column_v_disp_is_dual():
    assert ORGAN._applicable_bases(ITEMS["column_v_disp"]) == ("cumulative", "rate")


def test_scope_pit_bottom_heave_is_dual():
    assert ORGAN._applicable_bases(ITEMS["pit_bottom_heave"]) == ("cumulative", "rate")


def test_scope_prop_force_is_dual():
    assert ORGAN._applicable_bases(ITEMS["prop_force"]) == ("cumulative", "rate")


def test_scope_anchor_force_is_dual():
    assert ORGAN._applicable_bases(ITEMS["anchor_force"]) == ("cumulative", "rate")


def test_scope_water_level_is_dual():
    assert ORGAN._applicable_bases(ITEMS["water_level"]) == ("cumulative", "rate")


def test_scope_ground_v_disp_is_dual():
    assert ORGAN._applicable_bases(ITEMS["ground_v_disp"]) == ("cumulative", "rate")


def test_scope_building_v_disp_is_dual():
    assert ORGAN._applicable_bases(ITEMS["building_v_disp"]) == ("cumulative", "rate")


def test_scope_pipeline_v_disp_is_dual():
    assert ORGAN._applicable_bases(ITEMS["pipeline_v_disp"]) == ("cumulative", "rate")


def test_scope_soil_h_disp_is_dual():
    assert ORGAN._applicable_bases(ITEMS["soil_h_disp"]) == ("cumulative", "rate")


def test_scope_building_tilt_is_cumulative_only():
    assert ORGAN._applicable_bases(ITEMS["building_tilt"]) == ("cumulative",)


def test_scope_crack_width_is_cumulative_only():
    assert ORGAN._applicable_bases(ITEMS["crack_width"]) == ("cumulative",)


def test_cumulative_only_item_never_emits_rate_evidence():
    point = _point("P", "crack_width", [_obs(1, 1.0)], cum=5.0)
    point["control"]["rate"] = _control(9.0, "mm/d")
    assert _one(point).evidence["rate"] is None


# ---------------------------------------------------------------------------
# D. 状态迁移表 6×6（旧 ALLOWED_TRANSITIONS 全量，每条一条用例）
# ---------------------------------------------------------------------------
def test_transition_normal_to_normal_allowed():
    assert _has_transition("normal", "normal") is True


def test_transition_normal_to_prewarning_allowed():
    assert _has_transition("normal", "prewarning") is True


def test_transition_normal_to_alarm_allowed():
    assert _has_transition("normal", "alarm") is True


def test_transition_normal_to_alarmconfirmed_forbidden():
    assert _has_transition("normal", "alarm_confirmed") is False


def test_transition_normal_to_alarmhandled_forbidden():
    assert _has_transition("normal", "alarm_handled") is False


def test_transition_prewarning_to_normal_allowed():
    assert _has_transition("prewarning", "normal") is True


def test_transition_prewarning_to_prewarning_allowed():
    assert _has_transition("prewarning", "prewarning") is True


def test_transition_prewarning_to_alarm_allowed():
    assert _has_transition("prewarning", "alarm") is True


def test_transition_prewarning_to_alarmconfirmed_forbidden():
    assert _has_transition("prewarning", "alarm_confirmed") is False


def test_transition_prewarning_to_alarmhandled_forbidden():
    assert _has_transition("prewarning", "alarm_handled") is False


def test_transition_alarm_to_normal_forbidden():
    assert _has_transition("alarm", "normal") is False


def test_transition_alarm_to_prewarning_forbidden():
    assert _has_transition("alarm", "prewarning") is False


def test_transition_alarm_to_alarm_allowed():
    assert _has_transition("alarm", "alarm") is True


def test_transition_alarm_to_alarmconfirmed_allowed():
    assert _has_transition("alarm", "alarm_confirmed") is True


def test_transition_alarm_to_alarmhandled_allowed():
    assert _has_transition("alarm", "alarm_handled") is True


def test_transition_alarmconfirmed_to_normal_forbidden():
    assert _has_transition("alarm_confirmed", "normal") is False


def test_transition_alarmconfirmed_to_prewarning_forbidden():
    assert _has_transition("alarm_confirmed", "prewarning") is False


def test_transition_alarmconfirmed_to_alarm_forbidden():
    assert _has_transition("alarm_confirmed", "alarm") is False


def test_transition_alarmconfirmed_to_alarmconfirmed_allowed():
    assert _has_transition("alarm_confirmed", "alarm_confirmed") is True


def test_transition_alarmconfirmed_to_alarmhandled_allowed():
    assert _has_transition("alarm_confirmed", "alarm_handled") is True


def test_transition_alarmhandled_to_normal_allowed():
    assert _has_transition("alarm_handled", "normal") is True


def test_transition_alarmhandled_to_prewarning_allowed():
    assert _has_transition("alarm_handled", "prewarning") is True


def test_transition_alarmhandled_to_alarm_allowed():
    assert _has_transition("alarm_handled", "alarm") is True


def test_transition_alarmhandled_to_alarmconfirmed_forbidden():
    assert _has_transition("alarm_handled", "alarm_confirmed") is False


def test_transition_alarmhandled_to_alarmhandled_forbidden():
    assert _has_transition("alarm_handled", "alarm_handled") is False


def test_transition_table_has_five_states():
    assert sorted(ORGAN.TRANSITIONS) == [
        "alarm", "alarm_confirmed", "alarm_handled", "normal", "prewarning"]


def test_transition_unknown_state_is_refused():
    assert _has_transition("no_such_state", "normal") is False


def test_unclosed_states_are_the_two_alarm_states():
    assert sorted(ORGAN.UNCLOSED) == ["alarm", "alarm_confirmed"]


# ---------------------------------------------------------------------------
# E. 边界与容差（GE_EPS 1e-9 的两侧各测一次）
# ---------------------------------------------------------------------------
def test_boundary_cum_exactly_at_limit_is_rejected():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 25.0)], cum=25.0)) == REJECTED


def test_boundary_cum_one_eps_below_is_rejected():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 25.0 - 1e-10)], cum=25.0)) == REJECTED


def test_boundary_cum_one_eps_above_epsilon_band_is_ok():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 25.0 - 1e-6)], cum=25.0)) == OK


def test_boundary_cum_zero_against_zero_limit_is_rejected():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 0.0)], cum=0.0)) == REJECTED


def test_boundary_cum_negative_at_limit_is_rejected():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, -25.0)], cum=25.0)) == REJECTED


def test_boundary_rate_exactly_at_limit_is_rejected():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 0.0), _obs(2, 15.0)], cum=99.0, rate=3.0), 2) == REJECTED


def test_boundary_rate_one_eps_below_is_ok():
    assert _verdict(_point("P", "top_h_disp", [_obs(1, 0.0), _obs(2, 3.0 - 1e-6)], cum=99.0, rate=3.0), 2) == OK


def test_boundary_ratio_exactly_at_ratio_is_prewarning():
    record = _one(_point("P", "top_h_disp", [_obs(1, 17.5)], cum=25.0), ratio=0.7)
    assert record.evidence["state"] == "prewarning"


def test_boundary_ratio_one_eps_below_is_normal():
    record = _one(_point("P", "top_h_disp", [_obs(1, 17.5 - 1e-6)], cum=25.0), ratio=0.7)
    assert record.evidence["state"] == "normal"


def test_boundary_ratio_full_one_leaves_normal_below_limit():
    """ratio=1.0 时预警线就是控制值本身：未达控制值只能是 normal，预警线也不到。"""
    record = _one(_point("P", "top_h_disp", [_obs(1, 25.0 - 1e-6)], cum=25.0), ratio=1.0)
    assert record.evidence["state"] == "normal"


def test_boundary_window_equal_gap_is_included():
    point = _point("P", "top_h_disp", [_obs(1, 0.0), _obs(3, 8.0)], cum=99.0, rate=4.0)
    assert _one(point, 3, rate_window_days=2).evidence["rate"]["actual"] == pytest.approx(4.0)


def test_boundary_window_gap_beyond_window_is_excluded():
    point = _point("P", "top_h_disp", [_obs(1, 0.0), _obs(4, 8.0)], cum=99.0, rate=4.0)
    assert _one(point, 4, rate_window_days=2).evidence["rate"]["actual"] is None


def test_boundary_window_ignores_same_day_reading():
    rounds = [
        {"index": 1, "observed_on": "2026-01-01"},
        {"index": 2, "observed_on": "2026-01-01"},
    ]
    point = _point("P", "top_h_disp", [_obs(1, 0.0), _obs(2, 9.0)], cum=99.0, rate=1.0)
    subject = {"project": "MATRIX", "points": [point], "rounds": rounds, "rate_window_days": 5}
    records = _run(subject)
    assert records[-1].evidence["rate"]["actual"] is None


def test_boundary_slope_uses_absolute_change():
    point = _point("P", "top_h_disp", [_obs(1, 5.0), _obs(2, 0.0)], cum=99.0, rate=10.0)
    assert _one(point, 2).evidence["rate"]["actual"] == pytest.approx(5.0)


def test_boundary_missing_flag_hides_value():
    point = _point("P", "top_h_disp", [_obs(1, None, missing=True)], cum=25.0)
    with pytest.raises(ValueError, match="没有任何可判行"):
        _run({"project": "MATRIX", "points": [point], "rounds": _rounds(1)})


def test_boundary_zero_value_is_judged_normally():
    record = _one(_point("P", "top_h_disp", [_obs(1, 0.0)], cum=25.0))
    assert record.verdict == OK
    assert record.evidence["value_cum"] == 0.0


# ---------------------------------------------------------------------------
# F. 输入契约原因码（每条一个用例，码要能对上旧仓术语）
# ---------------------------------------------------------------------------
def _reason(point_cum, message_part):
    point = _point("P", "top_h_disp", [_obs(1, 1.0)], cum=None)
    point["control"] = {"cumulative": point_cum}
    return point, message_part


def test_reason_no_source_for_kind_none():
    point, part = _reason({"kind": "none", "status": "verified", "value": 1, "unit": "mm",
                           "evidence": "x"}, "no_source")
    with pytest.raises(ValueError, match=part):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_no_source_for_unknown_kind():
    point, part = _reason({"kind": "forge", "status": "verified", "value": 1, "unit": "mm",
                           "evidence": "x"}, "no_source")
    with pytest.raises(ValueError, match=part):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_source_not_confirmed_for_pending():
    point, part = _reason({"kind": "design_value", "status": "pending", "value": 1, "unit": "mm",
                           "evidence": "x"}, "source_not_confirmed")
    with pytest.raises(ValueError, match=part):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_source_not_confirmed_for_located():
    point, part = _reason({"kind": "design_value", "status": "located", "value": 1, "unit": "mm",
                           "evidence": "x"}, "source_not_confirmed")
    with pytest.raises(ValueError, match=part):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_value_missing_for_null():
    point, part = _reason({"kind": "design_value", "status": "verified", "value": None,
                           "unit": "mm", "evidence": "x"}, "value_missing")
    with pytest.raises(ValueError, match=part):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_unit_missing_for_empty_unit():
    point, part = _reason({"kind": "design_value", "status": "verified", "value": 1,
                           "unit": "", "evidence": "x"}, "unit_missing")
    with pytest.raises(ValueError, match=part):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_unit_inconsistent_for_cm():
    point, part = _reason({"kind": "design_value", "status": "verified", "value": 1,
                           "unit": "cm", "evidence": "x"}, "unit_inconsistent")
    with pytest.raises(ValueError, match=part):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_evidence_missing_for_empty_evidence():
    point, part = _reason({"kind": "design_value", "status": "verified", "value": 1,
                           "unit": "mm", "evidence": ""}, "evidence_missing")
    with pytest.raises(ValueError, match=part):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_window_unconfigured_for_no_window():
    point = _point("P", "top_h_disp", [_obs(1, 1.0)], cum=99.0, rate=2.0)
    with pytest.raises(ValueError, match="window_unconfigured"):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_bool_value_is_refused():
    point = _point("P", "top_h_disp", [_obs(1, True)], cum=25.0)
    with pytest.raises(ValueError, match="数值"):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_infinite_value_is_refused():
    point = _point("P", "top_h_disp", [_obs(1, float("inf"))], cum=25.0)
    with pytest.raises(ValueError, match="有限数值"):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_string_value_is_refused():
    point = _point("P", "top_h_disp", [_obs(1, "12")], cum=25.0)
    with pytest.raises(ValueError, match="数值"):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_non_integer_round_index_is_refused():
    point = _point("P", "top_h_disp", [_obs(1.5, 1.0)], cum=25.0)
    with pytest.raises(ValueError, match="整数"):
        _run({"project": "M", "points": [point], "rounds": _rounds(2)})


def test_reason_item_in_dictionary_is_enforced():
    point = {"code": "P", "item_code": "unknown_item",
             "control": {"cumulative": _control(25.0, "mm")},
             "observations": [_obs(1, 1.0)]}
    with pytest.raises(ValueError, match="不在字典里"):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_points_must_be_object_list():
    with pytest.raises(ValueError, match="points"):
        _run({"project": "M", "points": ["P"]})


def test_reason_subject_must_be_mapping():
    with pytest.raises(ValueError, match="JSON 对象"):
        _run(["not-a-mapping"])


def test_reason_control_must_be_mapping():
    point = _point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)
    point["control"] = "x"
    with pytest.raises(ValueError, match="control 必须是对象"):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


def test_reason_observations_must_be_list():
    point = _point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)
    point["observations"] = {"round": 1}
    with pytest.raises(ValueError, match="observations"):
        _run({"project": "M", "points": [point], "rounds": _rounds(1)})


# ---------------------------------------------------------------------------
# G. 记录形态：id / message / evidence 逐项
# ---------------------------------------------------------------------------
def test_record_verdict_values_are_only_ok_or_rejected():
    point = _point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 26.0)], cum=25.0)
    assert {record.verdict for record in _run({"project": "M", "points": [point],
                                               "rounds": _rounds(2)})} == {OK, REJECTED}


def test_record_basis_survives_ok_and_rejected():
    point = _point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 26.0)], cum=25.0)
    for record in _run({"project": "M", "points": [point], "rounds": _rounds(2)}):
        assert record.basis.code == "GB 50497-2019"
        assert record.basis.clause == "alarm-values"
        assert record.basis.version == "2019"


def test_record_evidence_reports_both_limits_when_dual():
    point = _point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0, rate=1.0)
    evidence = _one(point).evidence
    assert evidence["cumulative"]["limit"] == 25.0
    assert evidence["rate"]["limit"] == 1.0


def test_record_evidence_rate_none_without_rate_control():
    assert _one(_point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)).evidence["rate"] is None


def test_record_evidence_marks_unclosed():
    point = _point("P", "top_h_disp", [_obs(1, 26.0)], cum=25.0)
    assert _one(point).evidence["unclosed"] is True


def test_record_evidence_marks_closed_after_handle():
    point = _point("P", "top_h_disp", [_obs(1, 26.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(1),
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "handle"}]}
    record = _run(subject)[0]
    assert record.evidence["unclosed"] is False
    assert record.verdict == OK


def test_record_evidence_fell_back_only_when_below_limit():
    point = _point("P", "top_h_disp", [_obs(1, 26.0), _obs(2, 30.0)], cum=25.0)
    records = _run({"project": "M", "points": [point], "rounds": _rounds(2)})
    assert records[1].evidence["fell_back"] is False


def test_record_message_names_prewarning_state():
    record = _one(_point("P", "top_h_disp", [_obs(1, 18.0)], cum=25.0), ratio=0.7)
    assert record.message.startswith("预警")


def test_record_message_names_handled_state():
    point = _point("P", "top_h_disp", [_obs(1, 30.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(1),
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "confirm"}]}
    assert _run(subject)[0].message.startswith("报警已确认")


def test_record_id_contains_point_item_and_round():
    record = _one(_point("SYN-X-9", "water_level", [_obs(3, 0.1)], cum=1.0), 3)
    assert record.id == "SYN-X-9.water_level@R3@GB 50497-2019:alarm-values"


def test_record_ids_are_unique_across_points():
    points = [_point("P-1", "top_h_disp", [_obs(1, 1.0)], cum=25.0),
              _point("P-2", "top_h_disp", [_obs(1, 1.0)], cum=25.0)]
    ids = [record.id for record in _run({"project": "M", "points": points, "rounds": _rounds(1)})]
    assert len(ids) == len(set(ids)) == 2


def test_record_count_equals_point_round_pairs():
    point = _point("P", "top_h_disp", [_obs(i, 1.0) for i in (1, 2, 3)], cum=25.0)
    assert len(_run({"project": "M", "points": [point], "rounds": _rounds(3)})) == 3


def test_record_skips_rounds_absent_from_rounds_table():
    point = _point("P", "top_h_disp", [_obs(1, 1.0), _obs(9, 1.0)], cum=25.0)
    assert len(_run({"project": "M", "points": [point], "rounds": _rounds(2)})) == 1


def test_record_as_dict_has_no_null_basis_for_ok():
    record = _one(_point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0))
    payload = record.as_dict()
    assert payload["basis_ref"]["version"] == "2019"
    assert payload["verdict"] == OK


# ---------------------------------------------------------------------------
# H. 频率矩阵：3 个间隔档 × 两态 + 漏测/加密
# ---------------------------------------------------------------------------
def _fsub(points, rounds, limits, enabled):
    return {"project": "M", "points": list(points), "rounds": list(rounds),
            "frequency": {"interval_limits": limits, "enabled": enabled}}


def test_freq_band_d5_under_limit_ok():
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          _rounds(2, depth=4.0), [_limit("FREQ-MAX-INTERVAL-D5", 2)], ["interval"]))
    assert records[0].evidence["band"] == "FREQ-MAX-INTERVAL-D5"
    assert records[0].verdict == OK


def test_freq_band_d5_over_limit_rejected():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 4.0},
              {"index": 2, "observed_on": "2026-01-04", "excavation_depth_m": 4.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-D5", 2)], ["interval"]))
    assert records[0].verdict == REJECTED


def test_freq_band_d10_under_limit_ok():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 8.0},
              {"index": 2, "observed_on": "2026-01-04", "excavation_depth_m": 8.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-D10", 5)], ["interval"]))
    assert records[0].evidence["band"] == "FREQ-MAX-INTERVAL-D10"
    assert records[0].verdict == OK


def test_freq_band_d10_over_limit_rejected():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 8.0},
              {"index": 2, "observed_on": "2026-01-08", "excavation_depth_m": 8.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-D10", 5)], ["interval"]))
    assert records[0].verdict == REJECTED


def test_freq_band_deep_under_limit_ok():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 15.0},
              {"index": 2, "observed_on": "2026-01-08", "excavation_depth_m": 15.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-DEEP", 7)], ["interval"]))
    assert records[0].evidence["band"] == "FREQ-MAX-INTERVAL-DEEP"
    assert records[0].verdict == OK


def test_freq_band_deep_over_limit_rejected():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 15.0},
              {"index": 2, "observed_on": "2026-01-10", "excavation_depth_m": 15.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-DEEP", 7)], ["interval"]))
    assert records[0].verdict == REJECTED


def test_freq_band_selection_picks_shallowest_covering_band():
    assert ORGAN._interval_band(3.0)["id"] == "FREQ-MAX-INTERVAL-D5"
    assert ORGAN._interval_band(5.0)["id"] == "FREQ-MAX-INTERVAL-D5"


def test_freq_band_selection_moves_to_d10():
    assert ORGAN._interval_band(5.5)["id"] == "FREQ-MAX-INTERVAL-D10"


def test_freq_band_selection_uses_fallback_when_depth_unknown():
    assert ORGAN._interval_band(None)["id"] == "FREQ-MAX-INTERVAL-DEEP"


def test_freq_band_selection_uses_fallback_when_deeper_than_ten():
    assert ORGAN._interval_band(30.0)["id"] == "FREQ-MAX-INTERVAL-DEEP"


def test_freq_band_id_is_ten_m_boundary_inclusive():
    assert ORGAN._interval_band(10.0)["id"] == "FREQ-MAX-INTERVAL-D10"


def test_freq_missed_two_rounds_both_ok():
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          _rounds(2), [], ["missed"]))
    assert [record.verdict for record in records] == [OK, OK]


def test_freq_missed_second_round_rejected():
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)],
                          _rounds(2), [], ["missed"]))
    assert [record.verdict for record in records] == [OK, REJECTED]


def test_freq_missed_first_round_rejected():
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(2, 1.0)], cum=25.0)],
                          _rounds(2), [], ["missed"]))
    assert [record.verdict for record in records] == [REJECTED, OK]


def test_freq_missed_basis_is_frequency_clause():
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)],
                          _rounds(1), [], ["missed"]))
    assert records[0].basis.clause == "monitoring-frequency"


def test_freq_missed_skips_unscheduled_round():
    rounds = [{"index": 1, "observed_on": "2026-01-01"},
              {"index": 2, "observed_on": "2026-01-02", "scheduled": False}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)], rounds, [], ["missed"]))
    assert [record.item_id for record in records] == ["freq.missed@R1"]


def test_freq_interval_needs_two_scheduled_rounds():
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)],
                          _rounds(1), [_limit("FREQ-MAX-INTERVAL-D5", 2)], ["interval"]))
    assert records == ()


def test_freq_interval_same_day_gap_is_zero_days():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 3.0},
              {"index": 2, "observed_on": "2026-01-01", "excavation_depth_m": 3.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-D5", 2)], ["interval"]))
    assert records[0].evidence["gap_days"] == 0.0


def test_freq_interval_category_over_interval():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "condition_code": "C1",
               "excavation_depth_m": 3.0},
              {"index": 2, "observed_on": "2026-01-05", "condition_code": "C1",
               "excavation_depth_m": 3.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-D5", 2)], ["interval"]))
    assert records[0].evidence["category"] == "over_interval"


def test_freq_interval_category_stale_when_condition_changed():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "condition_code": "C1",
               "excavation_depth_m": 3.0},
              {"index": 2, "observed_on": "2026-01-05", "condition_code": "C2",
               "excavation_depth_m": 3.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-D5", 2)], ["interval"]))
    assert records[0].evidence["category"] == "stale_frequency"


def test_freq_interval_category_plain_when_change_within_limit():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "condition_code": "C1",
               "excavation_depth_m": 3.0},
              {"index": 2, "observed_on": "2026-01-02", "condition_code": "C2",
               "excavation_depth_m": 3.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-D5", 2)], ["interval"]))
    assert records[0].evidence["category"] == "over_interval"
    assert records[0].verdict == OK


def test_freq_interval_pending_limit_refused():
    with pytest.raises(ValueError, match="source_not_confirmed"):
        _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                    _rounds(2), [_limit("FREQ-MAX-INTERVAL-D5", 2, "pending")], ["interval"]))


def test_freq_intensify_rejected_without_flag():
    rounds = [{"index": 1, "observed_on": "2026-01-01"},
              {"index": 2, "observed_on": "2026-01-02"}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [], ["intensify-after-alarm"]))
    assert records[0].verdict == REJECTED
    assert records[0].basis.clause == "monitoring-frequency"


def test_freq_intensify_ok_with_flag():
    rounds = [{"index": 1, "observed_on": "2026-01-01"},
              {"index": 2, "observed_on": "2026-01-02", "intensified": True}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [], ["intensify-after-alarm"]))
    assert records[0].verdict == OK


def test_freq_intensify_only_after_unclosed_alarm():
    rounds = [{"index": 1, "observed_on": "2026-01-01"},
              {"index": 2, "observed_on": "2026-01-02"}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [], ["intensify-after-alarm"]))
    assert records == ()


def test_freq_intensify_not_required_after_handled():
    rounds = [{"index": 1, "observed_on": "2026-01-01"},
              {"index": 2, "observed_on": "2026-01-02"}]
    subject = {"project": "M",
               "points": [_point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 1.0)], cum=25.0)],
               "rounds": rounds,
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "handle"}],
               "frequency": {"interval_limits": [], "enabled": ["intensify-after-alarm"]}}
    assert _freq(subject) == ()


def test_freq_all_rules_enabled_by_default():
    """不给 enabled 就是四条全开：漏测两条 + 间隔一条 + 加密不需要（无未闭环）。"""
    rounds = [{"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 3.0},
              {"index": 2, "observed_on": "2026-01-02", "excavation_depth_m": 3.0}]
    subject = {"project": "M",
               "points": [_point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)],
               "rounds": rounds,
               "frequency": {"interval_limits": [_limit("FREQ-MAX-INTERVAL-D5", 2)]}}
    records = _freq(subject)
    assert [record.item_id for record in records] == [
        "freq.missed@R1", "freq.missed@R2", "freq.interval@R1->R2"]


def test_freq_enabled_list_narrows_rules():
    rounds = [{"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 3.0}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)],
                          rounds, [_limit("FREQ-MAX-INTERVAL-D5", 2)], []))
    assert records == ()


# ---------------------------------------------------------------------------
# I. 包数据不变量（判据 4 的伴生门：数据文件自己也得守纪律）
# ---------------------------------------------------------------------------
def test_data_items_have_unique_codes():
    codes = [item["code"] for item in DATA["items"]]
    assert len(codes) == len(set(codes)) == 14


def test_data_items_have_non_empty_units():
    assert all(item["unit"] for item in DATA["items"])


def test_data_item_control_kinds_are_declared():
    assert {item["control_kind"] for item in DATA["items"]} <= {"dual", "cumulative", "rate"}


def test_data_alarm_rules_reference_existing_clause():
    for key in ("cumulative", "rate", "prewarning"):
        assert DATA["rules"]["alarm"][key]["clause"] in DATA["clauses"]


def test_data_frequency_rules_reference_existing_clauses():
    clauses = DATA["clauses"]
    for key in ("missed", "interval", "condition-change", "intensify-after-alarm"):
        assert DATA["rules"]["frequency"][key]["clause"] in clauses


def test_data_intensify_rule_lists_two_clauses():
    assert DATA["rules"]["frequency"]["intensify-after-alarm"]["clause_ids"] == [
        "monitoring-frequency", "MOHURD-37"]


def test_data_interval_bands_are_ordered_shallow_to_deep():
    depths = [band["depth_max"] for band in DATA["rules"]["frequency"]["interval_bands"]]
    assert depths[-1] is None
    assert depths[:-1] == sorted(depths[:-1])


def test_data_interval_bands_have_unique_ids():
    ids = [band["id"] for band in DATA["rules"]["frequency"]["interval_bands"]]
    assert len(ids) == len(set(ids)) == 3


def test_data_states_list_matches_transition_table():
    assert set(DATA["states"]["transitions"]) == {
        "normal", "prewarning", "alarm", "alarm_confirmed", "alarm_handled"}


def test_data_clause_entries_all_have_code_and_clause():
    for entry in DATA["clauses"].values():
        assert entry["code"] and entry["clause"]


def test_data_source_is_traceable_to_target_map():
    assert DATA["source"]["target_map"] == "迁自 target-map ③ 行"
    assert DATA["source"]["ported_on"] == "2026-11-25"


def test_data_declares_ge_eps_as_one_nanometre_scale():
    assert DATA["constants"]["ge_eps"] == 1e-09


def test_data_declares_rate_unit_suffix():
    assert DATA["constants"]["rate_unit_suffix"] == "/d"


def test_data_input_contract_lists_all_reason_codes():
    reject_note = DATA["input_contract"]["control_value"]["reject_note"]
    for reason in ("none", "verified", "evidence"):
        assert reason in reject_note


def test_data_unit_rule_mentions_per_day():
    assert "/d" in DATA["input_contract"]["unit_rule"]


def test_clause_missing_carries_code_and_clause_in_message():
    empty = Basis(version="empty")
    with pytest.raises(ClauseMissing) as excinfo:
        _run({"project": "M", "points": [_point("P", "top_h_disp", [_obs(1, 30.0)], cum=25.0)],
              "rounds": _rounds(1)}, basis=empty)
    assert "GB 50497-2019" in str(excinfo.value)
    assert "alarm-values" in str(excinfo.value)


def test_contract_error_is_raised_for_disposition_without_alarm():
    subject = {"project": "M", "points": [_point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)],
               "rounds": _rounds(1),
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "confirm"}]}
    with pytest.raises(ContractError):
        _run(subject)


def test_organ_slug_matches_module_directory():
    assert SLUG == "excavation-monitor"
    assert ORGAN.__name__.endswith(SLUG)


def test_organ_version_is_declared():
    assert ORGAN.VERSION == "0.1.0"


# ---------------------------------------------------------------------------
# J. 状态机语义与多轮组合（不是重复断言：每条断言一个独立的迁移事实）
# ---------------------------------------------------------------------------
def test_sticky_alarm_survives_three_rounds():
    point = _point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 1.0), _obs(3, 2.0)], cum=25.0)
    records = _run({"project": "M", "points": [point], "rounds": _rounds(3)})
    assert [record.verdict for record in records] == [REJECTED, REJECTED, REJECTED]


def test_sticky_alarm_keeps_first_round_after_falling_back():
    point = _point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 1.0)], cum=25.0)
    records = _run({"project": "M", "points": [point], "rounds": _rounds(2)})
    assert records[1].evidence["first_alarm_round"] == 1
    assert records[1].evidence["trigger_basis"] == "cumulative"


def test_second_alarm_after_handle_starts_new_lifecycle():
    point = _point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 1.0), _obs(3, 40.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(3),
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "handle"}]}
    records = _run(subject)
    assert records[2].evidence["first_alarm_round"] == 3


def test_confirm_then_handle_closes_lifecycle():
    point = _point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 31.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(2),
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "confirm"},
                                {"point": "P", "item": "top_h_disp", "round": 2, "kind": "handle"}]}
    records = _run(subject)
    assert records[0].evidence["state"] == "alarm_confirmed"
    assert records[1].evidence["state"] == "alarm_handled"
    assert records[1].verdict == OK


def test_confirm_on_alarm_confirmed_stays_confirmed():
    point = _point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 31.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(2),
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "confirm"},
                                {"point": "P", "item": "top_h_disp", "round": 2, "kind": "confirm"}]}
    assert [record.evidence["state"] for record in _run(subject)] == ["alarm_confirmed", "alarm_confirmed"]


def test_handle_on_alarm_handled_keeps_handled():
    point = _point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 31.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(2),
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "handle"},
                                {"point": "P", "item": "top_h_disp", "round": 2, "kind": "handle"}]}
    assert [record.evidence["state"] for record in _run(subject)] == ["alarm_handled", "alarm_handled"]


def test_prewarning_does_not_start_unclosed_lifecycle():
    point = _point("P", "top_h_disp", [_obs(1, 18.0), _obs(2, 1.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(2), "prewarning_ratio": 0.7}
    records = _run(subject)
    assert records[0].evidence["state"] == "prewarning"
    assert records[0].evidence["first_alarm_round"] is None


def test_prewarning_then_alarm_starts_lifecycle_at_alarm_round():
    point = _point("P", "top_h_disp", [_obs(1, 18.0), _obs(2, 26.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(2), "prewarning_ratio": 0.7}
    records = _run(subject)
    assert records[1].evidence["state"] == "alarm"
    assert records[1].evidence["first_alarm_round"] == 2


def test_multi_point_isolation_of_states():
    points = [_point("P-1", "top_h_disp", [_obs(1, 30.0)], cum=25.0),
              _point("P-2", "top_h_disp", [_obs(1, 1.0)], cum=25.0)]
    records = _run({"project": "M", "points": points, "rounds": _rounds(1)})
    assert {record.item_id.split(".")[0]: record.verdict for record in records} == {
        "P-1": REJECTED, "P-2": OK}


def test_multi_point_alarm_does_not_leak_across_items():
    points = [_point("P", "top_h_disp", [_obs(1, 30.0)], cum=25.0),
              _point("P", "water_level", [_obs(1, 0.1)], cum=1.0)]
    records = _run({"project": "M", "points": points, "rounds": _rounds(1)})
    assert [record.verdict for record in records] == [REJECTED, OK]


def test_rate_window_picks_largest_of_three_candidates():
    """R4 处窗口内有两个候选：R1（3 天，5/3）与 R2（2 天，1.5）——取大的。"""
    point = _point("P", "top_h_disp", [_obs(1, 0.0), _obs(2, 2.0), _obs(4, 5.0)], cum=99.0, rate=1.6)
    assert _one(point, 4, rate_window_days=5).evidence["rate"]["actual"] == pytest.approx(5.0 / 3.0)


def test_rate_window_restricted_to_two_days_uses_last_prior_round():
    point = _point("P", "top_h_disp", [_obs(1, 0.0), _obs(4, 5.0)], cum=99.0, rate=1.6)
    assert _one(point, 4, rate_window_days=4).evidence["rate"]["actual"] == pytest.approx(5.0 / 3.0)


def test_rate_window_zero_days_between_distinct_dates():
    rounds = [{"index": 1, "observed_on": "2026-01-01"},
              {"index": 2, "observed_on": "2026-01-02"}]
    point = _point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 3.0)], cum=99.0, rate=2.0)
    subject = {"project": "M", "points": [point], "rounds": rounds, "rate_window_days": 1}
    assert _run(subject)[-1].evidence["rate"]["actual"] == pytest.approx(2.0)


def test_both_bases_hit_is_rejected_once_per_round():
    point = _point("P", "top_h_disp", [_obs(1, 0.0), _obs(2, 40.0)], cum=25.0, rate=1.0)
    records = _run({"project": "M", "points": [point], "rounds": _rounds(2), "rate_window_days": 5})
    assert len(records) == 2
    assert records[1].evidence["trigger_basis"] == "both"


def test_evidence_clause_ids_list_both_alarm_anchors():
    point = _point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)
    assert _one(point).evidence["clause_ids"] == ["alarm-values", "alarm-values"]


def test_evidence_records_observed_on_from_rounds():
    point = _point("P", "top_h_disp", [_obs(2, 1.0)], cum=25.0)
    assert _one(point, 2).evidence["observed_on"] == "2026-01-02"


def test_evidence_prewarning_ratio_present_only_when_hit():
    point = _point("P", "top_h_disp", [_obs(1, 20.0)], cum=25.0)
    record = _one(point, 1, ratio=0.7)
    assert record.evidence["prewarning_ratio"] == 0.7


def test_disposition_duplicate_is_refused():
    point = _point("P", "top_h_disp", [_obs(1, 30.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(1),
               "dispositions": [{"point": "P", "item": "top_h_disp", "round": 1, "kind": "handle"},
                                {"point": "P", "item": "top_h_disp", "round": 1, "kind": "confirm"}]}
    with pytest.raises(ValueError, match="处置记录重复"):
        _run(subject)


def test_disposition_for_unknown_point_is_refused():
    point = _point("P", "top_h_disp", [_obs(1, 30.0)], cum=25.0)
    subject = {"project": "M", "points": [point], "rounds": _rounds(1),
               "dispositions": [{"point": "GHOST", "item": "top_h_disp", "round": 1,
                                 "kind": "handle"}]}
    assert _run(subject)[0].verdict == REJECTED


def test_ratio_lower_bound_is_exclusive():
    point = _point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)
    with pytest.raises(ValueError, match="prewarning_ratio"):
        _one(point, 1, ratio=0.0)


def test_ratio_upper_bound_is_inclusive():
    point = _point("P", "top_h_disp", [_obs(1, 1.0)], cum=25.0)
    assert _one(point, 1, ratio=1.0).verdict == OK


def test_missed_honours_active_to():
    point = _point("P", "top_h_disp", [_obs(1, 1.0), _obs(2, 1.0)], cum=25.0)
    point["active_to"] = "2026-01-01"
    records = _freq(_fsub([point], _rounds(2), [], ["missed"]))
    assert [record.evidence["points_expected"] for record in records] == [1, 0]


def test_interval_multiple_pairs_emit_one_record_each():
    point = _point("P", "top_h_disp", [_obs(i, 1.0) for i in (1, 2, 3)], cum=25.0)
    records = _freq(_fsub([point], _rounds(3), [_limit("FREQ-MAX-INTERVAL-D5", 2)], ["interval"]))
    assert [record.item_id for record in records] == ["freq.interval@R1->R2", "freq.interval@R2->R3"]


def test_intensify_evidence_reports_round_pair():
    rounds = [{"index": 1, "observed_on": "2026-01-01"},
              {"index": 2, "observed_on": "2026-01-02"}]
    records = _freq(_fsub([_point("P", "top_h_disp", [_obs(1, 30.0), _obs(2, 1.0)], cum=25.0)],
                          rounds, [], ["intensify-after-alarm"]))
    assert records[0].evidence["previous_round"] == 1
    assert records[0].evidence["round"] == 2


def test_intensify_evidence_lists_each_unclosed_point_item():
    points = [_point("P-1", "top_h_disp", [_obs(1, 30.0), _obs(2, 1.0)], cum=25.0),
              _point("P-2", "deep_h_disp", [_obs(1, 40.0), _obs(2, 1.0)], cum=30.0)]
    rounds = [{"index": 1, "observed_on": "2026-01-01"},
              {"index": 2, "observed_on": "2026-01-02"}]
    records = _freq(_fsub(points, rounds, [], ["intensify-after-alarm"]))
    assert records[0].evidence["unclosed_points"] == ["P-1.top_h_disp", "P-2.deep_h_disp"]


def test_data_interval_bands_declare_labels():
    assert all(band["label"] for band in DATA["rules"]["frequency"]["interval_bands"])


def test_data_alarm_rule_applies_to_lists_are_disjoint_for_cumulative_only():
    assert "cumulative" in DATA["rules"]["alarm"]["cumulative"]["applies_to"]
    assert "dual" in DATA["rules"]["alarm"]["cumulative"]["applies_to"]


def test_data_source_lists_both_rulesets():
    assert len(DATA["source"]["rulesets"]) == 2


def test_data_severity_order_is_ascending():
    assert DATA["states"]["severity"] == ["normal", "prewarning", "alarm", "alarm_confirmed"]