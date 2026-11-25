"""器官 ``formwork-scaffold`` 的验算与数据测试（迁自 target-map ③ 行）。

覆盖面：注册与数据形状 / 四张查表 / 参数卡拒收 / M-1~M-6 算式与扫描 /
13 例算例真值 / 计算书记录形态。**不使用 parametrize**（一项一个 ``def test_``，
让「测试数」与「函数数」在台账上可机械对齐）。
"""

from __future__ import annotations

import copy
import importlib
import json
import math
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
    EXIT_OK,
    OK,
    REJECTED,
    Report,
    get,
)
from speccalc.core.data import load as load_data  # noqa: E402
from speccalc.modules import BUILTIN_MODULES, load_builtin  # noqa: E402

load_builtin()
ORGAN = importlib.import_module("speccalc.modules.formwork-scaffold")
SLUG = ORGAN.SLUG
VERSION = ORGAN.VERSION
PACK = ORGAN.PACK
DATA = load_data("formwork-scaffold.json")
EXAMPLES = os.path.join(ROOT, "samples", "formwork-scaffold", "examples")


def _basis() -> Basis:
    seen, clauses = set(), []
    for entry in DATA["clauses"].values():
        key = (entry["code"], entry["clause"])
        if key in seen:
            continue
        seen.add(key)
        clauses.append(Clause(code=entry["code"], clause=entry["clause"],
                              version=entry["version"], text=entry["topic"]))
    return Basis(version="formwork-scaffold-test-20261125", clauses=tuple(clauses))


BASIS = _basis()


# ---------------------------------------------------------------------------
# 构造器
# ---------------------------------------------------------------------------
BASE_M1 = {
    "category": "coupler_steel_pipe_scaffold", "rows": "double",
    "build_height_m": 12.0, "step_m": 1.8, "long_spacing_m": 1.5,
    "cross_spacing_m": 1.05, "wall_tie": "two_step_three_span",
    "pipe_spec": "48.3x3.6", "steel_grade": "Q235A", "wind": "不组合",
    "loads": {"gk_struct_kN_per_m": 0.1295, "board_kN_per_m2": 0.3,
              "board_layers": 2, "rail_kN_per_m": 0.16,
              "safety_net_kN_per_m2": 0.01, "live_kN_per_m2": 2.0},
}

BASE_M3 = {
    "category": "coupler_steel_pipe_scaffold", "rows": "double", "member": "cross",
    "step_m": 1.8, "long_spacing_m": 1.5, "cross_spacing_m": 1.05,
    "pipe_spec": "48.3x3.6",
    "loads": {"board_kN_per_m2": 0.3, "live_kN_per_m2": 2.0},
}

BASE_M4 = {
    "category": "coupler_steel_pipe_scaffold", "rows": "double",
    "build_height_m": 12.0, "step_m": 1.8, "long_spacing_m": 1.5,
    "wall_tie": "two_step_three_span", "tie_type": "steel_pipe_coupler",
    "tie_length_m": 1.35, "pipe_spec": "48.3x3.6",
    "wind": {"wk_kN_per_m2": 0.10},
}

BASE_M5 = {
    "category": "coupler_steel_pipe_scaffold", "pipe_spec": "48.3x3.6",
    "foundation": {"type": "回填土", "fgk_kPa": 180.0, "reduction": 0.4,
                   "pad_m": [0.4, 0.2], "nk_kN": 4.2615},
}

BASE_M6 = {
    "category": "formwork_support", "slab_thickness_m": 0.12, "story_height_m": 3.9,
    "step_m": 1.5, "pole_spacing_m": [1.0, 1.0], "pipe_spec": "48.3x3.6",
    "wind": "不组合",
    "loads": {"g1k_kN_per_m2": 0.75, "concrete_kN_per_m3": 24.0,
              "rebar_kN_per_m3_slab": 1.1, "q1k_kN_per_m2": 1.0},
}

M2_WIND = {"w0_kN_per_m2": 0.4, "mu_z": 1.0, "scaffold_state": "enclosed_net",
           "shape_phi": 0.8, "back_wall": "全封闭墙"}


def _run(module: str, card) -> dict:
    return ORGAN.run_calc(module, card, PACK)


def _check(result: dict, item: str) -> dict:
    hits = [entry for entry in result["checks"] if entry["item"] == item]
    assert len(hits) == 1, [entry["item"] for entry in result["checks"]]
    return hits[0]


def _ratio(result: dict, item: str = "lizhigan_stability") -> float:
    return _check(result, item)["ratio"]


def _calc_subject(card, module: str = "auto", case_id: str = "CASE-1") -> dict:
    return {"case_id": case_id, "mode": "calc",
            "calc": {"module": module, "card": card}}


def _records(subject, basis=None) -> tuple:
    return tuple(ORGAN.evaluate(subject, basis if basis is not None else BASIS))


def _examples() -> list:
    paths = sorted(os.path.join(EXAMPLES, name)
                   for name in os.listdir(EXAMPLES) if name.endswith(".json"))
    return [json.load(open(path, encoding="utf-8")) for path in paths]


def _assert_example(example_id: str) -> None:
    example = next(item for item in _examples() if item["example_id"] == example_id)
    card = example["input_card"]
    module = ORGAN.detect_module(card)
    assert module == example["module"], (example_id, module, example["module"])
    result = _run(module, card)
    assert result["status"] == "ok"
    for expected in example["expect"]["checks"]:
        got = _check(result, expected["item"])
        assert abs(got["ratio"] - expected["ratio"]) <= expected["tolerance"], (
            example_id, expected["item"], got["ratio"], expected["ratio"])
        assert got["verdict"] == expected["verdict"], (example_id, expected["item"])
    for key, value in (example["expect"].get("intermediate") or {}).items():
        assert key in result["detail"], (example_id, key)
        if isinstance(value, (int, float)):
            assert abs(result["detail"][key] - value) <= 0.02, (
                example_id, key, result["detail"][key], value)


# ---------------------------------------------------------------------------
# A. 注册与数据形状
# ---------------------------------------------------------------------------
def test_organ_registered():
    assert get(SLUG).slug == SLUG
    assert get(SLUG).version == VERSION


def test_input_fields_declared():
    assert get(SLUG).input_fields == ("mode", "case_id")


def test_summary_mentions_three_duties():
    summary = get(SLUG).summary
    assert "验算" in summary and "危大分级" in summary and "核查" in summary


def test_builtin_manifest_sorted():
    assert list(BUILTIN_MODULES) == sorted(BUILTIN_MODULES)


def test_builtin_manifest_contains_organ():
    assert SLUG in BUILTIN_MODULES


def test_cli_list_shows_organ(capsys):
    assert cli.main(["list"]) == EXIT_OK
    out = capsys.readouterr().out
    assert SLUG in out
    assert "脚手架" in out


def test_data_schema_and_organ_name():
    assert DATA["schema"] == "speccalc-organ-data/1"
    assert DATA["organ"] == SLUG
    assert DATA["version"] == VERSION


def test_data_declares_six_modules():
    assert sorted(DATA["modules"]) == ["M-1", "M-2", "M-3", "M-4", "M-5", "M-6"]


def test_data_declares_forty_one_clause_keys():
    assert len(DATA["clauses"]) == 41


def test_data_clause_entries_are_three_located():
    for key, entry in DATA["clauses"].items():
        assert entry["code"], key
        assert entry["clause"], key
        assert entry["version"], key
        assert entry["topic"], key


def test_data_thresholds_all_verified():
    assert DATA["thresholds"], "阈值表不得为空"
    for threshold_id, entry in DATA["thresholds"].items():
        assert entry["status"] == "已核对", threshold_id


def test_data_thresholds_have_clause_refs():
    for threshold_id, entry in DATA["thresholds"].items():
        assert entry.get("clause_ref"), threshold_id


def test_data_panorama_has_nine_items():
    assert len(DATA["grading"]["items"]) == 9


def test_data_checks_table_has_twelve_rules():
    assert len(DATA["checks"]["rules"]) == 12


def test_data_consistency_covers_six_params():
    assert sorted(DATA["consistency"]["tolerances"]) == [
        "build_height", "cross_spacing", "long_spacing", "step",
        "wall_tie_h", "wall_tie_v"]


def test_data_phi_table_has_251_entries():
    rows = DATA["tables"]["phi"]["rows"]
    assert sum(len(values) for values in rows.values()) == 251


def test_data_modules_checks_reference_known_clauses():
    for module_id, entry in DATA["modules"].items():
        assert entry["name"], module_id
        for clause_key in entry["checks"].values():
            assert clause_key in DATA["clauses"], (module_id, clause_key)


def test_data_every_grading_level_has_clause_key():
    for item in DATA["grading"]["items"]:
        for level in ("none", "weida", "chaoguimo"):
            assert item["levels"][level]["clause"] in DATA["clauses"], item["item_id"]


def test_data_every_rule_has_basis_key():
    for rule in DATA["checks"]["rules"]:
        assert rule["basis"] in DATA["clauses"], rule["rule_id"]


# ---------------------------------------------------------------------------
# B. 查表
# ---------------------------------------------------------------------------
def test_phi_table_complete():
    assert len(ORGAN._phi_table(PACK.tables)) == 251


def test_phi_table_monotonic_non_increasing():
    table = ORGAN._phi_table(PACK.tables)
    for lam in range(250):
        assert table[lam] >= table[lam + 1], lam


def test_phi_anchors():
    assert ORGAN.phi_of(PACK.tables, 80) == 0.722
    assert ORGAN.phi_of(PACK.tables, 100) == 0.588
    assert ORGAN.phi_of(PACK.tables, 150) == 0.308
    assert ORGAN.phi_of(PACK.tables, 200) == 0.180
    assert ORGAN.phi_of(PACK.tables, 250) == 0.117


def test_phi_ceil_lookup_convention():
    assert ORGAN.phi_of(PACK.tables, 196.132) == 0.186
    assert ORGAN.phi_of(PACK.tables, 84.9) == 0.692


def test_phi_over_250_formula():
    assert abs(ORGAN.phi_of(PACK.tables, 251.0) - 7320.0 / 251.0 ** 2) < 1e-15
    assert abs(ORGAN.phi_of(PACK.tables, 300.0) - 7320.0 / 300.0 ** 2) < 1e-15


def test_phi_rejects_non_positive():
    for lam in (0, -1.0):
        with pytest.raises(ValueError):
            ORGAN.phi_of(PACK.tables, lam)


def test_gk_anchors_match_ledger():
    anchors = DATA["thresholds"]["T-JGJ130-gk-table"]["value"]["锚点_双排"]
    for key, expected in anchors.items():
        h_text, la_text = key.replace("h=", "").replace("la=", "").split(",")
        got = ORGAN.gk_of(PACK.tables, float(h_text), float(la_text), "double")
        assert abs(got - expected) < 1e-9, (key, got, expected)


def test_gk_interpolates_inside_domain():
    value = ORGAN.gk_of(PACK.tables, 1.65, 1.65, "double")
    assert 0.11 < value < 0.16


def test_gk_rejects_out_of_domain():
    for h, la in ((1.0, 1.5), (2.5, 1.5), (1.8, 1.0), (1.8, 2.5)):
        with pytest.raises(ValueError):
            ORGAN.gk_of(PACK.tables, h, la, "double")


def test_gk_rejects_bad_rows():
    with pytest.raises(ValueError):
        ORGAN.gk_of(PACK.tables, 1.8, 1.5, "triple")


def test_mu_all_eight_entries():
    assert ORGAN.mu_of(PACK.tables, "double", "two_step_three_span", 1.05) == 1.50
    assert ORGAN.mu_of(PACK.tables, "double", "two_step_three_span", 1.30) == 1.55
    assert ORGAN.mu_of(PACK.tables, "double", "two_step_three_span", 1.55) == 1.60
    assert ORGAN.mu_of(PACK.tables, "double", "three_step_three_span", 1.05) == 1.70
    assert ORGAN.mu_of(PACK.tables, "double", "three_step_three_span", 1.30) == 1.75
    assert ORGAN.mu_of(PACK.tables, "double", "three_step_three_span", 1.55) == 1.80
    assert ORGAN.mu_of(PACK.tables, "single", "two_step_three_span", 1.2) == 1.80
    assert ORGAN.mu_of(PACK.tables, "single", "three_step_three_span", 1.2) == 2.00


def test_mu_single_rejects_cross_spacing_over_1_5():
    with pytest.raises(ValueError):
        ORGAN.mu_of(PACK.tables, "single", "two_step_three_span", 1.6)


def test_mu_double_requires_exact_table_value():
    with pytest.raises(ValueError):
        ORGAN.mu_of(PACK.tables, "double", "two_step_three_span", 1.10)


def test_wind_phi_a05_anchor():
    assert ORGAN.wind_phi_a05(PACK.tables, 1.8, 1.5) == 0.09


def test_wind_phi_a05_rejects_off_table():
    with pytest.raises(ValueError):
        ORGAN.wind_phi_a05(PACK.tables, 1.7, 1.5)
    with pytest.raises(ValueError):
        ORGAN.wind_phi_a05(PACK.tables, 1.8, 1.4)


def test_wind_phi_a05_rejects_bad_state_value():
    with pytest.raises(ValueError):
        ORGAN.wind_phi_a05(PACK.tables, 0.5, 1.5)


# ---------------------------------------------------------------------------
# C. M-1 参数卡拒收（旧仓 M2 DoD ④）
# ---------------------------------------------------------------------------
def _reject_m1(mutate) -> None:
    card = copy.deepcopy(BASE_M1)
    mutate(card)
    with pytest.raises(ValueError):
        _run("M-1", card)


def test_m1_rejects_zero_step():
    _reject_m1(lambda card: card.update(step_m=0))


def test_m1_rejects_negative_step():
    _reject_m1(lambda card: card.update(step_m=-1.8))


def test_m1_rejects_zero_long_spacing():
    _reject_m1(lambda card: card.update(long_spacing_m=0))


def test_m1_rejects_negative_cross_spacing():
    _reject_m1(lambda card: card.update(cross_spacing_m=-1.05))


def test_m1_rejects_zero_build_height():
    _reject_m1(lambda card: card.update(build_height_m=0))


def test_m1_rejects_negative_live_load():
    _reject_m1(lambda card: card["loads"].update(live_kN_per_m2=-2.0))


def test_m1_rejects_negative_board_load():
    _reject_m1(lambda card: card["loads"].update(board_kN_per_m2=-0.3))


def test_m1_rejects_negative_board_layers():
    _reject_m1(lambda card: card["loads"].update(board_layers=-1))


def test_m1_rejects_fractional_board_layers():
    _reject_m1(lambda card: card["loads"].update(board_layers=1.5))


def test_m1_rejects_zero_gk():
    _reject_m1(lambda card: card["loads"].update(gk_struct_kN_per_m=0))


def test_m1_rejects_bad_wall_tie_enum():
    _reject_m1(lambda card: card.update(wall_tie="four_step_four_span"))


def test_m1_rejects_unsupported_pipe_spec():
    _reject_m1(lambda card: card.update(pipe_spec="48.3x2.0"))


def test_m1_rejects_bad_rows_enum():
    _reject_m1(lambda card: card.update(rows="triple"))


def test_m1_rejects_missing_build_height():
    _reject_m1(lambda card: card.pop("build_height_m"))


def test_m1_rejects_missing_wall_tie():
    _reject_m1(lambda card: card.pop("wall_tie"))


def test_m1_rejects_missing_loads():
    _reject_m1(lambda card: card.pop("loads"))


def test_m1_rejects_missing_live_load():
    _reject_m1(lambda card: card["loads"].pop("live_kN_per_m2"))


def test_m1_rejects_non_finite_number():
    _reject_m1(lambda card: card.update(step_m=float("nan")))


def test_m1_rejects_string_number():
    _reject_m1(lambda card: card.update(step_m="1.8"))


def test_m1_rejects_wind_object():
    _reject_m1(lambda card: card.update(wind={"w0_kN_per_m2": 0.4}))


def test_m6_rejects_wrong_category():
    card = copy.deepcopy(BASE_M6)
    card["category"] = "coupler_steel_pipe_scaffold"
    with pytest.raises(ValueError):
        _run("M-6", card)


def test_m6_rejects_zero_pole_spacing():
    card = copy.deepcopy(BASE_M6)
    card["pole_spacing_m"] = [0, 1.0]
    with pytest.raises(ValueError):
        _run("M-6", card)


def test_m6_rejects_zero_slab_thickness():
    card = copy.deepcopy(BASE_M6)
    card["slab_thickness_m"] = 0
    with pytest.raises(ValueError):
        _run("M-6", card)


def test_m6_rejects_zero_concrete_weight():
    card = copy.deepcopy(BASE_M6)
    card["loads"]["concrete_kN_per_m3"] = 0
    with pytest.raises(ValueError):
        _run("M-6", card)


def test_m6_rejects_missing_step():
    card = copy.deepcopy(BASE_M6)
    card.pop("step_m")
    with pytest.raises(ValueError):
        _run("M-6", card)


def test_m5_rejects_without_nk_or_geometry():
    card = {
        "category": "coupler_steel_pipe_scaffold", "pipe_spec": "48.3x3.6",
        "foundation": {"type": "回填土", "fgk_kPa": 180.0, "reduction": 0.4,
                       "pad_m": [0.4, 0.2]},
    }
    with pytest.raises(ValueError):
        _run("M-5", card)


def test_m5_rejects_missing_reduction():
    card = copy.deepcopy(BASE_M5)
    card["foundation"].pop("reduction")
    with pytest.raises(ValueError):
        _run("M-5", card)


# ---------------------------------------------------------------------------
# D. M-1 立杆稳定性
# ---------------------------------------------------------------------------
def test_m1_example_verdict_and_ratio():
    result = _run("M-1", copy.deepcopy(BASE_M1))
    assert _check(result, "lizhigan_stability")["verdict"] == "pass"
    assert _ratio(result) == pytest.approx(0.2813756557812933, rel=1e-9)


def test_m1_example_intermediate_values():
    detail = _run("M-1", copy.deepcopy(BASE_M1))["detail"]
    assert detail["N_design_kN"] == pytest.approx(5.4288)
    assert detail["lambda"] == pytest.approx(196.132, rel=1e-3)
    assert detail["phi"] == 0.186
    assert detail["sigma_N_per_mm2"] == pytest.approx(57.682, rel=1e-3)


def test_m1_clause_refs_are_real():
    check = _check(_run("M-1", copy.deepcopy(BASE_M1)), "lizhigan_stability")
    assert "JGJ130-5.2.6" in check["clause_refs"]
    assert "JGJ130-5.2.8" in check["clause_refs"]


def test_m1_gk_table_lookup_equivalence():
    base = _run("M-1", copy.deepcopy(BASE_M1))
    card = copy.deepcopy(BASE_M1)
    del card["loads"]["gk_struct_kN_per_m"]
    via_table = _run("M-1", card)
    assert via_table["detail"]["gk_kN_per_m"] == pytest.approx(0.1295)
    assert _ratio(via_table) == pytest.approx(_ratio(base))


def test_m1_build_height_monotonic():
    ratios = []
    for height in (6.0, 9.0, 12.0, 15.0, 18.0, 21.0, 24.0):
        card = copy.deepcopy(BASE_M1)
        card["build_height_m"] = height
        ratios.append(_ratio(_run("M-1", card)))
    assert ratios == sorted(ratios)
    assert len(set(ratios)) == len(ratios)


def test_m1_live_load_monotonic():
    card = copy.deepcopy(BASE_M1)
    ratios = []
    for live in (2.0, 2.5, 3.0, 3.5):
        card["loads"]["live_kN_per_m2"] = live
        ratios.append(_ratio(_run("M-1", card)))
    assert ratios == sorted(ratios)


def test_m1_step_monotonic():
    ratios = []
    for step in (1.2, 1.35, 1.5, 1.8, 2.0):
        card = copy.deepcopy(BASE_M1)
        card["step_m"] = step
        ratios.append(_ratio(_run("M-1", card)))
    assert ratios == sorted(ratios)


def test_m1_cross_spacing_monotonic():
    ratios = []
    for lb in (1.05, 1.30, 1.55):
        card = copy.deepcopy(BASE_M1)
        card["cross_spacing_m"] = lb
        card["wall_tie"] = "three_step_three_span"
        ratios.append(_ratio(_run("M-1", card)))
    assert ratios == sorted(ratios)


def test_m1_board_layers_monotonic():
    card = copy.deepcopy(BASE_M1)
    ratios = []
    for layers in (0, 1, 2, 3, 4):
        card["loads"]["board_layers"] = layers
        ratios.append(_ratio(_run("M-1", card)))
    assert ratios == sorted(ratios)


def test_m1_overload_fails():
    card = copy.deepcopy(BASE_M1)
    card["loads"]["live_kN_per_m2"] = 40.0
    result = _run("M-1", card)
    assert _check(result, "lizhigan_stability")["verdict"] == "fail"
    assert _ratio(result) > 1.0


# ---------------------------------------------------------------------------
# E. M-2 组合风
# ---------------------------------------------------------------------------
def _m2_card(**wind_overrides) -> dict:
    card = copy.deepcopy(BASE_M1)
    wind = dict(M2_WIND)
    wind.update(wind_overrides)
    card["wind"] = wind
    return card


def test_m2_pass_with_declared_shape_phi():
    result = _run("M-2", _m2_card())
    assert _check(result, "lizhigan_stability")["verdict"] == "pass"
    assert result["detail"]["Mw_kNm"] > 0


def test_m2_open_state_uses_a05_table():
    card = _m2_card()
    card["wind"] = {"w0_kN_per_m2": 0.4, "mu_z": 1.0, "scaffold_state": "open"}
    result = _run("M-2", card)
    assert result["detail"]["wk_kN_per_m2"] == pytest.approx(0.4 * 1.0 * 1.3 * 0.09)


def test_m2_low_shape_phi_warns():
    result = _run("M-2", _m2_card(shape_phi=0.5))
    assert any("0.8" in warning for warning in result["warnings"])


def test_m2_wind_pressure_monotonic():
    card = _m2_card()
    ratios = []
    for w0 in (0.2, 0.3, 0.4, 0.5):
        card["wind"]["w0_kN_per_m2"] = w0
        ratios.append(_ratio(_run("M-2", card)))
    assert ratios == sorted(ratios)


def test_m2_missing_shape_phi_rejected():
    card = _m2_card()
    card["wind"].pop("shape_phi")
    with pytest.raises(ValueError):
        _run("M-2", card)


def test_m2_wk_direct_input_short_circuits():
    result = _run("M-2", _m2_card(wk_kN_per_m2=0.32))
    assert result["detail"]["wk_kN_per_m2"] == 0.32


def test_m2_unsupported_back_wall_rejected():
    card = _m2_card(back_wall="空旷无墙")
    with pytest.raises(ValueError):
        _run("M-2", card)


def test_m2_mw_formula_checked():
    result = _run("M-2", _m2_card())
    detail = result["detail"]
    assert detail["Mwk_kNm"] == pytest.approx(0.32 * 1.5 * 1.8 ** 2 / 10.0)
    assert detail["Mw_kNm"] == pytest.approx(0.9 * 1.4 * detail["Mwk_kNm"])


# ---------------------------------------------------------------------------
# F. M-3 水平杆
# ---------------------------------------------------------------------------
def test_m3_cross_emits_three_checks():
    result = _run("M-3", copy.deepcopy(BASE_M3))
    assert [entry["item"] for entry in result["checks"]] == [
        "bending_strength", "deflection", "antislip"]


def test_m3_long_emits_two_checks():
    card = copy.deepcopy(BASE_M3)
    card["member"] = "long"
    result = _run("M-3", card)
    assert [entry["item"] for entry in result["checks"]] == [
        "bending_strength", "antislip"]


def test_m3_cross_bending_formula():
    result = _run("M-3", copy.deepcopy(BASE_M3))
    qd = 1.2 * 0.3 * 1.5 + 1.4 * 2.0 * 1.5
    assert result["detail"]["M_design_kNm"] == pytest.approx(qd * 1.05 ** 2 / 8.0)


def test_m3_cross_deflection_limit_is_seven_mm():
    result = _run("M-3", copy.deepcopy(BASE_M3))
    assert result["detail"]["v_allow_mm"] == pytest.approx(7.0)
    assert result["detail"]["v_mm"] < 7.0


def test_m3_long_moment_uses_point_load():
    card = copy.deepcopy(BASE_M3)
    card["member"] = "long"
    result = _run("M-3", card)
    p_design = (1.2 * 0.3 * 1.5 + 1.4 * 2.0 * 1.5) * 1.05 / 2.0
    assert result["detail"]["P_design_kN"] == pytest.approx(p_design)
    assert result["detail"]["M_design_kNm"] == pytest.approx(0.175 * p_design * 1.5)


def test_m3_antislip_ratio():
    result = _run("M-3", copy.deepcopy(BASE_M3))
    assert result["detail"]["R_kN"] == pytest.approx(
        (1.2 * 0.3 * 1.5 + 1.4 * 2.0 * 1.5) * 1.05 / 2.0)
    assert result["detail"]["Rc_kN"] == 8.0


def test_m3_overload_fails():
    card = copy.deepcopy(BASE_M3)
    card["loads"]["live_kN_per_m2"] = 20.0
    result = _run("M-3", card)
    assert _check(result, "bending_strength")["verdict"] == "fail"


def test_m3_bad_member_rejected():
    card = copy.deepcopy(BASE_M3)
    card["member"] = "diagonal"
    with pytest.raises(ValueError):
        _run("M-3", card)


def test_m3_combined_wind_rejected():
    card = copy.deepcopy(BASE_M3)
    card["wind"] = "组合"
    with pytest.raises(ValueError):
        _run("M-3", card)


def test_m3_line_load_combo():
    result = _run("M-3", copy.deepcopy(BASE_M3))
    assert result["detail"]["qk_kN_per_m"] == pytest.approx(3.45)
    assert result["detail"]["qd_kN_per_m"] == pytest.approx(4.74)


# ---------------------------------------------------------------------------
# G. M-4 连墙件
# ---------------------------------------------------------------------------
def test_m4_emits_three_checks():
    result = _run("M-4", copy.deepcopy(BASE_M4))
    assert [entry["item"] for entry in result["checks"]] == [
        "tie_strength", "tie_stability", "antislip"]


def test_m4_aw_landed_branch():
    result = _run("M-4", copy.deepcopy(BASE_M4))
    assert result["detail"]["Aw_rule"] == "双排落地_H≤50m"
    assert result["detail"]["Aw_m2"] == pytest.approx(3 * 1.8 * 3 * 1.5)


def test_m4_aw_over_fifty_branch():
    card = copy.deepcopy(BASE_M4)
    card["build_height_m"] = 56.0
    result = _run("M-4", card)
    assert result["detail"]["Aw_rule"] == "双排悬挑_H>50m"
    assert result["detail"]["Aw_m2"] == pytest.approx(2 * 1.8 * 3 * 1.5)


def test_m4_single_over_twentyfour_warns():
    card = copy.deepcopy(BASE_M4)
    card["rows"] = "single"
    card["build_height_m"] = 30.0
    result = _run("M-4", card)
    assert any("24m" in warning for warning in result["warnings"])


def test_m4_n0_double_is_three():
    result = _run("M-4", copy.deepcopy(BASE_M4))
    assert result["detail"]["N0_kN"] == 3.0


def test_m4_n0_single_is_two():
    card = copy.deepcopy(BASE_M4)
    card["rows"] = "single"
    card["build_height_m"] = 12.0
    result = _run("M-4", card)
    assert result["detail"]["N0_kN"] == 2.0


def test_m4_high_wind_fails_antislip():
    card = copy.deepcopy(BASE_M4)
    card["wind"]["wk_kN_per_m2"] = 0.5
    result = _run("M-4", card)
    assert _check(result, "antislip")["verdict"] == "fail"


def test_m4_slenderness_ceil():
    result = _run("M-4", copy.deepcopy(BASE_M4))
    assert result["detail"]["lambda"] == math.ceil(1350.0 / 15.9)


# ---------------------------------------------------------------------------
# H. M-5 地基
# ---------------------------------------------------------------------------
def test_m5_explicit_nk_ratio():
    result = _run("M-5", copy.deepcopy(BASE_M5))
    assert result["detail"]["pk_kPa"] == pytest.approx(4.2615 / 0.08)
    assert _check(result, "foundation_bearing")["ratio"] == pytest.approx(
        (4.2615 / 0.08) / (180.0 * 0.4))


def test_m5_pad_area_inverse():
    ratios = []
    for pad in ([0.4, 0.2], [0.5, 0.3], [0.6, 0.4]):
        card = copy.deepcopy(BASE_M5)
        card["foundation"]["pad_m"] = pad
        ratios.append(_ratio(_run("M-5", card), "foundation_bearing"))
    assert ratios == sorted(ratios, reverse=True)


def test_m5_standard_combo_matches_m1_forces():
    card = copy.deepcopy(BASE_M1)
    card["foundation"] = {"type": "天然地基", "fgk_kPa": 180.0, "reduction": 1.0,
                          "pad_m": [0.4, 0.2]}
    result = _run("M-5", card)
    assert result["detail"]["Nk_kN"] == pytest.approx(4.2615)
    assert result["detail"]["fg_kPa"] == pytest.approx(180.0)


def test_m5_design_value_only_rejected():
    card = copy.deepcopy(BASE_M5)
    card["foundation"].pop("nk_kN")
    card["foundation"]["n_design_kN"] = 5.4
    with pytest.raises(ValueError):
        _run("M-5", card)


def test_m5_needs_reduction():
    card = copy.deepcopy(BASE_M5)
    card["foundation"]["reduction"] = None
    with pytest.raises(ValueError):
        _run("M-5", card)


# ---------------------------------------------------------------------------
# I. M-6 模板支架
# ---------------------------------------------------------------------------
def test_m6_column_pass():
    result = _run("M-6", copy.deepcopy(BASE_M6))
    assert _check(result, "column_stability")["verdict"] == "pass"


def test_m6_uses_162_strength_215():
    result = _run("M-6", copy.deepcopy(BASE_M6))
    assert result["detail"]["f"] == 215.0


def test_m6_step_over_limit_warns():
    card = copy.deepcopy(BASE_M6)
    card["step_m"] = 1.9
    result = _run("M-6", card)
    assert any("1.8" in warning for warning in result["warnings"])


def test_m6_foundation_pass():
    card = {"category": "formwork_support",
            "foundation": {"pad_m": [0.4, 0.2], "n_design_kN": 8.0,
                           "mf": 0.8, "fak_kPa": 150.0}}
    result = _run("M-6", card)
    assert _check(result, "foundation_bearing")["verdict"] == "pass"
    assert result["detail"]["p_kPa"] == pytest.approx(100.0)


def test_m6_foundation_missing_mf_rejected():
    card = {"category": "formwork_support",
            "foundation": {"pad_m": [0.4, 0.2], "n_design_kN": 8.0, "fak_kPa": 150.0}}
    with pytest.raises(ValueError):
        _run("M-6", card)


def test_m6_wind_path_pass():
    card = copy.deepcopy(BASE_M6)
    card["wind"] = {"wk_kN_per_m2": 0.2}
    result = _run("M-6", card)
    assert _check(result, "column_stability")["verdict"] == "pass"
    assert result["detail"]["Mw_kNm"] > 0


def test_m6_slab_thickness_monotonic():
    ratios = []
    for slab in (0.08, 0.10, 0.12, 0.15, 0.18):
        card = copy.deepcopy(BASE_M6)
        card["slab_thickness_m"] = slab
        ratios.append(_ratio(_run("M-6", card), "column_stability"))
    assert ratios == sorted(ratios)


def test_m6_gamma0_applied():
    result = _run("M-6", copy.deepcopy(BASE_M6))
    ng = (0.75 + 24.0 * 0.12 + 1.1 * 0.12) * 1.0 * 1.0
    expected = 0.9 * (1.2 * ng + 1.4 * 1.0)
    assert result["detail"]["N_design_kN"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# J. 算例真值（13 例）
# ---------------------------------------------------------------------------
def test_examples_count_thirteen():
    assert len(_examples()) == 13


def test_examples_cover_all_modules():
    assert {example["module"] for example in _examples()} == {
        "M-1", "M-2", "M-3", "M-4", "M-5", "M-6"}


def test_examples_have_fail_path():
    assert any(check["verdict"] == "fail"
               for example in _examples()
               for check in example["expect"]["checks"])


def test_example_intermediate_sigma_self_consistent():
    for example in _examples():
        detail = example["expect"].get("intermediate") or {}
        if example["module"] not in ("M-1", "M-2", "M-6"):
            continue
        if "phi" not in detail:
            continue
        force = detail.get("N_design_kN") or detail.get("Nw_kN")
        sigma = force * 1000.0 / (detail["phi"] * 506.0)
        if "Mw_kNm" in detail:
            sigma += detail["Mw_kNm"] * 1e6 / 5260.0
        assert abs(sigma - detail["sigma_N_per_mm2"]) < 0.02, example["example_id"]


def test_example_phi_anchors_reproduced():
    anchors = {85: 0.692, 95: 0.626, 191: 0.197, 197: 0.186, 236: 0.131}
    for example in _examples():
        detail = example["expect"].get("intermediate") or {}
        lam = detail.get("lambda")
        if lam is None:
            continue
        key = int(math.ceil(lam))
        if key in anchors:
            assert detail["phi"] == anchors[key], example["example_id"]


def test_example_diji_001():
    _assert_example("EX-diji-001")


def test_example_diji_162_001():
    _assert_example("EX-diji-162-001")


def test_example_lianqiangjian_001():
    _assert_example("EX-lianqiangjian-001")


def test_example_lianqiangjian_002():
    _assert_example("EX-lianqiangjian-002")


def test_example_lizhigan_nw_001():
    _assert_example("EX-lizhigan-nw-001")


def test_example_lizhigan_nw_002():
    _assert_example("EX-lizhigan-nw-002")


def test_example_lizhigan_nw_003():
    _assert_example("EX-lizhigan-nw-003")


def test_example_lizhigan_w_001():
    _assert_example("EX-lizhigan-w-001")


def test_example_lizhigan_w_002():
    _assert_example("EX-lizhigan-w-002")


def test_example_mubanzhijia_nw_001():
    _assert_example("EX-mubanzhijia-nw-001")


def test_example_mubanzhijia_w_001():
    _assert_example("EX-mubanzhijia-w-001")


def test_example_shuipinggan_hx_001():
    _assert_example("EX-shuipinggan-hx-001")


def test_example_shuipinggan_zx_001():
    _assert_example("EX-shuipinggan-zx-001")


# ---------------------------------------------------------------------------
# K. 计算书记录形态
# ---------------------------------------------------------------------------
def test_calc_mode_returns_record_with_basis():
    records = _records(_calc_subject(copy.deepcopy(BASE_M1)))
    assert len(records) == 1
    record = records[0]
    assert record.verdict == OK
    assert record.basis.code == "JGJ 130-2011"
    assert record.basis.clause == "5.2.6"
    assert record.basis.version == "2011"
    assert record.id == "M-1.lizhigan_stability@JGJ 130-2011:5.2.6"


def test_calc_mode_auto_detects_module():
    records = _records(_calc_subject(copy.deepcopy(BASE_M3)))
    assert records[0].item_id.startswith("M-3.")


def test_calc_record_id_stable_across_runs():
    subject = _calc_subject(copy.deepcopy(BASE_M1))
    assert _records(subject)[0].id == _records(subject)[0].id


def test_calc_json_is_deterministic():
    subject = _calc_subject(copy.deepcopy(BASE_M1))
    first = Report(product="speccalc", organ=SLUG, organ_version=VERSION,
                   subject="x.json", records=_records(subject)).as_dict()
    second = Report(product="speccalc", organ=SLUG, organ_version=VERSION,
                    subject="x.json", records=_records(subject)).as_dict()
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True)


def test_calc_pass_exit_code_is_zero():
    subject = _calc_subject(copy.deepcopy(BASE_M1))
    report = Report(product="speccalc", organ=SLUG, organ_version=VERSION,
                    subject="x.json", records=_records(subject))
    assert report.exit_code() == EXIT_OK


def test_calc_fail_exit_code_is_blocked():
    card = copy.deepcopy(BASE_M1)
    card["loads"]["live_kN_per_m2"] = 40.0
    report = Report(product="speccalc", organ=SLUG, organ_version=VERSION,
                    subject="x.json", records=_records(_calc_subject(card)))
    assert report.exit_code() == EXIT_BLOCKED


def test_calc_missing_basis_raises_clause_missing():
    with pytest.raises(ClauseMissing):
        _records(_calc_subject(copy.deepcopy(BASE_M1)), Basis.empty("0"))


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        _records({"case_id": "x", "mode": "audit"})


def test_missing_case_id_rejected():
    with pytest.raises(ValueError):
        _records({"mode": "calc", "calc": {"card": copy.deepcopy(BASE_M1)}})


def test_calc_mode_without_card_rejected():
    with pytest.raises(ValueError):
        _records({"case_id": "x", "mode": "calc", "calc": {"module": "M-1"}})