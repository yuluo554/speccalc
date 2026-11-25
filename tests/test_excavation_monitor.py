"""器官 ``excavation-monitor`` 的无损测试（迁自 target-map ③ 行）。

覆盖四块，每块都对应旧仓一个模块：
1. **注册与声明**（旧 ``test_cli_surface`` / ``test_rules_loader`` 的器官侧）；
2. **双控报警判定**（旧 ``test_alarm_engine`` / ``test_alarm_state_machine`` / ``test_clause_fallback``）；
3. **频率与时效检核**（旧 ``test_compliance_auditor`` 的四类规则）；
4. **旧仓对账**（旧 ``test_alarm_regression`` 的六起事件里可纯数值复现的两起）。

第 4 块用的输入是 ``samples/excavation-monitor/zhdq.json``：由旧仓自身命令链
（``pmc init`` → ``pmc synth --db`` → ``pmc import`` R09/R11/R12）建出的台账导出，
控制值取旧仓 ``tests/fixtures/point_grades.json`` 的夹具档位（``kind=user_input`` 且
``evidence`` 带 ``FIXTURE-GRADE`` 前缀，明确写着"非设计文件值、非规范条文值"）。
它只用于证明**判定通路**与旧引擎逐行一致，不构成任何规范依据。

约定：本文件不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按
``def test_`` 函数数计数，参数化会让「README 的 N 项」失真）。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from speccalc import cli  # noqa: E402
from speccalc.core import (  # noqa: E402
    Basis,
    CalculationRecord,
    Clause,
    ClauseMissing,
    ContractError,
    EXIT_BLOCKED,
    EXIT_CONTRACT,
    EXIT_INPUT,
    EXIT_OK,
    OK,
    REJECTED,
    get,
)
from speccalc.core.data import load as load_data  # noqa: E402
from speccalc.modules import BUILTIN_MODULES, load_builtin  # noqa: E402

SLUG = "excavation-monitor"
CODE_ALARM = "GB 50497-2019"
CODE_FREQ = "GB 50497-2019"
CODE_LAW = "住房城乡建设部令第 37 号"

BASIS = Basis(
    version="samples-20261125",
    clauses=(
        Clause(code=CODE_ALARM, clause="alarm-values", version="2019", text="累计量与变化速率报警值"),
        Clause(code=CODE_FREQ, clause="monitoring-frequency", version="2019", text="监测频率要求"),
        Clause(code=CODE_LAW, clause="MOHURD-37", version="2018", text="异常时增加监测频率"),
    ),
)

SAMPLES = os.path.join(ROOT, "samples")
SAMPLE_SUBJECT = os.path.join(SAMPLES, "excavation-monitor", "zhdq.json")
SAMPLE_BASIS = os.path.join(SAMPLES, "basis.json")


def _evaluate(subject, basis=BASIS):
    load_builtin()
    return tuple(get(SLUG).evaluate(subject, basis))


def _control(value, unit, kind="design_value", evidence="设计文件 SYN-JK-2026-0001"):
    return {"kind": kind, "status": "verified", "value": value, "unit": unit, "evidence": evidence}


def _point(
    code="P-01",
    item_code="top_h_disp",
    cum=25.0,
    rate=None,
    observations=(),
    unit="mm",
    rate_unit="mm/d",
):
    control = {"cumulative": _control(cum, unit)}
    if rate is not None:
        control["rate"] = _control(rate, rate_unit)
    return {
        "code": code,
        "item_code": item_code,
        "control": control,
        "observations": list(observations),
    }


def _obs(round_index, value, missing=False):
    return {"round": round_index, "value": value, "missing": missing}


def _rounds(count, start_day=1, depth=3.0):
    """从 2026-01-01 起每天一轮（窗口判据需要真实日历差）；默认落在 ≤5 m 的间隔档。"""
    out = []
    for index in range(1, count + 1):
        day = start_day + index - 1
        month, date_in_month = (1, day) if day <= 31 else (2, day - 31)
        out.append(
            {
                "index": index,
                "observed_on": "2026-%02d-%02d" % (month, date_in_month),
                "excavation_depth_m": depth,
            }
        )
    return out


def _subject(points, count=None, ratio=None, window=None, **extra):
    subject = {"project": "TEST-PIT", "points": list(points)}
    rounds = extra.pop("rounds", None)
    if rounds is None and count:
        rounds = _rounds(count)
    if rounds is not None:
        subject["rounds"] = rounds
    if ratio is not None:
        subject["prewarning_ratio"] = ratio
    if window is not None:
        subject["rate_window_days"] = window
    subject.update(extra)
    return subject


def _single(subject, basis=BASIS):
    records = _evaluate(subject, basis)
    assert len(records) == 1, [record.id for record in records]
    return records[0]


def _at(subject, round_index, basis=BASIS):
    """取某一轮的报警记录（多轮 subject 上逐轮判一次，按轮次挑）。"""
    records = [record for record in _evaluate(subject, basis) if record.evidence.get("round") == round_index]
    assert len(records) == 1, [record.id for record in records]
    return records[0]


def _freq(subject, basis=BASIS):
    """只要频率与时效检核的记录（报警记录另有断言）。"""
    return tuple(
        record for record in _evaluate(subject, basis) if record.item_id.startswith("freq.")
    )


# ---------------------------------------------------------------------------
# 1. 注册与声明
# ---------------------------------------------------------------------------
def test_organ_is_registered_with_declared_input_fields():
    load_builtin()
    pack = get(SLUG)
    assert pack.slug == SLUG
    assert pack.version == "0.1.0"
    assert pack.input_fields == ("project", "points")
    assert "基坑监测" in pack.summary


def test_builtin_manifest_contains_organ_and_stays_sorted():
    assert SLUG in BUILTIN_MODULES
    assert list(BUILTIN_MODULES) == sorted(BUILTIN_MODULES)


def test_cli_list_shows_organ(capsys):
    assert cli.main(["list"]) == EXIT_OK
    out = capsys.readouterr().out
    assert SLUG in out


def test_organ_data_is_package_data_with_item_dictionary():
    data = load_data("excavation-monitor.json")
    assert data["organ"] == SLUG
    items = {item["code"]: item for item in data["items"]}
    assert len(items) == 14
    assert items["top_h_disp"]["unit"] == "mm"
    assert items["prop_force"]["unit"] == "kN"
    assert items["building_tilt"]["control_kind"] == "cumulative"
    assert items["crack_width"]["control_kind"] == "cumulative"


def test_organ_data_declares_three_clause_anchors():
    data = load_data("excavation-monitor.json")
    anchors = {(entry["code"], entry["clause"]) for entry in data["clauses"].values()}
    assert (CODE_ALARM, "alarm-values") in anchors
    assert (CODE_FREQ, "monitoring-frequency") in anchors
    assert (CODE_LAW, "MOHURD-37") in anchors


def test_organ_data_carries_no_threshold_values():
    """旧仓纪律：数据文件里一个阈值数值都没有（全留 null / pending）。"""
    data = load_data("excavation-monitor.json")
    text = json.dumps(data, ensure_ascii=False)
    assert '"value":' not in text
    assert "max_interval_days\":" not in text or "max_interval_days\": 0" not in text


def test_organ_data_declares_clause_numbers_as_unknown():
    """条号未逐字核对：clause_no 一律 null，不凭记忆填。"""
    data = load_data("excavation-monitor.json")
    for entry in data["clauses"].values():
        assert entry["clause_no"] is None
    assert "clause_no_discipline" in data


def test_load_rejects_path_traversal_names():
    for name in ("../pyproject.toml", "/etc/passwd", "sub/dir.json", "excavation-monitor.jsonx"):
        with pytest.raises(ValueError):
            load_data(name)


# ---------------------------------------------------------------------------
# 2. 输入契约：控制值只认已核对来源
# ---------------------------------------------------------------------------
def test_missing_project_is_input_error():
    with pytest.raises(ValueError):
        _evaluate({"points": [_point(observations=(_obs(1, 1.0),))]})


def test_empty_points_is_input_error():
    with pytest.raises(ValueError):
        _evaluate({"project": "TEST-PIT", "points": []})


def test_unknown_item_code_is_input_error():
    point = _point(item_code="no_such_item", observations=(_obs(1, 1.0),))
    with pytest.raises(ValueError, match="不在字典里"):
        _evaluate(_subject([point], count=1))


def test_control_kind_none_is_rejected_as_no_source():
    point = _point(observations=(_obs(1, 1.0),))
    point["control"]["cumulative"]["kind"] = "none"
    with pytest.raises(ValueError, match="no_source"):
        _evaluate(_subject([point], count=1))


def test_unverified_control_is_rejected():
    point = _point(observations=(_obs(1, 1.0),))
    point["control"]["cumulative"]["status"] = "pending"
    with pytest.raises(ValueError, match="source_not_confirmed"):
        _evaluate(_subject([point], count=1))


def test_control_without_evidence_is_rejected():
    point = _point(observations=(_obs(1, 1.0),))
    point["control"]["cumulative"]["evidence"] = ""
    with pytest.raises(ValueError, match="evidence_missing"):
        _evaluate(_subject([point], count=1))


def test_control_without_value_is_rejected():
    point = _point(observations=(_obs(1, 1.0),))
    point["control"]["cumulative"]["value"] = None
    with pytest.raises(ValueError, match="value_missing"):
        _evaluate(_subject([point], count=1))


def test_control_without_unit_is_rejected():
    point = _point(observations=(_obs(1, 1.0),))
    point["control"]["cumulative"]["unit"] = ""
    with pytest.raises(ValueError, match="unit_missing"):
        _evaluate(_subject([point], count=1))


def test_unit_mismatch_is_rejected():
    """拿 cm 当 mm 用是必须拒的：宁可拒算，不给错数。"""
    point = _point(observations=(_obs(1, 1.0),))
    point["control"]["cumulative"]["unit"] = "cm"
    with pytest.raises(ValueError, match="unit_inconsistent"):
        _evaluate(_subject([point], count=1))


def test_unregistered_basis_is_skipped_not_defaulted():
    """旧仓口径：档案没登记这条判据 = 「还没轮到第二档」，整条判据不参与判定。"""
    point = _point(observations=(_obs(1, 30.0),))
    assert "rate" not in point["control"]
    record = _single(_subject([point], count=1))
    assert record.verdict == REJECTED
    assert record.evidence["rate"] is None
    assert record.evidence["trigger_basis"] == "cumulative"


def test_point_without_any_control_is_rejected():
    point = _point(observations=(_obs(1, 1.0),))
    point["control"] = {}
    with pytest.raises(ValueError, match="没有任何已核对的控制值"):
        _evaluate(_subject([point], count=1))


def test_rate_unit_must_carry_per_day_suffix():
    point = _point(rate=1.5, observations=(_obs(1, 1.0),))
    point["control"]["rate"]["unit"] = "mm"
    with pytest.raises(ValueError, match="unit_inconsistent"):
        _evaluate(_subject([point], count=1, window=5))


def test_rate_without_window_is_rejected():
    point = _point(rate=1.5, observations=(_obs(1, 1.0),))
    with pytest.raises(ValueError, match="window_unconfigured"):
        _evaluate(_subject([point], count=1))


def test_rate_window_must_be_positive():
    point = _point(rate=1.5, observations=(_obs(1, 1.0),))
    with pytest.raises(ValueError, match="window_unconfigured"):
        _evaluate(_subject([point], count=1, window=0))


def test_observations_without_rounds_are_rejected():
    with pytest.raises(ValueError, match="rounds"):
        _evaluate({"project": "TEST-PIT", "points": [_point(observations=(_obs(1, 1.0),))]})


def test_bad_observed_on_is_rejected():
    rounds = [{"index": 1, "observed_on": "2026/01/01"}]
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _evaluate(_subject([_point(observations=(_obs(1, 1.0),))], rounds=rounds))


def test_duplicate_point_is_rejected():
    points = [
        _point(code="P-01", observations=(_obs(1, 1.0),)),
        _point(code="P-01", observations=(_obs(1, 2.0),)),
    ]
    with pytest.raises(ValueError, match="测点重复"):
        _evaluate(_subject(points, count=1))


def test_duplicate_round_is_rejected():
    rounds = [{"index": 1, "observed_on": "2026-01-01"}, {"index": 1, "observed_on": "2026-01-02"}]
    with pytest.raises(ValueError, match="轮次重复"):
        _evaluate(_subject([_point(observations=(_obs(1, 1.0),))], rounds=rounds))


def test_duplicate_observation_round_is_rejected():
    point = _point(observations=(_obs(1, 1.0), _obs(1, 2.0)))
    with pytest.raises(ValueError, match="观测重复"):
        _evaluate(_subject([point], count=1))


def test_non_finite_value_is_rejected():
    point = _point(observations=(_obs(1, float("nan")),))
    with pytest.raises(ValueError):
        _evaluate(_subject([point], count=1))


def test_bad_disposition_kind_is_rejected():
    subject = _subject(
        [_point(observations=(_obs(1, 99.0),))],
        count=1,
        dispositions=[{"point": "P-01", "item": "top_h_disp", "round": 1, "kind": "dismiss"}],
    )
    with pytest.raises(ValueError, match="handle / confirm"):
        _evaluate(subject)


def test_disposition_on_normal_row_is_contract_violation():
    subject = _subject(
        [_point(observations=(_obs(1, 1.0),))],
        count=1,
        dispositions=[{"point": "P-01", "item": "top_h_disp", "round": 1, "kind": "handle"}],
    )
    with pytest.raises(ContractError, match="未报警"):
        _evaluate(subject)


def test_prewarning_ratio_out_of_range_is_rejected():
    subject = _subject([_point(observations=(_obs(1, 1.0),))], count=1, ratio=1.5)
    with pytest.raises(ValueError, match="prewarning_ratio"):
        _evaluate(subject)


def test_subject_without_any_judgeable_row_is_rejected():
    subject = _subject([_point(observations=())], count=3)
    with pytest.raises(ValueError, match="没有任何可判行"):
        _evaluate(subject)


def test_cli_reports_input_error_rc2(tmp_path, capsys):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"project": "X", "points": []}, ensure_ascii=False), encoding="utf-8")
    assert (
        cli.main(["check", SLUG, "--input", str(target), "--basis", SAMPLE_BASIS]) == EXIT_INPUT
    )
    assert "points" in capsys.readouterr().err


def test_cli_missing_required_input_field_is_rc2(tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"project": "X"}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", SAMPLE_BASIS]) == EXIT_INPUT


# ---------------------------------------------------------------------------
# 3. 累计量判据
# ---------------------------------------------------------------------------
def test_cumulative_below_limit_is_ok():
    record = _single(_subject([_point(observations=(_obs(1, 24.9),))], count=1))
    assert record.verdict == OK
    assert record.evidence["cumulative"]["hit"] is False


def test_cumulative_at_limit_is_rejected():
    record = _single(_subject([_point(observations=(_obs(1, 25.0),))], count=1))
    assert record.verdict == REJECTED
    assert record.evidence["state"] == "alarm"


def test_cumulative_inside_tolerance_is_rejected():
    """落盘值与阈值都是小数级：浮点尾差不得改变结论（旧 GE_EPS=1e-9）。"""
    record = _single(_subject([_point(observations=(_obs(1, 25.0 - 1e-12),))], count=1))
    assert record.verdict == REJECTED


def test_cumulative_just_below_tolerance_is_ok():
    record = _single(_subject([_point(observations=(_obs(1, 25.0 - 1e-7),))], count=1))
    assert record.verdict == OK


def test_cumulative_uses_absolute_value():
    record = _single(_subject([_point(observations=(_obs(1, -26.0),))], count=1))
    assert record.verdict == REJECTED
    assert record.evidence["value_cum"] == -26.0


def test_cumulative_only_item_ignores_rate_block():
    point = _point(item_code="building_tilt", cum=3.0, unit="‰", observations=(_obs(1, 2.0),))
    point["control"]["rate"] = _control(99.0, "‰/d")
    record = _single(_subject([point], count=1))
    assert record.verdict == OK
    assert record.evidence["rate"] is None
    assert record.evidence["cumulative"]["limit"] == 3.0


# ---------------------------------------------------------------------------
# 4. 速率判据与窗口
# ---------------------------------------------------------------------------
def test_rate_within_limit_is_ok():
    point = _point(rate=1.5, observations=(_obs(1, 0.0), _obs(2, 1.0)))
    record = _at(_subject([point], count=2, window=5), 2)
    assert record.verdict == OK
    assert record.evidence["rate"]["hit"] is False


def test_rate_over_limit_is_rejected():
    point = _point(rate=1.5, observations=(_obs(1, 0.0), _obs(2, 2.0)))
    record = _at(_subject([point], count=2, window=5), 2)
    assert record.verdict == REJECTED
    assert record.evidence["rate"]["hit"] is True


def test_rate_takes_maximum_slope_inside_window():
    point = _point(rate=1.5, observations=(_obs(1, 0.0), _obs(2, 3.0), _obs(4, 4.5)))
    record = _at(_subject([point], count=4, window=5), 4)
    assert record.evidence["rate"]["actual"] == pytest.approx(1.5, abs=1e-9)


def test_rate_ignores_readings_outside_window():
    """窗口 2 天：R1 的读数在 R4 处已经出窗。"""
    point = _point(rate=1.0, observations=(_obs(1, 0.0), _obs(4, 2.0)))
    record = _at(_subject([point], count=4, window=2), 4)
    assert record.evidence["rate"]["actual"] is None
    assert record.verdict == OK


def test_rate_needs_a_prior_reading_in_window():
    point = _point(rate=1.0, observations=(_obs(1, 5.0),))
    record = _single(_subject([point], count=1, window=5))
    assert record.evidence["rate"]["actual"] is None


def test_rate_window_boundary_is_inclusive():
    point = _point(rate=1.0, observations=(_obs(1, 0.0), _obs(3, 2.0)))
    record = _at(_subject([point], count=3, window=2), 3)
    assert record.evidence["rate"]["actual"] == pytest.approx(1.0)


def test_trigger_basis_is_both_when_two_bases_hit():
    point = _point(rate=1.0, observations=(_obs(1, 0.0), _obs(2, 30.0)))
    record = _at(_subject([point], count=2, window=5), 2)
    assert record.evidence["trigger_basis"] == "both"


def test_trigger_basis_is_cumulative_only():
    point = _point(rate=99.0, observations=(_obs(1, 0.0), _obs(2, 30.0)))
    record = _at(_subject([point], count=2, window=5), 2)
    assert record.evidence["trigger_basis"] == "cumulative"


def test_trigger_basis_is_rate_only():
    point = _point(rate=1.0, observations=(_obs(1, 0.0), _obs(2, 5.0)))
    record = _at(_subject([point], count=2, window=5), 2)
    assert record.evidence["trigger_basis"] == "rate"


# ---------------------------------------------------------------------------
# 5. 预警比例
# ---------------------------------------------------------------------------
def test_prewarning_ratio_marks_state_without_blocking():
    point = _point(observations=(_obs(1, 18.0),))
    record = _single(_subject([point], count=1, ratio=0.7))
    assert record.evidence["state"] == "prewarning"
    assert record.verdict == OK
    assert record.evidence["prewarning_ratio"] == 0.7


def test_prewarning_ratio_not_reached_is_normal():
    point = _point(observations=(_obs(1, 17.0),))
    record = _single(_subject([point], count=1, ratio=0.7))
    assert record.evidence["state"] == "normal"
    assert record.evidence["prewarning_ratio"] is None


def test_without_ratio_state_stays_normal():
    point = _point(observations=(_obs(1, 18.0),))
    record = _single(_subject([point], count=1))
    assert record.evidence["state"] == "normal"


def test_alarm_beats_prewarning():
    point = _point(observations=(_obs(1, 26.0),))
    record = _single(_subject([point], count=1, ratio=0.7))
    assert record.evidence["state"] == "alarm"


# ---------------------------------------------------------------------------
# 6. 状态机与未闭环
# ---------------------------------------------------------------------------
def test_alarm_is_sticky_when_value_falls_back():
    point = _point(observations=(_obs(1, 30.0), _obs(2, 1.0)))
    records = _evaluate(_subject([point], count=2))
    assert [record.verdict for record in records] == [REJECTED, REJECTED]
    assert records[1].evidence["unclosed_carried"] is True
    assert records[1].evidence["fell_back"] is True


def test_first_alarm_round_is_kept_across_rounds():
    point = _point(observations=(_obs(1, 30.0), _obs(2, 31.0), _obs(3, 32.0)))
    records = _evaluate(_subject([point], count=3))
    assert [record.evidence["first_alarm_round"] for record in records] == [1, 1, 1]


def test_handle_disposition_closes_alarm():
    point = _point(observations=(_obs(1, 30.0), _obs(2, 1.0)))
    subject = _subject(
        [point],
        count=2,
        dispositions=[{"point": "P-01", "item": "top_h_disp", "round": 1, "kind": "handle"}],
    )
    records = _evaluate(subject)
    assert records[0].evidence["state"] == "alarm_handled"
    assert records[0].verdict == OK
    assert records[1].verdict == OK


def test_confirm_disposition_keeps_alarm_open():
    point = _point(observations=(_obs(1, 30.0),))
    subject = _subject(
        [point],
        count=1,
        dispositions=[{"point": "P-01", "item": "top_h_disp", "round": 1, "kind": "confirm"}],
    )
    record = _single(subject)
    assert record.evidence["state"] == "alarm_confirmed"
    assert record.verdict == REJECTED


def test_alarm_restarts_after_handled():
    point = _point(observations=(_obs(1, 30.0), _obs(2, 1.0), _obs(3, 40.0)))
    subject = _subject(
        [point],
        count=3,
        dispositions=[{"point": "P-01", "item": "top_h_disp", "round": 1, "kind": "handle"}],
    )
    records = _evaluate(subject)
    assert records[2].evidence["state"] == "alarm"
    assert records[2].evidence["first_alarm_round"] == 3


def test_missing_observations_do_not_produce_rows():
    point = _point(observations=(_obs(1, 30.0), _obs(2, None, missing=True), _obs(3, 31.0)))
    records = _evaluate(_subject([point], count=3))
    assert [record.evidence["round"] for record in records] == [1, 3]


def test_state_machine_transition_table_is_declared():
    data = load_data("excavation-monitor.json")
    transitions = data["states"]["transitions"]
    assert "normal" not in transitions["alarm"]
    assert "normal" not in transitions["alarm_confirmed"]
    assert "alarm_handled" in transitions["alarm"]
    assert data["states"]["unclosed"] == ["alarm", "alarm_confirmed"]


# ---------------------------------------------------------------------------
# 7. 记录形态与依据
# ---------------------------------------------------------------------------
def test_every_record_carries_three_field_basis():
    point = _point(observations=(_obs(1, 30.0), _obs(2, 1.0)))
    for record in _evaluate(_subject([point], count=2)):
        assert record.basis is not None
        assert record.basis.code == CODE_ALARM
        assert record.basis.clause == "alarm-values"
        assert record.basis.version == "2019"
        assert record.basis.text


def test_ok_record_also_carries_basis():
    """本产品口径更严：'算合格了' 也是结论，一样必须挂依据。"""
    record = _single(_subject([_point(observations=(_obs(1, 1.0),))], count=1))
    assert record.verdict == OK
    assert record.basis is not None


def test_record_id_is_item_plus_clause():
    record = _single(_subject([_point(observations=(_obs(1, 30.0),))], count=1))
    assert record.id == "P-01.top_h_disp@R1@GB 50497-2019:alarm-values"
    assert record.item_id == "P-01.top_h_disp@R1"


def test_record_evidence_has_stable_keys():
    record = _at(_subject([_point(rate=1.0, observations=(_obs(1, 0.0), _obs(2, 30.0)))], count=2, window=5), 2)
    assert set(record.evidence) == {
        "formula",
        "point",
        "item_code",
        "round",
        "observed_on",
        "state",
        "trigger_basis",
        "unclosed",
        "unclosed_carried",
        "first_alarm_round",
        "fell_back",
        "value_cum",
        "cumulative",
        "rate",
        "prewarning_ratio",
        "clause_ids",
    }


def test_message_states_actual_and_limit():
    record = _single(_subject([_point(observations=(_obs(1, 30.0),))], count=1))
    assert "30" in record.message
    assert "25" in record.message
    assert "报警" in record.message


def test_basis_text_flows_into_record_without_changing_verdict():
    other = Basis(
        version="other",
        clauses=(Clause(code=CODE_ALARM, clause="alarm-values", version="2024", text="另一版文本"),),
    )
    record = _single(_subject([_point(observations=(_obs(1, 30.0),))], count=1), basis=other)
    assert record.basis.version == "2024"
    assert record.basis.text == "另一版文本"
    assert record.verdict == REJECTED


def test_missing_clause_propagates_clause_missing():
    empty = Basis(version="empty")
    with pytest.raises(ClauseMissing):
        _evaluate(_subject([_point(observations=(_obs(1, 30.0),))], count=1), basis=empty)


def test_cli_missing_clause_is_contract_error_rc3(tmp_path, capsys):
    target = tmp_path / "input.json"
    target.write_text(
        json.dumps(_subject([_point(observations=(_obs(1, 30.0),))], count=1), ensure_ascii=False),
        encoding="utf-8",
    )
    basis_path = tmp_path / "basis.json"
    basis_path.write_text(json.dumps({"version": "empty", "clauses": []}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", str(basis_path)]) == EXIT_CONTRACT
    assert "ClauseMissing" in capsys.readouterr().err


def test_cli_blocking_run_is_rc1(tmp_path, capsys):
    target = tmp_path / "input.json"
    target.write_text(
        json.dumps(_subject([_point(observations=(_obs(1, 30.0),))], count=1), ensure_ascii=False),
        encoding="utf-8",
    )
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", SAMPLE_BASIS]) == EXIT_BLOCKED
    assert "[rejected]" in capsys.readouterr().out


def test_cli_ok_run_is_rc0(tmp_path):
    target = tmp_path / "input.json"
    target.write_text(
        json.dumps(_subject([_point(observations=(_obs(1, 1.0),))], count=1), ensure_ascii=False),
        encoding="utf-8",
    )
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", SAMPLE_BASIS]) == EXIT_OK


def test_cli_output_is_deterministic(tmp_path, capsys):
    target = tmp_path / "input.json"
    target.write_text(
        json.dumps(_subject([_point(observations=(_obs(1, 30.0), _obs(2, 1.0)))], count=2), ensure_ascii=False),
        encoding="utf-8",
    )
    args = ["check", SLUG, "--input", str(target), "--basis", SAMPLE_BASIS, "--json"]
    cli.main(args)
    first = capsys.readouterr().out
    cli.main(args)
    assert capsys.readouterr().out == first
    assert str(tmp_path) not in first


# ---------------------------------------------------------------------------
# 8. 频率与时效检核
# ---------------------------------------------------------------------------
def _freq_subject(points, rounds, limits=None, enabled=None):
    subject = {"project": "TEST-PIT", "points": list(points), "rounds": list(rounds)}
    block = {
        "interval_limits": limits
        if limits is not None
        else [
            {
                "band": "FREQ-MAX-INTERVAL-D5",
                "max_interval_days": 2,
                "kind": "standard_value",
                "status": "verified",
                "evidence": "条款核对记录 FREQ-D5",
            }
        ]
    }
    if enabled is not None:
        block["enabled"] = enabled
    subject["frequency"] = block
    return subject


def _clean_point(code="P-01", count=3):
    return _point(code=code, observations=tuple(_obs(i, 1.0) for i in range(1, count + 1)))


def test_frequency_absent_produces_no_frequency_records():
    point = _point(observations=(_obs(1, 1.0),))
    records = _evaluate(_subject([point], count=1))
    assert not any(record.item_id.startswith("freq.") for record in records)


def test_missed_round_all_present_is_ok():
    records = _freq(_freq_subject([_clean_point()], _rounds(3), enabled=["missed"]))
    assert len(records) == 3
    assert all(record.verdict == OK for record in records)
    assert records[0].evidence["points_expected"] == 1


def test_missed_round_without_any_row_is_rejected():
    point = _point(observations=(_obs(1, 1.0),))
    records = _freq(_freq_subject([point], _rounds(2), enabled=["missed"]))
    assert records[1].verdict == REJECTED
    assert records[1].evidence["gap"] == "round_not_imported"


def test_missed_point_level_gap_is_rejected():
    points = [_clean_point("P-01"), _clean_point("P-02")]
    points[1]["observations"] = [_obs(1, 1.0), _obs(2, None, missing=True), _obs(3, 1.0)]
    records = _freq(_freq_subject(points, _rounds(3), enabled=["missed"]))
    hit = [record for record in records if record.verdict == REJECTED]
    assert len(hit) == 1
    assert hit[0].evidence["missing_points"] == [{"point": "P-02", "gap": "missing_flag_marked"}]


def test_missed_skips_points_outside_active_window():
    point = _clean_point("P-09")
    point["active_from"] = "2026-01-03"
    records = _freq(_freq_subject([point], _rounds(3), enabled=["missed"]))
    assert [record.evidence["points_expected"] for record in records] == [0, 0, 1]


def test_interval_within_limit_is_ok():
    records = _freq(_freq_subject([_clean_point()], _rounds(3), enabled=["interval"]))
    assert all(record.verdict == OK for record in records)
    assert records[0].evidence["gap_days"] == 1.0
    assert records[0].evidence["band"] == "FREQ-MAX-INTERVAL-D5"


def test_interval_over_limit_is_rejected():
    records = _freq(_freq_subject([_clean_point(count=5)], _rounds(5, start_day=1), enabled=["interval"]))
    assert all(record.verdict == OK for record in records)


def test_interval_over_limit_with_sparse_rounds_is_rejected():
    rounds = [
        {"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 3.0},
        {"index": 2, "observed_on": "2026-01-05", "excavation_depth_m": 3.0},
    ]
    point = _point(observations=(_obs(1, 1.0), _obs(2, 1.0)))
    records = _freq(_freq_subject([point], rounds, enabled=["interval"]))
    assert records[0].verdict == REJECTED
    assert records[0].evidence["gap_days"] == 4.0
    assert records[0].evidence["category"] == "over_interval"


def test_interval_uses_depth_band():
    rounds = [
        {"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 12.0},
        {"index": 2, "observed_on": "2026-01-08", "excavation_depth_m": 12.0},
    ]
    point = _point(observations=(_obs(1, 1.0), _obs(2, 1.0)))
    limits = [
        {"band": "FREQ-MAX-INTERVAL-D5", "max_interval_days": 1, "kind": "standard_value",
         "status": "verified", "evidence": "FREQ-D5"},
        {"band": "FREQ-MAX-INTERVAL-DEEP", "max_interval_days": 7, "kind": "standard_value",
         "status": "verified", "evidence": "FREQ-DEEP"},
    ]
    records = _freq(_freq_subject([point], rounds, limits=limits, enabled=["interval"]))
    assert records[0].evidence["band"] == "FREQ-MAX-INTERVAL-DEEP"
    assert records[0].verdict == OK


def test_interval_without_verified_limit_is_rejected_as_input():
    rounds = [
        {"index": 1, "observed_on": "2026-01-01", "excavation_depth_m": 3.0},
        {"index": 2, "observed_on": "2026-01-02", "excavation_depth_m": 3.0},
    ]
    point = _point(observations=(_obs(1, 1.0), _obs(2, 1.0)))
    with pytest.raises(ValueError, match="FREQ-MAX-INTERVAL-D5"):
        _evaluate(_freq_subject([point], rounds, limits=[], enabled=["interval"]))


def test_interval_unknown_band_is_rejected():
    point = _clean_point()
    with pytest.raises(ValueError, match="未知的间隔档位"):
        _evaluate(
            _freq_subject(
                [point],
                _rounds(3),
                limits=[{"band": "NO-SUCH-BAND", "max_interval_days": 2,
                         "kind": "standard_value", "status": "verified", "evidence": "x"}],
                enabled=["interval"],
            )
        )


def test_interval_pending_limit_is_rejected():
    point = _clean_point()
    with pytest.raises(ValueError, match="source_not_confirmed"):
        _evaluate(
            _freq_subject(
                [point],
                _rounds(3),
                limits=[{"band": "FREQ-MAX-INTERVAL-D5", "max_interval_days": 2,
                         "kind": "standard_value", "status": "pending", "evidence": "x"}],
                enabled=["interval"],
            )
        )


def test_interval_limit_without_evidence_is_rejected():
    point = _clean_point()
    with pytest.raises(ValueError, match="evidence_missing"):
        _evaluate(
            _freq_subject(
                [point],
                _rounds(3),
                limits=[{"band": "FREQ-MAX-INTERVAL-D5", "max_interval_days": 2,
                         "kind": "standard_value", "status": "verified", "evidence": ""}],
                enabled=["interval"],
            )
        )


def test_condition_change_with_over_interval_is_stale_frequency():
    rounds = [
        {"index": 1, "observed_on": "2026-01-01", "condition_code": "C1", "excavation_depth_m": 3.0},
        {"index": 2, "observed_on": "2026-01-05", "condition_code": "C2", "excavation_depth_m": 3.0},
    ]
    point = _point(observations=(_obs(1, 1.0), _obs(2, 1.0)))
    records = _freq(_freq_subject([point], rounds, enabled=["interval"]))
    assert records[0].evidence["category"] == "stale_frequency"
    assert records[0].evidence["condition_changed"] is True
    assert records[0].verdict == REJECTED


def test_condition_change_within_interval_stays_plain():
    rounds = [
        {"index": 1, "observed_on": "2026-01-01", "condition_code": "C1", "excavation_depth_m": 3.0},
        {"index": 2, "observed_on": "2026-01-02", "condition_code": "C2", "excavation_depth_m": 3.0},
    ]
    point = _point(observations=(_obs(1, 1.0), _obs(2, 1.0)))
    records = _freq(_freq_subject([point], rounds, enabled=["interval"]))
    assert records[0].evidence["category"] == "over_interval"


def test_intensify_missing_after_unclosed_alarm_is_rejected():
    point = _point(observations=(_obs(1, 30.0), _obs(2, 1.0)))
    rounds = [
        {"index": 1, "observed_on": "2026-01-01"},
        {"index": 2, "observed_on": "2026-01-02", "intensified": False},
    ]
    records = _freq(_freq_subject([point], rounds, enabled=["intensify-after-alarm"]))
    assert records[0].item_id == "freq.intensify@R2"
    assert records[0].verdict == REJECTED
    assert records[0].evidence["unclosed_points"] == ["P-01.top_h_disp"]


def test_intensify_present_after_unclosed_alarm_is_ok():
    point = _point(observations=(_obs(1, 30.0), _obs(2, 1.0)))
    rounds = [
        {"index": 1, "observed_on": "2026-01-01"},
        {"index": 2, "observed_on": "2026-01-02", "intensified": True},
    ]
    records = _freq(_freq_subject([point], rounds, enabled=["intensify-after-alarm"]))
    assert records[0].verdict == OK


def test_intensify_emits_nothing_without_unclosed_alarm():
    point = _point(observations=(_obs(1, 1.0), _obs(2, 1.0)))
    records = _freq(
        _freq_subject([point], _rounds(2), enabled=["intensify-after-alarm"])
    )
    assert records == ()


def test_intensify_evidence_records_both_clauses():
    point = _point(observations=(_obs(1, 30.0), _obs(2, 1.0)))
    rounds = [
        {"index": 1, "observed_on": "2026-01-01"},
        {"index": 2, "observed_on": "2026-01-02"},
    ]
    records = _freq(_freq_subject([point], rounds, enabled=["intensify-after-alarm"]))
    assert records[0].evidence["clause_ids"] == ["monitoring-frequency", "MOHURD-37"]
    assert records[0].basis.clause == "monitoring-frequency"


def test_frequency_clause_missing_propagates():
    basis = Basis(
        version="only-alarm",
        clauses=(Clause(code=CODE_ALARM, clause="alarm-values", version="2019", text="x"),),
    )
    with pytest.raises(ClauseMissing):
        _evaluate(_freq_subject([_clean_point()], _rounds(3), enabled=["interval"]), basis=basis)


def test_frequency_without_rounds_is_rejected():
    point = _point(observations=(_obs(1, 1.0),))
    subject = {"project": "TEST-PIT", "points": [point],
               "frequency": {"interval_limits": []}}
    with pytest.raises(ValueError, match="rounds"):
        _evaluate(subject)


# ---------------------------------------------------------------------------
# 9. 旧仓对账（samples/excavation-monitor/zhdq.json）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def zhdq_records():
    with open(SAMPLE_SUBJECT, "r", encoding="utf-8") as handle:
        subject = json.load(handle)
    return _evaluate(subject, Basis.from_json(SAMPLE_BASIS))


def test_sample_reproduces_old_engine_row_count(zhdq_records):
    """旧 `pmc check` 在 R09/R11/R12 共 392 行判定 + 195 行 R12（587 行链上有效读数）。"""
    assert len(zhdq_records) == 587


def test_sample_reproduces_old_engine_r11_alarm_set(zhdq_records):
    """旧 `CHECK_SUMMARY ... normal=194 ... alarm=2`：R11 只有 SYN-TH-03 / SYN-TH-18 报警。"""
    at_r11 = [record for record in zhdq_records if record.evidence["round"] == 11]
    assert len(at_r11) == 196
    rejected = sorted(record.item_id for record in at_r11 if record.verdict == REJECTED)
    assert rejected == ["SYN-TH-03.top_h_disp@R11", "SYN-TH-18.top_h_disp@R11"]
    assert sum(1 for record in at_r11 if record.verdict == OK) == 194


def test_sample_first_alarm_rounds_match_old_unclosed_list(zhdq_records):
    """旧 `UNCLOSED_LIST`：SYN-TH-03 首报 R11、SYN-TH-18 首报 R9。"""
    rows = {
        record.item_id: record
        for record in zhdq_records
        if record.item_id in ("SYN-TH-03.top_h_disp@R11", "SYN-TH-18.top_h_disp@R11")
    }
    assert rows["SYN-TH-03.top_h_disp@R11"].evidence["first_alarm_round"] == 11
    assert rows["SYN-TH-18.top_h_disp@R11"].evidence["first_alarm_round"] == 9


def test_sample_total_blocking_matches_three_rounds(zhdq_records):
    """3 轮里未闭环延续：R09 1 条 + R11 2 条 + R12 2 条 = 5 条阻断。"""
    rejected = [record for record in zhdq_records if record.verdict == REJECTED]
    assert len(rejected) == 5
    assert {record.evidence["round"] for record in rejected} == {9, 11, 12}


def test_sample_all_records_carry_alarm_clause(zhdq_records):
    for record in zhdq_records:
        assert record.basis is not None
        assert record.basis.code == CODE_ALARM
        assert record.basis.clause == "alarm-values"
        assert record.basis.version == "2019"


def test_sample_evidence_keeps_fixture_grade_provenance(zhdq_records):
    """夹具档位的出处必须原样带进 evidence，不得被洗成'设计值'。"""
    record = next(record for record in zhdq_records if record.item_id == "SYN-TH-18.top_h_disp@R11")
    assert record.evidence["cumulative"]["source"] == "user_input"
    assert record.evidence["cumulative"]["evidence"].startswith("FIXTURE-GRADE:")


def test_sample_cli_run_matches_old_engine_rc(capsys):
    """判据 2 的同参数重跑：旧 `pmc check` rc=1，新 `speccalc check` 必须 rc=1。"""
    assert (
        cli.main(["check", SLUG, "--input", SAMPLE_SUBJECT, "--basis", SAMPLE_BASIS, "--json"])
        == EXIT_BLOCKED
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["blocking"] == 5
    assert payload["summary"]["total"] == 587
    assert payload["organ"] == SLUG


def test_sample_json_is_byte_identical_across_runs(capsys):
    args = ["check", SLUG, "--input", SAMPLE_SUBJECT, "--basis", SAMPLE_BASIS, "--json"]
    cli.main(args)
    first = capsys.readouterr().out
    cli.main(args)
    assert capsys.readouterr().out == first


def test_sample_has_no_absolute_paths(capsys):
    cli.main(["check", SLUG, "--input", SAMPLE_SUBJECT, "--basis", SAMPLE_BASIS, "--json"])
    out = capsys.readouterr().out
    assert "C:\\\\" not in out and "C:/" not in out
    assert "ProgramData" not in out


def test_organ_does_not_read_environment_or_clock(monkeypatch):
    """器官只吃 subject + basis：环境变量与时钟被抹掉后结果不变。"""
    subject = _subject([_point(observations=(_obs(1, 30.0),))], count=1)
    before = _evaluate(subject)
    monkeypatch.setenv("PMC_DATA_DIR", "/nonexistent")
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    after = _evaluate(subject)
    assert [record.as_dict() for record in before] == [record.as_dict() for record in after]


def test_records_are_calculation_records():
    for record in _evaluate(_subject([_point(observations=(_obs(1, 30.0),))], count=1)):
        assert isinstance(record, CalculationRecord)