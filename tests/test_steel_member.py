"""器官 ``steel-member`` 的测试（迁自 target-map ③ 行）。

覆盖面：注册与条号锚点 / 5 个模块 × 9 条验算式 × ok·rejected 两态 / ratio 恒为作用÷抗力 /
ratio 容差 1e-3 与 need_adjust 提示 / 输入契约原因码 / 记录形态 / 样例端到端。

不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数）。
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from math import pi

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
ORGAN = importlib.import_module("speccalc.modules.steel-member")
SLUG = ORGAN.SLUG
SAMPLE = os.path.join(ROOT, "samples", "steel-member", "a2-fillet-weld.json")
BASIS_FILE = os.path.join(ROOT, "samples", "basis.json")

CODE = "GB 50017-2017"
CLAUSE_NUMBERS = ("11.2.1", "11.2.2", "11.4.1", "11.4.2", "7.2.1", "7.2.2")
BASIS = Basis(version="steel-20261125",
              clauses=tuple(Clause(code=CODE, clause=num, version="2017", text=num)
                            for num in CLAUSE_NUMBERS))


# ---------------------------------------------------------------------------
# 构造器
# ---------------------------------------------------------------------------
DESIGN = {
    "f_t_w": 175.0, "f_v_w": 100.0, "f_f_w": 160.0, "beta_f": 1.22,
    "f_v_b": 140.0, "f_c_b": 305.0, "k_hsb": 0.9, "mu_hsb": 0.45,
    "P_hsb": 155000.0, "f_y": 305.0, "phi": 0.75, "lambda_max": 150.0,
}


def _dv(**overrides):
    values = {key: {"kind": "standard_value", "status": "verified", "value": value,
                    "evidence": "FIXTURE:kb-1"} for key, value in DESIGN.items()}
    for key, value in overrides.items():
        if isinstance(value, dict):
            values[key] = value
        elif value is None:
            values.pop(key, None)
        else:
            values[key] = {"kind": "standard_value", "status": "verified", "value": value,
                           "evidence": "FIXTURE:kb-1"}
    return values


def _subject(module, params, forces, values=None, case_id="CASE-1"):
    return {"case_id": case_id, "module": module, "params": params, "forces": forces,
            "design_values": values if values is not None else _dv()}


BUTT = {"l_w": 200.0, "t": 10.0}
FILLET_SIDE = {"h_f": 8.0, "l_w": 200.0, "n_welds": 2, "load_direction": "side"}
FILLET_FRONT = {"h_f": 8.0, "l_w": 200.0, "n_welds": 2, "load_direction": "front"}
BOLT = {"d": 20.0, "bolt_count": 4.0, "t_sum": 20.0}
HSB = {"n_f": 2.0, "bolt_count": 4.0}
COLUMN = {"A": 5000.0, "l_0x": 6000.0, "l_0y": 6000.0, "i_x": 80.0, "i_y": 60.0}


def _run(subject, basis=BASIS):
    return tuple(ORGAN.evaluate(subject, basis))


def _row(module, params, forces, check, values=None):
    hits = [record for record in _run(_subject(module, params, forces, values))
            if record.evidence["check"] == check]
    assert len(hits) == 1, [record.item_id for record in hits]
    return hits[0]


# ---------------------------------------------------------------------------
# A. 注册与条号锚点
# ---------------------------------------------------------------------------
def test_organ_registered():
    assert get(SLUG).slug == SLUG
    assert get(SLUG).version == "0.1.0"


def test_input_fields_declared():
    assert get(SLUG).input_fields == ("module", "case_id", "params", "forces", "design_values")


def test_builtin_manifest_sorted_and_contains_migrated_organs():
    assert list(BUILTIN_MODULES) == sorted(BUILTIN_MODULES)
    # 2026-11-25：第 4 个器官 formwork-scaffold 迁入后，清单不再固定为 3 个；
    # 这里只锁「三个已吸收器官仍在册」，新增器官由各自的测试守门。
    for slug in ("excavation-monitor", "pavement-mqi", "steel-member"):
        assert slug in BUILTIN_MODULES


def test_cli_list_shows_three_organs(capsys):
    assert cli.main(["list"]) == EXIT_OK
    out = capsys.readouterr().out
    for slug in BUILTIN_MODULES:
        assert slug in out


def test_data_declares_nine_checks():
    assert len(load_data("steel-member.json")["clauses"]) == 9


def test_data_clause_numbers_are_real_not_register_keys():
    """本器官是三个里唯一有条号可引的：clause 必须是 11.2.1 这类条号，不是系数键。"""
    numbers = {entry["clause"] for entry in load_data("steel-member.json")["clauses"].values()}
    assert numbers <= set(CLAUSE_NUMBERS)
    assert all(number[0].isdigit() for number in numbers)


def test_data_declares_five_modules():
    assert sorted(load_data("steel-member.json")["modules"]) == [
        "bolt_hsb_friction", "bolt_normal", "butt_weld", "column_buckling", "fillet_weld"]


def test_data_ratio_tolerance_is_one_thousandth():
    assert load_data("steel-member.json")["constants"]["ratio_tol"] == 0.001


def test_data_need_adjust_floor_is_ninety_five_percent():
    assert load_data("steel-member.json")["constants"]["need_adjust_floor"] == 0.95


def test_data_fillet_effective_factor_is_point_seven():
    assert load_data("steel-member.json")["constants"]["fillet_effective_factor"] == 0.7


def test_data_design_value_keys_match_module_needs():
    keys = set(load_data("steel-member.json")["design_value_keys"])
    assert keys == set(DESIGN)


def test_data_carries_no_numeric_limits():
    text = json.dumps(load_data("steel-member.json"), ensure_ascii=False)
    assert '"value":' not in text


# ---------------------------------------------------------------------------
# B. 对接焊缝（11.2.1）
# ---------------------------------------------------------------------------
def test_butt_tension_ok():
    assert _row("butt_weld", BUTT, {"N": 200000.0}, "butt.tension").verdict == OK


def test_butt_tension_rejected():
    assert _row("butt_weld", BUTT, {"N": 400000.0}, "butt.tension").verdict == REJECTED


def test_butt_tension_ratio():
    assert _row("butt_weld", BUTT, {"N": 200000.0}, "butt.tension").evidence["ratio"] == pytest.approx(200000 / 350000)


def test_butt_shear_ok():
    assert _row("butt_weld", BUTT, {"V": 100000.0}, "butt.shear").verdict == OK


def test_butt_shear_rejected():
    assert _row("butt_weld", BUTT, {"V": 250000.0}, "butt.shear").verdict == REJECTED


def test_butt_both_forces_emit_two_rows():
    assert len(_run(_subject("butt_weld", BUTT, {"N": 1.0, "V": 1.0}))) == 2


def test_butt_only_tension_emits_one_row():
    assert len(_run(_subject("butt_weld", BUTT, {"N": 1.0}))) == 1


def test_butt_no_force_is_refused():
    with pytest.raises(ValueError, match="没有任何可验算的内力"):
        _run(_subject("butt_weld", BUTT, {}))


def test_butt_basis_clause_is_11_2_1():
    assert _row("butt_weld", BUTT, {"N": 1.0}, "butt.tension").basis.clause == "11.2.1"


def test_butt_capacity_is_area_times_strength():
    evidence = _row("butt_weld", BUTT, {"N": 200000.0}, "butt.tension").evidence
    assert evidence["A_w"] == 2000.0
    assert evidence["capacity"] == pytest.approx(350000.0)
    assert evidence["limit_value"] == 175.0


def test_butt_zero_length_is_refused():
    with pytest.raises(ValueError, match="params.l_w 必须为正"):
        _run(_subject("butt_weld", dict(BUTT, l_w=0.0), {"N": 1.0}))


def test_butt_negative_thickness_is_refused():
    with pytest.raises(ValueError, match="params.t 必须为正"):
        _run(_subject("butt_weld", dict(BUTT, t=-1.0), {"N": 1.0}))


# ---------------------------------------------------------------------------
# C. 角焊缝（11.2.2）
# ---------------------------------------------------------------------------
def test_fillet_side_ok():
    assert _row("fillet_weld", FILLET_SIDE, {"N": 300000.0}, "fillet.side").verdict == OK


def test_fillet_side_rejected():
    assert _row("fillet_weld", FILLET_SIDE, {"N": 400000.0}, "fillet.side").verdict == REJECTED


def test_fillet_side_ratio():
    evidence = _row("fillet_weld", FILLET_SIDE, {"N": 400000.0}, "fillet.side").evidence
    assert evidence["ratio"] == pytest.approx(400000 / 358400)


def test_fillet_effective_thickness_is_half_point_seven_of_h_f():
    assert _row("fillet_weld", FILLET_SIDE, {"N": 1.0}, "fillet.side").evidence["h_e"] == pytest.approx(5.6)


def test_fillet_total_length_counts_welds():
    assert _row("fillet_weld", FILLET_SIDE, {"N": 1.0}, "fillet.side").evidence["l_w_total"] == 400.0


def test_fillet_front_ok():
    assert _row("fillet_weld", FILLET_FRONT, {"N": 400000.0}, "fillet.front").verdict == OK


def test_fillet_front_rejected():
    assert _row("fillet_weld", FILLET_FRONT, {"N": 500000.0}, "fillet.front").verdict == REJECTED


def test_fillet_front_uses_beta_f():
    evidence = _row("fillet_weld", FILLET_FRONT, {"N": 1.0}, "fillet.front").evidence
    assert evidence["beta_f"] == 1.22
    assert evidence["capacity"] == pytest.approx(358400 * 1.22)


def test_fillet_side_does_not_need_beta_f():
    values = _dv(beta_f=None)
    assert _row("fillet_weld", FILLET_SIDE, {"N": 300000.0}, "fillet.side", values).verdict == OK


def test_fillet_basis_clause_is_11_2_2():
    assert _row("fillet_weld", FILLET_SIDE, {"N": 1.0}, "fillet.side").basis.clause == "11.2.2"


def test_fillet_unknown_direction_is_refused():
    with pytest.raises(ValueError, match="load_direction 非法"):
        _run(_subject("fillet_weld", dict(FILLET_SIDE, load_direction="端部"), {"N": 1.0}))


def test_fillet_requires_axial_force():
    with pytest.raises(ValueError, match="forces"):
        _run(_subject("fillet_weld", FILLET_SIDE, {"V": 1.0}))


# ---------------------------------------------------------------------------
# D. 普通螺栓（11.4.1）
# ---------------------------------------------------------------------------
def test_bolt_shear_ok():
    assert _row("bolt_normal", BOLT, {"V": 100000.0}, "bolt.shear").verdict == OK


def test_bolt_shear_rejected():
    assert _row("bolt_normal", BOLT, {"V": 400000.0}, "bolt.shear").verdict == REJECTED


def test_bolt_shear_ratio_uses_per_bolt_force():
    evidence = _row("bolt_normal", BOLT, {"V": 400000.0}, "bolt.shear").evidence
    assert evidence["N_v"] == pytest.approx(100000.0)
    assert evidence["ratio"] == pytest.approx(100000 / (pi * 400 / 4 * 140))


def test_bolt_area_is_pi_d_squared_over_four():
    assert _row("bolt_normal", BOLT, {"V": 1.0}, "bolt.shear").evidence["A_s"] == pytest.approx(pi * 400 / 4)


def test_bolt_bearing_ok():
    assert _row("bolt_normal", BOLT, {"V": 400000.0}, "bolt.bearing").verdict == OK


def test_bolt_bearing_rejected():
    assert _row("bolt_normal", BOLT, {"V": 600000.0}, "bolt.bearing").verdict == REJECTED


def test_bolt_bearing_ratio():
    evidence = _row("bolt_normal", BOLT, {"V": 600000.0}, "bolt.bearing").evidence
    assert evidence["ratio"] == pytest.approx(150000 / (20 * 20 * 305))


def test_bolt_two_rows_always():
    assert len(_run(_subject("bolt_normal", BOLT, {"V": 1.0}))) == 2


def test_bolt_basis_clause_is_11_4_1():
    for record in _run(_subject("bolt_normal", BOLT, {"V": 1.0})):
        assert record.basis.clause == "11.4.1"


def test_bolt_count_zero_is_refused():
    with pytest.raises(ValueError, match="bolt_count 必须为正"):
        _run(_subject("bolt_normal", dict(BOLT, bolt_count=0.0), {"V": 1.0}))


def test_bolt_t_sum_zero_is_refused():
    with pytest.raises(ValueError, match="t_sum 必须为正"):
        _run(_subject("bolt_normal", dict(BOLT, t_sum=0.0), {"V": 1.0}))


# ---------------------------------------------------------------------------
# E. 高强螺栓摩擦型（11.4.2）
# ---------------------------------------------------------------------------
def test_hsb_ok():
    assert _row("bolt_hsb_friction", HSB, {"V": 400000.0}, "hsb.friction").verdict == OK


def test_hsb_rejected():
    assert _row("bolt_hsb_friction", HSB, {"V": 600000.0}, "hsb.friction").verdict == REJECTED


def test_hsb_capacity_formula():
    evidence = _row("bolt_hsb_friction", HSB, {"V": 400000.0}, "hsb.friction").evidence
    assert evidence["capacity"] == pytest.approx(0.9 * 2 * 0.45 * 155000)
    assert evidence["ratio"] == pytest.approx(100000 / 125550)


def test_hsb_uses_n_f_and_count():
    evidence = _row("bolt_hsb_friction", HSB, {"V": 400000.0}, "hsb.friction").evidence
    assert evidence["n_f"] == 2.0
    assert evidence["bolt_count"] == 4.0


def test_hsb_basis_clause_is_11_4_2():
    assert _row("bolt_hsb_friction", HSB, {"V": 1.0}, "hsb.friction").basis.clause == "11.4.2"


def test_hsb_n_f_zero_is_refused():
    with pytest.raises(ValueError, match="n_f 必须为正"):
        _run(_subject("bolt_hsb_friction", dict(HSB, n_f=0.0), {"V": 1.0}))


def test_hsb_missing_preload_is_refused():
    with pytest.raises(ValueError, match="P_hsb"):
        _run(_subject("bolt_hsb_friction", HSB, {"V": 1.0}, _dv(P_hsb=None)))


# ---------------------------------------------------------------------------
# F. 轴压稳定与长细比（7.2.1 / 7.2.2）
# ---------------------------------------------------------------------------
def test_column_stability_ok():
    assert _row("column_buckling", COLUMN, {"N": 500000.0}, "column.stability").verdict == OK


def test_column_stability_rejected():
    assert _row("column_buckling", COLUMN, {"N": 1300000.0}, "column.stability").verdict == REJECTED


def test_column_stability_capacity_uses_phi_and_f():
    evidence = _row("column_buckling", COLUMN, {"N": 500000.0}, "column.stability").evidence
    assert evidence["capacity"] == pytest.approx(0.75 * 5000 * 305)


def test_column_lambda_is_max_of_two_axes():
    assert _row("column_buckling", COLUMN, {"N": 1.0}, "column.stability").evidence["lambda"] == 100.0


def test_column_lambda_x_when_longer():
    params = dict(COLUMN, i_x=40.0)
    assert _row("column_buckling", params, {"N": 1.0}, "column.stability").evidence["lambda"] == 150.0


def test_slenderness_ok():
    assert _row("column_buckling", COLUMN, {"N": 1.0}, "column.slenderness").verdict == OK


def test_slenderness_rejected():
    assert _row("column_buckling", COLUMN, {"N": 1.0}, "column.slenderness", _dv(lambda_max=80.0)).verdict == REJECTED


def test_slenderness_ratio():
    evidence = _row("column_buckling", COLUMN, {"N": 1.0}, "column.slenderness").evidence
    assert evidence["ratio"] == pytest.approx(100 / 150)


def test_slenderness_control_axis_is_y():
    assert "y" in _row("column_buckling", COLUMN, {"N": 1.0}, "column.slenderness").message


def test_column_two_rows_always():
    assert len(_run(_subject("column_buckling", COLUMN, {"N": 1.0}))) == 2


def test_column_stability_basis_clause_is_7_2_1():
    assert _row("column_buckling", COLUMN, {"N": 1.0}, "column.stability").basis.clause == "7.2.1"


def test_column_slenderness_basis_clause_is_7_2_2():
    assert _row("column_buckling", COLUMN, {"N": 1.0}, "column.slenderness").basis.clause == "7.2.2"


def test_column_requires_axial_force():
    with pytest.raises(ValueError, match="forces"):
        _run(_subject("column_buckling", COLUMN, {"V": 1.0}))


def test_column_area_zero_is_refused():
    with pytest.raises(ValueError, match="params.A 必须为正"):
        _run(_subject("column_buckling", dict(COLUMN, A=0.0), {"N": 1.0}))


# ---------------------------------------------------------------------------
# G. ratio 容差与 need_adjust
# ---------------------------------------------------------------------------
def test_ratio_exactly_one_is_ok():
    """N = 350000 正好等于抗力：ratio=1，加 1e-3 容差仍记 ok。"""
    assert _row("butt_weld", BUTT, {"N": 350000.0}, "butt.tension").verdict == OK


def test_ratio_inside_tolerance_is_ok():
    assert _row("butt_weld", BUTT, {"N": 350300.0}, "butt.tension").verdict == OK


def test_ratio_above_tolerance_is_rejected():
    assert _row("butt_weld", BUTT, {"N": 351000.0}, "butt.tension").verdict == REJECTED


def test_need_adjust_flag_above_floor():
    assert _row("butt_weld", BUTT, {"N": 340000.0}, "butt.tension").evidence["need_adjust"] is True


def test_need_adjust_flag_below_floor():
    assert _row("butt_weld", BUTT, {"N": 300000.0}, "butt.tension").evidence["need_adjust"] is False


def test_need_adjust_does_not_change_verdict():
    record = _row("butt_weld", BUTT, {"N": 340000.0}, "butt.tension")
    assert record.verdict == OK and record.evidence["need_adjust"] is True


def test_ratio_is_demand_over_capacity_for_hsb():
    """反向写法（抗力 ≥ 作用）也统一成作用/抗力：HSB 的 ratio 小于 1 才是合格。"""
    assert _row("bolt_hsb_friction", HSB, {"V": 400000.0}, "hsb.friction").evidence["ratio"] < 1.0


# ---------------------------------------------------------------------------
# H. 输入契约原因码
# ---------------------------------------------------------------------------
def _bad(key, **changes):
    block = {"kind": "standard_value", "status": "verified", "value": 1.0, "evidence": "FIXTURE:kb-1"}
    block.update(changes)
    return _dv(**{key: block})


def test_design_value_pending_is_refused():
    with pytest.raises(ValueError, match="source_not_confirmed"):
        _run(_subject("butt_weld", BUTT, {"N": 1.0}, _bad("f_t_w", status="pending")))


def test_design_value_located_is_refused():
    with pytest.raises(ValueError, match="source_not_confirmed"):
        _run(_subject("butt_weld", BUTT, {"N": 1.0}, _bad("f_t_w", status="located")))


def test_design_value_missing_evidence_is_refused():
    with pytest.raises(ValueError, match="evidence_missing"):
        _run(_subject("butt_weld", BUTT, {"N": 1.0}, _bad("f_t_w", evidence="")))


def test_design_value_missing_value_is_refused():
    with pytest.raises(ValueError, match="value_missing"):
        _run(_subject("butt_weld", BUTT, {"N": 1.0}, _bad("f_t_w", value=None)))


def test_design_value_nonnumeric_is_refused():
    with pytest.raises(ValueError, match="数值"):
        _run(_subject("butt_weld", BUTT, {"N": 1.0}, _bad("f_t_w", value="175")))


def test_design_value_block_must_be_object():
    values = _dv()
    values["f_t_w"] = 175.0
    with pytest.raises(ValueError, match="必须是对象"):
        _run(_subject("butt_weld", BUTT, {"N": 1.0}, values))


def test_design_values_must_be_non_empty():
    with pytest.raises(ValueError, match="design_values 必须是非空对象"):
        _run(_subject("butt_weld", BUTT, {"N": 1.0}, {}))


def test_missing_design_value_is_refused():
    with pytest.raises(ValueError, match="design_value_missing"):
        _run(_subject("butt_weld", BUTT, {"N": 1.0}, _dv(f_t_w=None)))


def test_unknown_module_is_refused():
    with pytest.raises(ValueError, match="module_unknown"):
        _run(_subject("no_such_module", {}, {}))


def test_module_listed_in_error_message():
    with pytest.raises(ValueError, match="bolt_normal"):
        _run(_subject("no_such_module", {}, {}))


def test_missing_case_id_is_refused():
    with pytest.raises(ValueError, match="case_id"):
        _run({"module": "butt_weld", "params": BUTT, "forces": {"N": 1.0}, "design_values": _dv()})


def test_missing_params_is_refused():
    with pytest.raises(ValueError, match="params"):
        _run({"case_id": "C", "module": "butt_weld", "forces": {"N": 1.0}, "design_values": _dv()})


def test_forces_must_be_object():
    with pytest.raises(ValueError, match="forces 必须是对象"):
        _run(_subject("butt_weld", BUTT, [1.0]))


def test_force_boolean_is_refused():
    with pytest.raises(ValueError, match="数值"):
        _run(_subject("butt_weld", BUTT, {"N": True}))


def test_force_infinite_is_refused():
    with pytest.raises(ValueError, match="有限数值"):
        _run(_subject("butt_weld", BUTT, {"N": float("inf")}))


def test_subject_must_be_mapping():
    with pytest.raises(ValueError, match="JSON 对象"):
        _run([1, 2, 3])


def test_clause_missing_propagates():
    thin = Basis(version="thin", clauses=(Clause(code=CODE, clause="11.2.1", version="2017", text="x"),))
    with pytest.raises(ClauseMissing):
        _run(_subject("bolt_normal", BOLT, {"V": 1.0}), basis=thin)


def test_cli_clause_missing_is_contract_error(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps(_subject("bolt_normal", BOLT, {"V": 1.0})), encoding="utf-8")
    thin = tmp_path / "basis.json"
    thin.write_text(json.dumps({"version": "thin", "clauses": []}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", str(thin)]) == EXIT_CONTRACT
    assert "ClauseMissing" in capsys.readouterr().err


def test_cli_input_error_is_rc2(tmp_path):
    target = tmp_path / "in.json"
    target.write_text(json.dumps({"module": "butt_weld"}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", BASIS_FILE]) == EXIT_INPUT


# ---------------------------------------------------------------------------
# I. 记录形态
# ---------------------------------------------------------------------------
def test_every_record_has_three_field_basis():
    for record in _run(_subject("bolt_normal", BOLT, {"V": 1.0})):
        assert record.basis.code == CODE
        assert record.basis.version == "2017"
        assert record.basis.clause in CLAUSE_NUMBERS


def test_verdict_only_ok_or_rejected():
    assert {record.verdict for record in _run(_subject("bolt_normal", BOLT, {"V": 400000.0}))} <= {OK, REJECTED}


def test_record_ids_are_check_names():
    assert [record.item_id for record in _run(_subject("bolt_normal", BOLT, {"V": 1.0}))] == [
        "bolt.shear", "bolt.bearing"]


def test_record_carries_module_and_case():
    evidence = _row("bolt_normal", BOLT, {"V": 1.0}, "bolt.shear").evidence
    assert evidence["module"] == "bolt_normal"
    assert evidence["case_id"] == "CASE-1"


def test_record_evidence_has_ratio_and_tolerance():
    evidence = _row("bolt_normal", BOLT, {"V": 1.0}, "bolt.shear").evidence
    assert evidence["ratio_tol"] == 0.001
    assert "verdict_rule" in evidence


def test_message_contains_demand_and_capacity():
    message = _row("butt_weld", BUTT, {"N": 200000.0}, "butt.tension").message
    assert "200000" in message and "350000" in message


def test_json_output_is_deterministic(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps(_subject("bolt_normal", BOLT, {"V": 100000.0})), encoding="utf-8")
    args = ["check", SLUG, "--input", str(target), "--basis", BASIS_FILE, "--json"]
    cli.main(args)
    first = capsys.readouterr().out
    cli.main(args)
    assert capsys.readouterr().out == first
    assert str(tmp_path) not in first


def test_env_does_not_change_result(monkeypatch):
    subject = _subject("bolt_normal", BOLT, {"V": 100000.0})
    before = [record.as_dict() for record in _run(subject)]
    monkeypatch.setenv("SDC_DATA_DIR", "/nonexistent")
    assert [record.as_dict() for record in _run(subject)] == before


# ---------------------------------------------------------------------------
# J. 样例端到端
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sample_records():
    with open(SAMPLE, "r", encoding="utf-8") as handle:
        subject = json.load(handle)
    return _run(subject, Basis.from_json(BASIS_FILE))


def test_sample_is_one_row(sample_records):
    assert len(sample_records) == 1


def test_sample_row_is_fillet_side(sample_records):
    assert sample_records[0].item_id == "fillet.side"


def test_sample_ratio_is_above_one(sample_records):
    assert sample_records[0].evidence["ratio"] == pytest.approx(400000 / 358400)


def test_sample_is_rejected(sample_records):
    assert sample_records[0].verdict == REJECTED


def test_sample_basis_clause_is_11_2_2(sample_records):
    assert sample_records[0].basis.clause == "11.2.2"


def test_sample_cli_rc_is_one(capsys):
    assert cli.main(["check", SLUG, "--input", SAMPLE, "--basis", BASIS_FILE]) == EXIT_BLOCKED
    assert "rejected" in capsys.readouterr().out


def test_sample_cli_json_summary(capsys):
    assert cli.main(["check", SLUG, "--input", SAMPLE, "--basis", BASIS_FILE, "--json"]) == EXIT_BLOCKED
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["blocking"] == 1
    assert payload["organ_version"] == "0.1.0"