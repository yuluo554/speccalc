"""器官：公路技术状况评定（pavement-mqi）。

迁自 target-map ③ 行（JTG 5210-2018 口径）。迁入后只保留**算这一层**：
台账、导入、GUI、报表、打包全部舍弃（``ORGAN-PLAYBOOK`` §2）。

一句话语义
    subject 给「路段实测（RQI / 车辙 / 抗滑）+ 破损明细 + 已核对的系数格 + 分档 + 对策规则」，
    basis 给「JTG 5210-2018 的对应条款键」，
    本器官算出：逐路段 PCI（含扣分展开与分项得分）、路况等级、养护对策、逐路线 MQI，
    每条结论都挂 ``code + clause + version``。

三条纪律（与旧仓一致）
1. **系数格只认已核对来源**：``status == "verified"`` 且有 ``value`` 与 ``evidence``；
   否则拒绝计算（旧仓此时出 ``blocked``；本产品无降级态 → 退出码 2）。
2. **未提供的分项不得按满分补齐**：权重 > 0 的分项缺实测值即输入不合法。
3. **拒算不外流数值**：输入不合法的报错里只出现键名与原因码，不出现半算的分数。

依据口径：``clause`` 字段取旧仓系数键（``deduct_ratio.asphalt_distress`` /
``grade_threshold.pci`` …），不是条号——旧仓 15 格系数的 ``basis[].clause`` 全为空
（官方渠道取不到条款号与表号原文）。详见 ``docs/pavement-mqi.md``。
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from speccalc.core.data import load
from speccalc.core.ledger import OK, REJECTED, CalculationRecord, ContractError
from speccalc.core.registry import Pack, register

SLUG = "pavement-mqi"
VERSION = "0.1.0"
DATA = load("pavement-mqi.json")

FLOOR = float(DATA["constants"]["score_floor"])
CEIL = float(DATA["constants"]["score_ceiling"])
DIGITS = int(DATA["constants"]["round_digits"])
GRADE_ORDER: Tuple[str, ...] = tuple(DATA["grades"]["order"])
BOUNDARIES = tuple(DATA["grades"]["boundaries"])
COMPONENTS: Tuple[str, ...] = tuple(DATA["metrics"]["pci_components"])
OPERATORS = tuple(DATA["metrics"]["operators"])

REASON_NOT_VERIFIED = "source_not_confirmed"
REASON_VALUE_MISSING = "value_missing"
REASON_EVIDENCE_MISSING = "evidence_missing"
REASON_KEY_MISSING = "coefficient_missing"
REASON_MEASURED_MISSING = "measured_missing"
REASON_UNIT_UNMAPPED = "unit_unmapped"


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
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("%s 必须是有限数值：%r" % (where, value))
    return value


def _mapping(value, where):
    """嵌套结构也必须是对象：形状不对是输入不合法（rc 2），不是崩溃。"""
    if not isinstance(value, Mapping):
        raise ValueError("%s 必须是对象" % where)
    return value


def _clamp(value: float) -> float:
    return max(FLOOR, min(CEIL, value))


def _round(value: float) -> float:
    return round(value, DIGITS)


def _coefficients(subject: Mapping) -> Dict[str, dict]:
    raw = _require(subject, "coefficients", "subject")
    if not isinstance(raw, list) or not raw:
        raise ValueError("coefficients 必须是非空数组")
    out: Dict[str, dict] = {}
    for entry in raw:
        key = _text(_require(entry, "key", "coefficients[]"), "coefficients[].key")
        if key in out:
            raise ValueError("系数格重复：%s" % key)
        if str(entry.get("status") or "") != "verified":
            raise ValueError("系数格 %s 未核对来源：status=%r（%s）"
                             % (key, entry.get("status"), REASON_NOT_VERIFIED))
        if not entry.get("evidence"):
            raise ValueError("系数格 %s 缺出处凭证（%s）" % (key, REASON_EVIDENCE_MISSING))
        if entry.get("value") is None:
            raise ValueError("系数格 %s 缺数值（%s）" % (key, REASON_VALUE_MISSING))
        out[key] = {"value": entry["value"], "evidence": str(entry["evidence"])}
    return out


def _coefficient(coefficients: Mapping, key: str) -> dict:
    block = coefficients.get(key)
    if block is None:
        raise ValueError("缺少系数格：%s（%s）" % (key, REASON_KEY_MISSING))
    return block


def _basis_ref(basis, key: str):
    entry = DATA["clauses"][key]
    return basis.ref(entry["code"], entry["clause"])


# ---------------------------------------------------------------------------
# 分项得分与 PCI
# ---------------------------------------------------------------------------
def _two_point_score(actual: float, ideal: float, zero: float, where: str) -> float:
    if ideal == zero:
        raise ValueError("%s 的 ideal 与 zero 不能相等" % where)
    return _clamp(100.0 * (actual - zero) / (ideal - zero))


def _component_scores(segment: Mapping, weights: Mapping, coefficients: Mapping) -> Dict[str, float]:
    """按权重只算用得到的分项：权重 0 的分项不需要实测值（也不许用 100 补齐）。"""
    measured = segment.get("measured") or {}
    if not isinstance(measured, Mapping):
        raise ValueError("segment.measured 必须是对象")
    scores: Dict[str, float] = {}
    if float(weights.get("ride_quality", 0)) > 0:
        block = _coefficient(coefficients, "pci_component.ride_quality")["value"]
        ideal = _number(_require(block, "ideal_value", "pci_component.ride_quality"),
                        "ride_quality.ideal_value")
        zero = _number(_require(block, "zero_value", "pci_component.ride_quality"),
                       "ride_quality.zero_value")
        actual = _number(_require(measured, "rqi", "measured"), "measured.rqi")
        scores["ride_quality"] = _two_point_score(actual, ideal, zero, "ride_quality")
    if float(weights.get("rutting", 0)) > 0:
        block = _coefficient(coefficients, "pci_component.rutting")["value"]
        ideal = _number(_require(block, "ideal_mm", "pci_component.rutting"), "rutting.ideal_mm")
        zero = _number(_require(block, "zero_mm", "pci_component.rutting"), "rutting.zero_mm")
        actual = _number(_require(measured, "rut_depth_mm", "measured"), "measured.rut_depth_mm")
        if zero == ideal:
            raise ValueError("rutting 的 ideal 与 zero 不能相等（分母为 0）")
        # 车辙是「越小越好」：depth=ideal_mm 得 100，depth=zero_mm 得 0
        scores["rutting"] = _clamp(100.0 * (zero - actual) / (zero - ideal))
    if float(weights.get("skid_resistance", 0)) > 0:
        block = _coefficient(coefficients, "pci_component.skid_resistance")["value"]
        ideal = _number(_require(block, "ideal_value", "pci_component.skid_resistance"),
                        "skid_resistance.ideal_value")
        zero = _number(_require(block, "zero_value", "pci_component.skid_resistance"),
                       "skid_resistance.zero_value")
        actual = _number(_require(measured, "skid", "measured"), "measured.skid")
        scores["skid_resistance"] = _two_point_score(actual, ideal, zero, "skid_resistance")
    return scores


def _deductions(segment: Mapping, surface: str, coefficients: Mapping) -> List[dict]:
    """扣分 = 比率 × (数量 / 几何分母) × 100；几何分母按 unit 映射到路段字段。"""
    block = _coefficient(coefficients, "deduct_ratio.%s_distress" % surface)
    ratios = _mapping(_require(block["value"], "ratios", "deduct_ratio"), "deduct_ratio.ratios")
    denominators = _mapping(_require(block["value"], "denominator", "deduct_ratio"),
                            "deduct_ratio.denominator")
    out: List[dict] = []
    for entry in segment.get("distresses") or []:
        if not isinstance(entry, Mapping):
            raise ValueError("segment.distresses[] 必须是对象")
        kind = _text(_require(entry, "type", "distresses[]"), "distresses[].type")
        severity = _text(_require(entry, "severity", "distresses[]"), "distresses[].severity")
        unit = _text(_require(entry, "unit", "distresses[]"), "distresses[].unit")
        quantity = _number(_require(entry, "quantity", "distresses[]"), "distresses[].quantity")
        if quantity < 0:
            raise ValueError("distresses[].quantity 不能为负：%r" % (quantity,))
        per_type = ratios.get(kind)
        if per_type is None:
            raise ValueError("破损类型 %r 不在扣分比率表里（%s）" % (kind, REASON_KEY_MISSING))
        per_type = _mapping(per_type, "deduct_ratio.ratios[%r]" % kind)
        ratio = per_type.get(severity)
        if ratio is None:
            raise ValueError("破损程度 %r 不在 %r 的比率档里（%s）" % (severity, kind, REASON_KEY_MISSING))
        field = denominators.get(unit)
        if field is None:
            raise ValueError("破损单位 %r 没有几何分母映射（%s）" % (unit, REASON_UNIT_UNMAPPED))
        denominator = _number(_require(segment, field, "segment"), "segment.%s" % field)
        if denominator <= 0:
            raise ValueError("segment.%s 必须为正（几何分母不能是 0）" % field)
        out.append({
            "type": kind,
            "severity": severity,
            "unit": unit,
            "quantity": quantity,
            "denominator": denominator,
            "denominator_field": field,
            "ratio": _number(ratio, "deduct_ratio.%s.%s" % (kind, severity)),
            "deducted": _round(_clamp(_number(ratio, "ratio") * (quantity / denominator) * 100.0)),
        })
    out.sort(key=lambda row: (row["type"], row["severity"], row["unit"]))
    return out


def _grade(value: float, bands_block: Mapping, where: str) -> str:
    boundary = str(_require(bands_block, "boundary", where))
    if boundary not in BOUNDARIES:
        raise ValueError("%s.boundary 非法：%r（允许 %s）" % (where, boundary, list(BOUNDARIES)))
    bands = _require(bands_block, "bands", where)
    if not isinstance(bands, list) or not bands:
        raise ValueError("%s.bands 必须是非空数组" % where)
    ordered = sorted(bands, key=lambda band: _number(_require(band, "min", "%s.bands[]" % where),
                                                     "%s.bands[].min" % where), reverse=True)
    for band in ordered:
        grade = _text(_require(band, "grade", "%s.bands[]" % where), "%s.bands[].grade" % where)
        if grade not in GRADE_ORDER:
            raise ValueError("%s.bands[].grade 非法：%r（允许 %s）" % (where, grade, list(GRADE_ORDER)))
        minimum = _number(band["min"], "%s.bands[].min" % where)
        if boundary == "lower_inclusive":
            if value >= minimum:
                return grade
        elif value > minimum:
            return grade
    return GRADE_ORDER[-1]


def _rank(grade: str) -> int:
    return GRADE_ORDER.index(grade)


def _action_class(metric_value: float, metric: str, rules: Sequence[Mapping]) -> Optional[dict]:
    for rule in rules:
        rule = _mapping(rule, "action_rule.rules[]")
        rule_metric = str(rule.get("metric") or "")
        if rule_metric != metric:
            continue
        op = str(_require(rule, "op", "action_rule.rules[]"))
        if op not in OPERATORS:
            raise ValueError("action_rule.rules[].op 非法：%r（允许 %s）" % (op, list(OPERATORS)))
        threshold = _number(_require(rule, "threshold", "action_rule.rules[]"), "rules[].threshold")
        hit = {
            "lt": metric_value < threshold,
            "le": metric_value <= threshold,
            "gt": metric_value > threshold,
            "ge": metric_value >= threshold,
        }[op]
        if hit:
            return {
                "rule_id": _text(_require(rule, "rule_id", "action_rule.rules[]"), "rules[].rule_id"),
                "metric": metric,
                "op": op,
                "threshold": threshold,
                "metric_value": metric_value,
                "action_class": _text(_require(rule, "action_class", "action_rule.rules[]"),
                                       "rules[].action_class"),
                "scale_band": rule.get("scale_band"),
            }
    return None


# ---------------------------------------------------------------------------
# 单路段
# ---------------------------------------------------------------------------
def _judge_segment(segment: Mapping, coefficients: Mapping, minimum_grade: str, basis) -> List[CalculationRecord]:
    segment_id = _text(_require(segment, "segment_id", "segments[]"), "segments[].segment_id")
    surface = _text(_require(segment, "surface_type", "segments[]"), "segments[].surface_type")
    where = "路段 %s" % segment_id

    weights_block = _coefficient(coefficients, "pci_weight.%s" % surface)
    weights = _mapping(_require(weights_block["value"], "weights", "pci_weight"),
                       "pci_weight.weights")
    unknown = set(weights) - set(COMPONENTS)
    if unknown:
        raise ValueError("%s 的权重出现未知分项：%s" % (where, sorted(unknown)))
    total_weight = sum(_number(weight, "weight") for weight in weights.values())
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError("%s 的分项权重之和必须为 1（实为 %r）" % (where, total_weight))

    contributions = _deductions(segment, surface, coefficients)
    deducted_total = _round(sum(row["deducted"] for row in contributions))
    components = _component_scores(segment, weights, coefficients)
    components["distress"] = _clamp(_round(CEIL - deducted_total))

    pci = _round(sum(float(weights[name]) * components.get(name, 0.0) for name in weights))
    pci = _clamp(pci)

    grade_block = _coefficient(coefficients, "grade_threshold.pci")["value"]
    grade = _grade(pci, grade_block, "grade_threshold.pci")

    action_block = _coefficient(coefficients, "action_rule.maintenance_trigger")["value"]
    rules = _require(action_block, "rules", "action_rule")
    if not isinstance(rules, list):
        raise ValueError("action_rule.rules 必须是数组")
    fired = _action_class(pci, "pci", rules) or _action_class(pci, "mqi", rules)

    records: List[CalculationRecord] = []

    pci_evidence = {
        "formula": "PCI = Σ 权重 × 分项得分；distress = 100 − Σ(比率 × 数量/几何分母 × 100)",
        "segment_id": segment_id,
        "surface_type": surface,
        "pci": pci,
        "weights": {name: float(weights[name]) for name in COMPONENTS if name in weights},
        "component_scores": {name: _round(components[name]) for name in COMPONENTS if name in components},
        "contributions": contributions,
        "deducted_total": deducted_total,
        "clause_ids": ["deduct_ratio.%s_distress" % surface, "pci_weight.%s" % surface,
                       "pci_component.ride_quality", "pci_component.rutting",
                       "pci_component.skid_resistance"],
    }
    records.append(CalculationRecord(
        item_id="pci.%s" % segment_id,
        verdict=OK,
        message="PCI %s（%s），扣分合计 %s，分项 %s"
        % (_fmt(pci), grade, _fmt(deducted_total),
           "，".join("%s=%s" % (name, _fmt(components[name])) for name in COMPONENTS if name in components)),
        basis=_basis_ref(basis, "pci_weight.%s" % surface),
        evidence=pci_evidence,
    ))

    grade_evidence = {
        "formula": "按 grade_threshold.pci 的 bands + boundary 查档",
        "segment_id": segment_id,
        "pci": pci,
        "grade": grade,
        "minimum_grade": minimum_grade,
        "boundary": str(grade_block["boundary"]),
        "bands": len(grade_block["bands"]),
        "grade_rank": _rank(grade),
        "minimum_rank": _rank(minimum_grade),
        "clause_ids": ["grade_threshold.pci"],
    }
    grade_rejected = _rank(grade) > _rank(minimum_grade)
    records.append(CalculationRecord(
        item_id="grade.%s" % segment_id,
        verdict=REJECTED if grade_rejected else OK,
        message="路况等级 %s（基线 %s，PCI %s）" % (grade, minimum_grade, _fmt(pci))
        + ("：低于项目基线" if grade_rejected else ""),
        basis=_basis_ref(basis, "grade_threshold.pci"),
        evidence=grade_evidence,
    ))

    action_evidence = {
        "formula": "IF 指标（pci|mqi） op 阈值 THEN 工程类别 + 规模档",
        "segment_id": segment_id,
        "pci": pci,
        "mqi_partial": pci,
        "metric_basis": "路段层 mqi 只有路面分项，取 PCI 等值（部分口径）",
        "action": fired,
        "clause_ids": ["action_rule.maintenance_trigger"],
    }
    records.append(CalculationRecord(
        item_id="action.%s" % segment_id,
        verdict=REJECTED if fired else OK,
        message=("触发养护对策：%s（%s %s %s）" % (fired["action_class"], fired["metric"],
                                                   fired["op"], _fmt(fired["threshold"])))
        if fired else "未触发养护对策（PCI %s 高于全部触发阈值）" % _fmt(pci),
        basis=_basis_ref(basis, "action_rule.maintenance_trigger"),
        evidence=action_evidence,
    ))
    return records


# ---------------------------------------------------------------------------
# 路线汇总（MQI）
# ---------------------------------------------------------------------------
def _judge_route(route_id: str, rows: Sequence[dict], coefficients: Mapping,
                 minimum_grade: str, basis) -> CalculationRecord:
    total_length = sum(row["length_m"] for row in rows)
    if total_length <= 0:
        raise ValueError("路线 %s 的长度合计必须为正" % route_id)
    mqi = _round(sum(row["length_m"] * row["pci"] for row in rows) / total_length)
    mqi = _clamp(mqi)
    block = _coefficient(coefficients, "grade_threshold.mqi")["value"]
    grade = _grade(mqi, block, "grade_threshold.mqi")
    rejected = _rank(grade) > _rank(minimum_grade)
    evidence = {
        "formula": "MQI = Σ(路段长度 × PCI) / Σ 路段长度（首期只有路面分项，partial）",
        "route_id": route_id,
        "level": "route",
        "scope_note": "只有 pavement 分项：MQI 等同长度加权 PCI，未套完整分项加权",
        "mqi": mqi,
        "grade": grade,
        "minimum_grade": minimum_grade,
        "weighted_length_m": _round(total_length),
        "segments": [{"segment_id": row["segment_id"], "length_m": row["length_m"],
                      "pci": row["pci"]} for row in rows],
        "clause_ids": ["mqi_weight.pavement", "grade_threshold.mqi"],
    }
    return CalculationRecord(
        item_id="mqi.%s" % route_id,
        verdict=REJECTED if rejected else OK,
        message="MQI %s（%s：%d 路段 / %s m）" % (_fmt(mqi), grade, len(rows), _fmt(total_length)),
        basis=_basis_ref(basis, "mqi_weight.pavement"),
        evidence=evidence,
    )


def _fmt(value: float) -> str:
    text = "%.2f" % float(value)
    return text.rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# 器官入口
# ---------------------------------------------------------------------------
def evaluate(subject: Mapping, basis) -> Iterable[CalculationRecord]:
    if not isinstance(subject, Mapping):
        raise ValueError("subject 必须是 JSON 对象")
    project = _text(_require(subject, "project", "subject"), "subject.project")
    minimum_grade = _text(_require(subject, "minimum_grade", "subject"), "subject.minimum_grade")
    if minimum_grade not in GRADE_ORDER:
        raise ValueError("minimum_grade 非法：%r（允许 %s）" % (minimum_grade, list(GRADE_ORDER)))
    segments = _require(subject, "segments", "subject")
    if not isinstance(segments, list) or not segments:
        raise ValueError("segments 必须是非空数组")
    coefficients = _coefficients(subject)

    records: List[CalculationRecord] = []
    by_route: Dict[str, List[dict]] = {}
    seen = set()
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise ValueError("segments[] 必须是对象")
        segment_id = _text(_require(segment, "segment_id", "segments[]"), "segments[].segment_id")
        if segment_id in seen:
            raise ValueError("路段重复：%s" % segment_id)
        seen.add(segment_id)
        route_id = _text(_require(segment, "route_id", "segments[]"), "segments[].route_id")
        length_m = _number(_require(segment, "length_m", "segments[]"), "segments[].length_m")
        if length_m <= 0:
            raise ValueError("segments[].length_m 必须为正：%r" % (length_m,))
        segment_records = _judge_segment(segment, coefficients, minimum_grade, basis)
        records.extend(segment_records)
        pci_record = next(record for record in segment_records if record.item_id.startswith("pci."))
        by_route.setdefault(route_id, []).append(
            {"segment_id": segment_id, "length_m": length_m, "pci": pci_record.evidence["pci"]}
        )

    for route_id in sorted(by_route):
        records.append(_judge_route(route_id, by_route[route_id], coefficients, minimum_grade, basis))

    if not records:
        raise ValueError("工程 %s 在给定输入上没有任何可判行" % project)
    return tuple(records)


register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary="公路技术状况评定：PCI / 路况等级 / 养护对策 / 路线 MQI（JTG 5210-2018 口径）",
        input_fields=("project", "minimum_grade", "segments", "coefficients"),
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "evaluate", "GRADE_ORDER", "COMPONENTS"]