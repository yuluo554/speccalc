"""``pavement-mqi`` · 扣分算术 / 分项得分 / 权重（JTG 5210-2018 口径）。

本文件只覆盖「算」的那一层：
- 扣分 = 比率 × 数量 / 几何分母 × 100，两类路面 × 4 破损类型 × 3 程度 × 3 单位；
- 分项得分（行驶质量 / 车辙 / 抗滑）的两点式与钳位、含界两侧；
- PCI 权重校验（和为 1 的容差边沿）与「未提供的分项不得按满分补齐」。

不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数）。
"""

from __future__ import annotations

import pytest

from pavement_mqi_kit import (
    CEMENT_RATIOS,
    RATIOS,
    WEIGHTS,
    coefficients,
    distress,
    get,
    pci_of,
    run,
    seg,
    subject,
)

# ---------------------------------------------------------------------------
# A. 水泥路面：另一套扣分比率（证明取的是 cement_distress 那一格）
# ---------------------------------------------------------------------------
def test_cement_transverse_light_uses_cement_ratio():
    assert pci_of(_cement([distress("横向裂缝", "轻", 100.0)])) == pytest.approx(80.9)


def test_cement_transverse_medium_uses_cement_ratio():
    assert pci_of(_cement([distress("横向裂缝", "中", 100.0)])) == pytest.approx(79.15)


def test_cement_transverse_heavy_uses_cement_ratio():
    assert pci_of(_cement([distress("横向裂缝", "重", 100.0)])) == pytest.approx(77.05)


def test_cement_longitudinal_light_uses_cement_ratio():
    assert pci_of(_cement([distress("纵向裂缝", "轻", 100.0)])) == pytest.approx(82.3)


def test_cement_longitudinal_medium_uses_cement_ratio():
    assert pci_of(_cement([distress("纵向裂缝", "中", 100.0)])) == pytest.approx(81.25)


def test_cement_longitudinal_heavy_uses_cement_ratio():
    assert pci_of(_cement([distress("纵向裂缝", "重", 100.0)])) == pytest.approx(79.15)


def test_cement_rutting_light_uses_cement_ratio():
    assert pci_of(_cement([distress("车辙", "轻", 100.0)])) == pytest.approx(81.6)


def test_cement_rutting_medium_uses_cement_ratio():
    assert pci_of(_cement([distress("车辙", "中", 100.0)])) == pytest.approx(79.85)


def test_cement_rutting_heavy_uses_cement_ratio():
    assert pci_of(_cement([distress("车辙", "重", 100.0)])) == pytest.approx(78.45)


def test_cement_pothole_light_uses_cement_ratio():
    assert pci_of(_cement([distress("坑槽", "轻", 100.0)])) == pytest.approx(79.5)


def test_cement_pothole_medium_uses_cement_ratio():
    assert pci_of(_cement([distress("坑槽", "中", 100.0)])) == pytest.approx(76.0)


def test_cement_pothole_heavy_uses_cement_ratio():
    assert pci_of(_cement([distress("坑槽", "重", 100.0)])) == pytest.approx(72.5)


def test_cement_pci_record_cites_cement_weight_clause():
    records = run(_cement([distress("横向裂缝", "轻", 100.0)]))
    assert get(records, "pci").basis.clause == "pci_weight.cement"


def test_cement_deduction_row_reports_cement_ratio():
    rows = run(_cement([distress("坑槽", "重", 100.0)]))[0].evidence["contributions"]
    assert rows[0]["ratio"] == pytest.approx(CEMENT_RATIOS["坑槽"]["重"])


# ---------------------------------------------------------------------------
# B. 几何分母：破损单位 → 路段字段（数量 5 处 / 200 m²）
# ---------------------------------------------------------------------------
def test_unit_spot_transverse_light_maps_to_panel_count():
    assert _deducted(_asphalt([distress("横向裂缝", "轻", 5.0, "处")])) == pytest.approx(0.4)


def test_unit_spot_transverse_medium_maps_to_panel_count():
    assert _deducted(_asphalt([distress("横向裂缝", "中", 5.0, "处")])) == pytest.approx(0.8)


def test_unit_spot_transverse_heavy_maps_to_panel_count():
    assert _deducted(_asphalt([distress("横向裂缝", "重", 5.0, "处")])) == pytest.approx(1.2)


def test_unit_spot_longitudinal_light_maps_to_panel_count():
    assert _deducted(_asphalt([distress("纵向裂缝", "轻", 5.0, "处")])) == pytest.approx(0.3)


def test_unit_spot_longitudinal_medium_maps_to_panel_count():
    assert _deducted(_asphalt([distress("纵向裂缝", "中", 5.0, "处")])) == pytest.approx(0.6)


def test_unit_spot_longitudinal_heavy_maps_to_panel_count():
    assert _deducted(_asphalt([distress("纵向裂缝", "重", 5.0, "处")])) == pytest.approx(0.9)


def test_unit_spot_rutting_light_maps_to_panel_count():
    assert _deducted(_asphalt([distress("车辙", "轻", 5.0, "处")])) == pytest.approx(0.5)


def test_unit_spot_rutting_medium_maps_to_panel_count():
    assert _deducted(_asphalt([distress("车辙", "中", 5.0, "处")])) == pytest.approx(1.0)


def test_unit_spot_rutting_heavy_maps_to_panel_count():
    assert _deducted(_asphalt([distress("车辙", "重", 5.0, "处")])) == pytest.approx(1.5)


def test_unit_spot_pothole_light_maps_to_panel_count():
    assert _deducted(_asphalt([distress("坑槽", "轻", 5.0, "处")])) == pytest.approx(0.8)


def test_unit_spot_pothole_medium_maps_to_panel_count():
    assert _deducted(_asphalt([distress("坑槽", "中", 5.0, "处")])) == pytest.approx(1.6)


def test_unit_spot_pothole_heavy_maps_to_panel_count():
    assert _deducted(_asphalt([distress("坑槽", "重", 5.0, "处")])) == pytest.approx(2.4)


def test_unit_area_transverse_light_maps_to_length():
    assert _deducted(_asphalt([distress("横向裂缝", "轻", 200.0, "m2")])) == pytest.approx(8.0)


def test_unit_area_transverse_medium_maps_to_length():
    assert _deducted(_asphalt([distress("横向裂缝", "中", 200.0, "m2")])) == pytest.approx(16.0)


def test_unit_area_transverse_heavy_maps_to_length():
    assert _deducted(_asphalt([distress("横向裂缝", "重", 200.0, "m2")])) == pytest.approx(24.0)


def test_unit_area_longitudinal_light_maps_to_length():
    assert _deducted(_asphalt([distress("纵向裂缝", "轻", 200.0, "m2")])) == pytest.approx(6.0)


def test_unit_area_longitudinal_medium_maps_to_length():
    assert _deducted(_asphalt([distress("纵向裂缝", "中", 200.0, "m2")])) == pytest.approx(12.0)


def test_unit_area_longitudinal_heavy_maps_to_length():
    assert _deducted(_asphalt([distress("纵向裂缝", "重", 200.0, "m2")])) == pytest.approx(18.0)


def test_unit_area_rutting_light_maps_to_length():
    assert _deducted(_asphalt([distress("车辙", "轻", 200.0, "m2")])) == pytest.approx(10.0)


def test_unit_area_rutting_medium_maps_to_length():
    assert _deducted(_asphalt([distress("车辙", "中", 200.0, "m2")])) == pytest.approx(20.0)


def test_unit_area_rutting_heavy_maps_to_length():
    assert _deducted(_asphalt([distress("车辙", "重", 200.0, "m2")])) == pytest.approx(30.0)


def test_unit_area_pothole_light_maps_to_length():
    assert _deducted(_asphalt([distress("坑槽", "轻", 200.0, "m2")])) == pytest.approx(16.0)


def test_unit_area_pothole_medium_maps_to_length():
    assert _deducted(_asphalt([distress("坑槽", "中", 200.0, "m2")])) == pytest.approx(32.0)


def test_unit_area_pothole_heavy_maps_to_length():
    assert _deducted(_asphalt([distress("坑槽", "重", 200.0, "m2")])) == pytest.approx(48.0)


def test_unit_spot_row_reports_panel_count_field():
    rows = _rows([distress("坑槽", "轻", 5.0, "处")])
    assert rows[0]["denominator_field"] == "panel_count"
    assert rows[0]["denominator"] == 500


def test_unit_area_row_reports_length_field():
    rows = _rows([distress("坑槽", "轻", 200.0, "m2")])
    assert rows[0]["denominator_field"] == "length_m"
    assert rows[0]["denominator"] == 1000.0


# ---------------------------------------------------------------------------
# C. 扣分边界：0 / 满分母 / 超额钳位 / 逐行舍入
# ---------------------------------------------------------------------------
def test_zero_quantity_deducts_nothing():
    assert _deducted(_asphalt([distress("横向裂缝", "轻", 0.0)])) == 0.0


def test_zero_quantity_keeps_distress_score_full():
    assert pci_of(_asphalt([distress("横向裂缝", "轻", 0.0)])) == pytest.approx(83.0)


def test_quantity_equal_to_denominator_deducts_ratio_times_hundred():
    assert _deducted(_asphalt([distress("横向裂缝", "轻", 1000.0)])) == pytest.approx(40.0)


def test_deduction_exactly_one_hundred_zeroes_distress():
    assert _deducted(_asphalt([distress("横向裂缝", "轻", 2500.0)])) == pytest.approx(100.0)


def test_deduction_above_one_hundred_is_clamped_per_row():
    rows = _rows([distress("横向裂缝", "轻", 3000.0)])
    assert rows[0]["deducted"] == 100.0


def test_clamped_row_zeroes_distress_score():
    records = run(_asphalt([distress("横向裂缝", "轻", 3000.0)]))
    assert get(records, "pci").evidence["component_scores"]["distress"] == 0.0


def test_clamped_row_leaves_only_other_components():
    """distress=0 时 PCI = 0.35×80 + 0.2×75 + 0.1×50 = 48。"""
    assert pci_of(_asphalt([distress("横向裂缝", "轻", 3000.0)])) == pytest.approx(48.0)


def test_two_rows_summing_over_one_hundred_clamp_distress_at_zero():
    rows = [distress("横向裂缝", "轻", 3000.0), distress("横向裂缝", "轻", 250.0)]
    records = run(_asphalt(rows))
    assert get(records, "pci").evidence["deducted_total"] == 110.0
    assert get(records, "pci").evidence["component_scores"]["distress"] == 0.0


def test_row_rounding_keeps_two_decimals():
    """第三位小数不保留：0.4×3.125/1000×100 = 0.12500000000000003 → 0.13。

    承诺的是「两位小数」，不是某种舍入模式——二进制表示决定进位方向，
    所以这里只钉住实际结果，不写「四舍五入」或「银行家舍入」。
    """
    assert _deducted(_asphalt([distress("横向裂缝", "轻", 3.125)])) == 0.13


def test_row_rounding_rounds_small_deduction_up():
    """0.008 → 0.01（两位小数舍入）。"""
    assert _deducted(_asphalt([distress("横向裂缝", "轻", 0.2)])) == 0.01


def test_rows_are_rounded_before_summing():
    """两行各 0.006：逐行舍入成 0.01 + 0.01 = 0.02（先加后舍入只得 0.01）。"""
    rows = [distress("横向裂缝", "轻", 0.15), distress("纵向裂缝", "轻", 0.2)]
    assert _deducted(_asphalt(rows)) == 0.02


def test_tiny_quantity_rounds_to_zero_deduction():
    assert _deducted(_asphalt([distress("横向裂缝", "轻", 0.000001)])) == 0.0


def test_contributions_sorted_by_type_severity_unit():
    rows = [
        distress("横向裂缝", "中", 100.0),
        distress("坑槽", "轻", 5.0, "处"),
        distress("横向裂缝", "轻", 100.0),
    ]
    assert [row["type"] for row in _rows(rows)] == ["坑槽", "横向裂缝", "横向裂缝"]


def test_contributions_carry_quantity_and_unit():
    row = _rows([distress("坑槽", "中", 5.0, "处")])[0]
    assert row["quantity"] == 5.0
    assert row["unit"] == "处"


def test_missing_panel_count_is_refused_when_spot_unit_used():
    segment = seg(distresses=[distress("坑槽", "轻", 1.0, "处")])
    del segment["panel_count"]
    with pytest.raises(ValueError, match="panel_count"):
        run(subject([segment]))


def test_quantity_boolean_is_refused():
    with pytest.raises(ValueError, match="必须是数值"):
        run(_asphalt([distress("横向裂缝", "轻", True)]))


# ---------------------------------------------------------------------------
# D. 分项得分：含界两侧与自定义端点
# ---------------------------------------------------------------------------
def test_ride_quality_just_below_ideal():
    assert _score(seg(rqi=9.99), "ride_quality") == pytest.approx(99.9)


def test_ride_quality_just_above_zero():
    assert _score(seg(rqi=0.01), "ride_quality") == pytest.approx(0.1)


def test_ride_quality_custom_endpoints():
    assert _score(seg(rqi=7.0), "ride_quality", block={"ideal_value": 12.0, "zero_value": 2.0}) == pytest.approx(50.0)


def test_rutting_just_above_ideal():
    assert _score(seg(rut=0.01), "rutting") == pytest.approx(99.95)


def test_rutting_just_below_zero():
    assert _score(seg(rut=19.99), "rutting") == pytest.approx(0.05)


def test_rutting_custom_endpoints():
    assert _score(seg(rut=12.0), "rutting", block={"ideal_mm": 2.0, "zero_mm": 22.0}) == pytest.approx(50.0)


def test_rutting_zero_equal_ideal_is_refused():
    """车辙分母 (zero − ideal) 为 0 时必须判输入不合法，不能冒 ZeroDivisionError。"""
    with pytest.raises(ValueError, match="ideal 与 zero 不能相等"):
        _score(seg(rut=1.0), "rutting", block={"ideal_mm": 5.0, "zero_mm": 5.0})


def test_skid_just_below_ideal():
    assert _score(seg(skid=59.99), "skid_resistance") == pytest.approx(99.98)


def test_skid_just_above_zero():
    assert _score(seg(skid=0.01), "skid_resistance") == pytest.approx(0.02)


def test_skid_custom_endpoints():
    assert _score(seg(skid=50.0), "skid_resistance",
                  block={"ideal_value": 80.0, "zero_value": 20.0}) == pytest.approx(50.0)


def test_ride_quality_missing_ideal_value_is_refused():
    with pytest.raises(ValueError, match="ideal_value"):
        _score(seg(), "ride_quality", block={"zero_value": 0.0})


def test_rutting_missing_ideal_mm_is_refused():
    with pytest.raises(ValueError, match="ideal_mm"):
        _score(seg(), "rutting", block={"zero_mm": 20.0})


def test_rutting_missing_zero_mm_is_refused():
    with pytest.raises(ValueError, match="zero_mm"):
        _score(seg(), "rutting", block={"ideal_mm": 0.0})


def test_skid_missing_zero_value_is_refused():
    with pytest.raises(ValueError, match="zero_value"):
        _score(seg(), "skid_resistance", block={"ideal_value": 60.0})


def test_component_score_is_rounded_to_two_digits():
    assert _score(seg(rqi=3.333), "ride_quality") == pytest.approx(33.33)


# ---------------------------------------------------------------------------
# E. 权重：和为 1 的容差两侧、零权重分项
# ---------------------------------------------------------------------------
def test_weight_sum_inside_tolerance_is_accepted():
    weights = {"distress": 0.3500005, "ride_quality": 0.35, "rutting": 0.2, "skid_resistance": 0.1}
    assert _pci_with_weights(weights) > 0.0


def test_weight_sum_above_tolerance_is_refused():
    weights = {"distress": 0.350002, "ride_quality": 0.35, "rutting": 0.2, "skid_resistance": 0.1}
    with pytest.raises(ValueError, match="权重之和必须为 1"):
        _pci_with_weights(weights)


def test_weight_sum_below_tolerance_is_refused():
    weights = {"distress": 0.349998, "ride_quality": 0.35, "rutting": 0.2, "skid_resistance": 0.1}
    with pytest.raises(ValueError, match="权重之和必须为 1"):
        _pci_with_weights(weights)


def test_weight_value_non_numeric_is_refused():
    weights = {"distress": "0.35", "ride_quality": 0.35, "rutting": 0.2, "skid_resistance": 0.1}
    with pytest.raises(ValueError, match="必须是数值"):
        _pci_with_weights(weights)


def test_weights_block_not_mapping_is_refused():
    weights = [0.35, 0.35, 0.2, 0.1]
    with pytest.raises(ValueError, match="pci_weight.weights 必须是对象"):
        _pci_with_weights(weights)


def test_weights_without_weights_key_is_refused():
    with pytest.raises(ValueError, match="缺少必填字段：weights"):
        run(subject([seg()], coefficients(components={"pci_weight.asphalt": {"w": {}}})))


def test_single_component_weights_yield_that_component_score():
    weights = {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}
    segment = seg(distresses=[distress("横向裂缝", "轻", 100.0)])
    segment["measured"] = {}
    assert _pci_of_segment(segment, weights) == pytest.approx(96.0)


def test_weight_key_order_does_not_change_pci():
    forward = {"distress": 0.35, "ride_quality": 0.35, "rutting": 0.2, "skid_resistance": 0.1}
    backward = {"skid_resistance": 0.1, "rutting": 0.2, "ride_quality": 0.35, "distress": 0.35}
    assert _pci_with_weights(forward) == _pci_with_weights(backward)


def test_three_component_weights_skip_missing_measurement():
    """0.4×100(distress) + 0.4×80(rqi) + 0.2×75(rut) = 40 + 32 + 15 = 87（skid 权重 0 不需实测）。"""
    weights = {"distress": 0.4, "ride_quality": 0.4, "rutting": 0.2, "skid_resistance": 0.0}
    segment = seg()
    segment["measured"] = {"rqi": 8.0, "rut_depth_mm": 5.0}
    assert _pci_of_segment(segment, weights) == pytest.approx(87.0)


# ---------------------------------------------------------------------------
# F. 扣分系数块形状：形状不对是输入不合法（rc 2），不是崩溃
# ---------------------------------------------------------------------------
def test_ratios_not_mapping_is_refused():
    block = {"ratios": [0.4], "denominator": {"m": "length_m"}}
    with pytest.raises(ValueError, match="deduct_ratio.ratios 必须是对象"):
        _pci_with_deduct(block)


def test_denominator_not_mapping_is_refused():
    block = {"ratios": RATIOS, "denominator": {"m"}}
    with pytest.raises(ValueError, match="deduct_ratio.denominator 必须是对象"):
        _pci_with_deduct(block)


def test_ratio_row_not_mapping_is_refused():
    block = {"ratios": {"横向裂缝": 0.4}, "denominator": {"m": "length_m"}}
    with pytest.raises(ValueError, match="必须是对象"):
        _pci_with_deduct(block)


def test_deduction_ratio_non_numeric_is_refused():
    block = {"ratios": {"横向裂缝": {"轻": "0.4"}}, "denominator": {"m": "length_m"}}
    with pytest.raises(ValueError, match="必须是数值"):
        _pci_with_deduct(block)


def test_deduct_block_without_ratios_is_refused():
    block = {"denominator": {"m": "length_m"}}
    with pytest.raises(ValueError, match="缺少必填字段：ratios"):
        _pci_with_deduct(block)


def test_deduct_block_without_denominator_is_refused():
    block = {"ratios": RATIOS}
    with pytest.raises(ValueError, match="缺少必填字段：denominator"):
        _pci_with_deduct(block)


def test_distress_row_missing_severity_is_refused():
    row = {"type": "横向裂缝", "quantity": 1.0, "unit": "m"}
    with pytest.raises(ValueError, match="severity"):
        run(_asphalt([row]))


def test_distress_row_missing_unit_is_refused():
    row = {"type": "横向裂缝", "severity": "轻", "quantity": 1.0}
    with pytest.raises(ValueError, match="unit"):
        run(_asphalt([row]))


def test_distress_row_missing_quantity_is_refused():
    row = {"type": "横向裂缝", "severity": "轻", "unit": "m"}
    with pytest.raises(ValueError, match="quantity"):
        run(_asphalt([row]))


def test_distress_row_missing_type_is_refused():
    row = {"severity": "轻", "quantity": 1.0, "unit": "m"}
    with pytest.raises(ValueError, match="type"):
        run(_asphalt([row]))


# ---------------------------------------------------------------------------
# 内部小工具
# ---------------------------------------------------------------------------
def _asphalt(rows):
    return subject([seg(distresses=rows)])


def _cement(rows):
    return subject([seg(surface="cement", distresses=rows)], coefficients("cement"))


def _rows(rows):
    return run(_asphalt(rows))[0].evidence["contributions"]


def _deducted(payload):
    return run(payload)[0].evidence["deducted_total"]


def _score(segment, name, block=None):
    overrides = {"pci_weight.asphalt": {"weights": WEIGHTS}}
    if block is not None:
        overrides["pci_component.%s" % name] = block
    records = run(subject([segment], coefficients(components=overrides)))
    return get(records, "pci").evidence["component_scores"][name]


def _pci_with_weights(weights):
    return _pci_of_segment(seg(), weights)


def _pci_of_segment(segment, weights):
    records = run(subject([segment], coefficients(weights=weights)))
    return get(records, "pci").evidence["pci"]


def _pci_with_deduct(block):
    records = run(subject([seg(distresses=[distress("横向裂缝", "轻", 100.0)])],
                          coefficients(components={"deduct_ratio.asphalt_distress": block})))
    return get(records, "pci").evidence["pci"]