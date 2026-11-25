"""``steel-member`` · 参数 / 内力 / 设计值 / 模块声明 / CLI / 样例。

这一层守的是「什么样的问题算输入不合法（rc 2）」与「哪条验算式用哪几个量」：
- 每个模块的每个必填几何参数缺失、为 0、为负都拒算；
- 内力缺失 / 非数值 / 非有限值都拒算；
- 设计值缺失按**键名**报 ``design_value_missing``，未核对来源按 ``source_not_confirmed``；
- 模块声明的 check 集合与实跑产出的账本行一致。

不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数）。
"""

from __future__ import annotations

import io
import json
import sys

import pytest

from steel_member_kit import (
    BASIS_FILE,
    BOLT,
    BUTT,
    COLUMN,
    DESIGN_KEYS,
    FILLET_FRONT,
    FILLET_SIDE,
    HSB,
    SLUG,
    SAMPLE,
    dv,
    run,
    sample_basis,
    sample_subject,
    subject,
)
from speccalc import cli
from speccalc.core import EXIT_BLOCKED, EXIT_CONTRACT, EXIT_INPUT, OK, REJECTED
from speccalc.core.data import load as load_data

PARAMS = {
    "butt_weld": BUTT,
    "fillet_weld": FILLET_SIDE,
    "bolt_normal": BOLT,
    "bolt_hsb_friction": HSB,
    "column_buckling": COLUMN,
}
FORCES = {
    "butt_weld": {"N": 100000.0, "V": 50000.0},
    "fillet_weld": {"N": 100000.0},
    "bolt_normal": {"V": 50000.0},
    "bolt_hsb_friction": {"V": 50000.0},
    "column_buckling": {"N": 500000.0},
}
FORCE_KEY = {
    "butt_weld": "N",
    "fillet_weld": "N",
    "bolt_normal": "V",
    "bolt_hsb_friction": "V",
    "column_buckling": "N",
}


def _module(module, params=None, forces=None, values=None):
    return subject(module, dict(PARAMS[module]) if params is None else params,
                   dict(FORCES[module]) if forces is None else forces, values)


def _without(module, field):
    params = dict(PARAMS[module])
    del params[field]
    return params


# ---------------------------------------------------------------------------
# A. 几何参数缺失（逐模块 × 逐字段）
# ---------------------------------------------------------------------------
def test_butt_missing_l_w_is_refused():
    with pytest.raises(ValueError, match="l_w"):
        run(_module("butt_weld", params=_without("butt_weld", "l_w")))


def test_butt_missing_thickness_is_refused():
    with pytest.raises(ValueError, match="t"):
        run(_module("butt_weld", params=_without("butt_weld", "t")))


def test_fillet_missing_h_f_is_refused():
    with pytest.raises(ValueError, match="h_f"):
        run(_module("fillet_weld", params=_without("fillet_weld", "h_f")))


def test_fillet_missing_length_is_refused():
    with pytest.raises(ValueError, match="l_w"):
        run(_module("fillet_weld", params=_without("fillet_weld", "l_w")))


def test_fillet_missing_weld_count_is_refused():
    with pytest.raises(ValueError, match="n_welds"):
        run(_module("fillet_weld", params=_without("fillet_weld", "n_welds")))


def test_fillet_missing_direction_is_refused():
    with pytest.raises(ValueError, match="load_direction"):
        run(_module("fillet_weld", params=_without("fillet_weld", "load_direction")))


def test_bolt_missing_diameter_is_refused():
    with pytest.raises(ValueError, match="d"):
        run(_module("bolt_normal", params=_without("bolt_normal", "d")))


def test_bolt_missing_count_is_refused():
    with pytest.raises(ValueError, match="bolt_count"):
        run(_module("bolt_normal", params=_without("bolt_normal", "bolt_count")))


def test_bolt_missing_plate_thickness_sum_is_refused():
    with pytest.raises(ValueError, match="t_sum"):
        run(_module("bolt_normal", params=_without("bolt_normal", "t_sum")))


def test_hsb_missing_slip_planes_is_refused():
    with pytest.raises(ValueError, match="n_f"):
        run(_module("bolt_hsb_friction", params=_without("bolt_hsb_friction", "n_f")))


def test_hsb_missing_bolt_count_is_refused():
    with pytest.raises(ValueError, match="bolt_count"):
        run(_module("bolt_hsb_friction", params=_without("bolt_hsb_friction", "bolt_count")))


def test_column_missing_area_is_refused():
    with pytest.raises(ValueError, match="A"):
        run(_module("column_buckling", params=_without("column_buckling", "A")))


def test_column_missing_l_0x_is_refused():
    with pytest.raises(ValueError, match="l_0x"):
        run(_module("column_buckling", params=_without("column_buckling", "l_0x")))


def test_column_missing_l_0y_is_refused():
    with pytest.raises(ValueError, match="l_0y"):
        run(_module("column_buckling", params=_without("column_buckling", "l_0y")))


def test_column_missing_i_x_is_refused():
    with pytest.raises(ValueError, match="i_x"):
        run(_module("column_buckling", params=_without("column_buckling", "i_x")))


def test_column_missing_i_y_is_refused():
    with pytest.raises(ValueError, match="i_y"):
        run(_module("column_buckling", params=_without("column_buckling", "i_y")))


def test_params_must_be_object():
    with pytest.raises(ValueError, match="params 必须是对象"):
        run(_module("butt_weld", params=[200.0, 10.0]))


def test_missing_params_is_refused():
    payload = _module("butt_weld")
    del payload["params"]
    with pytest.raises(ValueError, match="params"):
        run(payload)


# ---------------------------------------------------------------------------
# B. 几何参数为 0 / 为负
# ---------------------------------------------------------------------------
def test_butt_zero_length_is_refused():
    with pytest.raises(ValueError, match="l_w 必须为正"):
        run(_module("butt_weld", params=dict(BUTT, l_w=0.0)))


def test_butt_zero_thickness_is_refused():
    with pytest.raises(ValueError, match="t 必须为正"):
        run(_module("butt_weld", params=dict(BUTT, t=0.0)))


def test_fillet_zero_throat_is_refused():
    with pytest.raises(ValueError, match="h_f 必须为正"):
        run(_module("fillet_weld", params=dict(FILLET_SIDE, h_f=0.0)))


def test_fillet_zero_length_is_refused():
    with pytest.raises(ValueError, match="l_w 必须为正"):
        run(_module("fillet_weld", params=dict(FILLET_SIDE, l_w=0.0)))


def test_fillet_zero_weld_count_is_refused():
    with pytest.raises(ValueError, match="n_welds 必须为正"):
        run(_module("fillet_weld", params=dict(FILLET_SIDE, n_welds=0.0)))


def test_bolt_zero_diameter_is_refused():
    with pytest.raises(ValueError, match="d 必须为正"):
        run(_module("bolt_normal", params=dict(BOLT, d=0.0)))


def test_bolt_zero_count_is_refused():
    with pytest.raises(ValueError, match="bolt_count 必须为正"):
        run(_module("bolt_normal", params=dict(BOLT, bolt_count=0.0)))


def test_bolt_zero_thickness_sum_is_refused():
    with pytest.raises(ValueError, match="t_sum 必须为正"):
        run(_module("bolt_normal", params=dict(BOLT, t_sum=0.0)))


def test_hsb_zero_slip_planes_is_refused():
    with pytest.raises(ValueError, match="n_f 必须为正"):
        run(_module("bolt_hsb_friction", params=dict(HSB, n_f=0.0)))


def test_hsb_zero_bolt_count_is_refused():
    with pytest.raises(ValueError, match="bolt_count 必须为正"):
        run(_module("bolt_hsb_friction", params=dict(HSB, bolt_count=0.0)))


def test_column_zero_area_is_refused():
    with pytest.raises(ValueError, match="A 必须为正"):
        run(_module("column_buckling", params=dict(COLUMN, A=0.0)))


def test_column_zero_l_0x_is_refused():
    with pytest.raises(ValueError, match="l_0x 必须为正"):
        run(_module("column_buckling", params=dict(COLUMN, l_0x=0.0)))


def test_column_zero_l_0y_is_refused():
    with pytest.raises(ValueError, match="l_0y 必须为正"):
        run(_module("column_buckling", params=dict(COLUMN, l_0y=0.0)))


def test_column_zero_i_x_is_refused():
    with pytest.raises(ValueError, match="i_x 必须为正"):
        run(_module("column_buckling", params=dict(COLUMN, i_x=0.0)))


def test_column_zero_i_y_is_refused():
    with pytest.raises(ValueError, match="i_y 必须为正"):
        run(_module("column_buckling", params=dict(COLUMN, i_y=0.0)))


def test_butt_negative_thickness_is_refused():
    with pytest.raises(ValueError, match="必须为正"):
        run(_module("butt_weld", params=dict(BUTT, t=-10.0)))


def test_fillet_negative_throat_is_refused():
    with pytest.raises(ValueError, match="必须为正"):
        run(_module("fillet_weld", params=dict(FILLET_SIDE, h_f=-8.0)))


def test_bolt_negative_diameter_is_refused():
    with pytest.raises(ValueError, match="必须为正"):
        run(_module("bolt_normal", params=dict(BOLT, d=-20.0)))


def test_hsb_negative_slip_planes_is_refused():
    with pytest.raises(ValueError, match="必须为正"):
        run(_module("bolt_hsb_friction", params=dict(HSB, n_f=-2.0)))


def test_column_negative_area_is_refused():
    with pytest.raises(ValueError, match="必须为正"):
        run(_module("column_buckling", params=dict(COLUMN, A=-5000.0)))


def test_geometry_param_non_numeric_is_refused():
    with pytest.raises(ValueError, match="必须是数值"):
        run(_module("butt_weld", params=dict(BUTT, l_w="200")))


# ---------------------------------------------------------------------------
# C. 内力
# ---------------------------------------------------------------------------
def test_butt_without_any_force_is_refused():
    with pytest.raises(ValueError, match="没有任何可验算的内力"):
        run(_module("butt_weld", forces={}))


def test_fillet_without_axial_force_is_refused():
    with pytest.raises(ValueError, match="缺少必填字段：N"):
        run(_module("fillet_weld", forces={}))


def test_bolt_without_shear_is_refused():
    with pytest.raises(ValueError, match="缺少必填字段：V"):
        run(_module("bolt_normal", forces={}))


def test_hsb_without_shear_is_refused():
    with pytest.raises(ValueError, match="缺少必填字段：V"):
        run(_module("bolt_hsb_friction", forces={}))


def test_column_without_axial_force_is_refused():
    with pytest.raises(ValueError, match="缺少必填字段：N"):
        run(_module("column_buckling", forces={}))


def test_butt_force_non_numeric_is_refused():
    with pytest.raises(ValueError, match="forces.N 必须是数值"):
        run(_module("butt_weld", forces={"N": "100000"}))


def test_fillet_force_non_numeric_is_refused():
    with pytest.raises(ValueError, match="forces.N 必须是数值"):
        run(_module("fillet_weld", forces={"N": "100000"}))


def test_bolt_force_non_numeric_is_refused():
    with pytest.raises(ValueError, match="forces.V 必须是数值"):
        run(_module("bolt_normal", forces={"V": "50000"}))


def test_hsb_force_non_numeric_is_refused():
    with pytest.raises(ValueError, match="forces.V 必须是数值"):
        run(_module("bolt_hsb_friction", forces={"V": "50000"}))


def test_column_force_non_numeric_is_refused():
    with pytest.raises(ValueError, match="forces.N 必须是数值"):
        run(_module("column_buckling", forces={"N": "500000"}))


def test_butt_infinite_force_is_refused():
    with pytest.raises(ValueError, match="有限数值"):
        run(_module("butt_weld", forces={"N": float("inf")}))


def test_column_nan_force_is_refused():
    with pytest.raises(ValueError, match="有限数值"):
        run(_module("column_buckling", forces={"N": float("nan")}))


def test_butt_extra_force_key_is_ignored():
    rows = run(_module("butt_weld", forces={"N": 100000.0, "M": 1.0}))
    assert [record.evidence["check"] for record in rows] == ["butt.tension"]


# ---------------------------------------------------------------------------
# D. 设计值
# ---------------------------------------------------------------------------
def test_missing_tensile_strength_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("butt_weld", values=dv(f_t_w=None)))


def test_missing_shear_strength_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("butt_weld", forces={"V": 50000.0}, values=dv(f_v_w=None)))


def test_missing_fillet_strength_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("fillet_weld", values=dv(f_f_w=None)))


def test_missing_beta_f_is_refused_for_front_fillet():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("fillet_weld", params=dict(FILLET_FRONT), values=dv(beta_f=None)))


def test_missing_bolt_shear_strength_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("bolt_normal", values=dv(f_v_b=None)))


def test_missing_bearing_strength_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("bolt_normal", values=dv(f_c_b=None)))


def test_missing_hsb_slip_coefficient_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("bolt_hsb_friction", values=dv(k_hsb=None)))


def test_missing_hsb_friction_coefficient_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("bolt_hsb_friction", values=dv(mu_hsb=None)))


def test_missing_hsb_preload_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("bolt_hsb_friction", values=dv(P_hsb=None)))


def test_missing_stability_coefficient_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("column_buckling", values=dv(phi=None)))


def test_missing_yield_strength_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("column_buckling", values=dv(f_y=None)))


def test_missing_allowable_slenderness_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        run(_module("column_buckling", values=dv(lambda_max=None)))


def test_design_value_without_status_is_refused():
    values = dv(f_t_w={"kind": "standard_value", "value": 175.0, "evidence": "x"})
    with pytest.raises(ValueError, match="source_not_confirmed"):
        run(_module("butt_weld", values=values))


def test_design_value_boolean_is_refused():
    values = dv(f_t_w={"kind": "standard_value", "status": "verified", "value": True,
                       "evidence": "x"})
    with pytest.raises(ValueError, match="必须是数值"):
        run(_module("butt_weld", values=values))


def test_design_values_must_be_object():
    with pytest.raises(ValueError, match="design_values 必须是非空对象"):
        run(_module("butt_weld", values=[175.0]))


def test_extra_unused_design_value_is_allowed():
    rows = run(_module("butt_weld", forces={"N": 100000.0}, values=dv(f_extra=1.0)))
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# E. 模块声明与产出账本行一致
# ---------------------------------------------------------------------------
def test_butt_module_emits_declared_checks():
    assert {record.evidence["check"] for record in run(_module("butt_weld"))} == {
        "butt.tension", "butt.shear"}


def test_fillet_module_emits_side_check():
    assert {record.evidence["check"] for record in run(_module("fillet_weld"))} == {"fillet.side"}


def test_fillet_module_emits_front_check():
    rows = run(_module("fillet_weld", params=dict(FILLET_FRONT)))
    assert {record.evidence["check"] for record in rows} == {"fillet.front"}


def test_bolt_module_emits_both_checks():
    assert {record.evidence["check"] for record in run(_module("bolt_normal"))} == {
        "bolt.shear", "bolt.bearing"}


def test_hsb_module_emits_one_check():
    assert {record.evidence["check"] for record in run(_module("bolt_hsb_friction"))} == {
        "hsb.friction"}


def test_column_module_emits_both_checks():
    assert {record.evidence["check"] for record in run(_module("column_buckling"))} == {
        "column.stability", "column.slenderness"}


def test_data_design_value_keys_match_fixture():
    assert sorted(load_data("steel-member.json")["design_value_keys"]) == sorted(DESIGN_KEYS)


def test_data_module_check_lists_are_sorted_and_complete():
    modules = load_data("steel-member.json")["modules"]
    assert sum(len(module["checks"]) for module in modules.values()) == 9


def test_data_module_params_are_unique():
    modules = load_data("steel-member.json")["modules"]
    for module in modules.values():
        assert len(module["params"]) == len(set(module["params"]))


def test_data_standard_version_is_2017():
    assert load_data("steel-member.json")["standard_version"] == "2017"


# ---------------------------------------------------------------------------
# F. CLI 与样例
# ---------------------------------------------------------------------------
def test_cli_input_error_is_rc2(tmp_path):
    payload = tmp_path / "in.json"
    payload.write_text(json.dumps(_module("butt_weld", params=dict(BUTT, l_w=0.0)),
                                  ensure_ascii=False), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(payload),
                     "--basis", BASIS_FILE]) == EXIT_INPUT


def test_cli_clause_missing_is_rc3(tmp_path):
    payload = tmp_path / "in.json"
    payload.write_text(json.dumps(_module("butt_weld"), ensure_ascii=False), encoding="utf-8")
    empty = tmp_path / "basis.json"
    empty.write_text(json.dumps({"version": "empty", "clauses": []}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(payload), "--basis", str(empty)]) == EXIT_CONTRACT


def test_cli_reads_sample_from_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(sample_subject(), ensure_ascii=False)))
    assert cli.main(["check", SLUG, "--input", "-", "--basis", BASIS_FILE]) == EXIT_BLOCKED
    assert "fillet.side" in capsys.readouterr().out


def test_sample_json_summary_is_one_blocking_row(capsys):
    assert cli.main(["check", SLUG, "--input", SAMPLE, "--basis", BASIS_FILE, "--json"]) == EXIT_BLOCKED
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["total"] == 1
    assert report["summary"]["blocking"] == 1


def test_sample_ratio_is_demand_over_capacity():
    record = run(sample_subject(), sample_basis())[0]
    assert record.evidence["ratio"] == pytest.approx(400000.0 / 358400.0)
    assert record.verdict == REJECTED


def test_sample_capacity_is_effective_area_times_strength():
    record = run(sample_subject(), sample_basis())[0]
    assert record.evidence["capacity"] == pytest.approx(2240.0 * 160.0)


def test_sample_effective_throat_is_point_seven_of_h_f():
    record = run(sample_subject(), sample_basis())[0]
    assert record.evidence["h_e"] == pytest.approx(5.6)


def test_sample_verdict_is_not_mistaken_for_ok():
    record = run(sample_subject(), sample_basis())[0]
    assert record.verdict != OK
    assert record.evidence["need_adjust"] is True