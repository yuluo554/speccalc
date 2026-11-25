"""器官 ``formwork-scaffold`` 的核查测试（构造限值 / 两张皮 / 分级联动 / CLI）。

覆盖面：规则表结构 / threshold 与参数化限值 / only_if 门控 / presence /
grading 联动 / 未核对双层拦截 / 一致性方向定级 / review 记录 / CLI 退出码。
**不使用 parametrize**。
"""

from __future__ import annotations

import copy
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
    EXIT_BLOCKED,
    EXIT_CONTRACT,
    EXIT_INPUT,
    EXIT_OK,
    OK,
    REJECTED,
)
from speccalc.core.data import load as load_data  # noqa: E402
from speccalc.modules import load_builtin  # noqa: E402

load_builtin()
ORGAN = importlib.import_module("speccalc.modules.formwork-scaffold")
SLUG = ORGAN.SLUG
DATA = load_data("formwork-scaffold.json")
PACK = ORGAN.PACK
SAMPLES = os.path.join(ROOT, "samples", "formwork-scaffold")
CALC_SAMPLE = os.path.join(SAMPLES, "calc-example.json")
CALC_FAIL_SAMPLE = os.path.join(SAMPLES, "calc-fail-example.json")
GRADE_SAMPLE = os.path.join(SAMPLES, "grade-example.json")
REVIEW_SAMPLE = os.path.join(SAMPLES, "review-example.json")
BASIS_SAMPLE = os.path.join(SAMPLES, "basis.json")


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

DEFAULTS = {
    "build_height": 12.0, "step": 1.5, "long_spacing": 1.5,
    "cross_spacing": 1.05, "wall_tie": "two_step_three_span",
    "wall_tie_v": 3.0, "wall_tie_h": 4.5, "rows": "double",
    "scissor_brace": True, "expert_review": False, "special_plan": True,
}


def _scheme(project_type="某工程 落地式扣件钢管脚手架专项施工方案", **params):
    values = dict(DEFAULTS)
    values.update(params)
    return ORGAN.Card("scheme", project_type=project_type, params=values)


def _calcbook(**params):
    return ORGAN.Card("calcbook", params=params)


def _grading_for(scheme):
    item_id = ORGAN.recognize_item(PACK, scheme.project_type)
    if item_id is None:
        return ORGAN.judge(PACK, "pan-no-such-item", {})
    return ORGAN.judge(PACK, item_id, scheme.params)


def _run(scheme, calcbook=None, grading_result=None):
    if calcbook is None:
        calcbook = _calcbook()
    if grading_result is None:
        grading_result = _grading_for(scheme)
    return ORGAN.run_checks(PACK, scheme, calcbook, grading_result)


def _finding(findings, rule_id):
    hits = [entry for entry in findings if entry["rule_id"] == rule_id]
    return hits[0] if hits else None


def _confirmation(confirmations, rule_id):
    hits = [entry for entry in confirmations if entry["rule_id"] == rule_id]
    return hits[0] if hits else None


def _review_subject(scheme_params=None, project_type=DEFAULTS and
                    "某工程 落地式扣件钢管脚手架专项施工方案",
                    calcbook_params=None, unknown=None):
    params = dict(DEFAULTS)
    params.update(scheme_params or {})
    scheme = {"project_type": project_type, "params": params}
    if unknown:
        scheme["unknown"] = unknown
    return {"case_id": "REVIEW-1", "mode": "review",
            "review": {"scheme": scheme,
                       "calcbook": {"params": calcbook_params or {
                           "step": 1.5, "long_spacing": 1.5,
                           "cross_spacing": 1.05}}}}


def _records(subject, basis=None):
    return tuple(ORGAN.evaluate(subject, basis if basis is not None else BASIS))


# ---------------------------------------------------------------------------
# A. 规则表结构
# ---------------------------------------------------------------------------
def test_checks_table_has_twelve_rules():
    assert len(DATA["checks"]["rules"]) == 12


def test_checks_table_covers_four_types():
    assert {rule["check_type"] for rule in DATA["checks"]["rules"]} == {
        "threshold", "presence", "consistency", "grading"}


def test_threshold_rules_always_reference_a_limit():
    for rule in DATA["checks"]["rules"]:
        if rule["check_type"] == "threshold":
            assert rule.get("limit_ref"), rule["rule_id"]


def test_rule_ids_unique():
    ids = [rule["rule_id"] for rule in DATA["checks"]["rules"]]
    assert len(ids) == len(set(ids))


def test_every_rule_has_a_basis_key():
    for rule in DATA["checks"]["rules"]:
        assert rule["basis"] in DATA["clauses"], rule["rule_id"]


def test_only_if_is_a_list():
    for rule in DATA["checks"]["rules"]:
        assert isinstance(rule.get("only_if", []), list)


# ---------------------------------------------------------------------------
# B. threshold 规则
# ---------------------------------------------------------------------------
def test_step_over_limit_fires_both_rules():
    findings, _ = _run(_scheme(step=2.4))
    first = _finding(findings, "R-step-limit")
    second = _finding(findings, "R-step-limit-20")
    assert first["verdict"] == "violation" and first["limit_value"] == 1.8
    assert first["actual"] == 2.4 and first["level"] == "不合格"
    assert second["verdict"] == "violation" and second["limit_value"] == 2.0


def test_step_at_limit_passes():
    findings, _ = _run(_scheme(step=1.8))
    assert _finding(findings, "R-step-limit")["verdict"] == "pass"
    assert _finding(findings, "R-step-limit-20")["verdict"] == "pass"


def test_walltie_v_limit_is_three_h_at_step_1_5():
    findings, _ = _run(_scheme(step=1.5, wall_tie_v=6.0))
    finding = _finding(findings, "R-walltie-vspacing")
    assert finding["verdict"] == "violation"
    assert finding["limit_value"] == 4.5


def test_walltie_v_limit_is_three_h_at_step_1_8():
    findings, _ = _run(_scheme(step=1.8, wall_tie_v=5.5))
    assert _finding(findings, "R-walltie-vspacing")["limit_value"] == 5.4


def test_walltie_branch_keeps_three_h_at_fifty():
    findings, _ = _run(_scheme(step=1.5, wall_tie_v=3.2, build_height=50.0))
    finding = _finding(findings, "R-walltie-vspacing")
    assert finding["verdict"] == "pass"
    assert finding["limit_value"] == 4.5


def test_walltie_branch_switches_to_two_h_over_fifty():
    findings, _ = _run(_scheme(step=1.5, wall_tie_v=3.2, build_height=50.1))
    finding = _finding(findings, "R-walltie-vspacing")
    assert finding["verdict"] == "violation"
    assert finding["limit_value"] == 3.0


def test_walltie_area_is_computed_product():
    findings, _ = _run(_scheme(step=1.5, wall_tie_v=9.0, wall_tie_h=4.5))
    finding = _finding(findings, "R-walltie-area")
    assert finding["verdict"] == "violation"
    assert finding["actual"] == 40.5
    assert finding["limit_value"] == 40.0


def test_walltie_horizontal_at_three_la_passes():
    findings, _ = _run(_scheme(step=1.5, wall_tie_h=4.5))
    assert _finding(findings, "R-walltie-hspacing")["verdict"] == "pass"


def test_walltie_horizontal_over_three_la_violates():
    findings, _ = _run(_scheme(step=1.5, wall_tie_h=4.6))
    finding = _finding(findings, "R-walltie-hspacing")
    assert finding["verdict"] == "violation"
    assert finding["limit_value"] == 4.5


# ---------------------------------------------------------------------------
# C. only_if 门控
# ---------------------------------------------------------------------------
def test_gate_excludes_cantilever_from_landed_step_rules():
    findings, _ = _run(_scheme(project_type="某工程 悬挑式扣件钢管脚手架专项施工方案",
                               step=2.4))
    assert _finding(findings, "R-step-limit") is None
    assert _finding(findings, "R-step-limit-20") is None


def test_gate_excludes_scaffold_rules_for_formwork_project():
    scheme = _scheme(project_type="某工程 混凝土模板支撑工程专项施工方案", step=2.0)
    scheme.category = "formwork_support"
    findings, _ = _run(scheme,
                       grading_result=ORGAN.judge(PACK, "pan-muban-zhicheng", {}))
    for rule_id in ("R-step-limit", "R-step-limit-20", "R-walltie-vspacing",
                    "R-brace-presence"):
        assert _finding(findings, rule_id) is None, rule_id
    finding = _finding(findings, "R-formwork-step-limit")
    assert finding["verdict"] == "violation"
    assert finding["limit_value"] == 1.8


def test_gate_excludes_formwork_rule_for_scaffold_project():
    findings, _ = _run(_scheme(step=2.4))
    assert _finding(findings, "R-formwork-step-limit") is None


def test_gate_applies_to_presence_type():
    findings, _ = _run(_scheme(project_type="碗扣式钢管脚手架专项施工方案",
                               scissor_brace=False))
    assert _finding(findings, "R-brace-presence") is None


# ---------------------------------------------------------------------------
# D. presence
# ---------------------------------------------------------------------------
def test_missing_brace_is_violation():
    findings, _ = _run(_scheme(scissor_brace=False))
    finding = _finding(findings, "R-brace-presence")
    assert finding["verdict"] == "violation"
    assert finding["level"] == "不合格"


def test_present_brace_passes():
    findings, _ = _run(_scheme(scissor_brace=True))
    assert _finding(findings, "R-brace-presence")["verdict"] == "pass"


# ---------------------------------------------------------------------------
# E. grading 联动
# ---------------------------------------------------------------------------
def test_expert_review_rule_fires_for_over_scale():
    findings, _ = _run(_scheme(build_height=56.0, expert_review=False))
    finding = _finding(findings, "R-grading-expert-review")
    assert finding["verdict"] == "violation"
    assert finding["level"] == "严重"
    assert finding["actual"] == 56.0
    assert "37号令-第十二条" in finding["clause_refs"]


def test_expert_review_rule_passes_when_documented():
    findings, _ = _run(_scheme(build_height=56.0, expert_review=True))
    assert _finding(findings, "R-grading-expert-review")["verdict"] == "pass"


def test_grading_rules_inapplicable_below_level():
    findings, _ = _run(_scheme(build_height=12.0))
    assert _finding(findings, "R-grading-expert-review")["verdict"] == "pass"
    assert _finding(findings, "R-grading-special-plan")["verdict"] == "pass"


def test_special_plan_rule_fires_for_weida_without_plan():
    findings, _ = _run(_scheme(build_height=30.0, special_plan=False))
    finding = _finding(findings, "R-grading-special-plan")
    assert finding["verdict"] == "violation"
    assert finding["level"] == "不合格"


def test_grading_rule_waits_when_grading_pending():
    scheme = _scheme()
    scheme.params.pop("build_height")
    findings, confirmations = _run(
        scheme, grading_result=ORGAN.judge(PACK, "pan-luodi-gangguan-24", {}))
    assert _finding(findings, "R-grading-expert-review") is None
    confirmation = _confirmation(confirmations, "R-grading-expert-review")
    assert confirmation and "待人工确认" in confirmation["reason"]


# ---------------------------------------------------------------------------
# F. 未核对双层拦截
# ---------------------------------------------------------------------------
def test_unverified_rule_is_skipped_with_confirmation():
    rules = ORGAN.Rules(copy.deepcopy(DATA))
    rules.checks["rules"][0]["status"] = "待核对"
    findings, confirmations = ORGAN.run_checks(
        rules, _scheme(step=2.4), _calcbook(), _grading_for(_scheme()))
    assert _finding(findings, "R-step-limit") is None
    confirmation = _confirmation(confirmations, "R-step-limit")
    assert confirmation and "待核对" in confirmation["reason"]


def test_unverified_threshold_entry_blocks_rule():
    rules = ORGAN.Rules(copy.deepcopy(DATA))
    rules.thresholds["T-JGJ130-step-max"]["status"] = "待核对"
    findings, confirmations = ORGAN.run_checks(
        rules, _scheme(step=2.4), _calcbook(), _grading_for(_scheme()))
    assert _finding(findings, "R-step-limit") is None
    confirmation = _confirmation(confirmations, "R-step-limit")
    assert confirmation and "不可用" in confirmation["reason"]


def test_missing_limit_ref_entry_blocks_rule():
    rules = ORGAN.Rules(copy.deepcopy(DATA))
    rules.thresholds.pop("T-JGJ130-step-max")
    findings, confirmations = ORGAN.run_checks(
        rules, _scheme(step=2.4), _calcbook(), _grading_for(_scheme()))
    assert _finding(findings, "R-step-limit") is None
    assert _confirmation(confirmations, "R-step-limit")


def test_missing_branch_params_become_confirmation():
    scheme = _scheme()
    scheme.params.pop("rows")
    findings, confirmations = _run(scheme)
    confirmation = _confirmation(confirmations, "R-walltie-vspacing")
    assert confirmation and "分支" in confirmation["reason"]


# ---------------------------------------------------------------------------
# G. 两张皮一致性
# ---------------------------------------------------------------------------
CONSISTENCY_RULE = {"rule_id": "R-consistency-step", "name": "验算书步距取值与方案正文一致",
                    "check_type": "consistency", "param": "step", "level": "不合格",
                    "clause_refs": ["37号令-第十六条"]}


def _consistency(scheme_value, calcbook_value, rule=None):
    rule = rule or CONSISTENCY_RULE
    scheme = ORGAN.Card("scheme", params={"step": scheme_value})
    calcbook = ORGAN.Card("calcbook", params={"step": calcbook_value})
    return ORGAN.check_consistency(rule, scheme, calcbook, PACK)


def test_identical_values_pass():
    kind, finding = _consistency(1.8, 1.8)
    assert kind == "finding"
    assert finding["verdict"] == "pass"
    assert finding["level"] is None


def test_within_tolerance_passes():
    kind, finding = _consistency(1.8, 1.805)
    assert finding["verdict"] == "pass"


def test_over_tolerance_violates():
    kind, finding = _consistency(1.8, 1.82)
    assert finding["verdict"] == "violation"


def test_scheme_worse_is_unqualified():
    kind, finding = _consistency(1.8, 1.5)
    assert finding["level"] == "不合格"
    assert "实况未被验算覆盖" in finding["impact"]
    assert "37号令-第十六条" in finding["clause_refs"]


def test_scheme_better_is_hint():
    kind, finding = _consistency(1.5, 1.8)
    assert finding["verdict"] == "violation"
    assert finding["level"] == "提示"
    assert "偏保守" in finding["impact"]


def test_missing_calcbook_side_becomes_confirmation():
    scheme = ORGAN.Card("scheme", params={"step": 1.8})
    calcbook = ORGAN.Card("calcbook", params={})
    kind, payload = ORGAN.check_consistency(
        CONSISTENCY_RULE, scheme, calcbook, PACK)
    assert kind == "confirmation"
    assert "验算书卡缺少字段 step" in payload["reason"]


def test_missing_scheme_side_becomes_confirmation():
    scheme = ORGAN.Card("scheme", params={})
    calcbook = ORGAN.Card("calcbook", params={"step": 1.8})
    kind, payload = ORGAN.check_consistency(
        CONSISTENCY_RULE, scheme, calcbook, PACK)
    assert kind == "confirmation"
    assert "方案卡缺少字段 step" in payload["reason"]


def test_worse_sign_minus_one_respected():
    rule = dict(CONSISTENCY_RULE, worse_sign=-1)
    kind, finding = _consistency(1.5, 1.8, rule)
    assert finding["verdict"] == "violation"
    assert finding["level"] == "不合格"


def test_worse_sign_minus_one_other_direction_is_hint():
    rule = dict(CONSISTENCY_RULE, worse_sign=-1)
    kind, finding = _consistency(1.8, 1.5, rule)
    assert finding["level"] == "提示"


# ---------------------------------------------------------------------------
# H. review 记录
# ---------------------------------------------------------------------------
def test_review_pass_emits_twelve_records():
    records = _records(_review_subject())
    assert len(records) == 12
    assert all(record.verdict == OK for record in records)


def test_review_violation_counts():
    subject = _review_subject(scheme_params={
        "build_height": 56.0, "step": 2.4, "wall_tie_v": 6.0, "wall_tie_h": 4.6,
        "scissor_brace": False, "expert_review": False, "special_plan": False},
        calcbook_params={"step": 1.8, "long_spacing": 1.5, "cross_spacing": 1.05})
    records = _records(subject)
    assert len(records) == 12
    rejected = [record for record in records if record.verdict == REJECTED]
    assert len(rejected) == 8


def test_review_grading_record_level():
    records = _records(_review_subject(scheme_params={"build_height": 56.0}))
    grading = [record for record in records
               if record.item_id.startswith("grading.")][0]
    assert grading.verdict == OK
    assert grading.evidence["level"] == "chaoguimo"


def test_review_pending_grading_record():
    subject = _review_subject(scheme_params={"build_height": None})
    records = _records(subject)
    pending = [record for record in records if record.item_id == "grading.pending"]
    assert pending
    assert pending[0].verdict == OK
    assert pending[0].evidence["status"] == "pending"


def test_review_unrecognized_type_pending_record():
    subject = _review_subject(project_type="基坑支护及土方开挖专项施工方案")
    records = _records(subject)
    pending = [record for record in records if record.item_id == "grading.pending"]
    assert pending
    assert pending[0].basis.clause == "第一条"


def test_review_rule_record_has_basis():
    records = _records(_review_subject())
    rule_record = [record for record in records
                   if record.item_id == "rule.R-step-limit"][0]
    assert rule_record.basis.code == "JGJ 130-2011"
    assert rule_record.basis.clause == "6.1.1"


def test_review_records_deterministic():
    subject = _review_subject()
    first = [record.as_dict() for record in _records(subject)]
    second = [record.as_dict() for record in _records(subject)]
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True)


def test_review_unknown_category_rejected():
    subject = _review_subject()
    subject["review"]["scheme"]["category"] = "no_such_category"
    with pytest.raises(ValueError):
        _records(subject)


# ---------------------------------------------------------------------------
# I. CLI 退出码
# ---------------------------------------------------------------------------
def test_cli_calc_pass_returns_zero():
    assert cli.main(["check", SLUG, "--input", CALC_SAMPLE,
                     "--basis", BASIS_SAMPLE]) == EXIT_OK


def test_cli_calc_fail_returns_blocked():
    assert cli.main(["check", SLUG, "--input", CALC_FAIL_SAMPLE,
                     "--basis", BASIS_SAMPLE]) == EXIT_BLOCKED


def test_cli_grade_returns_zero():
    assert cli.main(["check", SLUG, "--input", GRADE_SAMPLE,
                     "--basis", BASIS_SAMPLE]) == EXIT_OK


def test_cli_review_pass_returns_zero():
    assert cli.main(["check", SLUG, "--input", REVIEW_SAMPLE,
                     "--basis", BASIS_SAMPLE]) == EXIT_OK


def test_cli_review_violation_returns_blocked(tmp_path):
    subject = _review_subject(scheme_params={"step": 2.4, "scissor_brace": False})
    path = tmp_path / "review.json"
    path.write_text(json.dumps(subject, ensure_ascii=False), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(path),
                     "--basis", BASIS_SAMPLE]) == EXIT_BLOCKED


def test_cli_missing_basis_returns_contract_error():
    assert cli.main(["check", SLUG, "--input", CALC_SAMPLE]) == EXIT_CONTRACT


def test_cli_missing_input_returns_input_error():
    assert cli.main(["check", SLUG, "--input",
                     os.path.join(SAMPLES, "no-such.json"),
                     "--basis", BASIS_SAMPLE]) == EXIT_INPUT


def test_cli_unknown_slug_returns_contract_error():
    assert cli.main(["check", "no-such-organ", "--input", CALC_SAMPLE,
                     "--basis", BASIS_SAMPLE]) == EXIT_CONTRACT


def test_cli_json_output_is_deterministic(capsys):
    assert cli.main(["check", SLUG, "--input", CALC_SAMPLE,
                     "--basis", BASIS_SAMPLE, "--json"]) == EXIT_OK
    first = capsys.readouterr().out
    assert cli.main(["check", SLUG, "--input", CALC_SAMPLE,
                     "--basis", BASIS_SAMPLE, "--json"]) == EXIT_OK
    second = capsys.readouterr().out
    assert first == second