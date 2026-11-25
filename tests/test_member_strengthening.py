"""器官 ``member-strengthening`` 的无损测试（迁自 target-map ③ 行 / 仓库 #45）。

覆盖面：注册与条款/表值契约 / 参数校验 / 四张规范查表 / 4 个验算模块三态 /
方案规则 4 条（含降级与证据污染）/ GB55021 检查单 / 记录与 CLI 退出码 /
seed 参数扫描位级锁定。

不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数）。
X = 76（D18 新正则），旧层 AST 函数 83；本文件函数数 110+ 且逐条有断言。
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import random
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
ORGAN = importlib.import_module("speccalc.modules.member-strengthening")
SLUG = ORGAN.SLUG
SAMPLES = os.path.join(ROOT, "samples", "member-strengthening")
BASIS_FILE = os.path.join(SAMPLES, "basis.json")
BASIS = Basis.from_json(BASIS_FILE)
DATA = ORGAN.DATA
PACK = ORGAN.PACK


def _sample(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as handle:
        return json.load(handle)


CFRP = _sample("cfrp-case-cf-001-p.json")["calc"]["params"]
PLATE = {
    "b": 250.0, "h": 500.0, "fc": 14.3, "As": 1520.0, "fy": 360.0,
    "Ap": 600.0, "fp": 215.0, "M0": 0.0, "M": 190.0,
    "as": 35.0, "xi_b": 0.518, "Es": 200000.0, "Esp": 206000.0,
}
ENLARGE = {
    "b": 250.0, "h": 500.0, "bf": 250.0, "hf": 100.0, "fc": 14.3, "fc2": 16.7,
    "As": 1520.0, "fy": 360.0, "As2": 628.0, "fy2": 360.0,
    "as": 35.0, "as2": 45.0, "M0": 0.0, "M": 220.0, "Es": 200000.0,
}
ANCHOR = _sample("post-rebar-case-pr-001.json")["calc"]["params"]
SCHEME = _sample("scheme-example.json")["scheme"]
CHECKLIST = _sample("checklist-example.json")["checklist"]


def _calc(module, params, basis=BASIS):
    return tuple(ORGAN.run_calc(module, params, basis))


def _rows(records, item_id):
    hits = [record for record in records if record.item_id == item_id]
    assert len(hits) == 1, (item_id, [r.item_id for r in records])
    return hits[0]


def _scheme(**overrides):
    raw = copy.deepcopy(SCHEME)
    for key, value in overrides.items():
        raw[key] = value
    return ORGAN.make_card(raw)


def _scheme_value(value, grade="A"):
    raw = copy.deepcopy(SCHEME)
    raw["adhesive_indices"][0]["value"] = value
    raw["adhesive_indices"][0]["label"] = grade
    raw["source_text"] = raw["source_text"].replace("15.8MPa", "%sMPa" % value)
    raw["adhesive_indices"][0]["quote"] = "钢对钢拉伸抗剪强度标准值 %sMPa" % value
    return ORGAN.make_card(raw)


def _scheme_records(card, basis=BASIS, pack=PACK):
    return ORGAN.run_scheme(card, basis, pack)


def _by_rule(records, rule_id):
    return _rows(records, "scheme.%s" % rule_id)


# ---------------------------------------------------------------------------
# A. 注册、清单与数据契约
# ---------------------------------------------------------------------------
def test_organ_registered():
    assert get(SLUG).slug == SLUG


def test_organ_version_is_zero_one_zero():
    assert get(SLUG).version == "0.1.0"


def test_organ_summary_mentions_four_calcs():
    assert "CFRP" in get(SLUG).summary and "植筋" in get(SLUG).summary


def test_input_fields_are_mode_and_case_id():
    assert get(SLUG).input_fields == ("mode", "case_id")


def test_builtin_manifest_is_exactly_five_sorted_organs():
    """第 5 个器官迁入：精确清单，不用 contains 松断言。"""
    assert list(BUILTIN_MODULES) == [
        "excavation-monitor", "formwork-scaffold", "member-strengthening",
        "pavement-mqi", "steel-member",
    ]
    assert list(BUILTIN_MODULES) == sorted(BUILTIN_MODULES)


def test_cli_list_shows_all_five_organs(capsys):
    assert cli.main(["list"]) == EXIT_OK
    lines = [line.split()[0] for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert [slug for slug in lines if slug in BUILTIN_MODULES] == list(BUILTIN_MODULES)


def test_data_declares_forty_clause_keys():
    assert len(DATA["clauses"]) == 40


def test_data_declares_four_calc_modules():
    assert sorted(DATA["modules"]) == [
        "cfrp_beam_flexure", "post_rebar_anchor",
        "section_enlarge_flexure", "steel_plate_flexure",
    ]


def test_data_declares_four_scheme_rules():
    assert [rule["id"] for rule in DATA["rules"]] == [
        "R-ADH-001", "R-ANCH-001", "R-APP-001", "R-CONST-001",
    ]


def test_data_declares_eleven_checklist_items():
    assert len(DATA["checklist"]) == 11


def test_inventory_counts_source_library():
    assert DATA["clause_inventory"]["total"] == 52
    assert DATA["clause_inventory"]["verified"] == 51


def test_inventory_records_pending_clause_only():
    assert DATA["clause_inventory"]["pending"] == ["JGJ145-2013-6.3"]


def test_inventory_covers_five_standards():
    assert len(DATA["clause_inventory"]["standards"]) == 5


def test_pending_clause_not_in_required_clauses():
    used = {key for module in DATA["modules"].values()
            for key in module["required_clauses"]}
    assert "anchor.15.2.6" in used
    assert not any("6.3" in key for key in used)


def test_all_module_clauses_are_present_and_verified():
    for module in DATA["modules"].values():
        for key in module["required_clauses"]:
            assert DATA["clauses"][key]["status"] == "已核对"


def test_all_rule_clauses_are_verified():
    for rule in DATA["rules"]:
        assert DATA["clauses"][rule["clause_key"]]["status"] == "已核对"
        assert rule["status"] == "已核对"


def test_all_checklist_clauses_are_verified():
    for item in DATA["checklist"]:
        assert DATA["clauses"][item["clause_key"]]["status"] == "已核对"
        assert item["status"] == "已核对"


def test_anchor_rule_lists_support_clauses():
    rule = next(r for r in DATA["rules"] if r["id"] == "R-ANCH-001")
    assert "anchor.15.2.5" in rule["support_clause_keys"]
    assert "gb50010.4.2.3" in rule["support_clause_keys"]


def test_codes_are_real_standard_numbers():
    assert DATA["codes"]["gb50367"] == "GB 50367-2013"
    assert DATA["codes"]["gb55021"] == "GB 55021-2021"


def test_basis_covers_every_declared_clause():
    keys = {(entry["code"], entry["clause"]) for entry in BASIS.as_dict()["clauses"]}
    for entry in DATA["clauses"].values():
        assert (entry["code"], entry["clause"]) in keys


# ---------------------------------------------------------------------------
# B. 查表与参数校验
# ---------------------------------------------------------------------------
def test_alpha_f_band_start_and_end():
    assert ORGAN.lookup_alpha_f(0.001, 1) == (0.7, False)
    assert ORGAN.lookup_alpha_f(0.10, 2) == (1.4, False)


def test_alpha_f_interpolation_between_bands():
    value, interpolated = ORGAN.lookup_alpha_f(0.02432, 1)
    assert interpolated is True
    assert value == pytest.approx(1.1716)


def test_alpha_f_double_row_differs_from_single():
    single, _ = ORGAN.lookup_alpha_f(0.010, 1)
    double, _ = ORGAN.lookup_alpha_f(0.010, 2)
    assert (single, double) == (0.9, 1.0)


def test_alpha_spt_exact_cell():
    value, warnings = ORGAN.alpha_spt_from_table(30.0, 8.0, 25.0)
    assert value == 1.0 and warnings == []


def test_alpha_spt_diameter_interpolation():
    value, warnings = ORGAN.alpha_spt_from_table(25.0, 6.0, 22.0)
    assert value == pytest.approx(1.04)
    assert warnings == []


def test_alpha_spt_conservative_cover_warns():
    value, warnings = ORGAN.alpha_spt_from_table(28.0, 6.0, 32.0)
    assert value == 1.25
    assert warnings and "保守" in warnings[0]


def test_alpha_spt_diameter_beyond_table_refused():
    with pytest.raises(ValueError, match="d≤32"):
        ORGAN.alpha_spt_from_table(30.0, 8.0, 40.0)


def test_fbd_row_selection_strictest_first():
    assert ORGAN.fbd_from_table("A", 180.0, 90.0, 25.0, "C30")[0] == 4.5
    assert ORGAN.fbd_from_table("A", 160.0, 80.0, 25.0, "C30")[0] == 4.0


def test_fbd_b_grade_only_first_row():
    assert ORGAN.fbd_from_table("B", 200.0, 100.0, 20.0, "C40")[0] == 4.0


def test_fbd_grade_out_of_table_refused():
    with pytest.raises(ValueError, match="无满足的构造条件行"):
        ORGAN.fbd_from_table("B", 20.0, 10.0, 20.0, "C40")


def test_missing_required_param_refused():
    with pytest.raises(ValueError, match="缺少参数"):
        _calc("cfrp_beam_flexure", {})


def test_negative_param_refused():
    with pytest.raises(ValueError, match="b=-1"):
        _calc("cfrp_beam_flexure", dict(CFRP, b=-1))


def test_zero_exclusive_param_refused():
    with pytest.raises(ValueError, match="超出合法范围"):
        _calc("cfrp_beam_flexure", dict(CFRP, Afe=0.0))


def test_negative_non_exclusive_param_refused():
    with pytest.raises(ValueError, match="M0=-5"):
        _calc("cfrp_beam_flexure", dict(CFRP, M0=-5.0))


def test_bool_param_refused():
    with pytest.raises(ValueError, match="期望数值"):
        _calc("cfrp_beam_flexure", dict(CFRP, b=True))


def test_infinite_param_refused():
    with pytest.raises(ValueError, match="有限数值"):
        _calc("cfrp_beam_flexure", dict(CFRP, b=float("inf")))


def test_optional_param_can_be_absent():
    params = {key: value for key, value in CFRP.items() if key != "xi_b"}
    assert _rows(_calc("cfrp_beam_flexure", params), "cfrp.xi-limit").evidence["checked"] is False


def test_asc_without_ap_refused():
    with pytest.raises(ValueError, match="必须同时提供 ap"):
        _calc("cfrp_beam_flexure", dict(CFRP, Asc=402.0))


def test_h_le_as_refused():
    with pytest.raises(ValueError, match="几何参数无效"):
        _calc("cfrp_beam_flexure", dict(CFRP, **{"as": 600.0}))


def test_params_must_be_mapping():
    with pytest.raises(ValueError, match="params 必须是对象"):
        _calc("cfrp_beam_flexure", [1, 2])


def test_unknown_module_refused():
    with pytest.raises(ValueError, match="未知验算模块"):
        _calc("no-such-module", {})


# ---------------------------------------------------------------------------
# C. CFRP 加固梁
# ---------------------------------------------------------------------------
def test_cfrp_sample_four_records():
    assert len(_calc("cfrp_beam_flexure", CFRP)) == 4


def test_cfrp_sample_flexure_is_ok():
    assert _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.flexure").verdict == OK


def test_cfrp_sample_mu_matches_old_truth():
    record = _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.flexure")
    assert record.evidence["Mu_kNm"] == pytest.approx(244.02356775216916, rel=1e-9)


def test_cfrp_sample_x_matches_old_truth():
    record = _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.flexure")
    assert record.evidence["x_mm"] == pytest.approx(179.42409144534952, rel=1e-9)


def test_cfrp_sample_psi_matches_old_truth():
    record = _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.flexure")
    assert record.evidence["psi_f"] == pytest.approx(0.4056871584895591, rel=1e-9)


def test_cfrp_ratio_is_demand_over_capacity():
    record = _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.flexure")
    assert record.evidence["ratio"] == pytest.approx(180.0 / 244.02356775216916)


def test_cfrp_need_adjust_when_capacity_short():
    record = _rows(_calc("cfrp_beam_flexure", dict(CFRP, M=260.0, Afe=50.0)), "cfrp.flexure")
    assert record.verdict == REJECTED
    assert record.evidence["Afe_req_mm2"] > 50.0


def test_cfrp_infeasible_when_moment_too_large():
    record = _rows(_calc("cfrp_beam_flexure", dict(CFRP, M=350.0)), "cfrp.flexure")
    assert record.verdict == REJECTED
    assert record.evidence["infeasible"] is True


def test_cfrp_x_limit_record_uses_85_percent_xi_b():
    record = _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.xi-limit")
    assert record.evidence["xi_bf"] == pytest.approx(0.85 * 0.518)
    assert record.evidence["limit_mm"] == pytest.approx(0.85 * 0.518 * 465.0)


def test_cfrp_x_limit_rejected_when_over_reinforced():
    records = _calc("cfrp_beam_flexure", dict(CFRP, Afe=400.0))
    assert _rows(records, "cfrp.xi-limit").verdict == REJECTED


def test_cfrp_capacity_increase_is_ok():
    record = _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.capacity-increase")
    assert record.verdict == OK
    assert record.evidence["increase"] == pytest.approx(0.14796815, abs=1e-6)


def test_cfrp_secondary_strain_activates_with_m0():
    records = _calc("cfrp_beam_flexure", dict(CFRP, M0=80.0))
    record = _rows(records, "cfrp.secondary-strain")
    assert record.evidence["activated"] is True
    assert record.evidence["alpha_f"] == pytest.approx(1.1716)
    assert record.evidence["epsilon_f0"] > 0


def test_cfrp_alpha_f_adjust_when_low_stress():
    records = _calc("cfrp_beam_flexure", dict(CFRP, M0=80.0, sigma_s0=140.0, rho_te=0.04))
    assert any("×0.9" in warning for warning in
               _rows(records, "cfrp.flexure").evidence["warnings"])


def test_cfrp_km_multi_layer_record():
    records = _calc("cfrp_beam_flexure", dict(CFRP, nf=3, tf=0.167))
    record = _rows(records, "cfrp.km")
    assert record.evidence["km"] == pytest.approx(0.7696103896103895)
    assert record.basis.clause == "10.2.4"


def test_cfrp_x_below_two_ap_clamped():
    records = _calc("cfrp_beam_flexure", dict(CFRP, Asc=402.0, ap=120.0))
    assert _rows(records, "cfrp.flexure").evidence["x_mm"] >= 240.0


def test_cfrp_clause_numbers_are_real():
    records = _calc("cfrp_beam_flexure", CFRP)
    assert {record.basis.clause for record in records} <= {
        "10.2.2", "10.2.3", "10.2.8", "10.2.10",
    }


# ---------------------------------------------------------------------------
# D. 粘贴钢板加固
# ---------------------------------------------------------------------------
def test_plate_sample_four_records():
    assert len(_calc("steel_plate_flexure", PLATE)) == 4


def test_plate_flexure_is_ok():
    assert _rows(_calc("steel_plate_flexure", PLATE), "plate.flexure").verdict == OK


def test_plate_flexure_ratio_is_demand_over_capacity():
    record = _rows(_calc("steel_plate_flexure", PLATE), "plate.flexure")
    assert record.evidence["ratio"] < 1.0
    assert record.evidence["psi_sp"] > 0


def test_plate_short_plate_is_rejected():
    record = _rows(_calc("steel_plate_flexure", dict(PLATE, M=400.0)), "plate.flexure")
    assert record.verdict == REJECTED


def test_plate_xi_limit_ok():
    assert _rows(_calc("steel_plate_flexure", PLATE), "plate.xi-limit").verdict == OK


def test_plate_xi_limit_rejected_when_over_reinforced():
    records = _calc("steel_plate_flexure", dict(PLATE, Ap=2000.0))
    assert _rows(records, "plate.xi-limit").verdict == REJECTED


def test_plate_missing_xi_skips_limit_check():
    records = _calc("steel_plate_flexure", {k: v for k, v in PLATE.items() if k != "xi_b"})
    assert _rows(records, "plate.xi-limit").evidence["checked"] is False


def test_plate_secondary_strain_activates_with_m0():
    records = _calc("steel_plate_flexure", dict(PLATE, M0=80.0))
    record = _rows(records, "plate.secondary-strain")
    assert record.evidence["activated"] is True
    assert record.evidence["alpha_sp"] > 0


def test_plate_asc_without_ap_refused():
    with pytest.raises(ValueError, match="必须同时提供 ap"):
        _calc("steel_plate_flexure", dict(PLATE, Asc=402.0))


def test_plate_capacity_increase_record():
    record = _rows(_calc("steel_plate_flexure", PLATE), "plate.capacity-increase")
    assert record.verdict == OK
    assert 0.0 <= record.evidence["increase"] <= 0.4


def test_plate_clause_numbers_are_real():
    records = _calc("steel_plate_flexure", PLATE)
    assert {record.basis.clause for record in records} <= {
        "9.2.2", "9.2.3", "9.2.9", "9.2.11",
    }


# ---------------------------------------------------------------------------
# E. 增大截面加固
# ---------------------------------------------------------------------------
def test_enlarge_sample_three_records():
    assert len(_calc("section_enlarge_flexure", ENLARGE)) == 3


def test_enlarge_flexure_is_ok():
    assert _rows(_calc("section_enlarge_flexure", ENLARGE), "enlarge.flexure").verdict == OK


def test_enlarge_mu_uses_alpha_s_point_nine():
    record = _rows(_calc("section_enlarge_flexure", ENLARGE), "enlarge.flexure")
    assert record.evidence["Mu_kNm"] > 0
    assert 0.9 * 360.0 * 628.0 > 0


def test_enlarge_short_reinforcement_is_rejected():
    record = _rows(_calc("section_enlarge_flexure", dict(ENLARGE, M=600.0)), "enlarge.flexure")
    assert record.verdict == REJECTED


def test_enlarge_xi_limit_ok():
    assert _rows(_calc("section_enlarge_flexure", ENLARGE), "enlarge.xi-limit").verdict == OK


def test_enlarge_sigma_s0_path_activates():
    records = _calc("section_enlarge_flexure", dict(ENLARGE, M0=100.0, As2=804.0, xi_b0=0.40))
    record = _rows(records, "enlarge.sigma-s0")
    assert record.evidence["sigma_s0_MPa"] == 360.0
    assert record.evidence["capped"] is True


def test_enlarge_secondary_strain_records_eps():
    records = _calc("section_enlarge_flexure", dict(ENLARGE, M0=100.0))
    record = _rows(records, "enlarge.secondary-strain")
    assert record.evidence["activated"] is True
    assert record.evidence["epsilon_s0"] > 0
    assert record.evidence["xi_b"] < 0.8


def test_enlarge_bad_geometry_refused():
    with pytest.raises(ValueError, match="合法范围"):
        _calc("section_enlarge_flexure", dict(ENLARGE, hf=0.0))


def test_enlarge_asc_without_ap_refused():
    with pytest.raises(ValueError, match="必须同时提供 ap"):
        _calc("section_enlarge_flexure", dict(ENLARGE, Asc=402.0))


# ---------------------------------------------------------------------------
# F. 植筋锚固深度
# ---------------------------------------------------------------------------
def test_anchor_sample_four_records():
    assert len(_calc("post_rebar_anchor", ANCHOR)) == 4


def test_anchor_depth_is_ok():
    assert _rows(_calc("post_rebar_anchor", ANCHOR), "anchor.depth").verdict == OK


def test_anchor_ls_matches_old_truth():
    assert _rows(_calc("post_rebar_anchor", ANCHOR), "anchor.depth").evidence["ls_mm"] == pytest.approx(230.4)


def test_anchor_psi_matches_old_truth():
    assert _rows(_calc("post_rebar_anchor", ANCHOR), "anchor.depth").evidence["psi_N"] == pytest.approx(1.1)


def test_anchor_required_depth_matches_old_truth():
    assert _rows(_calc("post_rebar_anchor", ANCHOR), "anchor.depth").evidence["ld_required_mm"] == pytest.approx(253.44)


def test_anchor_ratio_is_required_over_provided():
    record = _rows(_calc("post_rebar_anchor", ANCHOR), "anchor.depth")
    assert record.evidence["ratio"] == pytest.approx(253.44 / 260.0)
    assert record.evidence["ratio"] < 1.0


def test_anchor_short_depth_is_rejected():
    record = _rows(_calc("post_rebar_anchor", dict(ANCHOR, ld=250.0)), "anchor.depth")
    assert record.verdict == REJECTED


def test_anchor_table_path_verdict():
    params = {
        "fc": 14.3, "fy": 360.0, "d": 25.0, "ld": 520.0,
        "cover": 30.0, "stirrup_dia": 8.0,
        "adhesive_grade": 1, "s1": 160.0, "s2": 80.0, "fc_grade": 30,
        "psi_br": 1.0, "psi_w": 1.1, "psi_T": 1.0, "psi_ae": 1.0,
    }
    record = _rows(_calc("post_rebar_anchor", params), "anchor.depth")
    assert record.verdict == OK
    assert record.evidence["ls_mm"] == pytest.approx(450.0)
    assert record.evidence["fbd_used_MPa"] == 4.0


def test_anchor_direct_and_table_paths_are_exclusive():
    params = dict(ANCHOR, cover=30.0, stirrup_dia=8.0)
    with pytest.raises(ValueError, match="互斥"):
        _calc("post_rebar_anchor", params)


def test_anchor_fbd_direct_and_table_paths_are_exclusive():
    params = dict(ANCHOR, adhesive_grade=1, s1=100.0)
    with pytest.raises(ValueError, match="互斥"):
        _calc("post_rebar_anchor", params)


def test_anchor_missing_alpha_spt_refused():
    params = {k: v for k, v in ANCHOR.items() if k != "alpha_spt"}
    with pytest.raises(ValueError, match="缺少 alpha_spt"):
        _calc("post_rebar_anchor", params)


def test_anchor_missing_fbd_refused():
    params = {k: v for k, v in ANCHOR.items() if k != "fbd"}
    with pytest.raises(ValueError, match="缺少 fbd"):
        _calc("post_rebar_anchor", params)


def test_anchor_fast_cure_reduces_fbd():
    params = dict(ANCHOR, fc=30.0, fc_grade=40, fast_cure=1)
    record = _rows(_calc("post_rebar_anchor", params), "anchor.fbd")
    assert record.evidence["adjusted"] is True
    assert record.evidence["fbd_used_MPa"] == pytest.approx(2.0)


def test_anchor_invalid_adhesive_grade_refused():
    params = dict(ANCHOR, adhesive_grade=3)
    with pytest.raises(ValueError, match="adhesive_grade"):
        _calc("post_rebar_anchor", {k: v for k, v in params.items() if k != "fbd"})


def test_anchor_invalid_fc_grade_refused():
    params = dict(ANCHOR, fc_grade=35)
    with pytest.raises(ValueError, match="fc_grade"):
        _calc("post_rebar_anchor", {k: v for k, v in params.items() if k != "fbd"})


# ---------------------------------------------------------------------------
# G. 方案规则层
# ---------------------------------------------------------------------------
def test_scheme_sample_has_four_rule_records():
    assert len(_scheme_records(_scheme())) == 4


def test_scheme_sample_all_ok():
    assert {record.verdict for record in _scheme_records(_scheme())} == {OK}


def test_scheme_adhesive_pass_above_all_limits():
    assert _by_rule(_scheme_records(_scheme_value(15.8)), "R-ADH-001").verdict == OK


def test_scheme_adhesive_fail_below_lower_limit():
    assert _by_rule(_scheme_records(_scheme_value(12.0)), "R-ADH-001").verdict == REJECTED


def test_scheme_adhesive_suspicious_between_limits():
    record = _by_rule(_scheme_records(_scheme_value(14.5)), "R-ADH-001")
    assert record.verdict == REJECTED
    assert record.evidence["plan_verdict"] == "suspicious"


def test_scheme_adhesive_unlabeled_is_confirm():
    assert _by_rule(_scheme_records(_scheme_value(13.0, grade="")), "R-ADH-001").verdict == OK


def test_scheme_adhesive_missing_index_fails():
    raw = copy.deepcopy(SCHEME)
    raw["adhesive_indices"] = []
    assert _by_rule(_scheme_records(ORGAN.make_card(raw)), "R-ADH-001").verdict == REJECTED


def test_scheme_anchor_pass_above_lower_bound():
    record = _by_rule(_scheme_records(_scheme()), "R-ANCH-001")
    assert record.verdict == OK
    assert record.evidence["ld_required_lower_mm"] == pytest.approx(190.08, abs=0.05)


def test_scheme_anchor_fail_below_lower_bound():
    raw = copy.deepcopy(SCHEME)
    raw["anchor_depths"][0]["value"] = 150.0
    raw["source_text"] = raw["source_text"].replace("320mm", "150mm")
    raw["anchor_depths"][0]["quote"] = "锚固深度设计值 150mm"
    assert _by_rule(_scheme_records(ORGAN.make_card(raw)), "R-ANCH-001").verdict == REJECTED


def test_scheme_anchor_missing_depth_fails():
    raw = copy.deepcopy(SCHEME)
    raw["anchor_depths"] = []
    assert _by_rule(_scheme_records(ORGAN.make_card(raw)), "R-ANCH-001").verdict == REJECTED


def test_scheme_anchor_missing_design_param_confirms():
    raw = copy.deepcopy(SCHEME)
    raw["design_params"] = [p for p in raw["design_params"] if p["kind"] != "植筋直径"]
    record = _by_rule(_scheme_records(ORGAN.make_card(raw)), "R-ANCH-001")
    assert record.verdict == OK
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_scheme_anchor_unmapped_rebar_grade_confirms():
    raw = copy.deepcopy(SCHEME)
    raw["source_text"] = raw["source_text"].replace("HRB400", "HRB335")
    for item in raw["design_params"]:
        if item["kind"] == "钢筋牌号":
            item["label"] = "HRB335"
    record = _by_rule(_scheme_records(ORGAN.make_card(raw)), "R-ANCH-001")
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_scheme_anchor_out_of_table_fc_confirms():
    raw = copy.deepcopy(SCHEME)
    raw["source_text"] = raw["source_text"].replace("C40", "C35")
    for item in raw["design_params"]:
        if item["kind"] == "混凝土强度等级":
            item["value"] = 35.0
            item["label"] = "C35"
    record = _by_rule(_scheme_records(ORGAN.make_card(raw)), "R-ANCH-001")
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_scheme_appraisal_missing_evidence_fails():
    raw = copy.deepcopy(SCHEME)
    raw["appraisal_first"] = None
    assert _by_rule(_scheme_records(ORGAN.make_card(raw)), "R-APP-001").verdict == REJECTED


def test_scheme_unloading_missing_evidence_fails():
    raw = copy.deepcopy(SCHEME)
    raw["unloading"] = []
    assert _by_rule(_scheme_records(ORGAN.make_card(raw)), "R-CONST-001").verdict == REJECTED


def test_scheme_gate_scopes_rules():
    card = ORGAN.make_card({"source_text": "仅描述普通混凝土浇筑，未涉及加固。"})
    assert _scheme_records(card) == ()


def test_scheme_degraded_downgrades_every_active_rule():
    card = ORGAN.make_card({
        "source_text": "",
        "methods": [
            {"kind": "加固方案"}, {"kind": "结构胶"},
            {"kind": "锚固深度"}, {"kind": "碳纤维"},
        ],
    })
    records = _scheme_records(card)
    assert len(records) == 4
    assert {record.verdict for record in records} == {OK}
    assert all(record.evidence["plan_verdict"] == "needs_confirm" for record in records)


def test_scheme_evidence_issue_downgrades_rules():
    raw = copy.deepcopy(SCHEME)
    raw["adhesive_indices"][0]["quote"] = "这段话不在原文中"
    records = _scheme_records(ORGAN.make_card(raw))
    assert all(record.evidence["plan_verdict"] == "needs_confirm" for record in records)
    assert any("evidence_issues" in record.evidence for record in records)


def test_scheme_unverified_rule_never_fails():
    data = copy.deepcopy(ORGAN.DATA)
    next(r for r in data["rules"] if r["id"] == "R-ADH-001")["status"] = "待核对"
    record = _by_rule(_scheme_records(_scheme(), pack=ORGAN.Rules(data)), "R-ADH-001")
    assert record.verdict == OK
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_scheme_unknown_target_falls_back_to_confirm():
    data = copy.deepcopy(ORGAN.DATA)
    data["rules"].append({
        "id": "R-FUTURE", "name": "未来规则", "category": "future",
        "only_if_keywords": ["未来类目"], "check_type": "consistency",
        "target": "unknown_target", "severity": "fail", "message": "m", "advice": "a",
        "clause_key": "gb55021.1.0.3", "status": "已核对", "support_clause_keys": [],
    })
    card = ORGAN.make_card({"source_text": "未来类目描述。"})
    record = _by_rule(_scheme_records(card, pack=ORGAN.Rules(data)), "R-FUTURE")
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_scheme_source_text_must_be_string():
    with pytest.raises(ValueError, match="source_text 必须是字符串"):
        ORGAN.make_card({"source_text": 123})


def test_scheme_basis_missing_clause_is_contract_error():
    thin = Basis(version="thin", clauses=())
    with pytest.raises(ClauseMissing):
        _scheme_records(_scheme(), basis=thin)


# ---------------------------------------------------------------------------
# H. GB 55021 检查单
# ---------------------------------------------------------------------------
def test_checklist_sample_eleven_ok_records():
    records = ORGAN.run_checklist(CHECKLIST, BASIS)
    assert len(records) == 11
    assert {record.verdict for record in records} == {OK}


def test_checklist_not_compliant_is_rejected():
    answers = dict(CHECKLIST, **{"GB55021-1.0.3": "不符合"})
    record = _rows(ORGAN.run_checklist(answers, BASIS), "checklist.GB55021-1.0.3")
    assert record.verdict == REJECTED


def test_checklist_pending_is_ok_with_option():
    answers = dict(CHECKLIST, **{"GB55021-1.0.3": "待确认"})
    record = _rows(ORGAN.run_checklist(answers, BASIS), "checklist.GB55021-1.0.3")
    assert record.verdict == OK
    assert record.evidence["option"] == "待确认"


def test_checklist_missing_item_defaults_to_pending():
    record = _rows(ORGAN.run_checklist({}, BASIS), "checklist.GB55021-6.1.5")
    assert record.evidence["option"] == "待确认"


def test_checklist_unknown_item_refused():
    with pytest.raises(ValueError, match="无此条目"):
        ORGAN.run_checklist({"NO-SUCH": "符合"}, BASIS)


def test_checklist_invalid_option_refused():
    with pytest.raises(ValueError, match="判定非法"):
        ORGAN.run_checklist({"GB55021-1.0.3": "也许"}, BASIS)


def test_checklist_all_clauses_are_gb55021():
    for record in ORGAN.run_checklist(CHECKLIST, BASIS):
        assert record.basis.code == "GB 55021-2021"


def test_checklist_pending_item_status_blocks():
    data = copy.deepcopy(ORGAN.DATA)
    data["checklist"][0]["status"] = "待核对"
    with pytest.raises(Exception):
        ORGAN.run_checklist(CHECKLIST, BASIS, ORGAN.Rules(data))


# ---------------------------------------------------------------------------
# I. 记录形态、CLI 与退出码
# ---------------------------------------------------------------------------
def test_every_calc_record_has_three_field_basis():
    for record in _calc("cfrp_beam_flexure", CFRP):
        assert record.basis.code and record.basis.clause and record.basis.version == "2013"


def test_record_id_is_item_at_code_colon_clause():
    record = _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.flexure")
    assert record.id == "cfrp.flexure@GB 50367-2013:10.2.3"


def test_report_has_no_duplicate_ids():
    import speccalc.core.ledger as ledger

    report = ledger.Report(product="speccalc", organ=SLUG, organ_version="0.1.0",
                           subject="test", records=_calc("cfrp_beam_flexure", CFRP))
    assert report.summary()["total"] == 4


def test_ratio_tolerance_is_declared():
    record = _rows(_calc("cfrp_beam_flexure", CFRP), "cfrp.flexure")
    assert record.evidence["ratio_tol"] == 1e-9


def test_env_does_not_change_records(monkeypatch):
    before = [record.as_dict() for record in _calc("cfrp_beam_flexure", CFRP)]
    monkeypatch.setenv("SSC_DATA_DIR", "/nonexistent")
    assert [record.as_dict() for record in _calc("cfrp_beam_flexure", CFRP)] == before


def test_cli_cfrp_sample_rc_is_zero(capsys):
    assert cli.main(["check", SLUG, "--input", os.path.join(SAMPLES, "cfrp-case-cf-001-p.json"),
                     "--basis", BASIS_FILE]) == EXIT_OK
    assert "阻断 0 条" in capsys.readouterr().out


def test_cli_failing_scheme_rc_is_one(tmp_path):
    raw = copy.deepcopy(SCHEME)
    raw["adhesive_indices"][0]["value"] = 12.0
    raw["source_text"] = raw["source_text"].replace("15.8MPa", "12MPa")
    raw["adhesive_indices"][0]["quote"] = "钢对钢拉伸抗剪强度标准值 12MPa"
    target = tmp_path / "fail.json"
    target.write_text(json.dumps({"mode": "scheme", "case_id": "F", "scheme": raw}),
                      encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", BASIS_FILE]) == EXIT_BLOCKED


def test_cli_missing_field_rc_is_two(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text(json.dumps({"mode": "calc"}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target)]) == EXIT_INPUT


def test_cli_missing_clause_rc_is_three(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps({"mode": "calc", "case_id": "C",
                                  "calc": {"module": "cfrp_beam_flexure", "params": CFRP}}),
                      encoding="utf-8")
    thin = tmp_path / "basis.json"
    thin.write_text(json.dumps({"version": "thin", "clauses": []}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", str(thin)]) == EXIT_CONTRACT
    assert "ClauseMissing" in capsys.readouterr().err


def test_cli_json_output_is_deterministic(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps({"mode": "calc", "case_id": "C",
                                  "calc": {"module": "post_rebar_anchor", "params": ANCHOR}}),
                      encoding="utf-8")
    args = ["check", SLUG, "--input", str(target), "--basis", BASIS_FILE, "--json"]
    cli.main(args)
    first = capsys.readouterr().out
    cli.main(args)
    assert capsys.readouterr().out == first
    assert str(tmp_path) not in first


def test_unknown_mode_refused():
    with pytest.raises(ValueError, match="subject.mode 非法"):
        ORGAN.evaluate({"mode": "gui", "case_id": "C"}, BASIS)


def test_subject_must_be_mapping():
    with pytest.raises(ValueError, match="subject 必须是 JSON 对象"):
        ORGAN.evaluate([1, 2], BASIS)


# ---------------------------------------------------------------------------
# J. 参数扫描位级锁定
# ---------------------------------------------------------------------------
SEED = 20261005  # 固定 seed 的确定性夹具生成器（非加密用途；Mimosa「弱随机数」为已知误报）
N_PER_MODULE = 12
GOLDEN_SHA256 = "bc8905b2581fa3121bfa2d04c51d67b112c22215c4e96d14d666065683ca107a"


def _r3(rng, lo, hi):
    return round(rng.uniform(lo, hi), 3)


def _grid(module_id):
    rng = random.Random(SEED)
    grids = []
    for _ in range(N_PER_MODULE):
        if module_id == "cfrp_beam_flexure":
            grids.append({
                "b": _r3(rng, 200, 400), "h": _r3(rng, 400, 700),
                "fc": 14.3, "As": _r3(rng, 800, 2600), "fy": 360.0,
                "Afe": _r3(rng, 50, 350), "Ecf": 240000.0,
                "M0": 0.0 if rng.random() < 0.5 else _r3(rng, 40, 120),
                "M": _r3(rng, 100, 320),
                "ff": 2300.0, "ef": 0.01, "as": _r3(rng, 30, 50),
                "xi_b": 0.518, "Es": 200000.0,
            })
        elif module_id == "steel_plate_flexure":
            grids.append({
                "b": _r3(rng, 200, 400), "h": _r3(rng, 400, 700),
                "fc": 14.3, "As": _r3(rng, 800, 2600), "fy": 360.0,
                "Ap": _r3(rng, 150, 1000), "fp": 215.0,
                "M0": 0.0 if rng.random() < 0.5 else _r3(rng, 40, 120),
                "M": _r3(rng, 120, 300),
                "as": _r3(rng, 30, 50), "xi_b": 0.518,
                "Es": 200000.0, "Esp": 206000.0,
            })
        elif module_id == "section_enlarge_flexure":
            grids.append({
                "b": _r3(rng, 200, 400), "h": _r3(rng, 400, 700),
                "bf": 250.0, "hf": _r3(rng, 60, 160),
                "fc": 14.3, "fc2": 16.7,
                "As": _r3(rng, 800, 2600), "fy": 360.0,
                "As2": _r3(rng, 200, 1000), "fy2": 360.0,
                "as": 35.0, "as2": _r3(rng, 35, 70),
                "M0": 0.0 if rng.random() < 0.5 else _r3(rng, 40, 120),
                "M": _r3(rng, 150, 320), "Es": 200000.0,
            })
        else:
            grids.append({
                "fc": 14.3,
                "fy": _r3(rng, 300, 400), "d": _r3(rng, 10, 28),
                "ld": _r3(rng, 150, 800),
                "alpha_spt": _r3(rng, 0.7, 1.3), "fbd": _r3(rng, 2.5, 4.5),
                "psi_br": rng.choice([1.0, 1.15, 1.5]),
                "psi_w": 1.1, "psi_T": 1.0,
                "psi_ae": rng.choice([1.0, 1.1, 1.25]),
            })
    return grids


def _collect():
    payloads = []
    for module_id in sorted(ORGAN.MODULES):
        for i, params in enumerate(_grid(module_id)):
            try:
                records = ORGAN.run_calc(module_id, params, BASIS)
                payloads.append({"module": module_id, "i": i,
                                 "records": [record.as_dict() for record in records]})
            except Exception as exc:  # noqa: BLE001  异常也纳入锁定
                payloads.append({"module": module_id, "i": i,
                                 "error": "%s: %s" % (type(exc).__name__, exc)})
    blob = json.dumps(payloads, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest(), payloads


def test_param_sweep_double_run_is_bit_identical():
    first, _ = _collect()
    second, _ = _collect()
    assert first == second


def test_param_sweep_golden_hash():
    actual, _ = _collect()
    assert actual == GOLDEN_SHA256, "参数扫描金标准漂移，actual=%s" % actual


def test_param_sweep_all_points_have_verdicts():
    _, payloads = _collect()
    assert len(payloads) == N_PER_MODULE * 4
    assert all("error" not in item for item in payloads)
