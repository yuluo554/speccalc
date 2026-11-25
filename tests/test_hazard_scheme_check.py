"""器官 ``hazard-scheme-check`` 的无损测试（迁自 target-map ③ 行 / 仓库 #46）。

覆盖面：注册与数据契约 / 输入校验 / 7 类规则的 ok·rejected·needs_confirm 三路径 /
only_if_text 门控 / 多值冲突 / 记录形态与确定性 / CLI 退出码 / 两个样例端到端。

口径：
- D18 新正则下旧仓判定层实跑 **68 passed + 4 skipped**（7 文件 / 72 collected）；
- 旧层 AST 函数数按旧记录 86（本次实测 7 文件 72 / 8 文件 107，取保守门槛 86）；
- 本文件不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数），
  每条用例都有独立断言。
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
from speccalc.modules import BUILTIN_MODULES, load_builtin  # noqa: E402

load_builtin()
ORGAN = importlib.import_module("speccalc.modules.hazard-scheme-check")
SLUG = ORGAN.SLUG
DATA = ORGAN.DATA
PACK = ORGAN.PACK

SAMPLES = os.path.join(ROOT, "samples", "hazard-scheme-check")
BASIS_FILE = os.path.join(SAMPLES, "basis.json")
BASIS = Basis.from_json(BASIS_FILE)
GEN_PATH = os.path.join(SAMPLES, "gen-0001-deep-pit.json")
FORM_PATH = os.path.join(SAMPLES, "formwork-high.json")

_DEFAULT = object()

SECTIONS = [
    "一、工程概况",
    "二、编制依据",
    "三、施工计划",
    "四、施工工艺技术",
    "五、施工安全保证措施",
    "5.2 监测方案",
    "六、施工管理及作业人员配备和分工",
    "七、验收要求",
    "八、应急处置措施",
    "九、计算书及相关图纸",
]
DOC_LINES = [
    "本工程为深基坑，基坑开挖深度4.6m。",
    "基坑监测方案已编制，监测频率0.5次/d。",
    "本专项施工方案已组织专家论证。",
]
DOC = {"sections": SECTIONS, "lines": DOC_LINES}

FORM_SECTIONS = [
    "工程概况", "编制依据", "施工计划", "施工工艺技术",
    "施工安全保证措施", "施工管理及作业人员配备和分工",
    "验收要求", "计算书及相关图纸",
]
FORM_LINES = [
    "模板支撑体系搭设高度为8.5m。",
    "立杆纵距、横距均为1.5m。",
    "采用扣件式钢管模板支撑体系。",
    "本专项施工方案经施工单位技术负责人审核批准。",
    "本方案已组织专家论证。",
]
FORM_DOC = {"sections": FORM_SECTIONS, "lines": FORM_LINES}


def _sample(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as handle:
        return json.load(handle)


GEN = _sample("gen-0001-deep-pit.json")
FORM = _sample("formwork-high.json")


def _card(pid, value=None, text=None, unit="", line="", raw=""):
    card = {
        "param_id": pid,
        "value": value,
        "text_value": text,
        "unit": unit,
        "raw_text": raw,
    }
    if line:
        card["evidence"] = {"line_text": line}
    return card


def _subject(category, cards, document=_DEFAULT, case_id="CASE-T"):
    subject = {"case_id": case_id, "category": category, "cards": cards}
    if document is _DEFAULT:
        subject["document"] = DOC
    elif document is not None:
        subject["document"] = document
    return subject


def _run(cards, category="deep_pit", document=_DEFAULT, basis=BASIS, case_id="CASE-T"):
    return tuple(ORGAN.evaluate(_subject(category, cards, document, case_id=case_id), basis))


def _row(records, rule_id):
    hits = [record for record in records if record.item_id == rule_id]
    assert len(hits) == 1, (rule_id, [record.item_id for record in records])
    return hits[0]


def _hits(records, rule_id):
    return [record for record in records if record.item_id == rule_id]


def _base_cards():
    return [
        _card("dp.excavation_depth", 4.6, unit="m", line="基坑开挖深度为4.6m。"),
        _card("dp.support_type", text="放坡+土钉墙", line="采用放坡+土钉墙支护形式。"),
        _card("dp.safety_grade", text="二级", line="基坑侧壁安全等级为二级。"),
        _card("dp.retaining.displacement", 35.0, unit="mm", line="位移控制值为35mm。"),
        _card("dp.monitoring.frequency", 0.5, unit="次/d", line="监测频率为0.5次/d。"),
    ]


def _form_cards(height=8.5, spacing=1.5, formwork_type="扣件式"):
    cards = []
    if height is not None:
        cards.append(_card("fs.support.height", height, unit="m", line="搭设高度8.5m。"))
    if spacing is not None:
        cards.append(_card("fs.pole.spacing", spacing, unit="m", line="立杆间距1.5m。"))
    if formwork_type is not None:
        cards.append(_card("fs.formwork.type", text=formwork_type, line="采用扣件式支撑。"))
    return cards


# ---------------------------------------------------------------------------
# A. 注册与数据契约
# ---------------------------------------------------------------------------
def test_organ_registered():
    assert get(SLUG).slug == SLUG


def test_organ_version_is_0_1_0():
    assert get(SLUG).version == "0.1.0"


def test_organ_summary_mentions_29_rules():
    assert "29 条规则" in get(SLUG).summary


def test_organ_summary_mentions_deep_pit_and_formwork():
    summary = get(SLUG).summary
    assert "深基坑" in summary and "高支模" in summary


def test_input_fields_are_case_category_cards():
    assert get(SLUG).input_fields == ("case_id", "category", "cards")


def test_builtin_manifest_is_exactly_six_sorted_organs():
    assert list(BUILTIN_MODULES) == [
        "excavation-monitor", "formwork-scaffold", "hazard-scheme-check",
        "member-strengthening", "pavement-mqi", "steel-member",
    ]
    assert list(BUILTIN_MODULES) == sorted(BUILTIN_MODULES)


def test_cli_list_shows_all_six_organs(capsys):
    assert cli.main(["list"]) == EXIT_OK
    lines = [line.split()[0] for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert [slug for slug in lines if slug in BUILTIN_MODULES] == list(BUILTIN_MODULES)


def test_data_organ_matches_slug():
    assert DATA["organ"] == SLUG


def test_data_version_matches_pack():
    assert DATA["version"] == get(SLUG).version


def test_data_source_head_is_0cad8a5():
    assert DATA["source"]["head"] == "0cad8a5"


def test_data_source_repo_is_weida_plan_review():
    assert DATA["source"]["repo"] == "weida-plan-review"


def test_data_declares_29_rules():
    assert len(DATA["rules"]) == 29
    assert DATA["clause_inventory"]["total_rules"] == 29


def test_data_categories_are_19_and_10():
    assert DATA["clause_inventory"]["categories"] == {
        "deep_pit": 19, "formwork_support": 10}


def test_data_standard_backed_and_sanity_counts():
    assert DATA["clause_inventory"]["standard_backed"] == 23
    assert DATA["clause_inventory"]["sanity_only"] == 6


def test_data_all_rules_pending_review():
    assert DATA["clause_inventory"]["pending_review"] == 29
    assert {entry["status"] for entry in DATA["clauses"].values()} == {"待核对"}


def test_data_clause_codes_cover_five_standards():
    assert DATA["clause_inventory"]["standards"] == [
        "建办质〔2018〕31号", "住建部令第37号", "JGJ 120-2012",
        "GB 50497-2019", "JGJ 162-2008",
    ]


def test_data_rule_ids_are_sorted():
    ids = [rule["id"] for rule in DATA["rules"]]
    assert ids == sorted(ids)


def test_data_deep_pit_rule_ids_start_with_dp():
    ids = [rule["id"] for rule in DATA["rules"] if rule["category"] == "deep_pit"]
    assert all(rule_id.startswith("R-DP-") for rule_id in ids)


def test_data_formwork_rule_ids_start_with_fs():
    ids = [rule["id"] for rule in DATA["rules"] if rule["category"] == "formwork_support"]
    assert all(rule_id.startswith("R-FS-") for rule_id in ids)


def test_data_check_types_cover_seven():
    assert {rule["check_type"] for rule in DATA["rules"]} == {
        "required", "threshold_min", "threshold_max", "within_range",
        "enum", "conditional_program", "checklist_section",
    }


def test_data_threshold_status_carries_example_markers():
    by_id = {rule["id"]: rule for rule in DATA["rules"]}
    for rule_id in ("R-DP-021", "R-DP-031", "R-FS-031"):
        assert "示例阈值" in by_id[rule_id]["threshold_status"]


def test_data_sanity_rules_are_six_exact_ids():
    sanity = {rule_id for rule_id, entry in DATA["clauses"].items()
              if entry["basis_kind"] == "sanity"}
    assert sanity == {
        "R-DP-022", "R-DP-062", "R-DP-063", "R-DP-072", "R-DP-073", "R-FS-012",
    }


def test_data_clause_versions_are_non_empty():
    assert all(entry["version"] for entry in DATA["clauses"].values())


def test_data_constants_declare_policies():
    constants = DATA["constants"]
    assert "needs_confirm" in constants["multi_value_policy"]
    assert "needs_confirm" in constants["sanity_policy"]
    assert "待核对" in constants["status_policy"]


def test_validate_data_rejects_wrong_rule_count():
    broken = copy.deepcopy(DATA)
    broken["rules"] = broken["rules"][:-1]
    with pytest.raises(ContractError, match="29"):
        ORGAN.validate_data(broken)


def test_validate_data_rejects_duplicate_rule_id():
    broken = copy.deepcopy(DATA)
    broken["rules"][1]["id"] = broken["rules"][0]["id"]
    with pytest.raises(ContractError, match="重复"):
        ORGAN.validate_data(broken)


def test_validate_data_rejects_unknown_category():
    broken = copy.deepcopy(DATA)
    broken["rules"][0]["category"] = "lifting"
    with pytest.raises(ContractError, match="category"):
        ORGAN.validate_data(broken)


def test_validate_data_rejects_bad_check_type():
    broken = copy.deepcopy(DATA)
    broken["rules"][0]["check_type"] = "formula"
    with pytest.raises(ContractError, match="check_type"):
        ORGAN.validate_data(broken)


def test_validate_data_rejects_missing_param():
    broken = copy.deepcopy(DATA)
    broken["rules"][0]["param"] = ""
    with pytest.raises(ContractError, match="param"):
        ORGAN.validate_data(broken)


def test_validate_data_rejects_unregistered_basis_key():
    broken = copy.deepcopy(DATA)
    broken["rules"][0]["basis_key"] = "R-NO-SUCH"
    with pytest.raises(ContractError, match="basis_key"):
        ORGAN.validate_data(broken)


# ---------------------------------------------------------------------------
# B. 输入契约
# ---------------------------------------------------------------------------
def test_subject_must_be_mapping():
    with pytest.raises(ValueError, match="JSON 对象"):
        ORGAN.evaluate([1, 2, 3], BASIS)


def test_missing_case_id_is_refused():
    with pytest.raises(ValueError, match="case_id"):
        ORGAN.evaluate({"category": "deep_pit", "cards": []}, BASIS)


def test_blank_case_id_is_refused():
    with pytest.raises(ValueError, match="case_id 不能为空"):
        ORGAN.evaluate({"case_id": "  ", "category": "deep_pit", "cards": []}, BASIS)


def test_missing_category_is_refused():
    with pytest.raises(ValueError, match="category"):
        ORGAN.evaluate({"case_id": "C", "cards": []}, BASIS)


def test_unknown_category_is_refused():
    with pytest.raises(ValueError, match="category 非法"):
        ORGAN.evaluate({"case_id": "C", "category": "lifting", "cards": []}, BASIS)


def test_unknown_category_error_lists_both_options():
    with pytest.raises(ValueError, match="formwork_support"):
        ORGAN.evaluate({"case_id": "C", "category": "lifting", "cards": []}, BASIS)


def test_missing_cards_is_refused():
    with pytest.raises(ValueError, match="cards"):
        ORGAN.evaluate({"case_id": "C", "category": "deep_pit"}, BASIS)


def test_cards_must_be_array():
    with pytest.raises(ValueError, match="cards 必须是数组"):
        ORGAN.evaluate({"case_id": "C", "category": "deep_pit", "cards": {}}, BASIS)


def test_card_must_be_object():
    with pytest.raises(ValueError, match="cards\\[0\\] 必须是对象"):
        ORGAN.evaluate({"case_id": "C", "category": "deep_pit", "cards": ["x"]}, BASIS)


def test_card_missing_param_id_is_refused():
    with pytest.raises(ValueError, match="param_id"):
        _run([{"value": 4.6}])


def test_card_value_must_be_number():
    with pytest.raises(ValueError, match="必须是数值"):
        _run([_card("dp.excavation_depth", "4.6")])


def test_card_bool_value_is_refused():
    with pytest.raises(ValueError, match="必须是数值"):
        _run([_card("dp.excavation_depth", True)])


def test_card_infinite_value_is_refused():
    with pytest.raises(ValueError, match="有限数值"):
        _run([_card("dp.excavation_depth", float("inf"))])


def test_card_text_value_must_be_string():
    with pytest.raises(ValueError, match="必须是字符串"):
        _run([_card("dp.support_type", text=123)])


def test_card_evidence_must_be_object():
    card = _card("dp.excavation_depth", 4.6)
    card["evidence"] = "line"
    with pytest.raises(ValueError, match="evidence 必须是对象"):
        _run([card])


def test_document_must_be_object():
    with pytest.raises(ValueError, match="document 必须是对象"):
        _run([], document="doc")


def test_document_sections_must_be_array():
    with pytest.raises(ValueError, match="document.sections 必须是数组"):
        _run([], document={"sections": "工程概况", "lines": []})


def test_document_lines_must_be_array():
    with pytest.raises(ValueError, match="document.lines 必须是数组"):
        _run([], document={"sections": [], "lines": "line"})


def test_document_section_item_must_be_string_or_object():
    with pytest.raises(ValueError, match="必须是字符串或对象"):
        _run([], document={"sections": [1], "lines": []})


def test_document_accepts_object_sections_and_lines():
    document = {"sections": [{"title": "工程概况"}], "lines": [{"text": "基坑"}]}
    assert _row(_run([], document=document), "R-DP-001").verdict == REJECTED


def test_unknown_param_cards_are_ignored():
    records = _run([_card("dp.unknown", 1.0)])
    assert "dp.unknown" not in {record.evidence["param"] for record in records}


def test_unknown_param_does_not_change_record_count():
    assert len(_run([_card("dp.unknown", 1.0)])) == len(_run([]))


# ---------------------------------------------------------------------------
# C. required 规则
# ---------------------------------------------------------------------------
def test_required_depth_missing_is_rejected():
    assert _row(_run([]), "R-DP-001").verdict == REJECTED


def test_required_depth_present_is_ok():
    assert _row(_run([_card("dp.excavation_depth", 4.6, unit="m")]), "R-DP-001").verdict == OK


def test_required_uses_text_value():
    record = _row(_run([_card("dp.support_type", text="放坡")]), "R-DP-002")
    assert record.verdict == OK and "放坡" in record.message


def test_required_uses_raw_text_when_value_empty():
    record = _row(_run([_card("dp.excavation_depth", raw="4.6m")]), "R-DP-001")
    assert record.verdict == OK and "4.6m" in record.message


def test_required_uses_placeholder_when_card_empty():
    record = _row(_run([_card("dp.excavation_depth")]), "R-DP-001")
    assert record.verdict == OK and "空值" in record.message


def test_required_message_contains_param_id_when_missing():
    assert "dp.monitoring.frequency" in _row(_run([]), "R-DP-032").message


def test_required_evidence_card_count_is_two():
    cards = [_card("dp.excavation_depth", 4.6), _card("dp.excavation_depth", 4.8)]
    assert _row(_run(cards), "R-DP-001").evidence["card_count"] == 2


def test_required_basis_clause_is_content_list():
    assert _row(_run([]), "R-DP-001").basis.clause == "内容清单（条号待核对）"


def test_empty_cards_fail_five_required_rules():
    records = _run([])
    rejected = {record.item_id for record in records if record.verdict == REJECTED}
    assert rejected == {"R-DP-001", "R-DP-002", "R-DP-003", "R-DP-004", "R-DP-032"}


def test_empty_cards_total_records_are_seven():
    assert len(_run([])) == 7


# ---------------------------------------------------------------------------
# D. threshold_min / threshold_max
# ---------------------------------------------------------------------------
def test_displacement_35_is_rejected():
    assert _row(_run([_card("dp.retaining.displacement", 35.0)]), "R-DP-021").verdict == REJECTED


def test_displacement_30_is_ok():
    assert _row(_run([_card("dp.retaining.displacement", 30.0)]), "R-DP-021").verdict == OK


def test_displacement_31_is_rejected():
    assert _row(_run([_card("dp.retaining.displacement", 31.0)]), "R-DP-021").verdict == REJECTED


def test_displacement_message_contains_actual_and_limit():
    message = _row(_run([_card("dp.retaining.displacement", 35.0)]), "R-DP-021").message
    assert "35mm" in message and "30mm" in message


def test_displacement_basis_clause_is_chapter_8():
    assert _row(_run([_card("dp.retaining.displacement", 35.0)]), "R-DP-021").basis.clause == "第8章（待核对）"


def test_frequency_below_one_is_rejected():
    assert _row(_run([_card("dp.monitoring.frequency", 0.5)]), "R-DP-031").verdict == REJECTED


def test_frequency_one_is_ok():
    assert _row(_run([_card("dp.monitoring.frequency", 1.0)]), "R-DP-031").verdict == OK


def test_frequency_below_two_is_rejected_by_warning_rule():
    assert _row(_run([_card("dp.monitoring.frequency", 0.5)]), "R-DP-061").verdict == REJECTED


def test_frequency_two_is_ok():
    assert _row(_run([_card("dp.monitoring.frequency", 2.0)]), "R-DP-061").verdict == OK


def test_frequency_above_24_is_sanity_needs_confirm():
    record = _row(_run([_card("dp.monitoring.frequency", 25.0)]), "R-DP-072")
    assert record.verdict == OK and record.evidence["plan_verdict"] == "needs_confirm"


def test_displacement_below_5_is_sanity_needs_confirm():
    record = _row(_run([_card("dp.retaining.displacement", 4.0)]), "R-DP-062")
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_displacement_above_500_is_sanity_needs_confirm():
    record = _row(_run([_card("dp.retaining.displacement", 501.0)]), "R-DP-073")
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_sanity_fail_does_not_block():
    record = _row(_run([_card("dp.retaining.displacement", 501.0)]), "R-DP-073")
    assert record.verdict == OK


def test_sanity_fail_message_keeps_actual_and_limit():
    message = _row(_run([_card("dp.retaining.displacement", 501.0)]), "R-DP-073").message
    assert "501mm" in message and "500mm" in message


def test_threshold_evidence_formula():
    evidence = _row(_run([_card("dp.retaining.displacement", 35.0)]), "R-DP-021").evidence
    assert evidence["formula"] == "35 <= 30"


def test_threshold_evidence_limit_is_number():
    assert _row(_run([_card("dp.retaining.displacement", 35.0)]), "R-DP-021").evidence["limit"] == 30.0


def test_threshold_evidence_actual_is_number():
    assert _row(_run([_card("dp.retaining.displacement", 35.0)]), "R-DP-021").evidence["actual"] == 35.0


def test_multiple_distinct_values_are_needs_confirm():
    cards = [_card("dp.retaining.displacement", 35.0), _card("dp.retaining.displacement", 40.0)]
    record = _row(_run(cards), "R-DP-021")
    assert record.verdict == OK and record.evidence["plan_verdict"] == "needs_confirm"


def test_multiple_distinct_values_message_lists_both():
    cards = [_card("dp.retaining.displacement", 35.0), _card("dp.retaining.displacement", 40.0)]
    message = _row(_run(cards), "R-DP-021").message
    assert "35" in message and "40" in message and "待人工确认" in message


def test_duplicate_same_value_is_not_multi_value():
    cards = [_card("dp.retaining.displacement", 35.0), _card("dp.retaining.displacement", 35.0)]
    assert _row(_run(cards), "R-DP-021").verdict == REJECTED


def test_missing_numeric_value_emits_no_threshold_row():
    assert not _hits(_run([_card("dp.retaining.displacement")]), "R-DP-021")


def test_non_numeric_card_does_not_trigger_threshold():
    assert not _hits(_run([_card("dp.retaining.displacement", text="35mm")]), "R-DP-021")


# ---------------------------------------------------------------------------
# E. within_range
# ---------------------------------------------------------------------------
def test_depth_4_6_in_range_is_ok():
    assert _row(_run([_card("dp.excavation_depth", 4.6)]), "R-DP-063").verdict == OK


def test_depth_below_2_is_sanity_needs_confirm():
    record = _row(_run([_card("dp.excavation_depth", 1.0)]), "R-DP-063")
    assert record.verdict == OK and record.evidence["plan_verdict"] == "needs_confirm"


def test_depth_above_50_is_sanity_needs_confirm():
    record = _row(_run([_card("dp.excavation_depth", 51.0)]), "R-DP-063")
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_depth_lower_boundary_is_ok():
    assert _row(_run([_card("dp.excavation_depth", 2.0)]), "R-DP-063").verdict == OK


def test_depth_upper_boundary_is_ok():
    assert _row(_run([_card("dp.excavation_depth", 50.0)]), "R-DP-063").verdict == OK


def test_range_message_contains_bracket():
    assert "[2,50]m" in _row(_run([_card("dp.excavation_depth", 4.6)]), "R-DP-063").message


def test_range_evidence_limit_is_dict():
    evidence = _row(_run([_card("dp.excavation_depth", 4.6)]), "R-DP-063").evidence
    assert evidence["limit"] == {"min": 2.0, "max": 50.0}


def test_displacement_4_is_sanity_needs_confirm():
    record = _row(_run([_card("dp.retaining.displacement", 4.0)]), "R-DP-022")
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_displacement_5_is_ok():
    assert _row(_run([_card("dp.retaining.displacement", 5.0)]), "R-DP-022").verdict == OK


def test_displacement_100_is_ok():
    assert _row(_run([_card("dp.retaining.displacement", 100.0)]), "R-DP-022").verdict == OK


def test_displacement_101_is_sanity_needs_confirm():
    record = _row(_run([_card("dp.retaining.displacement", 101.0)]), "R-DP-022")
    assert record.evidence["plan_verdict"] == "needs_confirm"


def test_range_basis_is_sanity_code():
    assert _row(_run([_card("dp.excavation_depth", 4.6)]), "R-DP-063").basis.code == "工程合理性校核（非规范条款）"


# ---------------------------------------------------------------------------
# F. enum
# ---------------------------------------------------------------------------
def test_safety_grade_second_is_ok():
    assert _row(_run([_card("dp.safety_grade", text="二级")]), "R-DP-041").verdict == OK


def test_safety_grade_first_is_ok():
    assert _row(_run([_card("dp.safety_grade", text="一级")]), "R-DP-041").verdict == OK


def test_safety_grade_unknown_is_rejected():
    assert _row(_run([_card("dp.safety_grade", text="四级")]), "R-DP-041").verdict == REJECTED


def test_support_type_pile_anchor_is_ok():
    assert _row(_run([_card("dp.support_type", text="桩锚")]), "R-DP-042").verdict == OK


def test_support_type_unknown_is_rejected():
    assert _row(_run([_card("dp.support_type", text="逆作法")]), "R-DP-042").verdict == REJECTED


def test_enum_substring_match_is_bidirectional():
    assert _row(_run([_card("dp.support_type", text="放坡+土钉墙")]), "R-DP-042").verdict == OK


def test_enum_multiple_cards_emit_multiple_rows():
    cards = [_card("dp.safety_grade", text="二级"), _card("dp.safety_grade", text="三级")]
    assert len(_hits(_run(cards), "R-DP-041#1")) == 1
    assert len(_hits(_run(cards), "R-DP-041#2")) == 1


def test_enum_multiple_rows_have_indexed_item_ids():
    cards = [_card("dp.safety_grade", text="二级"), _card("dp.safety_grade", text="三级")]
    item_ids = [record.item_id for record in _run(cards) if record.item_id.startswith("R-DP-041")]
    assert item_ids == ["R-DP-041#1", "R-DP-041#2"]


def test_enum_numeric_only_card_emits_nothing():
    assert not _hits(_run([_card("dp.safety_grade", 2.0)]), "R-DP-041")


def test_enum_message_lists_allowed_on_failure():
    message = _row(_run([_card("dp.safety_grade", text="四级")]), "R-DP-041").message
    assert "一级" in message and "二级" in message and "三级" in message


def test_enum_basis_clause_is_3_1_2():
    assert _row(_run([_card("dp.safety_grade", text="二级")]), "R-DP-041").basis.clause == "3.1.2（待核对）"


def test_support_type_allowed_has_eleven_options():
    rule = PACK.rule("R-DP-042")
    assert len(rule["allowed"]) == 11


# ---------------------------------------------------------------------------
# G. conditional_program
# ---------------------------------------------------------------------------
def test_depth_over_3_triggers_monitoring_rule():
    assert _row(_run([_card("dp.excavation_depth", 4.6)]), "R-DP-103").verdict == OK


def test_monitoring_text_missing_is_rejected():
    document = {"sections": SECTIONS, "lines": ["基坑开挖深度4.6m。"]}
    assert _row(_run([_card("dp.excavation_depth", 4.6)], document=document), "R-DP-103").verdict == REJECTED


def test_depth_below_3_does_not_trigger_monitoring():
    assert not _hits(_run([_card("dp.excavation_depth", 2.9)]), "R-DP-103")


def test_depth_boundary_3_triggers_monitoring():
    assert _hits(_run([_card("dp.excavation_depth", 3.0)]), "R-DP-103")


def test_depth_5_triggers_expert_review():
    assert _row(_run([_card("dp.excavation_depth", 5.0)]), "R-DP-101").verdict == OK


def test_expert_review_text_missing_is_rejected():
    document = {"sections": SECTIONS, "lines": ["基坑开挖深度5m。", "基坑监测方案已编制。"]}
    assert _row(_run([_card("dp.excavation_depth", 5.0)], document=document), "R-DP-101").verdict == REJECTED


def test_expert_review_text_present_is_ok():
    record = _row(_run([_card("dp.excavation_depth", 5.0)]), "R-DP-101")
    assert record.verdict == OK and record.evidence["text_found"] is True


def test_conditional_evidence_condition_is_dict():
    assert _row(_run([_card("dp.excavation_depth", 4.6)]), "R-DP-103").evidence["limit"] == {"min": 3}


def test_conditional_evidence_require_text():
    assert _row(_run([_card("dp.excavation_depth", 4.6)]), "R-DP-103").evidence["require_text"] == "监测"


def test_conditional_without_document_is_skipped():
    assert not _hits(_run([_card("dp.excavation_depth", 5.0)], document=None), "R-DP-101")


def test_formwork_height_8_5_triggers_expert_review():
    records = _run(_form_cards(height=8.5), category="formwork_support", document=FORM_DOC)
    assert _row(records, "R-FS-101").verdict == OK


def test_formwork_height_5_triggers_special_scheme():
    records = _run(_form_cards(height=5.0), category="formwork_support", document=FORM_DOC)
    assert _row(records, "R-FS-102").verdict == OK


def test_formwork_height_4_9_does_not_trigger_special_scheme():
    records = _run(_form_cards(height=4.9), category="formwork_support", document=FORM_DOC)
    assert not _hits(records, "R-FS-102")


# ---------------------------------------------------------------------------
# H. checklist_section
# ---------------------------------------------------------------------------
def test_checklist_all_sections_pass():
    assert _row(_run([]), "R-DP-051").verdict == OK


def test_checklist_missing_one_is_rejected():
    sections = [title for title in SECTIONS if title != "八、应急处置措施"]
    records = _run([], document={"sections": sections, "lines": DOC_LINES})
    assert _row(records, "R-DP-051").verdict == REJECTED


def test_checklist_missing_message_lists_title():
    sections = [title for title in SECTIONS if title != "八、应急处置措施"]
    records = _run([], document={"sections": sections, "lines": DOC_LINES})
    assert "应急处置措施" in _row(records, "R-DP-051").message


def test_checklist_missing_two_lists_both():
    sections = [title for title in SECTIONS
                if title not in ("八、应急处置措施", "九、计算书及相关图纸")]
    records = _run([], document={"sections": sections, "lines": DOC_LINES})
    message = _row(records, "R-DP-051").message
    assert "应急处置措施" in message and "计算书及相关图纸" in message


def test_checklist_accepts_progress_plan_keyword():
    sections = ["三、进度计划" if title == "三、施工计划" else title for title in SECTIONS]
    records = _run([], document={"sections": sections, "lines": DOC_LINES})
    assert _row(records, "R-DP-051").verdict == OK


def test_checklist_accepts_emergency_plan_keyword():
    sections = ["八、应急预案" if title == "八、应急处置措施" else title for title in SECTIONS]
    records = _run([], document={"sections": sections, "lines": DOC_LINES})
    assert _row(records, "R-DP-051").verdict == OK


def test_checklist_without_document_is_skipped():
    assert not _hits(_run([], document=None), "R-DP-051")


def test_monitoring_section_pass():
    assert _row(_run([]), "R-DP-052").verdict == OK


def test_monitoring_section_missing_is_rejected():
    sections = [title for title in SECTIONS if "监测" not in title]
    records = _run([], document={"sections": sections, "lines": DOC_LINES})
    assert _row(records, "R-DP-052").verdict == REJECTED


def test_checklist_evidence_lists_nine_required_sections():
    assert len(_row(_run([]), "R-DP-051").evidence["required_sections"]) == 9


def test_checklist_missing_sections_evidence():
    sections = [title for title in SECTIONS if title != "八、应急处置措施"]
    records = _run([], document={"sections": sections, "lines": DOC_LINES})
    assert _row(records, "R-DP-051").evidence["missing_sections"] == ["应急处置措施"]


def test_formwork_checklist_missing_emergency_is_rejected():
    records = _run(_form_cards(), category="formwork_support", document=FORM_DOC)
    assert _row(records, "R-FS-051").verdict == REJECTED


# ---------------------------------------------------------------------------
# I. only_if_text 门控
# ---------------------------------------------------------------------------
def test_gate_skips_rules_when_text_absent():
    document = {"sections": SECTIONS, "lines": ["本工程为一般土建工程。"]}
    assert not _hits(_run([], document=document), "R-DP-001")


def test_gate_keeps_rules_when_text_present():
    assert _hits(_run([]), "R-DP-001")


def test_gate_without_document_evaluates_gated_rules():
    assert _hits(_run([], document=None), "R-DP-001")


def test_gate_closed_does_not_emit_required_failure():
    document = {"sections": SECTIONS, "lines": ["本工程为一般土建工程。"]}
    records = _run([], document=document)
    assert not _hits(records, "R-DP-002")


def test_gate_closed_keeps_ungated_threshold_rules():
    document = {"sections": SECTIONS, "lines": ["本工程为一般土建工程。"]}
    records = _run([_card("dp.retaining.displacement", 35.0)], document=document)
    assert _row(records, "R-DP-021").verdict == REJECTED


def test_gate_closed_skips_checklist_rules():
    document = {"sections": [], "lines": ["本工程为一般土建工程。"]}
    assert not _hits(_run([], document=document), "R-DP-051")


def test_gate_formwork_keyword_template_engineering():
    document = {"sections": FORM_SECTIONS, "lines": ["本工程为模板工程。"]}
    records = _run([], category="formwork_support", document=document)
    assert _hits(records, "R-FS-001")


def test_gate_formwork_keyword_not_matched_by_pit():
    document = {"sections": FORM_SECTIONS, "lines": ["本工程为深基坑。"]}
    records = _run([], category="formwork_support", document=document)
    assert not _hits(records, "R-FS-001")


# ---------------------------------------------------------------------------
# J. 记录形态、排序与确定性
# ---------------------------------------------------------------------------
def test_every_record_has_three_field_basis():
    for record in _run(_base_cards()):
        assert record.basis.code and record.basis.clause and record.basis.version


def test_verdict_only_ok_or_rejected():
    assert {record.verdict for record in _run(_base_cards())} <= {OK, REJECTED}


def test_records_sorted_by_item_id():
    item_ids = [record.item_id for record in _run(_base_cards())]
    assert item_ids == sorted(item_ids)


def test_record_id_contains_basis_code_and_clause():
    record = _row(_run(_base_cards()), "R-DP-021")
    assert record.id == "R-DP-021@GB 50497-2019:第8章（待核对）"


def test_evidence_has_case_id_and_category():
    evidence = _row(_run(_base_cards(), case_id="MY-CASE"), "R-DP-021").evidence
    assert evidence["case_id"] == "MY-CASE" and evidence["category"] == "deep_pit"


def test_evidence_has_source_status_pending():
    assert _row(_run(_base_cards()), "R-DP-021").evidence["source_status"] == "待核对"


def test_evidence_has_threshold_status():
    evidence = _row(_run(_base_cards()), "R-DP-021").evidence
    assert "示例阈值" in evidence["threshold_status"]


def test_evidence_plan_verdict_is_known_value():
    values = {record.evidence["plan_verdict"] for record in _run(_base_cards())}
    assert values <= {"pass", "fail", "needs_confirm"}


def test_evidence_has_level_and_severity():
    evidence = _row(_run(_base_cards()), "R-DP-021").evidence
    assert evidence["level"] == "强制" and evidence["severity"] == "error"


def test_two_runs_are_identical():
    first = [record.as_dict() for record in _run(_base_cards())]
    second = [record.as_dict() for record in _run(_base_cards())]
    assert first == second


def test_records_contain_no_absolute_paths():
    payload = json.dumps([record.as_dict() for record in _run(_base_cards())], ensure_ascii=False)
    assert ROOT not in payload


def test_record_ids_are_unique():
    records = _run(_base_cards())
    assert len({record.id for record in records}) == len(records)


def test_clause_version_comes_from_clause_not_basis_library():
    assert _row(_run(_base_cards()), "R-DP-021").basis.version == "2019"


def test_evidence_line_is_carried():
    evidence = _row(_run(_base_cards()), "R-DP-021").evidence
    assert "35mm" in evidence["evidence_line"]


def test_env_does_not_change_result(monkeypatch):
    subject = _subject("deep_pit", _base_cards())
    before = [record.as_dict() for record in ORGAN.evaluate(subject, BASIS)]
    monkeypatch.setenv("SDC_DATA_DIR", "/nonexistent")
    assert [record.as_dict() for record in ORGAN.evaluate(subject, BASIS)] == before


# ---------------------------------------------------------------------------
# K. CLI 契约
# ---------------------------------------------------------------------------
def test_cli_list_json_contains_six(capsys):
    assert cli.main(["list", "--json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert [item["slug"] for item in payload] == list(BUILTIN_MODULES)


def test_cli_check_gen_sample_rc_is_one(capsys):
    assert cli.main(["check", SLUG, "--input", GEN_PATH, "--basis", BASIS_FILE]) == EXIT_BLOCKED
    assert "合计" in capsys.readouterr().out


def test_cli_check_gen_sample_human_summary(capsys):
    cli.main(["check", SLUG, "--input", GEN_PATH, "--basis", BASIS_FILE])
    out = capsys.readouterr().out
    assert "合计 18 条，阻断 3 条" in out


def test_cli_check_gen_sample_json_summary(capsys):
    assert cli.main(["check", SLUG, "--input", GEN_PATH, "--basis", BASIS_FILE, "--json"]) == EXIT_BLOCKED
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"blocking": 3, "total": 18, "verdicts": {"ok": 15, "rejected": 3}}


def test_cli_check_formwork_rc_is_one(capsys):
    assert cli.main(["check", SLUG, "--input", FORM_PATH, "--basis", BASIS_FILE]) == EXIT_BLOCKED
    assert "合计 10 条，阻断 2 条" in capsys.readouterr().out


def test_cli_check_missing_field_rc_two(tmp_path, capsys):
    target = tmp_path / "in.json"
    target.write_text(json.dumps({"case_id": "C"}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", BASIS_FILE]) == EXIT_INPUT
    assert "缺少必填字段" in capsys.readouterr().err


def test_cli_check_unknown_category_rc_two(tmp_path, capsys):
    subject = _subject("lifting", [])
    target = tmp_path / "in.json"
    target.write_text(json.dumps(subject), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", BASIS_FILE]) == EXIT_INPUT
    assert "category" in capsys.readouterr().err


def test_cli_check_clause_missing_rc_three(tmp_path, capsys):
    thin = tmp_path / "basis.json"
    thin.write_text(json.dumps({"version": "thin", "clauses": []}), encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", GEN_PATH, "--basis", str(thin)]) == EXIT_CONTRACT
    assert "ClauseMissing" in capsys.readouterr().err


def test_cli_input_file_missing_rc_two(capsys):
    assert cli.main(["check", SLUG, "--input", "no-such.json", "--basis", BASIS_FILE]) == EXIT_INPUT
    assert "输入不合法" in capsys.readouterr().err


def test_cli_json_output_is_deterministic(capsys):
    args = ["check", SLUG, "--input", GEN_PATH, "--basis", BASIS_FILE, "--json"]
    cli.main(args)
    first = capsys.readouterr().out
    cli.main(args)
    assert capsys.readouterr().out == first


def test_cli_json_output_has_no_absolute_path(capsys):
    cli.main(["check", SLUG, "--input", GEN_PATH, "--basis", BASIS_FILE, "--json"])
    assert ROOT not in capsys.readouterr().out


def test_cli_json_exposes_organ_version(capsys):
    cli.main(["check", SLUG, "--input", GEN_PATH, "--basis", BASIS_FILE, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["organ"] == SLUG and payload["organ_version"] == "0.1.0"


# ---------------------------------------------------------------------------
# L. 样例端到端
# ---------------------------------------------------------------------------
def test_gen_sample_has_five_cards():
    assert len(GEN["cards"]) == 5


def test_gen_sample_category_is_deep_pit():
    assert GEN["category"] == "deep_pit"


def test_gen_sample_records_are_eighteen():
    assert len(ORGAN.evaluate(GEN, BASIS)) == 18


def test_gen_sample_rejected_rules_are_three():
    records = tuple(ORGAN.evaluate(GEN, BASIS))
    assert [record.item_id for record in records if record.verdict == REJECTED] == [
        "R-DP-021", "R-DP-031", "R-DP-061"]


def test_gen_sample_has_no_expert_review_row():
    assert not _hits(ORGAN.evaluate(GEN, BASIS), "R-DP-101")


def test_gen_sample_sections_cover_nine_checklist_items():
    record = _row(ORGAN.evaluate(GEN, BASIS), "R-DP-051")
    assert record.verdict == OK and record.evidence["missing_sections"] == []


def test_gen_sample_monitoring_row_passes():
    assert _row(ORGAN.evaluate(GEN, BASIS), "R-DP-103").verdict == OK


def test_form_sample_has_three_cards():
    assert len(FORM["cards"]) == 3


def test_form_sample_records_are_ten():
    assert len(ORGAN.evaluate(FORM, BASIS)) == 10


def test_form_sample_rejected_rules_are_two():
    records = tuple(ORGAN.evaluate(FORM, BASIS))
    assert [record.item_id for record in records if record.verdict == REJECTED] == [
        "R-FS-031", "R-FS-051"]


def test_form_sample_enum_passes():
    assert _row(ORGAN.evaluate(FORM, BASIS), "R-FS-041").verdict == OK


def test_form_sample_expert_review_passes():
    assert _row(ORGAN.evaluate(FORM, BASIS), "R-FS-101").verdict == OK


def test_basis_json_has_nineteen_clauses():
    assert len(BASIS) == 19


def test_basis_json_covers_every_rule_basis_key():
    for rule in DATA["rules"]:
        entry = DATA["clauses"][rule["basis_key"]]
        assert BASIS.clause(entry["code"], entry["clause"]) is not None


def test_basis_texts_are_non_empty():
    for item in BASIS.as_dict()["clauses"]:
        assert BASIS.clause(item["code"], item["clause"]).text


# ---------------------------------------------------------------------------
# M. 条文库契约
# ---------------------------------------------------------------------------
def test_clause_missing_propagates():
    thin = Basis(version="thin", clauses=(Clause(
        code="建办质〔2018〕31号", clause="内容清单（条号待核对）", version="2018", text="x"),))
    with pytest.raises(ClauseMissing):
        _run(_base_cards(), basis=thin)


def test_basis_requires_non_empty_version():
    with pytest.raises(ContractError, match="条文库版本为空"):
        Basis.from_dict({"version": "", "clauses": []})


def test_basis_rejects_duplicate_clause():
    clause = {"code": "X", "clause": "1", "version": "v", "text": "t"}
    with pytest.raises(ContractError, match="条款重复"):
        Basis.from_dict({"version": "v", "clauses": [clause, clause]})


def test_basis_rejects_clause_without_version():
    with pytest.raises(ContractError, match="version"):
        Basis.from_dict({"version": "v", "clauses": [
            {"code": "X", "clause": "1", "version": "", "text": "t"}]})


def test_basis_require_returns_clause():
    entry = DATA["clauses"]["R-DP-001"]
    assert BASIS.require(entry["code"], entry["clause"]).version == "2018"