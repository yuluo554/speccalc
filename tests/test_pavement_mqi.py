"""器官 ``pavement-mqi`` 的测试（迁自 target-map ③ 行）。

覆盖面：注册与包数据 / 扣分算术（类型 × 程度 × 单位分母）/ 分项得分与钳位 /
权重校验 / 等级分档（含界口径两侧）/ 养护对策规则（四种比较符）/ 路线 MQI 加权 /
输入契约原因码 / 记录形态 / 样例端到端。

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

from speccalc import cli  # noqa: E402
from speccalc.core import (  # noqa: E402
    Basis,
    Clause,
    ClauseMissing,
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

load_builtin()
ORGAN = importlib.import_module("speccalc.modules.pavement-mqi")
SLUG = ORGAN.SLUG
SAMPLE = os.path.join(ROOT, "samples", "pavement-mqi", "s99-2022.json")
BASIS_FILE = os.path.join(ROOT, "samples", "basis.json")

JTG = "JTG 5210-2018"
KEYS = (
    "deduct_ratio.asphalt_distress", "deduct_ratio.cement_distress",
    "pci_component.ride_quality", "pci_component.rutting", "pci_component.skid_resistance",
    "pci_weight.asphalt", "pci_weight.cement",
    "grade_threshold.pci", "grade_threshold.mqi", "mqi_weight.pavement",
    "action_rule.maintenance_trigger",
)
BASIS = Basis(version="road-20261125",
              clauses=tuple(Clause(code=JTG, clause=key, version="2018", text=key) for key in KEYS))


# ---------------------------------------------------------------------------
# 构造器
# ---------------------------------------------------------------------------
def _coef(key, value, status="verified", evidence="FIXTURE:road-1"):
    return {"key": key, "status": status, "value": value, "evidence": evidence}


BANDS = {"boundary": "lower_inclusive",
         "bands": [{"grade": "优", "min": 90}, {"grade": "良", "min": 80},
                   {"grade": "中", "min": 70}, {"grade": "次", "min": 60},
                   {"grade": "差", "min": 0}]}


def _coefficients(surface="asphalt", **overrides):
    blocks = {
        "deduct_ratio.%s_distress" % surface: {
            "ratios": {"横向裂缝": {"轻": 0.4, "中": 0.8, "重": 1.2},
                       "纵向裂缝": {"轻": 0.3, "中": 0.6, "重": 0.9},
                       "车辙": {"轻": 0.5, "中": 1.0, "重": 1.5},
                       "坑槽": {"轻": 0.8, "中": 1.6, "重": 2.4}},
            "denominator": {"m": "length_m", "m2": "length_m", "处": "panel_count"}},
        "pci_component.ride_quality": {"ideal_value": 10.0, "zero_value": 0.0},
        "pci_component.rutting": {"ideal_mm": 0.0, "zero_mm": 20.0},
        "pci_component.skid_resistance": {"ideal_value": 60.0, "zero_value": 0.0},
        "pci_weight.%s" % surface: {"weights": {"distress": 0.35, "ride_quality": 0.35,
                                                "rutting": 0.2, "skid_resistance": 0.1}},
        "grade_threshold.pci": BANDS,
        "grade_threshold.mqi": BANDS,
        "mqi_weight.pavement": {"weights": {"pavement": 1.0}},
        "action_rule.maintenance_trigger": {"rules": [
            {"rule_id": "AR-60", "metric": "pci", "op": "lt", "threshold": 60,
             "action_class": "大修", "scale_band": "全幅"},
            {"rule_id": "AR-70", "metric": "pci", "op": "lt", "threshold": 70,
             "action_class": "中修", "scale_band": "分段"},
            {"rule_id": "AR-80", "metric": "pci", "op": "lt", "threshold": 80,
             "action_class": "小修", "scale_band": "点状"}]},
    }
    blocks.update(overrides)
    return [_coef(key, value) for key, value in blocks.items()]


def _seg(segment_id="S-1", route_id="R1", length_m=1000.0, surface="asphalt",
         rqi=8.0, rut=5.0, skid=30.0, distresses=(), **extra):
    segment = {
        "segment_id": segment_id, "route_id": route_id, "surface_type": surface,
        "length_m": length_m, "lane_count": 2, "width_m": 7.5, "panel_count": 500,
        "measured": {"rqi": rqi, "rut_depth_mm": rut, "skid": skid},
        "distresses": list(distresses),
    }
    segment.update(extra)
    return segment


def _subject(segments, coefficients=None, minimum_grade="中", **extra):
    subject = {"project": "P", "minimum_grade": minimum_grade, "segments": list(segments),
               "coefficients": coefficients if coefficients is not None else _coefficients()}
    subject.update(extra)
    return subject


def _run(subject, basis=BASIS):
    return tuple(ORGAN.evaluate(subject, basis))


def _get(records, prefix):
    hits = [record for record in records if record.item_id.startswith(prefix + ".")]
    assert len(hits) == 1, [record.item_id for record in records]
    return hits[0]


def _pci(segment=None, **kwargs):
    return _get(_run(_subject([segment or _seg(**kwargs)])), "pci").evidence["pci"]


def _distress(kind="横向裂缝", severity="轻", quantity=100.0, unit="m"):
    return {"type": kind, "severity": severity, "quantity": quantity, "unit": unit}


# ---------------------------------------------------------------------------
# A. 注册与包数据
# ---------------------------------------------------------------------------
def test_organ_registered():
    assert get(SLUG).slug == SLUG
    assert get(SLUG).version == "0.1.0"


def test_organ_input_fields_declared():
    assert get(SLUG).input_fields == ("project", "minimum_grade", "segments", "coefficients")


def test_builtin_manifest_sorted_and_contains_slug():
    assert SLUG in BUILTIN_MODULES
    assert list(BUILTIN_MODULES) == sorted(BUILTIN_MODULES)


def test_cli_list_shows_both_organs(capsys):
    assert cli.main(["list"]) == EXIT_OK
    out = capsys.readouterr().out
    assert SLUG in out and "excavation-monitor" in out


def test_data_declares_eleven_clause_anchors():
    assert len(load_data("pavement-mqi.json")["clauses"]) == 11


def test_data_item_keys_match_coefficient_keys():
    data = load_data("pavement-mqi.json")
    assert set(data["clauses"]) == set(KEYS)


def test_data_grades_order_is_five_levels():
    assert load_data("pavement-mqi.json")["grades"]["order"] == ["优", "良", "中", "次", "差"]


def test_data_boundaries_are_two_idioms():
    assert load_data("pavement-mqi.json")["grades"]["boundaries"] == ["lower_inclusive", "lower_exclusive"]


def test_data_components_are_four():
    assert load_data("pavement-mqi.json")["metrics"]["pci_components"] == [
        "distress", "ride_quality", "rutting", "skid_resistance"]


def test_data_operators_are_four():
    assert load_data("pavement-mqi.json")["metrics"]["operators"] == ["lt", "le", "gt", "ge"]


def test_data_clause_numbers_are_all_null():
    assert all(entry["clause_no"] is None for entry in load_data("pavement-mqi.json")["clauses"].values())


def test_data_carries_no_coefficient_values():
    text = json.dumps(load_data("pavement-mqi.json"), ensure_ascii=False)
    assert '"ratios"' not in text
    assert '"min":' not in text
    assert '"threshold":' not in text


# ---------------------------------------------------------------------------
# B. 扣分算术：类型 × 程度 × 单位分母
# ---------------------------------------------------------------------------
def test_no_distress_means_full_distress_score():
    records = _run(_subject([_seg()]))
    assert _get(records, "pci").evidence["component_scores"]["distress"] == 100.0


def test_deduct_horizontal_crack_light():
    assert _pci(distresses=[_distress("横向裂缝", "轻", 100.0)]) == pytest.approx(81.6)


def test_deduct_horizontal_crack_medium():
    assert _pci(distresses=[_distress("横向裂缝", "中", 100.0)]) == pytest.approx(80.2)


def test_deduct_horizontal_crack_heavy():
    assert _pci(distresses=[_distress("横向裂缝", "重", 100.0)]) == pytest.approx(78.8)


def test_deduct_longitudinal_crack_light():
    assert _pci(distresses=[_distress("纵向裂缝", "轻", 100.0)]) == pytest.approx(81.95)


def test_deduct_longitudinal_crack_medium():
    assert _pci(distresses=[_distress("纵向裂缝", "中", 100.0)]) == pytest.approx(80.9)


def test_deduct_longitudinal_crack_heavy():
    assert _pci(distresses=[_distress("纵向裂缝", "重", 100.0)]) == pytest.approx(79.85)


def test_deduct_rutting_light():
    assert _pci(distresses=[_distress("车辙", "轻", 100.0)]) == pytest.approx(81.25)


def test_deduct_rutting_medium():
    assert _pci(distresses=[_distress("车辙", "中", 100.0)]) == pytest.approx(79.5)


def test_deduct_rutting_heavy():
    assert _pci(distresses=[_distress("车辙", "重", 100.0)]) == pytest.approx(77.75)


def test_deduct_pothole_light_in_panels():
    assert _pci(distresses=[_distress("坑槽", "轻", 10.0, "处")]) == pytest.approx(82.44)


def test_deduct_pothole_medium_in_panels():
    assert _pci(distresses=[_distress("坑槽", "中", 10.0, "处")]) == pytest.approx(81.88)


def test_deduct_pothole_heavy_in_panels():
    assert _pci(distresses=[_distress("坑槽", "重", 10.0, "处")]) == pytest.approx(81.32)


def test_deduct_area_unit_uses_length_denominator():
    assert _pci(distresses=[_distress("横向裂缝", "轻", 100.0, "m2")]) == pytest.approx(81.6)


def test_deduct_accumulates_multiple_rows():
    rows = [_distress("横向裂缝", "轻", 100.0), _distress("纵向裂缝", "轻", 100.0)]
    assert _pci(distresses=rows) == pytest.approx(80.55)


def test_deduct_total_is_reported():
    records = _run(_subject([_seg(distresses=[_distress("横向裂缝", "轻", 100.0)])]))
    assert _get(records, "pci").evidence["deducted_total"] == 4.0


def test_deduct_contributions_are_sorted():
    rows = [_distress("纵向裂缝", "轻", 100.0), _distress("横向裂缝", "轻", 100.0)]
    contributions = _run(_subject([_seg(distresses=rows)]))[0].evidence["contributions"]
    assert [row["type"] for row in contributions] == ["横向裂缝", "纵向裂缝"]


def test_deduct_contribution_carries_ratio_and_denominator():
    contributions = _run(_subject([_seg(distresses=[_distress("横向裂缝", "轻", 100.0)])]))[0].evidence["contributions"]
    assert contributions[0]["ratio"] == 0.4
    assert contributions[0]["denominator"] == 1000.0
    assert contributions[0]["denominator_field"] == "length_m"


def test_deduct_score_is_clamped_at_zero():
    """破损分项扣到 0 后 PCI 只剩其余分项：0.35×0 + 0.35×80 + 0.2×75 + 0.1×50 = 48。"""
    rows = [_distress("坑槽", "重", 500.0, "处") for _ in range(3)]
    assert _pci(distresses=rows) == pytest.approx(48.0)


def test_deduct_quantity_must_not_be_negative():
    with pytest.raises(ValueError, match="不能为负"):
        _run(_subject([_seg(distresses=[_distress(quantity=-1.0)])]))


def test_deduct_unknown_type_is_refused():
    with pytest.raises(ValueError, match="不在扣分比率表"):
        _run(_subject([_seg(distresses=[_distress("沉陷", "轻", 10.0)])]))


def test_deduct_unknown_severity_is_refused():
    with pytest.raises(ValueError, match="不在"):
        _run(_subject([_seg(distresses=[_distress("横向裂缝", "极重", 10.0)])]))


def test_deduct_unmapped_unit_is_refused():
    with pytest.raises(ValueError, match="unit_unmapped"):
        _run(_subject([_seg(distresses=[_distress(unit="km")])]))


def test_deduct_zero_denominator_is_refused():
    with pytest.raises(ValueError, match="必须为正"):
        _run(_subject([_seg(length_m=0.0)]))


def test_deduct_zero_panel_count_is_refused():
    segment = _seg(distresses=[_distress("坑槽", "轻", 1.0, "处")], panel_count=0)
    with pytest.raises(ValueError, match="必须为正"):
        _run(_subject([segment]))


# ---------------------------------------------------------------------------
# C. 分项得分与钳位
# ---------------------------------------------------------------------------
def test_ride_quality_at_ideal_is_hundred():
    records = _run(_subject([_seg(rqi=10.0)]))
    assert _get(records, "pci").evidence["component_scores"]["ride_quality"] == 100.0


def test_ride_quality_at_zero_is_zero():
    records = _run(_subject([_seg(rqi=0.0)]))
    assert _get(records, "pci").evidence["component_scores"]["ride_quality"] == 0.0


def test_ride_quality_midpoint():
    records = _run(_subject([_seg(rqi=5.0)]))
    assert _get(records, "pci").evidence["component_scores"]["ride_quality"] == 50.0


def test_ride_quality_above_ideal_is_clamped():
    records = _run(_subject([_seg(rqi=20.0)]))
    assert _get(records, "pci").evidence["component_scores"]["ride_quality"] == 100.0


def test_rutting_at_ideal_is_hundred():
    records = _run(_subject([_seg(rut=0.0)]))
    assert _get(records, "pci").evidence["component_scores"]["rutting"] == 100.0


def test_rutting_at_zero_is_zero():
    records = _run(_subject([_seg(rut=20.0)]))
    assert _get(records, "pci").evidence["component_scores"]["rutting"] == 0.0


def test_rutting_midpoint():
    records = _run(_subject([_seg(rut=10.0)]))
    assert _get(records, "pci").evidence["component_scores"]["rutting"] == 50.0


def test_rutting_beyond_zero_is_clamped():
    records = _run(_subject([_seg(rut=40.0)]))
    assert _get(records, "pci").evidence["component_scores"]["rutting"] == 0.0


def test_skid_at_ideal_is_hundred():
    records = _run(_subject([_seg(skid=60.0)]))
    assert _get(records, "pci").evidence["component_scores"]["skid_resistance"] == 100.0


def test_skid_at_zero_is_zero():
    records = _run(_subject([_seg(skid=0.0)]))
    assert _get(records, "pci").evidence["component_scores"]["skid_resistance"] == 0.0


def test_skid_midpoint():
    records = _run(_subject([_seg(skid=30.0)]))
    assert _get(records, "pci").evidence["component_scores"]["skid_resistance"] == 50.0


def test_skid_negative_is_clamped():
    records = _run(_subject([_seg(skid=-5.0)]))
    assert _get(records, "pci").evidence["component_scores"]["skid_resistance"] == 0.0


def test_ideal_equals_zero_is_refused():
    coefficients = _coefficients(**{"pci_component.ride_quality": {"ideal_value": 5.0, "zero_value": 5.0}})
    with pytest.raises(ValueError, match="ideal 与 zero 不能相等"):
        _run(_subject([_seg(rqi=5.0)], coefficients=coefficients))


def test_missing_required_measurement_is_refused():
    segment = _seg()
    segment["measured"] = {"rqi": 8.0}
    with pytest.raises(ValueError, match="rut_depth_mm"):
        _run(_subject([segment]))


def test_measurement_must_be_numeric():
    segment = _seg()
    segment["measured"]["rqi"] = "8"
    with pytest.raises(ValueError, match="数值"):
        _run(_subject([segment]))


def test_measurement_boolean_is_refused():
    segment = _seg()
    segment["measured"]["rqi"] = True
    with pytest.raises(ValueError, match="数值"):
        _run(_subject([segment]))


def test_pci_matches_weighted_sum_for_clean_segment():
    """rqi=8→80，rut=5→75，skid=30→50，distress=100：0.35*100+0.35*80+0.2*75+0.1*50=83。"""
    assert _pci(rqi=8.0, rut=5.0, skid=30.0) == pytest.approx(83.0)


def test_pci_is_rounded_to_two_digits():
    """rqi=7→70，rut=3→85，skid=37→61.67：0.35×100+0.35×70+0.2×85+0.1×61.67=82.67。"""
    assert _pci(rqi=7.0, rut=3.0, skid=37.0) == pytest.approx(82.67)


def test_pci_floor_keeps_remaining_components():
    """其余分项全 0 时 PCI 只剩破损分项：0.35×100 = 35。"""
    assert _pci(rut=100.0, skid=0.0, rqi=0.0) == pytest.approx(35.0)


# ---------------------------------------------------------------------------
# D. 权重校验
# ---------------------------------------------------------------------------
def test_weights_must_sum_to_one():
    weights = {"weights": {"distress": 0.5, "ride_quality": 0.35, "rutting": 0.2, "skid_resistance": 0.1}}
    with pytest.raises(ValueError, match="权重之和必须为 1"):
        _run(_subject([_seg()], coefficients=_coefficients(**{"pci_weight.asphalt": weights})))


def test_unknown_component_in_weights_is_refused():
    weights = {"weights": {"distress": 0.5, "ride_quality": 0.3, "rutting": 0.2, "bogus": 0.0}}
    with pytest.raises(ValueError, match="未知分项"):
        _run(_subject([_seg()], coefficients=_coefficients(**{"pci_weight.asphalt": weights})))


def test_zero_weight_component_skips_measurement_requirement():
    weights = {"weights": {"distress": 0.6, "ride_quality": 0.3, "rutting": 0.1, "skid_resistance": 0.0}}
    segment = _seg()
    segment["measured"] = {"rqi": 8.0, "rut_depth_mm": 5.0}
    assert _get(_run(_subject([segment], coefficients=_coefficients(**{"pci_weight.asphalt": weights}))),
                "pci").evidence["component_scores"]["distress"] == 100.0


def test_zero_weight_component_absent_from_scores():
    weights = {"weights": {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}}
    segment = _seg()
    segment["measured"] = {}
    scores = _get(_run(_subject([segment], coefficients=_coefficients(**{"pci_weight.asphalt": weights}))),
                  "pci").evidence["component_scores"]
    assert scores == {"distress": 100.0}


def test_distress_only_weight_ignores_measured_garbage():
    weights = {"weights": {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}}
    segment = _seg()
    segment["measured"] = {"rqi": "not-a-number"}
    records = _run(_subject([segment], coefficients=_coefficients(**{"pci_weight.asphalt": weights})))
    assert _get(records, "pci").evidence["pci"] == 100.0


# ---------------------------------------------------------------------------
# E. 等级分档（含界口径两侧）
# ---------------------------------------------------------------------------
def _grade_of(pci_target, boundary="lower_inclusive"):
    """构造一个 PCI 正好等于目标值的路段（只保留 distress 权重，扣分可控）。"""
    weights = {"weights": {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}}
    segment = _seg()
    segment["measured"] = {}
    # 扣分 = ratio(0.4) × qty/1000 × 100 = 0.04 × qty → PCI = 100 − 0.04×qty
    quantity = round((100.0 - pci_target) / 0.04, 6)
    segment["distresses"] = [_distress("横向裂缝", "轻", quantity)]
    bands = dict(BANDS)
    bands["boundary"] = boundary
    coefficients = _coefficients(**{"pci_weight.asphalt": weights,
                                   "grade_threshold.pci": bands,
                                   "grade_threshold.mqi": bands})
    return _get(_run(_subject([segment], coefficients=coefficients)), "grade")


def test_grade_inclusive_at_ninety_is_excellent():
    assert _grade_of(90.0).evidence["grade"] == "优"


def test_grade_exclusive_at_ninety_is_good():
    assert _grade_of(90.0, "lower_exclusive").evidence["grade"] == "良"


def test_grade_inclusive_at_eighty_is_good():
    assert _grade_of(80.0).evidence["grade"] == "良"


def test_grade_exclusive_at_eighty_is_medium():
    assert _grade_of(80.0, "lower_exclusive").evidence["grade"] == "中"


def test_grade_inclusive_at_seventy_is_medium():
    assert _grade_of(70.0).evidence["grade"] == "中"


def test_grade_exclusive_at_seventy_is_poor():
    assert _grade_of(70.0, "lower_exclusive").evidence["grade"] == "次"


def test_grade_inclusive_at_sixty_is_poor():
    assert _grade_of(60.0).evidence["grade"] == "次"


def test_grade_exclusive_at_sixty_is_bad():
    assert _grade_of(60.0, "lower_exclusive").evidence["grade"] == "差"


def test_grade_below_lowest_band_is_bad():
    assert _grade_of(10.0).evidence["grade"] == "差"


def test_grade_record_passes_when_at_or_above_baseline():
    assert _grade_of(70.0).verdict == OK


def test_grade_record_rejects_below_baseline():
    assert _grade_of(65.0).verdict == REJECTED


def test_grade_evidence_carries_ranks():
    evidence = _grade_of(65.0).evidence
    assert evidence["grade_rank"] == 3
    assert evidence["minimum_rank"] == 2


def test_grade_boundary_value_must_be_known():
    bands = dict(BANDS)
    bands["boundary"] = "midpoint"
    with pytest.raises(ValueError, match="boundary 非法"):
        _run(_subject([_seg()], coefficients=_coefficients(**{"grade_threshold.pci": bands})))


def test_grade_band_grade_must_be_known():
    bands = {"boundary": "lower_inclusive", "bands": [{"grade": "甲", "min": 0}]}
    with pytest.raises(ValueError, match="grade 非法"):
        _run(_subject([_seg()], coefficients=_coefficients(**{"grade_threshold.pci": bands})))


def test_grade_bands_must_not_be_empty():
    with pytest.raises(ValueError, match="bands 必须是非空数组"):
        _run(_subject([_seg()], coefficients=_coefficients(**{"grade_threshold.pci": {"boundary": "lower_inclusive", "bands": []}})))


def test_grade_uses_highest_matching_band_regardless_of_input_order():
    bands = {"boundary": "lower_inclusive",
             "bands": [{"grade": "差", "min": 0}, {"grade": "优", "min": 90},
                       {"grade": "良", "min": 80}, {"grade": "中", "min": 70},
                       {"grade": "次", "min": 60}]}
    assert _run(_subject([_seg(rqi=10.0, rut=0.0, skid=60.0)],
                         coefficients=_coefficients(**{"grade_threshold.pci": bands})))[1].evidence["grade"] == "优"


def test_minimum_grade_must_be_known():
    with pytest.raises(ValueError, match="minimum_grade 非法"):
        _run(_subject([_seg()], minimum_grade="甲"))


# ---------------------------------------------------------------------------
# F. 养护对策规则
# ---------------------------------------------------------------------------
def _action_of(pci_target, op="lt", threshold=None):
    weights = {"weights": {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}}
    segment = _seg()
    segment["measured"] = {}
    segment["distresses"] = [_distress("横向裂缝", "轻", round((100.0 - pci_target) / 0.04, 6))]
    rules = {"rules": [{"rule_id": "AR-1", "metric": "pci", "op": op,
                        "threshold": threshold if threshold is not None else pci_target,
                        "action_class": "中修", "scale_band": "分段"}]}
    coefficients = _coefficients(**{"pci_weight.asphalt": weights,
                                   "action_rule.maintenance_trigger": rules})
    return _get(_run(_subject([segment], coefficients=coefficients)), "action")


def test_action_lt_fires_when_below():
    assert _action_of(70.0, "lt", 75.0).verdict == REJECTED


def test_action_lt_does_not_fire_at_threshold():
    assert _action_of(70.0, "lt", 70.0).verdict == OK


def test_action_le_fires_at_threshold():
    assert _action_of(70.0, "le", 70.0).verdict == REJECTED


def test_action_gt_fires_when_above():
    assert _action_of(70.0, "gt", 60.0).verdict == REJECTED


def test_action_gt_does_not_fire_at_threshold():
    assert _action_of(70.0, "gt", 70.0).verdict == OK


def test_action_ge_fires_at_threshold():
    assert _action_of(70.0, "ge", 70.0).verdict == REJECTED


def test_action_none_fires_when_no_rule_matches():
    assert _action_of(95.0, "lt", 60.0).verdict == OK


def test_action_reports_action_class_and_band():
    evidence = _action_of(70.0, "lt", 75.0).evidence
    assert evidence["action"]["action_class"] == "中修"
    assert evidence["action"]["scale_band"] == "分段"


def test_action_reports_rule_id_and_metric_value():
    action = _action_of(70.0, "lt", 75.0).evidence["action"]
    assert action["rule_id"] == "AR-1"
    assert action["metric_value"] == pytest.approx(70.0)


def test_action_unknown_operator_is_refused():
    with pytest.raises(ValueError, match="op 非法"):
        _action_of(70.0, "eq", 70.0)


def test_action_first_matching_rule_wins():
    weights = {"weights": {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}}
    segment = _seg()
    segment["measured"] = {}
    segment["distresses"] = [_distress("横向裂缝", "轻", 750.0)]  # PCI 70
    rules = {"rules": [
        {"rule_id": "AR-FIRST", "metric": "pci", "op": "lt", "threshold": 80, "action_class": "小修"},
        {"rule_id": "AR-SECOND", "metric": "pci", "op": "lt", "threshold": 71, "action_class": "中修"}]}
    coefficients = _coefficients(**{"pci_weight.asphalt": weights,
                                   "action_rule.maintenance_trigger": rules})
    action = _get(_run(_subject([segment], coefficients=coefficients)), "action")
    assert action.evidence["action"]["rule_id"] == "AR-FIRST"


def test_action_mqi_metric_uses_segment_partial_mqi():
    weights = {"weights": {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}}
    segment = _seg()
    segment["measured"] = {}
    segment["distresses"] = [_distress("横向裂缝", "轻", 750.0)]
    rules = {"rules": [{"rule_id": "AR-MQI", "metric": "mqi", "op": "lt",
                        "threshold": 80, "action_class": "中修"}]}
    coefficients = _coefficients(**{"pci_weight.asphalt": weights,
                                   "action_rule.maintenance_trigger": rules})
    action = _get(_run(_subject([segment], coefficients=coefficients)), "action")
    assert action.evidence["action"]["metric"] == "mqi"
    assert action.evidence["mqi_partial"] == pytest.approx(70.0)


def test_action_ignores_rules_for_other_metrics_when_pci_matches():
    weights = {"weights": {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}}
    segment = _seg()
    segment["measured"] = {}
    segment["distresses"] = [_distress("横向裂缝", "轻", 750.0)]
    rules = {"rules": [{"rule_id": "AR-MQIONLY", "metric": "mqi", "op": "lt",
                        "threshold": 10, "action_class": "中修"}]}
    coefficients = _coefficients(**{"pci_weight.asphalt": weights,
                                   "action_rule.maintenance_trigger": rules})
    assert _get(_run(_subject([segment], coefficients=coefficients)), "action").verdict == OK


def test_action_evidence_lists_clause_key():
    assert _action_of(70.0, "lt", 75.0).evidence["clause_ids"] == ["action_rule.maintenance_trigger"]


# ---------------------------------------------------------------------------
# G. 路线 MQI 加权
# ---------------------------------------------------------------------------
def test_mqi_of_single_segment_equals_its_pci():
    records = _run(_subject([_seg()]))
    assert _get(records, "mqi").evidence["mqi"] == pytest.approx(83.0)


def test_mqi_is_length_weighted():
    records = _run(_subject([_seg("S-1", length_m=1000.0), _seg("S-2", length_m=1000.0)]))
    assert _get(records, "mqi").evidence["mqi"] == pytest.approx(83.0)


def test_mqi_weights_short_segment_less():
    heavy = _seg("S-2", length_m=1.0, rqi=0.0, rut=20.0, skid=0.0)
    records = _run(_subject([_seg("S-1", length_m=1000.0), heavy]))
    mqi = _get(records, "mqi").evidence["mqi"]
    assert mqi > 80.0


def test_mqi_reports_weighted_length():
    records = _run(_subject([_seg("S-1", length_m=1000.0), _seg("S-2", length_m=500.0)]))
    assert _get(records, "mqi").evidence["weighted_length_m"] == 1500.0


def test_mqi_reports_scope_note_as_partial():
    assert "pavement" in _get(_run(_subject([_seg()])), "mqi").evidence["scope_note"]


def test_mqi_grade_uses_mqi_bands():
    records = _run(_subject([_seg(rqi=4.0, rut=18.0, skid=10.0)]))
    assert _get(records, "mqi").evidence["grade"] == "差"


def test_mqi_rejected_below_baseline():
    records = _run(_subject([_seg(rqi=4.0, rut=18.0, skid=10.0)]))
    assert _get(records, "mqi").verdict == REJECTED


def test_mqi_ok_at_baseline():
    records = _run(_subject([_seg()]))
    assert _get(records, "mqi").verdict == OK


def test_mqi_groups_segments_by_route():
    records = _run(_subject([_seg("S-1", "R1"), _seg("S-2", "R2")]))
    assert sorted(record.item_id for record in records if record.item_id.startswith("mqi.")) == [
        "mqi.R1", "mqi.R2"]


def test_mqi_lists_member_segments():
    evidence = _get(_run(_subject([_seg("S-1"), _seg("S-2")])), "mqi").evidence
    assert [row["segment_id"] for row in evidence["segments"]] == ["S-1", "S-2"]


def test_mqi_zero_length_is_refused():
    with pytest.raises(ValueError, match="length_m 必须为正"):
        _run(_subject([_seg(length_m=0.0)]))


def test_pci_record_basis_is_surface_weight_clause():
    assert _get(_run(_subject([_seg()])), "pci").basis.clause == "pci_weight.asphalt"


def test_mqi_record_basis_is_pavement_weight_clause():
    assert _get(_run(_subject([_seg()])), "mqi").basis.clause == "mqi_weight.pavement"


def test_grade_record_basis_is_pci_threshold_clause():
    assert _get(_run(_subject([_seg()])), "grade").basis.clause == "grade_threshold.pci"


def test_action_record_basis_is_action_rule_clause():
    assert _get(_run(_subject([_seg()])), "action").basis.clause == "action_rule.maintenance_trigger"


# ---------------------------------------------------------------------------
# H. 输入契约原因码
# ---------------------------------------------------------------------------
def test_coefficient_pending_is_refused():
    coefficients = _coefficients()
    coefficients[0] = _coef(coefficients[0]["key"], coefficients[0]["value"], status="pending")
    with pytest.raises(ValueError, match="source_not_confirmed"):
        _run(_subject([_seg()], coefficients=coefficients))


def test_coefficient_missing_evidence_is_refused():
    coefficients = _coefficients()
    coefficients[0] = _coef(coefficients[0]["key"], coefficients[0]["value"], evidence="")
    with pytest.raises(ValueError, match="evidence_missing"):
        _run(_subject([_seg()], coefficients=coefficients))


def test_coefficient_missing_value_is_refused():
    coefficients = _coefficients()
    coefficients[0] = {"key": coefficients[0]["key"], "status": "verified", "evidence": "x"}
    with pytest.raises(ValueError, match="value_missing"):
        _run(_subject([_seg()], coefficients=coefficients))


def test_missing_coefficient_block_is_refused():
    coefficients = [block for block in _coefficients() if block["key"] != "grade_threshold.pci"]
    with pytest.raises(ValueError, match="coefficient_missing"):
        _run(_subject([_seg()], coefficients=coefficients))


def test_missing_weights_coefficient_is_refused():
    coefficients = [block for block in _coefficients() if block["key"] != "pci_weight.asphalt"]
    with pytest.raises(ValueError, match="pci_weight.asphalt"):
        _run(_subject([_seg()], coefficients=coefficients))


def test_duplicate_coefficient_key_is_refused():
    coefficients = _coefficients()
    coefficients.append(dict(coefficients[0]))
    with pytest.raises(ValueError, match="系数格重复"):
        _run(_subject([_seg()], coefficients=coefficients))


def test_empty_coefficients_is_refused():
    with pytest.raises(ValueError, match="coefficients 必须是非空数组"):
        _run(_subject([_seg()], coefficients=[]))


def test_coefficients_must_be_list():
    with pytest.raises(ValueError, match="coefficients"):
        _run({"project": "P", "minimum_grade": "中", "segments": [_seg()], "coefficients": {}})


def test_missing_project_is_refused():
    with pytest.raises(ValueError, match="project"):
        _run({"minimum_grade": "中", "segments": [_seg()], "coefficients": _coefficients()})


def test_empty_segments_is_refused():
    with pytest.raises(ValueError, match="segments 必须是非空数组"):
        _run(_subject([]))


def test_segment_must_be_mapping():
    with pytest.raises(ValueError, match="segments\\[\\] 必须是对象"):
        _run(_subject(["S-1"]))


def test_duplicate_segment_id_is_refused():
    with pytest.raises(ValueError, match="路段重复"):
        _run(_subject([_seg("S-1"), _seg("S-1")]))


def test_segment_missing_route_is_refused():
    segment = _seg()
    del segment["route_id"]
    with pytest.raises(ValueError, match="route_id"):
        _run(_subject([segment]))


def test_segment_surface_must_have_weight_block():
    with pytest.raises(ValueError, match="pci_weight.cement"):
        _run(_subject([_seg(surface="cement")]))


def test_cement_surface_uses_cement_blocks():
    coefficients = _coefficients(surface="cement")
    records = _run(_subject([_seg(surface="cement")], coefficients=coefficients))
    assert _get(records, "pci").basis.clause == "pci_weight.cement"


def test_measured_must_be_mapping():
    segment = _seg()
    segment["measured"] = "8.0"
    with pytest.raises(ValueError, match="measured 必须是对象"):
        _run(_subject([segment]))


def test_distress_row_must_be_mapping():
    with pytest.raises(ValueError, match="distresses\\[\\] 必须是对象"):
        _run(_subject([_seg(distresses=["横向裂缝"])]))


def test_subject_must_be_mapping():
    with pytest.raises(ValueError, match="JSON 对象"):
        _run([_seg()])


def test_clause_missing_propagates():
    thin = Basis(version="thin", clauses=(Clause(code=JTG, clause="pci_weight.asphalt",
                                                 version="2018", text="x"),))
    with pytest.raises(ClauseMissing):
        _run(_subject([_seg()]), basis=thin)


def test_cli_clause_missing_is_contract_error(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps(_subject([_seg()]), ensure_ascii=False), encoding="utf-8")
    thin = tmp_path / "basis.json"
    thin.write_text(json.dumps({"version": "thin", "clauses": []}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", str(thin)]) == EXIT_CONTRACT
    assert "ClauseMissing" in capsys.readouterr().err


def test_cli_input_error_is_rc2(tmp_path):
    target = tmp_path / "in.json"
    target.write_text(json.dumps({"project": "P"}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", BASIS_FILE]) == EXIT_INPUT


# ---------------------------------------------------------------------------
# I. 记录形态
# ---------------------------------------------------------------------------
def test_every_record_carries_basis_and_version():
    for record in _run(_subject([_seg()])):
        assert record.basis is not None
        assert record.basis.code == JTG
        assert record.basis.version == "2018"


def test_four_records_per_segment_plus_route():
    records = _run(_subject([_seg("S-1"), _seg("S-2")]))
    assert sorted(record.item_id for record in records) == [
        "action.S-1", "action.S-2", "grade.S-1", "grade.S-2",
        "mqi.R1", "pci.S-1", "pci.S-2"]


def test_pci_record_is_always_ok():
    for record in _run(_subject([_seg(), _seg("S-2", rqi=0.0, rut=20.0, skid=0.0)])):
        if record.item_id.startswith("pci."):
            assert record.verdict == OK


def test_verdicts_are_only_ok_or_rejected():
    assert {record.verdict for record in _run(_subject([_seg()]))} <= {OK, REJECTED}


def test_message_states_pci_value():
    assert "83" in _get(_run(_subject([_seg()])), "pci").message


def test_pci_evidence_formula_is_present():
    assert "PCI" in _get(_run(_subject([_seg()])), "pci").evidence["formula"]


def test_grade_evidence_reports_boundary():
    assert _get(_run(_subject([_seg()])), "grade").evidence["boundary"] == "lower_inclusive"


def test_record_ids_are_unique():
    records = _run(_subject([_seg("S-1"), _seg("S-2")]))
    ids = [record.id for record in records]
    assert len(ids) == len(set(ids))


def test_json_output_is_deterministic(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps(_subject([_seg()]), ensure_ascii=False), encoding="utf-8")
    args = ["check", SLUG, "--input", str(target), "--basis", BASIS_FILE, "--json"]
    cli.main(args)
    first = capsys.readouterr().out
    cli.main(args)
    assert capsys.readouterr().out == first
    assert str(tmp_path) not in first


def test_env_and_clock_do_not_change_result(monkeypatch):
    subject = _subject([_seg()])
    before = [record.as_dict() for record in _run(subject)]
    monkeypatch.setenv("RMQC_DATA_DIR", "/nonexistent")
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    assert [record.as_dict() for record in _run(subject)] == before


# ---------------------------------------------------------------------------
# J. 样例端到端（samples/pavement-mqi/s99-2022.json）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sample_records():
    with open(SAMPLE, "r", encoding="utf-8") as handle:
        subject = json.load(handle)
    return _run(subject, Basis.from_json(BASIS_FILE))


def test_sample_produces_seven_records(sample_records):
    assert len(sample_records) == 7


def test_sample_a1_pci_matches_hand_calculation(sample_records):
    """A1：扣分 2.4（横向裂缝轻 60m）+ 12.0（车辙中 120m2）= 14.4 → distress 85.6。

    PCI = 0.35×85.6 + 0.35×74 + 0.2×70 + 0.1×80 = 29.96 + 25.9 + 14 + 8 = 77.86
    """
    hits = [record for record in sample_records if record.item_id == "pci.S99-A1"]
    assert hits[0].evidence["pci"] == pytest.approx(77.86)


def test_sample_ids_are_stable(sample_records):
    assert sorted(record.item_id for record in sample_records) == [
        "action.S99-A1", "action.S99-A2", "grade.S99-A1", "grade.S99-A2",
        "mqi.S99", "pci.S99-A1", "pci.S99-A2"]


def test_sample_a2_is_rejected_by_grade(sample_records):
    hits = [record for record in sample_records if record.item_id == "grade.S99-A2"]
    assert hits[0].verdict == REJECTED


def test_sample_a1_grade_is_ok(sample_records):
    hits = [record for record in sample_records if record.item_id == "grade.S99-A1"]
    assert hits[0].verdict == OK


def test_sample_route_mqi_is_rejected(sample_records):
    assert _get(sample_records, "mqi").verdict == REJECTED


def test_sample_cli_rc_is_one(capsys):
    assert cli.main(["check", SLUG, "--input", SAMPLE, "--basis", BASIS_FILE]) == EXIT_BLOCKED
    assert "rejected" in capsys.readouterr().out


def test_sample_pci_values_sum_by_length_to_mqi(sample_records):
    mqi = _get(sample_records, "mqi").evidence
    weighted = sum(row["length_m"] * row["pci"] for row in mqi["segments"]) / mqi["weighted_length_m"]
    assert mqi["mqi"] == pytest.approx(float("%.2f" % weighted))