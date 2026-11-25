"""器官：危大工程专项施工方案合规校核（hazard-scheme-check）。

迁自 target-map ③ 行（仓库 #46）。旧仓是「规则优先 + LLM 兜底」的危大方案审查系统；
本器官只保留**判定层**：参数卡 × 29 条规则（深基坑 19 + 高支模 10）→ 逐条结论。
文档解析（docx/PDF）、LLM 兜底抽取、Web 面板、报告排版、基准与数据生成全部舍弃
（见 ``docs/hazard-scheme-check.md`` 的处置表）。

一句话语义
    ``subject`` 给「类别 + 参数卡 +（可选）文档骨架」，``basis`` 给「规范条款」，
    本器官按 29 条规则逐条判定，每条结论挂一条依据：

    - 数值/枚举/必填规则读参数卡；
    - 程序性规则（专家论证/监测/专项方案名目）与章节齐套规则读文档骨架；
    - 同一参数多个取值 → ``needs_confirm``（不硬判）。

纪律
1. **三态 → 二态**：旧仓「pass」→ ``ok``；「fail」→ ``rejected``；
   「manual / 待人工确认」→ ``ok`` + ``evidence.plan_verdict="needs_confirm"``。
2. **不拿产品内部阈值冒充规范**：6 条「工程合理性校核」规则的 ``basis_kind="sanity"``，
   失败只记 ``needs_confirm``，不产生阻断；其余 23 条规则有规范代码依据。
3. **源仓 status 原样保留**：29 条规则的 ``basis.status`` 都是「待核对」，
   写进 ``evidence.source_status``，不声称已核对。
4. **无依据不入账**：每条记录都经 ``basis.ref(code, clause)`` 取依据；器官不读文件、
   不打印、不读时钟、不自带 CLI。
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Dict, Iterable, List, Mapping

from speccalc.core.data import load
from speccalc.core.ledger import OK, REJECTED, CalculationRecord, ContractError
from speccalc.core.registry import Pack, register

SLUG = "hazard-scheme-check"
VERSION = "0.1.0"
DATA = load("hazard-scheme-check.json")

RULES: List[dict] = DATA["rules"]
CLAUSES: Dict[str, dict] = DATA["clauses"]
CATEGORIES: Dict[str, dict] = DATA["categories"]
CONSTANTS: Dict[str, str] = DATA["constants"]

DOC_TYPES = ("conditional_program", "checklist_section")

PLAN_PASS = "pass"
PLAN_FAIL = "fail"
PLAN_CONFIRM = "needs_confirm"
PLAN_LABELS = {PLAN_PASS: "通过", PLAN_FAIL: "不符合", PLAN_CONFIRM: "待人工确认"}
CHECK_TYPES = (
    "required", "threshold_min", "threshold_max", "within_range",
    "enum", "conditional_program", "checklist_section",
)


# ---------------------------------------------------------------------------
# 规则包视图
# ---------------------------------------------------------------------------
class Rules(object):
    """器官的规则包：条款引用只经 ``basis.ref(code, clause)``。"""

    def __init__(self, data: Mapping):
        self.data = data
        self.rules = list(data["rules"])
        self.clauses = dict(data["clauses"])
        self.categories = dict(data["categories"])
        self.constants = dict(data["constants"])

    def clause(self, key: str) -> Mapping:
        entry = self.clauses.get(key)
        if entry is None:
            raise ContractError("规则包缺条款键：%s" % key)
        return entry

    def ref(self, basis, key: str):
        entry = self.clause(key)
        return basis.ref(entry["code"], entry["clause"])

    def rule(self, rule_id: str) -> Mapping:
        for entry in self.rules:
            if entry["id"] == rule_id:
                return entry
        raise ContractError("规则包缺 rule_id：%s" % rule_id)


PACK = Rules(DATA)


# ---------------------------------------------------------------------------
# 数据契约（import 时自检：打包漏字段立刻红）
# ---------------------------------------------------------------------------
def validate_data(data: Mapping = None) -> None:
    data = DATA if data is None else data
    rules = data.get("rules") or []
    clauses = data.get("clauses") or {}
    categories = data.get("categories") or {}
    if len(rules) != 29:
        raise ContractError("规则包应为 29 条，实际 %d" % len(rules))
    seen = set()
    for rule in rules:
        rule_id = rule.get("id")
        if not rule_id or rule_id in seen:
            raise ContractError("规则 id 缺失或重复：%r" % (rule_id,))
        seen.add(rule_id)
        if rule.get("category") not in categories:
            raise ContractError("规则 %s 的 category 未登记：%r" % (rule_id, rule.get("category")))
        if rule.get("check_type") not in CHECK_TYPES:
            raise ContractError("规则 %s 的 check_type 非法：%r" % (rule_id, rule.get("check_type")))
        if not str(rule.get("param") or "").strip():
            raise ContractError("规则 %s 缺 param" % rule_id)
        if rule.get("basis_key") not in clauses:
            raise ContractError("规则 %s 的 basis_key 未登记" % rule_id)


validate_data()


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------
def _require(mapping, key, where):
    if not isinstance(mapping, Mapping):
        raise ValueError("%s 必须是对象" % where)
    if key not in mapping or mapping[key] is None:
        raise ValueError("%s 缺少必填字段：%s" % (where, key))
    return mapping[key]


def _text(value, where):
    if value is None or not str(value).strip():
        raise ValueError("%s 不能为空" % where)
    return str(value)


def _number(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s 必须是数值：%r" % (where, value))
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("%s 必须是有限数值：%r" % (where, number))
    return number


def _optional_number(value, where):
    if value is None:
        return None
    return _number(value, where)


def _optional_text(value, where):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("%s 必须是字符串：%r" % (where, value))
    text = value.strip()
    return text or None


def _card(raw, index):
    """一张参数卡：``param_id`` 必填；数值与文本取值都可空（空值不参与判定）。"""
    where = "cards[%d]" % index
    if not isinstance(raw, Mapping):
        raise ValueError("%s 必须是对象" % where)
    param_id = _text(raw.get("param_id"), where + ".param_id")
    value = _optional_number(raw.get("value"), where + ".value")
    text_value = _optional_text(raw.get("text_value"), where + ".text_value")
    evidence = raw.get("evidence")
    if evidence is not None and not isinstance(evidence, Mapping):
        raise ValueError("%s.evidence 必须是对象" % where)
    return {
        "param_id": param_id,
        "name": str(raw.get("name") or ""),
        "value": value,
        "unit": str(raw.get("unit") or ""),
        "text_value": text_value,
        "raw_text": str(raw.get("raw_text") or ""),
        "evidence": dict(evidence or {}),
    }


def _document(raw):
    """文档骨架：``{sections: [...], lines: [...]}``；两种元素接受字符串或对象。"""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("document 必须是对象")
    raw_sections = raw.get("sections") or []
    raw_lines = raw.get("lines") or []
    if not isinstance(raw_sections, list):
        raise ValueError("document.sections 必须是数组")
    if not isinstance(raw_lines, list):
        raise ValueError("document.lines 必须是数组")

    def title_of(item, where):
        if isinstance(item, str):
            return item
        if isinstance(item, Mapping):
            return str(item.get("title") or item.get("text") or "")
        raise ValueError("%s 必须是字符串或对象" % where)

    def text_of(item, where):
        if isinstance(item, str):
            return item
        if isinstance(item, Mapping):
            return str(item.get("text") or "")
        raise ValueError("%s 必须是字符串或对象" % where)

    sections = [title_of(item, "document.sections[%d]" % index)
                for index, item in enumerate(raw_sections)]
    lines = [text_of(item, "document.lines[%d]" % index)
             for index, item in enumerate(raw_lines)]
    return {"sections": sections, "lines": lines}


def _gate_hit(keywords, lines):
    return any(keyword and any(keyword in line for line in lines) for keyword in keywords)


def _cards_by_param(cards):
    grouped: Dict[str, List[dict]] = {}
    for card in cards:
        grouped.setdefault(card["param_id"], []).append(card)
    return grouped


def _distinct_numbers(cards):
    values = {card["value"] for card in cards if card["value"] is not None}
    return sorted(values)


def _first_evidence_line(cards):
    for card in cards:
        line = (card.get("evidence") or {}).get("line_text")
        if line:
            return str(line)
    return ""


def _fmt(value):
    return ("%.6f" % float(value)).rstrip("0").rstrip(".")


def _substitute(template, values):
    """替换 advice 里的 ``{value}/{limit}/{unit}`` 占位符（缺失的保持原样）。"""
    text = str(template or "")
    for key, value in values.items():
        if value is None:
            continue
        text = text.replace("{%s}" % key, str(value))
    return text


def _compare(value, op, limit):
    if op == ">=":
        return value >= limit
    if op == "<=":
        return value <= limit
    if op == ">":
        return value > limit
    if op == "<":
        return value < limit
    raise ContractError("阈值规则 op 非法：%r" % (op,))


def _in_range(value, rule):
    low = rule.get("min_value")
    high = rule.get("max_value")
    if low is None and high is None:
        raise ContractError("区间规则 %s 既无 min_value 也无 max_value" % rule["id"])
    return ((low is None or value >= low) and (high is None or value <= high))


def _range_text(rule):
    low = rule.get("min_value")
    high = rule.get("max_value")
    unit = rule.get("unit", "")
    parts = []
    if low is not None:
        parts.append(str(low))
    if high is not None:
        parts.append(str(high))
    return "[%s]%s" % (",".join(parts), unit)


def _make_record(rule, message, basis, pack, plan_verdict, evidence, item_id=None):
    """统一账本行：每条都挂依据；sanity/manual 失败只记 needs_confirm。"""
    entry = pack.clause(rule["basis_key"])
    failed = plan_verdict == PLAN_FAIL
    verdict = OK
    if failed and entry.get("basis_kind") == "sanity":
        plan_verdict = PLAN_CONFIRM
        verdict = OK
    elif failed:
        verdict = REJECTED

    payload = {
        "rule_id": rule["id"],
        "rule_name": rule.get("name", ""),
        "check_type": rule["check_type"],
        "param": rule.get("param", ""),
        "level": rule.get("level", ""),
        "severity": rule.get("severity", ""),
        "basis_kind": entry.get("basis_kind", "standard"),
        "source_status": entry.get("status", ""),
        "threshold_status": rule.get("threshold_status", ""),
        "plan_verdict": plan_verdict,
        "plan_label": PLAN_LABELS.get(plan_verdict, plan_verdict),
        "verdict_rule": "pass->ok；fail->rejected；manual/sanity-fail->ok+needs_confirm",
        "advice": rule.get("advice", ""),
    }
    payload.update(evidence)
    return CalculationRecord(
        item_id=item_id or rule["id"],
        verdict=verdict,
        message=message,
        basis=pack.ref(basis, rule["basis_key"]),
        evidence=payload,
    )


# ---------------------------------------------------------------------------
# 各规则类型
# ---------------------------------------------------------------------------
def _eval_required(rule, cards, basis, pack, context):
    if not cards:
        advice = rule.get("advice") or pack.constants["required_missing_advice"]
        return [_make_record(
            rule,
            "未提取到参数 %s；%s" % (rule["param"], advice),
            basis, pack, PLAN_FAIL,
            {"actual": None, "limit": None, "unit": "", "card_count": 0,
             "evidence_line": "", "relation": "required"},
        )]
    card = cards[0]
    if card["text_value"]:
        shown = card["text_value"]
    elif card["value"] is not None:
        shown = "%s%s" % (_fmt(card["value"]), card["unit"])
    else:
        shown = card["raw_text"] or "（空值）"
    return [_make_record(
        rule,
        "已提取到 %s：%s" % (rule["param"], shown),
        basis, pack, PLAN_PASS,
        {"actual": shown, "limit": None, "unit": card["unit"],
         "card_count": len(cards), "evidence_line": _first_evidence_line(cards),
         "relation": "required"},
    )]


def _eval_numeric(rule, cards, basis, pack, context):
    rule_id = rule["id"]
    values = _distinct_numbers(cards)
    if not values:
        return []
    unit = rule.get("unit", "")
    if len(values) > 1:
        shown = "、".join("%s%s" % (_fmt(value), unit) for value in values)
        return [_make_record(
            rule,
            "同一参数提取到 %d 个取值：%s（疑似多出处冲突），待人工确认"
            % (len(values), shown),
            basis, pack, PLAN_CONFIRM,
            {"actual": values, "limit": None, "unit": unit, "card_count": len(cards),
             "evidence_line": _first_evidence_line(cards), "relation": "multi_value"},
        )]

    value = values[0]
    if rule["check_type"] == "within_range":
        passed = _in_range(value, rule)
        limit = {"min": rule.get("min_value"), "max": rule.get("max_value")}
        message = "实测 %s%s，要求区间 %s" % (_fmt(value), unit, _range_text(rule))
        formula = "%s in %s" % (_fmt(value), _range_text(rule))
        relation = "within_range"
    else:
        op = rule.get("op")
        limit_value = float(rule["value"])
        passed = _compare(value, op, limit_value)
        limit = limit_value
        message = "实测 %s%s，要求 %s %s%s" % (_fmt(value), unit, op, _fmt(limit_value), unit)
        formula = "%s %s %s" % (_fmt(value), op, _fmt(limit_value))
        relation = "threshold"

    advice = _substitute(rule.get("advice"), {
        "value": _fmt(value),
        "limit": None if isinstance(limit, dict) else _fmt(limit),
        "unit": unit,
    })
    plan = PLAN_PASS if passed else PLAN_FAIL
    return [_make_record(
        rule,
        message + ("；%s" % advice if not passed and advice else ""),
        basis, pack, plan,
        {"actual": value, "limit": limit, "unit": unit, "card_count": len(cards),
         "evidence_line": _first_evidence_line(cards), "relation": relation,
         "formula": formula, "rule_id": rule_id},
    )]


def _eval_enum(rule, cards, basis, pack, context):
    allowed = list(rule.get("allowed") or [])
    if not allowed:
        raise ContractError("枚举规则 %s 的 allowed 为空" % rule["id"])
    typed = [card for card in cards if card["text_value"]]
    if not typed:
        return []
    records = []
    total = len(typed)
    for index, card in enumerate(typed, start=1):
        value = card["text_value"]
        hit = any(value == option or value in option or option in value for option in allowed)
        plan = PLAN_PASS if hit else PLAN_FAIL
        advice = _substitute(rule.get("advice"), {"value": value})
        message = (
            "取值「%s」在允许集合内（%s）" % (value, " / ".join(allowed))
            if hit else
            "取值「%s」不在允许集合：%s" % (value, " / ".join(allowed))
        )
        if not hit and advice:
            message = message + "；" + advice
        item_id = rule["id"] if total == 1 else "%s#%d" % (rule["id"], index)
        records.append(_make_record(
            rule, message, basis, pack, plan,
            {"actual": value, "limit": allowed, "unit": card["unit"],
             "card_count": len(cards), "evidence_line": _first_evidence_line([card]),
             "relation": "enum", "card_index": index},
            item_id=item_id,
        ))
    return records


def _eval_conditional(rule, cards, basis, pack, context):
    values = _distinct_numbers(cards)
    if not values:
        return []
    condition = rule.get("condition") or {}
    low = condition.get("min")
    high = condition.get("max")
    if low is None and high is None:
        raise ContractError("程序性规则 %s 的 condition 为空" % rule["id"])
    triggered = any(
        (low is None or value >= low) and (high is None or value <= high)
        for value in values
    )
    if not triggered:
        return []
    require_text = str(rule.get("require_text") or "")
    if not require_text:
        raise ContractError("程序性规则 %s 缺 require_text" % rule["id"])
    lines = context["document"]["lines"]
    found = any(require_text in line for line in lines)
    condition_text = "≥%s%s" % (low, "m" if rule.get("unit") else "")
    if high is not None:
        condition_text = "≤%s%s" % (high, "m" if rule.get("unit") else "")
    message = (
        "触发条件 %s，全文存在「%s」" % (condition_text, require_text)
        if found else
        "触发条件 %s，全文未检出「%s」" % (condition_text, require_text)
    )
    advice = _substitute(rule.get("advice"), {"value": _fmt(values[0])})
    if not found and advice:
        message = message + "；" + advice
    return [_make_record(
        rule, message, basis, pack, PLAN_PASS if found else PLAN_FAIL,
        {"actual": values, "limit": condition, "unit": rule.get("unit", ""),
         "card_count": len(cards), "evidence_line": "",
         "relation": "conditional", "require_text": require_text,
         "condition_text": condition_text, "text_found": found},
    )]


def _eval_checklist(rule, cards, basis, pack, context):
    required = list(rule.get("sections") or [])
    if not required:
        raise ContractError("章节规则 %s 的 sections 为空" % rule["id"])
    titles = context["document"]["sections"]
    missing = []
    for item in required:
        title = str(item.get("title") or "")
        keywords = list(item.get("keywords") or [title])
        if not any(keyword and any(keyword in section for section in titles)
                   for keyword in keywords):
            missing.append(title)
    if missing:
        message = "缺少章节/内容：%s" % "、".join(missing)
        plan = PLAN_FAIL
    else:
        message = "必备章节齐套（%d 项）" % len(required)
        plan = PLAN_PASS
    advice = _substitute(rule.get("advice"), {})
    if missing and advice:
        message = message + "；" + advice
    return [_make_record(
        rule, message, basis, pack, plan,
        {"actual": [item.get("title") for item in required],
         "limit": None, "unit": "", "card_count": len(cards),
         "evidence_line": "", "relation": "checklist",
         "required_sections": [item.get("title") for item in required],
         "missing_sections": missing},
    )]


_EVALUATORS = {
    "required": _eval_required,
    "threshold_min": _eval_numeric,
    "threshold_max": _eval_numeric,
    "within_range": _eval_numeric,
    "enum": _eval_enum,
    "conditional_program": _eval_conditional,
    "checklist_section": _eval_checklist,
}


def evaluate(subject: Mapping, basis) -> Iterable[CalculationRecord]:
    """按 29 条规则逐条判定；只读 subject / basis，不读文件、不打印。"""
    if not isinstance(subject, Mapping):
        raise ValueError("subject 必须是 JSON 对象")
    case_id = _text(subject.get("case_id"), "case_id")
    category = _text(subject.get("category"), "category")
    if category not in CATEGORIES:
        raise ValueError("category 非法：%r（可用 %s）"
                         % (category, ", ".join(sorted(CATEGORIES))))
    raw_cards = _require(subject, "cards", "subject")
    if not isinstance(raw_cards, list):
        raise ValueError("cards 必须是数组")
    cards = [_card(raw, index) for index, raw in enumerate(raw_cards)]
    document = _document(subject.get("document"))
    grouped = _cards_by_param(cards)

    context = {
        "case_id": case_id,
        "category": category,
        "document": document,
        "pack": PACK,
    }
    records: List[CalculationRecord] = []
    for rule in RULES:
        if rule["category"] != category:
            continue
        if document is not None and rule.get("only_if_text"):
            if not _gate_hit(rule["only_if_text"], document["lines"]):
                continue
        if rule["check_type"] in DOC_TYPES and document is None:
            # 旧仓口径：缺文档骨架时程序性/章节规则不判定（skipped），不留假结论。
            continue
        cards_for_rule = grouped.get(rule["param"], [])
        evaluator = _EVALUATORS[rule["check_type"]]
        records.extend(evaluator(rule, cards_for_rule, basis, PACK, context))
    return tuple(
        replace(record, evidence=dict(record.evidence, case_id=case_id, category=category))
        for record in records
    )


register(Pack(
    slug=SLUG,
    version=VERSION,
    summary="危大工程专项施工方案合规校核：参数卡 × 29 条规则（深基坑 19 + 高支模 10）",
    input_fields=("case_id", "category", "cards"),
    evaluate=evaluate,
))