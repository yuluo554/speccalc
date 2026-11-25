"""``pavement-mqi`` · 等级分档 / 养护对策 / 路线 MQI（JTG 5210-2018 口径）。

判据形态的三层「两态」写满：
- ``grade_threshold.pci`` × 5 档基线：PCI 落在每一档时，对每个项目基线是 ok 还是 rejected；
- ``grade_threshold.*`` 的两种含界口径（``lower_inclusive`` / ``lower_exclusive``）在档位边沿两侧；
- ``action_rule.maintenance_trigger`` 的四种比较符 × pci / mqi 两个指标 + 首命中生效；
- ``mqi_weight.pavement`` 的长度加权（首期只有 pavement 分项，partial）。

不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数）。
"""

from __future__ import annotations

import pytest

from pavement_mqi_kit import (
    BANDS,
    DISTRESS_ONLY,
    JTG,
    KEYS,
    coefficients,
    grade_of,
    mqi_of,
    seg,
    seg_with_pci,
    subject,
)
from speccalc.core import Basis, Clause, ClauseMissing

PASS = "ok"
FAIL = "rejected"


# ---------------------------------------------------------------------------
# A. 分档 × 项目基线：5 档 PCI × 5 个基线
# ---------------------------------------------------------------------------
def test_baseline_excellent_pci_excellent_is_ok():
    record = grade_of(95.0, minimum_grade="优")
    assert record.evidence["grade"] == "优"
    assert record.verdict == PASS


def test_baseline_excellent_pci_good_is_rejected():
    assert grade_of(85.0, minimum_grade="优").verdict == FAIL


def test_baseline_excellent_pci_medium_is_rejected():
    assert grade_of(75.0, minimum_grade="优").verdict == FAIL


def test_baseline_excellent_pci_poor_is_rejected():
    assert grade_of(65.0, minimum_grade="优").verdict == FAIL


def test_baseline_excellent_pci_bad_is_rejected():
    assert grade_of(50.0, minimum_grade="优").verdict == FAIL


def test_baseline_good_pci_excellent_is_ok():
    assert grade_of(95.0, minimum_grade="良").verdict == PASS


def test_baseline_good_pci_good_is_ok():
    record = grade_of(85.0, minimum_grade="良")
    assert record.evidence["grade"] == "良"
    assert record.verdict == PASS


def test_baseline_good_pci_medium_is_rejected():
    assert grade_of(75.0, minimum_grade="良").verdict == FAIL


def test_baseline_good_pci_poor_is_rejected():
    assert grade_of(65.0, minimum_grade="良").verdict == FAIL


def test_baseline_good_pci_bad_is_rejected():
    assert grade_of(50.0, minimum_grade="良").verdict == FAIL


def test_baseline_medium_pci_excellent_is_ok():
    assert grade_of(95.0, minimum_grade="中").verdict == PASS


def test_baseline_medium_pci_good_is_ok():
    assert grade_of(85.0, minimum_grade="中").verdict == PASS


def test_baseline_medium_pci_medium_is_ok():
    record = grade_of(75.0, minimum_grade="中")
    assert record.evidence["grade"] == "中"
    assert record.verdict == PASS


def test_baseline_medium_pci_poor_is_rejected():
    record = grade_of(65.0, minimum_grade="中")
    assert record.evidence["grade"] == "次"
    assert record.verdict == FAIL


def test_baseline_medium_pci_bad_is_rejected():
    assert grade_of(50.0, minimum_grade="中").verdict == FAIL


def test_baseline_poor_pci_excellent_is_ok():
    assert grade_of(95.0, minimum_grade="次").verdict == PASS


def test_baseline_poor_pci_good_is_ok():
    assert grade_of(85.0, minimum_grade="次").verdict == PASS


def test_baseline_poor_pci_medium_is_ok():
    assert grade_of(75.0, minimum_grade="次").verdict == PASS


def test_baseline_poor_pci_poor_is_ok():
    record = grade_of(65.0, minimum_grade="次")
    assert record.evidence["grade"] == "次"
    assert record.verdict == PASS


def test_baseline_poor_pci_bad_is_rejected():
    assert grade_of(50.0, minimum_grade="次").verdict == FAIL


def test_baseline_bad_pci_excellent_is_ok():
    assert grade_of(95.0, minimum_grade="差").verdict == PASS


def test_baseline_bad_pci_good_is_ok():
    assert grade_of(85.0, minimum_grade="差").verdict == PASS


def test_baseline_bad_pci_medium_is_ok():
    assert grade_of(75.0, minimum_grade="差").verdict == PASS


def test_baseline_bad_pci_poor_is_ok():
    assert grade_of(65.0, minimum_grade="差").verdict == PASS


def test_baseline_bad_pci_bad_is_ok():
    record = grade_of(50.0, minimum_grade="差")
    assert record.evidence["grade"] == "差"
    assert record.verdict == PASS


# ---------------------------------------------------------------------------
# B. 档位边沿两侧（两种含界口径）
# ---------------------------------------------------------------------------
def test_inclusive_just_above_ninety_is_excellent():
    assert grade_of(90.01).evidence["grade"] == "优"


def test_inclusive_just_below_ninety_is_good():
    assert grade_of(89.99).evidence["grade"] == "良"


def test_inclusive_just_above_eighty_is_good():
    assert grade_of(80.01).evidence["grade"] == "良"


def test_inclusive_just_below_eighty_is_medium():
    assert grade_of(79.99).evidence["grade"] == "中"


def test_inclusive_just_below_seventy_is_poor():
    assert grade_of(69.99).evidence["grade"] == "次"


def test_exclusive_just_above_ninety_is_excellent():
    assert grade_of(90.01, "lower_exclusive").evidence["grade"] == "优"


def test_exclusive_just_below_ninety_is_good():
    assert grade_of(89.99, "lower_exclusive").evidence["grade"] == "良"


def test_exclusive_just_below_eighty_is_medium():
    assert grade_of(79.99, "lower_exclusive").evidence["grade"] == "中"


def test_exclusive_just_below_seventy_is_poor():
    assert grade_of(69.99, "lower_exclusive").evidence["grade"] == "次"


def test_exclusive_just_below_sixty_is_bad():
    assert grade_of(59.99, "lower_exclusive").evidence["grade"] == "差"


def test_full_score_is_excellent():
    assert grade_of(100.0).evidence["grade"] == "优"


def test_zero_score_is_worst():
    assert grade_of(0.0).evidence["grade"] == "差"


# ---------------------------------------------------------------------------
# C. 自定义分档表
# ---------------------------------------------------------------------------
THREE_BANDS = {"boundary": "lower_inclusive",
               "bands": [{"grade": "优", "min": 85}, {"grade": "中", "min": 60},
                         {"grade": "差", "min": 0}]}


def _grade_with(bands, target, minimum_grade="中"):
    payload = subject([seg_with_pci(target)], coefficients(weights=DISTRESS_ONLY, pci_bands=bands))
    payload["minimum_grade"] = minimum_grade
    from pavement_mqi_kit import get, run
    return get(run(payload), "grade")


def test_three_band_table_top_band():
    assert _grade_with(THREE_BANDS, 90.0).evidence["grade"] == "优"


def test_three_band_table_middle_band():
    assert _grade_with(THREE_BANDS, 70.0).evidence["grade"] == "中"


def test_three_band_table_bottom_band():
    assert _grade_with(THREE_BANDS, 50.0).evidence["grade"] == "差"


def test_single_band_table_matches_high_score():
    assert _grade_with({"boundary": "lower_inclusive", "bands": [{"grade": "优", "min": 90}]},
                       95.0).evidence["grade"] == "优"


def test_single_band_table_falls_back_to_worst_grade():
    """低于全部档位下沿时按最差档入账（不是「无结论」）。"""
    assert _grade_with({"boundary": "lower_inclusive", "bands": [{"grade": "优", "min": 90}]},
                       50.0).evidence["grade"] == "差"


def test_unsorted_three_band_table_still_picks_highest_match():
    bands = {"boundary": "lower_inclusive",
             "bands": [{"grade": "差", "min": 0}, {"grade": "优", "min": 85},
                       {"grade": "中", "min": 60}]}
    assert _grade_with(bands, 90.0).evidence["grade"] == "优"


def test_equal_minimum_bands_keep_declaration_order():
    bands = {"boundary": "lower_inclusive",
             "bands": [{"grade": "优", "min": 80}, {"grade": "良", "min": 80}]}
    assert _grade_with(bands, 85.0).evidence["grade"] == "优"


def test_band_minimum_is_inclusive_at_lowest_band():
    bands = {"boundary": "lower_inclusive", "bands": [{"grade": "差", "min": 10}]}
    assert _grade_with(bands, 10.0).evidence["grade"] == "差"


# ---------------------------------------------------------------------------
# D. 分档表非法
# ---------------------------------------------------------------------------
def test_grade_boundary_missing_is_refused():
    with pytest.raises(ValueError, match="boundary"):
        _grade_with({"bands": [{"grade": "差", "min": 0}]}, 50.0)


def test_grade_bands_not_list_is_refused():
    with pytest.raises(ValueError, match="bands 必须是非空数组"):
        _grade_with({"boundary": "lower_inclusive", "bands": {"grade": "差"}}, 50.0)


def test_grade_band_entry_not_object_is_refused():
    with pytest.raises(ValueError, match="必须是对象"):
        _grade_with({"boundary": "lower_inclusive", "bands": ["差"]}, 50.0)


def test_grade_band_minimum_missing_is_refused():
    with pytest.raises(ValueError, match="缺少必填字段：min"):
        _grade_with({"boundary": "lower_inclusive", "bands": [{"grade": "差"}]}, 50.0)


def test_grade_band_minimum_non_numeric_is_refused():
    with pytest.raises(ValueError, match="必须是数值"):
        _grade_with({"boundary": "lower_inclusive", "bands": [{"grade": "差", "min": "0"}]}, 50.0)


# ---------------------------------------------------------------------------
# E. 养护对策：四种比较符 × pci / mqi
# ---------------------------------------------------------------------------
def _rules(metric, op, threshold, rule_id="AR-1", action_class="中修", scale_band="分段"):
    return {"rules": [{"rule_id": rule_id, "metric": metric, "op": op,
                       "threshold": threshold, "action_class": action_class,
                       "scale_band": scale_band}]}


def _action_with(target, rules):
    payload = subject([seg_with_pci(target)], coefficients(weights=DISTRESS_ONLY, rules=rules))
    from pavement_mqi_kit import get, run
    return get(run(payload), "action")


def test_action_mqi_lt_fires_when_below():
    assert _action_with(70.0, _rules("mqi", "lt", 75.0)).verdict == FAIL


def test_action_mqi_lt_does_not_fire_at_threshold():
    assert _action_with(70.0, _rules("mqi", "lt", 70.0)).verdict == PASS


def test_action_mqi_le_fires_at_threshold():
    assert _action_with(70.0, _rules("mqi", "le", 70.0)).verdict == FAIL


def test_action_mqi_gt_fires_when_above():
    assert _action_with(70.0, _rules("mqi", "gt", 65.0)).verdict == FAIL


def test_action_mqi_gt_does_not_fire_at_threshold():
    assert _action_with(70.0, _rules("mqi", "gt", 70.0)).verdict == PASS


def test_action_mqi_ge_fires_at_threshold():
    assert _action_with(70.0, _rules("mqi", "ge", 70.0)).verdict == FAIL


def test_action_three_tier_table_picks_major_repair():
    action = _action_with(55.0, coefficients()[-1]["value"])
    assert action.evidence["action"]["action_class"] == "大修"


def test_action_three_tier_table_picks_medium_repair():
    action = _action_with(65.0, coefficients()[-1]["value"])
    assert action.evidence["action"]["action_class"] == "中修"


def test_action_three_tier_table_picks_minor_repair():
    action = _action_with(75.0, coefficients()[-1]["value"])
    assert action.evidence["action"]["action_class"] == "小修"


def test_action_three_tier_table_fires_nothing_above_eighty():
    assert _action_with(85.0, coefficients()[-1]["value"]).verdict == PASS


def test_action_empty_rule_list_fires_nothing():
    assert _action_with(50.0, {"rules": []}).verdict == PASS


def test_action_rules_not_list_is_refused():
    with pytest.raises(ValueError, match="rules 必须是数组"):
        _action_with(70.0, {"rules": {"op": "lt"}})


def test_action_rule_entry_not_object_is_refused():
    with pytest.raises(ValueError, match="rules\\[\\] 必须是对象"):
        _action_with(70.0, {"rules": ["AR-1"]})


def test_action_rule_without_rule_id_is_refused():
    rules = {"rules": [{"metric": "pci", "op": "lt", "threshold": 80, "action_class": "小修"}]}
    with pytest.raises(ValueError, match="rule_id"):
        _action_with(70.0, rules)


def test_action_rule_without_threshold_is_refused():
    rules = {"rules": [{"rule_id": "AR-1", "metric": "pci", "op": "lt", "action_class": "小修"}]}
    with pytest.raises(ValueError, match="threshold"):
        _action_with(70.0, rules)


def test_action_rule_without_operator_is_refused():
    rules = {"rules": [{"rule_id": "AR-1", "metric": "pci", "threshold": 80,
                        "action_class": "小修"}]}
    with pytest.raises(ValueError, match="op"):
        _action_with(70.0, rules)


def test_action_rule_without_action_class_is_refused():
    rules = {"rules": [{"rule_id": "AR-1", "metric": "pci", "op": "lt", "threshold": 80}]}
    with pytest.raises(ValueError, match="action_class"):
        _action_with(70.0, rules)


def test_action_rule_for_unknown_metric_never_fires():
    assert _action_with(50.0, _rules("iri", "lt", 100.0)).verdict == PASS


def test_action_pci_rule_miss_falls_back_to_mqi_rule():
    rules = {"rules": [{"rule_id": "P", "metric": "pci", "op": "lt", "threshold": 60,
                        "action_class": "大修"},
                       {"rule_id": "M", "metric": "mqi", "op": "lt", "threshold": 80,
                        "action_class": "小修"}]}
    action = _action_with(70.0, rules)
    assert action.verdict == FAIL
    assert action.evidence["action"]["rule_id"] == "M"


def test_action_pci_rule_wins_over_mqi_rule():
    rules = {"rules": [{"rule_id": "P", "metric": "pci", "op": "lt", "threshold": 80,
                        "action_class": "小修"},
                       {"rule_id": "M", "metric": "mqi", "op": "lt", "threshold": 90,
                        "action_class": "大修"}]}
    assert _action_with(70.0, rules).evidence["action"]["rule_id"] == "P"


def test_action_strictly_below_full_marks_does_not_fire():
    assert _action_with(100.0, _rules("pci", "lt", 100.0)).verdict == PASS


def test_action_scale_band_may_be_absent():
    rules = {"rules": [{"rule_id": "AR-1", "metric": "pci", "op": "lt", "threshold": 80,
                        "action_class": "小修"}]}
    assert _action_with(70.0, rules).evidence["action"]["scale_band"] is None


def test_action_evidence_reports_metric_value():
    assert _action_with(70.0, _rules("pci", "lt", 75.0)).evidence["action"]["metric_value"] == pytest.approx(70.0)


# ---------------------------------------------------------------------------
# F. 路线 MQI：长度加权、分档、两态
# ---------------------------------------------------------------------------
def test_mqi_two_segments_is_length_weighted():
    """(1000×90 + 500×60) / 1500 = 80。"""
    segments = [seg_with_pci(90.0, "S-1", length_m=1000.0),
                seg_with_pci(60.0, "S-2", length_m=500.0)]
    assert mqi_of(segments).evidence["mqi"] == pytest.approx(80.0)


def test_mqi_three_segments_is_length_weighted():
    """(1000×90 + 1000×80 + 500×50) / 2500 = 78。"""
    segments = [seg_with_pci(90.0, "S-1", length_m=1000.0),
                seg_with_pci(80.0, "S-2", length_m=1000.0),
                seg_with_pci(50.0, "S-3", length_m=500.0)]
    assert mqi_of(segments).evidence["mqi"] == pytest.approx(78.0)


def test_mqi_single_segment_equals_its_pci():
    assert mqi_of([seg_with_pci(66.5, "S-1")]).evidence["mqi"] == pytest.approx(66.5)


def test_mqi_is_rounded_to_two_digits():
    """(1×100 + 2×0) / 3 = 33.333… → 33.33。"""
    segments = [seg_with_pci(100.0, "S-1", length_m=1.0),
                seg_with_pci(0.0, "S-2", length_m=2.0)]
    assert mqi_of(segments).evidence["mqi"] == pytest.approx(33.33)


def test_mqi_full_marks_reach_one_hundred():
    segments = [seg_with_pci(100.0, "S-1"), seg_with_pci(100.0, "S-2", length_m=500.0)]
    assert mqi_of(segments).evidence["mqi"] == pytest.approx(100.0)


def test_mqi_grade_inclusive_at_eighty_is_good():
    segments = [seg_with_pci(80.0, "S-1")]
    assert mqi_of(segments).evidence["grade"] == "良"


def test_mqi_grade_exclusive_at_eighty_is_medium():
    segments = [seg_with_pci(80.0, "S-1")]
    bands = dict(BANDS)
    bands["boundary"] = "lower_exclusive"
    assert mqi_of(segments, mqi_bands=bands).evidence["grade"] == "中"


def test_mqi_baseline_medium_excellent_is_ok():
    assert mqi_of([seg_with_pci(95.0, "S-1")], minimum_grade="中").verdict == PASS


def test_mqi_baseline_medium_good_is_ok():
    assert mqi_of([seg_with_pci(85.0, "S-1")], minimum_grade="中").verdict == PASS


def test_mqi_baseline_medium_medium_is_ok():
    assert mqi_of([seg_with_pci(75.0, "S-1")], minimum_grade="中").verdict == PASS


def test_mqi_baseline_medium_poor_is_rejected():
    record = mqi_of([seg_with_pci(65.0, "S-1")], minimum_grade="中")
    assert record.evidence["grade"] == "次"
    assert record.verdict == FAIL


def test_mqi_baseline_medium_bad_is_rejected():
    assert mqi_of([seg_with_pci(50.0, "S-1")], minimum_grade="中").verdict == FAIL


def test_mqi_two_routes_report_their_own_values():
    from pavement_mqi_kit import run
    segments = [seg_with_pci(90.0, "S-1", route_id="R1"),
                seg_with_pci(60.0, "S-2", route_id="R2")]
    records = {record.item_id: record for record in
               run(subject(segments, coefficients(weights=DISTRESS_ONLY)))}
    assert records["mqi.R1"].evidence["mqi"] == pytest.approx(90.0)
    assert records["mqi.R2"].evidence["mqi"] == pytest.approx(60.0)


def test_mqi_two_routes_emit_two_records():
    from pavement_mqi_kit import run
    segments = [seg_with_pci(90.0, "S-1", route_id="R1"),
                seg_with_pci(60.0, "S-2", route_id="R2")]
    records = run(subject(segments, coefficients(weights=DISTRESS_ONLY)))
    ids = sorted(record.item_id for record in records if record.item_id.startswith("mqi."))
    assert ids == ["mqi.R1", "mqi.R2"]


def test_mqi_member_rows_carry_length_and_pci():
    segments = [seg_with_pci(90.0, "S-1", length_m=1000.0),
                seg_with_pci(60.0, "S-2", length_m=500.0)]
    rows = mqi_of(segments).evidence["segments"]
    assert [(row["segment_id"], row["length_m"], row["pci"]) for row in rows] == [
        ("S-1", 1000.0, 90.0), ("S-2", 500.0, 60.0)]


def test_mqi_mixes_surfaces_within_one_route():
    """沥青 90 与水泥 100 各 1000 m → 95（MQI 不按路面类型再加权）。"""
    segments = [seg_with_pci(90.0, "S-1", surface="asphalt"),
                seg_with_pci(100.0, "S-2", surface="cement")]
    blocks = coefficients("asphalt", weights=DISTRESS_ONLY)
    blocks.extend(block for block in coefficients("cement", weights=DISTRESS_ONLY)
                  if "cement" in block["key"])
    assert mqi_of(segments, component_list=blocks).evidence["mqi"] == pytest.approx(95.0)


def test_mqi_ignores_pavement_weight_value():
    """首期只有 pavement 分项：``mqi_weight.pavement`` 的系数值不参与加权（partial 口径）。"""
    segments = [seg_with_pci(90.0, "S-1"), seg_with_pci(60.0, "S-2", length_m=500.0)]
    half = coefficients(weights=DISTRESS_ONLY,
                        components={"mqi_weight.pavement": {"weights": {"pavement": 0.5}}})
    assert mqi_of(segments, component_list=half).evidence["mqi"] == pytest.approx(80.0)


def test_mqi_evidence_marks_route_level():
    assert mqi_of([seg_with_pci(90.0, "S-1")]).evidence["level"] == "route"


def test_mqi_id_keeps_route_id_verbatim():
    record = mqi_of([seg_with_pci(90.0, "S-1", route_id="S.99")])
    assert record.item_id == "mqi.S.99"


# ---------------------------------------------------------------------------
# G. 依据：四条被 ``basis.ref`` 的锚点缺失即 ClauseMissing
# ---------------------------------------------------------------------------
def _basis_without(*drop, version="thin-2018"):
    clauses = tuple(Clause(code=JTG, clause=key, version="2018", text=key)
                    for key in KEYS if key not in drop)
    return Basis(version=version, clauses=clauses)


def test_missing_pci_weight_clause_raises():
    with pytest.raises(ClauseMissing):
        from pavement_mqi_kit import run
        run(subject([seg()]), _basis_without("pci_weight.asphalt"))


def test_missing_grade_threshold_clause_raises():
    with pytest.raises(ClauseMissing):
        from pavement_mqi_kit import run
        run(subject([seg()]), _basis_without("grade_threshold.pci"))


def test_missing_action_rule_clause_raises():
    with pytest.raises(ClauseMissing):
        from pavement_mqi_kit import run
        run(subject([seg()]), _basis_without("action_rule.maintenance_trigger"))


def test_missing_mqi_weight_clause_raises():
    from pavement_mqi_kit import run
    with pytest.raises(ClauseMissing):
        run(subject([seg()]), _basis_without("mqi_weight.pavement"))


def test_declared_code_must_match_basis():
    """器官按台账里的 ``code`` 取依据：换一本规范（码不同）即 ClauseMissing。"""
    from pavement_mqi_kit import run
    other = Basis(version="other", clauses=tuple(
        Clause(code="JTG D50-2017", clause=key, version="2017", text=key) for key in KEYS))
    with pytest.raises(ClauseMissing):
        run(subject([seg()]), other)


def test_record_version_follows_basis_clause_version():
    from pavement_mqi_kit import run
    basis = Basis(version="lib-2026", clauses=tuple(
        Clause(code=JTG, clause=key, version="2026", text=key) for key in KEYS))
    record = [item for item in run(subject([seg()]), basis) if item.item_id.startswith("grade.")][0]
    assert record.basis.version == "2026"


def test_pci_evidence_cites_five_clause_keys():
    from pavement_mqi_kit import run
    evidence = [item for item in run(subject([seg()])) if item.item_id.startswith("pci.")][0].evidence
    assert evidence["clause_ids"] == [
        "deduct_ratio.asphalt_distress", "pci_weight.asphalt",
        "pci_component.ride_quality", "pci_component.rutting", "pci_component.skid_resistance"]


def test_grade_evidence_reports_band_count():
    assert grade_of(90.0).evidence["bands"] == 5