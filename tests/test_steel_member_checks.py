"""``steel-member`` · 9 条验算式 × 结论两态 / 容差 / 提示 / 依据（GB 50017-2017）。

矩阵口径（每条验算式都走一遍）：
- ``ratio = 1``（作用 = 抗力）→ ``ok``；
- ``ratio = 1.0005``（容差 1e-3 之内）→ ``ok``；
- ``ratio = 1.002``（超出容差）→ ``rejected``；
- ``ratio = 0.96`` → ``need_adjust = true`` 但结论仍是 ``ok``（提示不改判）；
- ``ratio = 0.90`` → ``need_adjust = false``；
- 依据条号 / 绑定的设计值键 / 作用与抗力入账值；
- 从条文库里抽掉该条号 → ``ClauseMissing`` 冒到上层。

不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数）。
"""

from __future__ import annotations

import pytest

from steel_member_kit import (
    BASIS,
    CLAUSE_OF,
    LIMIT_KEY,
    SPEC,
    basis_without,
    payload_for,
    row_for,
    run,
)
from speccalc.core import OK, REJECTED, ClauseMissing

INSIDE = 1.0005
ABOVE = 1.002
NEAR = 0.96
BELOW = 0.90


# ---------------------------------------------------------------------------
# butt.tension · 11.2.1
# ---------------------------------------------------------------------------
def test_butt_tension_ratio_exactly_one_is_ok():
    record = row_for("butt.tension", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_butt_tension_ratio_inside_tolerance_is_ok():
    assert row_for("butt.tension", INSIDE).verdict == OK


def test_butt_tension_ratio_above_tolerance_is_rejected():
    assert row_for("butt.tension", ABOVE).verdict == REJECTED


def test_butt_tension_need_adjust_at_ninety_six_percent():
    record = row_for("butt.tension", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_butt_tension_need_adjust_false_at_ninety_percent():
    assert row_for("butt.tension", BELOW).evidence["need_adjust"] is False


def test_butt_tension_cites_clause_11_2_1():
    assert row_for("butt.tension", 1.0).basis.clause == "11.2.1"


def test_butt_tension_binds_tensile_strength():
    assert row_for("butt.tension", 1.0).evidence["limit_key"] == "f_t_w"


def test_butt_tension_without_its_clause_raises():
    payload = payload_for("butt.tension", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("11.2.1"))


def test_butt_tension_reports_demand_and_capacity():
    evidence = row_for("butt.tension", ABOVE).evidence
    assert evidence["demand"] == pytest.approx(350000.0 * ABOVE)
    assert evidence["capacity"] == pytest.approx(350000.0)


# ---------------------------------------------------------------------------
# butt.shear · 11.2.1
# ---------------------------------------------------------------------------
def test_butt_shear_ratio_exactly_one_is_ok():
    record = row_for("butt.shear", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_butt_shear_ratio_inside_tolerance_is_ok():
    assert row_for("butt.shear", INSIDE).verdict == OK


def test_butt_shear_ratio_above_tolerance_is_rejected():
    assert row_for("butt.shear", ABOVE).verdict == REJECTED


def test_butt_shear_need_adjust_at_ninety_six_percent():
    record = row_for("butt.shear", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_butt_shear_need_adjust_false_at_ninety_percent():
    assert row_for("butt.shear", BELOW).evidence["need_adjust"] is False


def test_butt_shear_cites_clause_11_2_1():
    assert row_for("butt.shear", 1.0).basis.clause == "11.2.1"


def test_butt_shear_binds_shear_strength():
    assert row_for("butt.shear", 1.0).evidence["limit_key"] == "f_v_w"


def test_butt_shear_without_its_clause_raises():
    payload = payload_for("butt.shear", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("11.2.1"))


def test_butt_shear_reports_demand_and_capacity():
    evidence = row_for("butt.shear", ABOVE).evidence
    assert evidence["demand"] == pytest.approx(200000.0 * ABOVE)
    assert evidence["capacity"] == pytest.approx(200000.0)


# ---------------------------------------------------------------------------
# fillet.side · 11.2.2
# ---------------------------------------------------------------------------
def test_fillet_side_ratio_exactly_one_is_ok():
    record = row_for("fillet.side", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_fillet_side_ratio_inside_tolerance_is_ok():
    assert row_for("fillet.side", INSIDE).verdict == OK


def test_fillet_side_ratio_above_tolerance_is_rejected():
    assert row_for("fillet.side", ABOVE).verdict == REJECTED


def test_fillet_side_need_adjust_at_ninety_six_percent():
    record = row_for("fillet.side", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_fillet_side_need_adjust_false_at_ninety_percent():
    assert row_for("fillet.side", BELOW).evidence["need_adjust"] is False


def test_fillet_side_cites_clause_11_2_2():
    assert row_for("fillet.side", 1.0).basis.clause == "11.2.2"


def test_fillet_side_binds_fillet_strength():
    assert row_for("fillet.side", 1.0).evidence["limit_key"] == "f_f_w"


def test_fillet_side_without_its_clause_raises():
    payload = payload_for("fillet.side", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("11.2.2"))


def test_fillet_side_reports_demand_and_capacity():
    evidence = row_for("fillet.side", ABOVE).evidence
    assert evidence["demand"] == pytest.approx(358400.0 * ABOVE)
    assert evidence["capacity"] == pytest.approx(358400.0)


# ---------------------------------------------------------------------------
# fillet.front · 11.2.2
# ---------------------------------------------------------------------------
def test_fillet_front_ratio_exactly_one_is_ok():
    record = row_for("fillet.front", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_fillet_front_ratio_inside_tolerance_is_ok():
    assert row_for("fillet.front", INSIDE).verdict == OK


def test_fillet_front_ratio_above_tolerance_is_rejected():
    assert row_for("fillet.front", ABOVE).verdict == REJECTED


def test_fillet_front_need_adjust_at_ninety_six_percent():
    record = row_for("fillet.front", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_fillet_front_need_adjust_false_at_ninety_percent():
    assert row_for("fillet.front", BELOW).evidence["need_adjust"] is False


def test_fillet_front_cites_clause_11_2_2():
    assert row_for("fillet.front", 1.0).basis.clause == "11.2.2"


def test_fillet_front_binds_fillet_strength():
    assert row_for("fillet.front", 1.0).evidence["limit_key"] == "f_f_w"


def test_fillet_front_without_its_clause_raises():
    payload = payload_for("fillet.front", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("11.2.2"))


def test_fillet_front_reports_demand_and_capacity():
    evidence = row_for("fillet.front", ABOVE).evidence
    assert evidence["demand"] == pytest.approx(437248.0 * ABOVE)
    assert evidence["capacity"] == pytest.approx(437248.0)


# ---------------------------------------------------------------------------
# bolt.shear · 11.4.1
# ---------------------------------------------------------------------------
def test_bolt_shear_ratio_exactly_one_is_ok():
    record = row_for("bolt.shear", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_bolt_shear_ratio_inside_tolerance_is_ok():
    assert row_for("bolt.shear", INSIDE).verdict == OK


def test_bolt_shear_ratio_above_tolerance_is_rejected():
    assert row_for("bolt.shear", ABOVE).verdict == REJECTED


def test_bolt_shear_need_adjust_at_ninety_six_percent():
    record = row_for("bolt.shear", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_bolt_shear_need_adjust_false_at_ninety_percent():
    assert row_for("bolt.shear", BELOW).evidence["need_adjust"] is False


def test_bolt_shear_cites_clause_11_4_1():
    assert row_for("bolt.shear", 1.0).basis.clause == "11.4.1"


def test_bolt_shear_binds_shear_strength():
    assert row_for("bolt.shear", 1.0).evidence["limit_key"] == "f_v_b"


def test_bolt_shear_without_its_clause_raises():
    payload = payload_for("bolt.shear", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("11.4.1"))


def test_bolt_shear_reports_per_bolt_demand_and_capacity():
    evidence = row_for("bolt.shear", ABOVE).evidence
    assert evidence["N_v"] == pytest.approx(43982.2971502571 * ABOVE)
    assert evidence["capacity"] == pytest.approx(43982.2971502571)


# ---------------------------------------------------------------------------
# bolt.bearing · 11.4.1
# ---------------------------------------------------------------------------
def test_bolt_bearing_ratio_exactly_one_is_ok():
    record = row_for("bolt.bearing", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_bolt_bearing_ratio_inside_tolerance_is_ok():
    assert row_for("bolt.bearing", INSIDE).verdict == OK


def test_bolt_bearing_ratio_above_tolerance_is_rejected():
    assert row_for("bolt.bearing", ABOVE).verdict == REJECTED


def test_bolt_bearing_need_adjust_at_ninety_six_percent():
    record = row_for("bolt.bearing", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_bolt_bearing_need_adjust_false_at_ninety_percent():
    assert row_for("bolt.bearing", BELOW).evidence["need_adjust"] is False


def test_bolt_bearing_cites_clause_11_4_1():
    assert row_for("bolt.bearing", 1.0).basis.clause == "11.4.1"


def test_bolt_bearing_binds_bearing_strength():
    assert row_for("bolt.bearing", 1.0).evidence["limit_key"] == "f_c_b"


def test_bolt_bearing_without_its_clause_raises():
    payload = payload_for("bolt.bearing", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("11.4.1"))


def test_bolt_bearing_reports_per_bolt_demand_and_capacity():
    evidence = row_for("bolt.bearing", ABOVE).evidence
    assert evidence["N_v"] == pytest.approx(122000.0 * ABOVE)
    assert evidence["capacity"] == pytest.approx(122000.0)


# ---------------------------------------------------------------------------
# hsb.friction · 11.4.2
# ---------------------------------------------------------------------------
def test_hsb_friction_ratio_exactly_one_is_ok():
    record = row_for("hsb.friction", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_hsb_friction_ratio_inside_tolerance_is_ok():
    assert row_for("hsb.friction", INSIDE).verdict == OK


def test_hsb_friction_ratio_above_tolerance_is_rejected():
    assert row_for("hsb.friction", ABOVE).verdict == REJECTED


def test_hsb_friction_need_adjust_at_ninety_six_percent():
    record = row_for("hsb.friction", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_hsb_friction_need_adjust_false_at_ninety_percent():
    assert row_for("hsb.friction", BELOW).evidence["need_adjust"] is False


def test_hsb_friction_cites_clause_11_4_2():
    assert row_for("hsb.friction", 1.0).basis.clause == "11.4.2"


def test_hsb_friction_binds_preload():
    assert row_for("hsb.friction", 1.0).evidence["limit_key"] == "P_hsb"


def test_hsb_friction_without_its_clause_raises():
    payload = payload_for("hsb.friction", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("11.4.2"))


def test_hsb_friction_reports_per_bolt_demand_and_capacity():
    evidence = row_for("hsb.friction", ABOVE).evidence
    assert evidence["N_v"] == pytest.approx(125550.0 * ABOVE)
    assert evidence["capacity"] == pytest.approx(125550.0)


# ---------------------------------------------------------------------------
# column.stability · 7.2.1
# ---------------------------------------------------------------------------
def test_column_stability_ratio_exactly_one_is_ok():
    record = row_for("column.stability", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_column_stability_ratio_inside_tolerance_is_ok():
    assert row_for("column.stability", INSIDE).verdict == OK


def test_column_stability_ratio_above_tolerance_is_rejected():
    assert row_for("column.stability", ABOVE).verdict == REJECTED


def test_column_stability_need_adjust_at_ninety_six_percent():
    record = row_for("column.stability", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_column_stability_need_adjust_false_at_ninety_percent():
    assert row_for("column.stability", BELOW).evidence["need_adjust"] is False


def test_column_stability_cites_clause_7_2_1():
    assert row_for("column.stability", 1.0).basis.clause == "7.2.1"


def test_column_stability_evidence_carries_phi_area_and_strength():
    """稳定验算没有「单一设计值键」：φ、A、f 三个量分别入账。"""
    evidence = row_for("column.stability", 1.0).evidence
    assert evidence["phi"] == pytest.approx(0.75)
    assert evidence["A"] == pytest.approx(5000.0)
    assert evidence["f"] == pytest.approx(305.0)


def test_column_stability_without_its_clause_raises():
    payload = payload_for("column.stability", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("7.2.1"))


def test_column_stability_reports_demand_and_capacity():
    evidence = row_for("column.stability", ABOVE).evidence
    assert evidence["demand"] == pytest.approx(1143750.0 * ABOVE)
    assert evidence["capacity"] == pytest.approx(1143750.0)


# ---------------------------------------------------------------------------
# column.slenderness · 7.2.2
# ---------------------------------------------------------------------------
def test_column_slenderness_ratio_exactly_one_is_ok():
    record = row_for("column.slenderness", 1.0)
    assert record.verdict == OK
    assert record.evidence["ratio"] == pytest.approx(1.0)


def test_column_slenderness_ratio_inside_tolerance_is_ok():
    assert row_for("column.slenderness", INSIDE).verdict == OK


def test_column_slenderness_ratio_above_tolerance_is_rejected():
    assert row_for("column.slenderness", ABOVE).verdict == REJECTED


def test_column_slenderness_need_adjust_at_ninety_six_percent():
    record = row_for("column.slenderness", NEAR)
    assert record.verdict == OK
    assert record.evidence["need_adjust"] is True


def test_column_slenderness_need_adjust_false_at_ninety_percent():
    assert row_for("column.slenderness", BELOW).evidence["need_adjust"] is False


def test_column_slenderness_cites_clause_7_2_2():
    assert row_for("column.slenderness", 1.0).basis.clause == "7.2.2"


def test_column_slenderness_binds_allowable_ratio():
    assert row_for("column.slenderness", 1.0).evidence["limit_key"] == "lambda_max"


def test_column_slenderness_without_its_clause_raises():
    payload = payload_for("column.slenderness", 1.0)
    with pytest.raises(ClauseMissing):
        run(payload, basis_without("7.2.2"))


def test_column_slenderness_reports_lambda_and_allowable():
    evidence = row_for("column.slenderness", ABOVE).evidence
    assert evidence["lambda"] == pytest.approx(150.0 * ABOVE)
    assert evidence["limit_value"] == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# 矩阵完整性：9 条验算式一条不漏
# ---------------------------------------------------------------------------
def test_matrix_covers_all_nine_checks():
    assert set(SPEC) == {
        "butt.tension", "butt.shear", "fillet.side", "fillet.front", "bolt.shear",
        "bolt.bearing", "hsb.friction", "column.stability", "column.slenderness"}


def test_matrix_limit_keys_match_organ_data():
    for check, key in LIMIT_KEY.items():
        assert row_for(check, 1.0).evidence["limit_key"] == key


def test_matrix_clause_numbers_match_organ_data():
    for check, number in CLAUSE_OF.items():
        assert row_for(check, 1.0).basis.clause == number