"""器官 ``formwork-scaffold`` 的危大分级测试（建办质〔2018〕31号 附件1/附件2）。

覆盖面：9 条目边界值 ±ε / 类型识别全条目 / 三值逻辑（参数缺失不猜值）/
依据未核对拦截 / grade 模式的计算书记录。**不使用 parametrize**。
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

from speccalc.core import Basis, Clause, OK  # noqa: E402
from speccalc.core.data import load as load_data  # noqa: E402
from speccalc.modules import load_builtin  # noqa: E402

load_builtin()
ORGAN = importlib.import_module("speccalc.modules.formwork-scaffold")
SLUG = ORGAN.SLUG
DATA = load_data("formwork-scaffold.json")


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


def _judge(item_id: str, params) -> dict:
    return ORGAN.judge(ORGAN.PACK, item_id, params)


def _level(item_id: str, params) -> str:
    result = _judge(item_id, params)
    assert result["status"] == "definite", (item_id, result)
    return result["level"]


def _muban(height=0.1, span=0.1, total=0.1, linear=0.1, independent=False) -> dict:
    return {"support_height": height, "support_span": span,
            "total_load_design": total, "linear_load_design": linear,
            "independent_member": independent}


def _grade_subject(**grading) -> dict:
    return {"case_id": "GRADE-1", "mode": "grade", "grading": grading}


# ---------------------------------------------------------------------------
# A. 类型识别（覆盖全部 9 条目）
# ---------------------------------------------------------------------------
def test_recognize_landed_scaffold():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "某工程 落地式扣件钢管脚手架专项施工方案") == "pan-luodi-gangguan-24"


def test_recognize_attached_lift():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "附着式升降脚手架工程专项施工方案") == "pan-fuzhuo-shengjiang"


def test_recognize_cantilever():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "悬挑式脚手架专项施工方案") == "pan-xuantiao-jiaoshoujia"


def test_recognize_gondola():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "高处作业吊篮专项施工方案") == "pan-gaochudiaolan"


def test_recognize_platform():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "卸料平台、操作平台工程专项施工方案") == "pan-xieliao-pingtai"


def test_recognize_special_shape():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "异型脚手架工程专项施工方案") == "pan-yixing-jiaoshoujia"


def test_recognize_tool_formwork():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "滑模、爬模工具式模板工程专项施工方案") == "pan-gongjushi-muban"


def test_recognize_concrete_formwork_support():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "混凝土模板支撑工程专项施工方案") == "pan-muban-zhicheng"


def test_recognize_load_bearing_support():
    assert ORGAN.recognize_item(
        ORGAN.PACK, "钢结构安装满堂支撑体系（承重支撑）方案") == "pan-chengzhong-zhicheng"


def test_recognize_unknown_returns_none():
    assert ORGAN.recognize_item(ORGAN.PACK, "基坑支护及土方开挖专项施工方案") is None


def test_recognize_empty_returns_none():
    assert ORGAN.recognize_item(ORGAN.PACK, "") is None


def test_recognize_none_returns_none():
    assert ORGAN.recognize_item(ORGAN.PACK, None) is None


# ---------------------------------------------------------------------------
# B. 落地架 24m / 50m 边界
# ---------------------------------------------------------------------------
def test_luodi_below_24_is_none():
    assert _level("pan-luodi-gangguan-24", {"build_height": 23.9}) == "none"


def test_luodi_at_24_is_weida():
    assert _level("pan-luodi-gangguan-24", {"build_height": 24.0}) == "weida"


def test_luodi_above_24_is_weida():
    assert _level("pan-luodi-gangguan-24", {"build_height": 24.1}) == "weida"


def test_luodi_below_50_is_weida():
    assert _level("pan-luodi-gangguan-24", {"build_height": 49.9}) == "weida"


def test_luodi_at_50_is_chaoguimo():
    assert _level("pan-luodi-gangguan-24", {"build_height": 50.0}) == "chaoguimo"


def test_luodi_above_50_is_chaoguimo():
    assert _level("pan-luodi-gangguan-24", {"build_height": 50.1}) == "chaoguimo"


def test_luodi_zero_is_none():
    assert _level("pan-luodi-gangguan-24", {"build_height": 0.0}) == "none"


def test_luodi_twelve_is_none():
    assert _level("pan-luodi-gangguan-24", {"build_height": 12.0}) == "none"


def test_luodi_thirty_is_weida():
    assert _level("pan-luodi-gangguan-24", {"build_height": 30.0}) == "weida"


def test_luodi_fiftysix_is_chaoguimo():
    assert _level("pan-luodi-gangguan-24", {"build_height": 56.0}) == "chaoguimo"


# ---------------------------------------------------------------------------
# C. 悬挑 / 附着式 / 承重支撑 边界
# ---------------------------------------------------------------------------
def test_xuantiao_below_20_is_weida():
    assert _level("pan-xuantiao-jiaoshoujia", {"segment_height": 19.9}) == "weida"


def test_xuantiao_at_20_is_chaoguimo():
    assert _level("pan-xuantiao-jiaoshoujia", {"segment_height": 20.0}) == "chaoguimo"


def test_xuantiao_above_20_is_chaoguimo():
    assert _level("pan-xuantiao-jiaoshoujia", {"segment_height": 20.1}) == "chaoguimo"


def test_fuzhuo_below_150_is_weida():
    assert _level("pan-fuzhuo-shengjiang", {"lift_height": 149.9}) == "weida"


def test_fuzhuo_at_150_is_chaoguimo():
    assert _level("pan-fuzhuo-shengjiang", {"lift_height": 150.0}) == "chaoguimo"


def test_fuzhuo_above_150_is_chaoguimo():
    assert _level("pan-fuzhuo-shengjiang", {"lift_height": 150.1}) == "chaoguimo"


def test_chengzhong_below_7_is_weida():
    assert _level("pan-chengzhong-zhicheng", {"single_point_load": 6.9}) == "weida"


def test_chengzhong_at_7_is_chaoguimo():
    assert _level("pan-chengzhong-zhicheng", {"single_point_load": 7.0}) == "chaoguimo"


def test_chengzhong_above_7_is_chaoguimo():
    assert _level("pan-chengzhong-zhicheng", {"single_point_load": 7.1}) == "chaoguimo"


# ---------------------------------------------------------------------------
# D. 混凝土模板支撑：危大 5 条件 OR / 超规模 4 条件 OR
# ---------------------------------------------------------------------------
def test_muban_default_is_none():
    assert _level("pan-muban-zhicheng", _muban()) == "none"


def test_muban_height_4_9_is_none():
    assert _level("pan-muban-zhicheng", _muban(height=4.9)) == "none"


def test_muban_height_5_0_is_weida():
    assert _level("pan-muban-zhicheng", _muban(height=5.0)) == "weida"


def test_muban_height_8_0_is_chaoguimo():
    assert _level("pan-muban-zhicheng", _muban(height=8.0)) == "chaoguimo"


def test_muban_span_9_9_is_none():
    assert _level("pan-muban-zhicheng", _muban(span=9.9)) == "none"


def test_muban_span_10_0_is_weida():
    assert _level("pan-muban-zhicheng", _muban(span=10.0)) == "weida"


def test_muban_span_18_0_is_chaoguimo():
    assert _level("pan-muban-zhicheng", _muban(span=18.0)) == "chaoguimo"


def test_muban_total_9_9_is_none():
    assert _level("pan-muban-zhicheng", _muban(total=9.9)) == "none"


def test_muban_total_10_0_is_weida():
    assert _level("pan-muban-zhicheng", _muban(total=10.0)) == "weida"


def test_muban_total_15_0_is_chaoguimo():
    assert _level("pan-muban-zhicheng", _muban(total=15.0)) == "chaoguimo"


def test_muban_linear_14_9_is_none():
    assert _level("pan-muban-zhicheng", _muban(linear=14.9)) == "none"


def test_muban_linear_15_0_is_weida():
    assert _level("pan-muban-zhicheng", _muban(linear=15.0)) == "weida"


def test_muban_linear_20_0_is_chaoguimo():
    assert _level("pan-muban-zhicheng", _muban(linear=20.0)) == "chaoguimo"


def test_muban_independent_member_is_weida():
    assert _level("pan-muban-zhicheng", _muban(independent=True)) == "weida"


# ---------------------------------------------------------------------------
# E. 类型即危大条目
# ---------------------------------------------------------------------------
def test_gondola_is_weida_without_params():
    assert _level("pan-gaochudiaolan", {}) == "weida"


def test_unload_platform_is_weida_without_params():
    assert _level("pan-xieliao-pingtai", {}) == "weida"


def test_special_scaffold_is_weida_without_params():
    assert _level("pan-yixing-jiaoshoujia", {}) == "weida"


def test_tool_formwork_is_weida_without_params():
    assert _level("pan-gongjushi-muban", {}) == "weida"


# ---------------------------------------------------------------------------
# F. 结论字段（rule_id / duty / basis）
# ---------------------------------------------------------------------------
def test_luodi_chaoguimo_rule_id_and_duty():
    result = _judge("pan-luodi-gangguan-24", {"build_height": 56.0})
    assert result["rule_id"] == "G-pan-luodi-50"
    assert "专家论证" in result["duty"]
    assert result["label"] == "超过一定规模的危大工程"


def test_luodi_weida_rule_id_and_duty():
    result = _judge("pan-luodi-gangguan-24", {"build_height": 30.0})
    assert result["rule_id"] == "G-pan-luodi-24"
    assert "专项施工方案" in result["duty"]


def test_luodi_basis_excerpts_non_empty():
    result = _judge("pan-luodi-gangguan-24", {"build_height": 56.0})
    assert result["basis"]
    assert all("31号" in entry["doc"] for entry in result["basis"])


def test_weida_verdict_is_triggered_not_fail():
    result = _judge("pan-luodi-gangguan-24", {"build_height": 30.0})
    assert result["verdict"] == "triggered"


def test_none_verdict_is_pass():
    result = _judge("pan-luodi-gangguan-24", {"build_height": 12.0})
    assert result["verdict"] == "pass"


def test_actual_is_primary_param_value():
    result = _judge("pan-xuantiao-jiaoshoujia", {"segment_height": 20.0})
    assert result["param"] == "segment_height"
    assert result["actual"] == 20.0


# ---------------------------------------------------------------------------
# G. 待人工确认（三值逻辑）
# ---------------------------------------------------------------------------
def test_missing_params_pending():
    result = _judge("pan-luodi-gangguan-24", {})
    assert result["status"] == "pending"
    assert result["unknown_params"] == ["build_height"]


def test_partial_params_or_short_circuit_decides():
    result = _judge("pan-muban-zhicheng", {"support_height": 8.0})
    assert result["status"] == "definite"
    assert result["level"] == "chaoguimo"


def test_partial_params_without_hit_stays_pending():
    result = _judge("pan-muban-zhicheng", {"support_height": 3.0})
    assert result["status"] == "pending"


def test_unknown_item_pending():
    result = _judge("pan-no-such-item", {})
    assert result["status"] == "pending"


def test_unverified_basis_pending():
    rules = ORGAN.Rules(copy.deepcopy(DATA))
    rules.grading["items"][0]["basis"][0]["status"] = "待核对"
    result = ORGAN.judge(rules, "pan-luodi-gangguan-24", {"build_height": 56.0})
    assert result["status"] == "pending"
    assert "待核对" in result["note"]


def test_unverified_item_status_pending():
    rules = ORGAN.Rules(copy.deepcopy(DATA))
    rules.grading["items"][0]["status"] = "待核对"
    result = ORGAN.judge(rules, "pan-luodi-gangguan-24", {"build_height": 56.0})
    assert result["status"] == "pending"


def test_uncovered_values_pending():
    result = _judge("pan-chengzhong-zhicheng", {"single_point_load": None})
    assert result["status"] == "pending"


# ---------------------------------------------------------------------------
# H. 条件求值器
# ---------------------------------------------------------------------------
def test_eval_cond_literals():
    assert ORGAN.eval_cond("true", {}) is True
    assert ORGAN.eval_cond("false", {}) is False
    assert ORGAN.eval_cond("false（该类型工程即为危大）", {}) is False


def test_eval_cond_chained_comparison():
    params = {"build_height": 30.0}
    assert ORGAN.eval_cond("24 <= build_height < 50", params) is True
    assert ORGAN.eval_cond("build_height >= 50", params) is False
    assert ORGAN.eval_cond("build_height < 24", params) is False


def test_eval_cond_and_or_not():
    params = {"a": 5.0, "b": 1.0, "flag": False}
    assert ORGAN.eval_cond("a >= 5 && b >= 1", params) is True
    assert ORGAN.eval_cond("a >= 5 || b >= 9", params) is True
    assert ORGAN.eval_cond("!(flag)", params) is True
    assert ORGAN.eval_cond("a >= 5 && !(flag)", params) is True


def test_eval_cond_three_valued():
    params = {"a": 5.0}
    assert ORGAN.eval_cond("a >= 5 || missing >= 1", params) is True
    assert ORGAN.eval_cond("a >= 9 && missing >= 1", params) is False
    assert ORGAN.eval_cond("missing >= 1", params) is None
    assert ORGAN.eval_cond("a >= 9 || missing >= 1", params) is None


def test_eval_cond_boolean_param():
    assert ORGAN.eval_cond("independent_member", {"independent_member": True}) is True
    assert ORGAN.eval_cond("independent_member", {"independent_member": False}) is False


def test_eval_cond_bad_atom_rejected():
    with pytest.raises(ValueError):
        ORGAN.eval_cond("a ~~ 1", {"a": 1.0})


# ---------------------------------------------------------------------------
# I. grade 模式的计算书
# ---------------------------------------------------------------------------
def test_grade_mode_emits_one_record():
    records = tuple(ORGAN.evaluate(
        _grade_subject(item_id="pan-luodi-gangguan-24",
                       params={"build_height": 56.0}), BASIS))
    assert len(records) == 1
    assert records[0].verdict == OK


def test_grade_record_basis_is_annex2_clause():
    records = tuple(ORGAN.evaluate(
        _grade_subject(item_id="pan-luodi-gangguan-24",
                       params={"build_height": 56.0}), BASIS))
    assert records[0].basis.code == "建办质〔2018〕31号"
    assert records[0].basis.clause == "附件2 四（一）"
    assert records[0].basis.version == "2018"


def test_grade_record_evidence_carries_level_and_duty():
    records = tuple(ORGAN.evaluate(
        _grade_subject(item_id="pan-luodi-gangguan-24",
                       params={"build_height": 56.0}), BASIS))
    evidence = records[0].evidence
    assert evidence["level"] == "chaoguimo"
    assert "专家论证" in evidence["duty"]
    assert evidence["rule_id"] == "G-pan-luodi-50"


def test_grade_record_id_is_stable():
    subject = _grade_subject(item_id="pan-luodi-gangguan-24",
                             params={"build_height": 56.0})
    first = tuple(ORGAN.evaluate(subject, BASIS))[0]
    second = tuple(ORGAN.evaluate(subject, BASIS))[0]
    assert first.id == second.id
    assert first.id.startswith("grading.pan-luodi-gangguan-24@")


def test_grade_mode_accepts_project_type():
    records = tuple(ORGAN.evaluate(
        _grade_subject(project_type="混凝土模板支撑工程",
                       params=_muban(height=8.0)), BASIS))
    assert records[0].evidence["level"] == "chaoguimo"


def test_grade_mode_unknown_type_rejected():
    with pytest.raises(ValueError):
        tuple(ORGAN.evaluate(
            _grade_subject(project_type="基坑支护方案", params={}), BASIS))


def test_grade_mode_missing_params_rejected():
    with pytest.raises(ValueError):
        tuple(ORGAN.evaluate(
            _grade_subject(item_id="pan-luodi-gangguan-24", params={}), BASIS))


def test_grade_mode_missing_basis_clause_raises():
    from speccalc.core import ClauseMissing
    with pytest.raises(ClauseMissing):
        tuple(ORGAN.evaluate(
            _grade_subject(item_id="pan-luodi-gangguan-24",
                           params={"build_height": 56.0}), Basis.empty("0")))


def test_grade_json_roundtrip_is_deterministic():
    subject = _grade_subject(item_id="pan-luodi-gangguan-24",
                             params={"build_height": 30.0})
    first = tuple(ORGAN.evaluate(subject, BASIS))[0].as_dict()
    second = tuple(ORGAN.evaluate(subject, BASIS))[0].as_dict()
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True)