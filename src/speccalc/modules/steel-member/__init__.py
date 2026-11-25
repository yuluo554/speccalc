"""器官：钢结构验算（steel-member）。

迁自 target-map ③ 行（GB 50017-2017 口径，5 个计算模块）。
迁入后只保留**算这一层**：IR 解析、知识库装载、检查单、报告、GUI、打包全部舍弃。

一句话语义
    subject 给「模块 + 内力 + 几何参数 + 已核对的设计值/系数」，
    basis 给「GB 50017-2017 的条号」，
    本器官逐条验算式算出 ratio（作用 / 抗力），并按 ratio 与构造限值给出 ok / rejected。

三个模块共 9 条验算式，每条一个账本行：
  butt_weld            抗拉 N/(l_w·t) ≤ f_t^w      抗剪 V/(l_w·t) ≤ f_v^w       （11.2.1）
  fillet_weld          侧面 N/(h_e·l_w总) ≤ f_f^w   正面 ≤ β_f·f_f^w             （11.2.2）
  bolt_normal          抗剪 N_v/A_s ≤ f_v^b         承压 N_v/(d·Σt) ≤ f_c^b     （11.4.1）
  bolt_hsb_friction    摩擦 k·n_f·μ·P ≥ N_v                                    （11.4.2）
  column_buckling      稳定 N/(φ·A) ≤ f            长细比 λ ≤ 容许长细比        （7.2.1 / 7.2.2）

纪律（与旧仓一致，本产品更严的地方写清）
1. **设计值只认已核对来源**：``status == "verified"`` + ``value`` + ``evidence``；
   否则拒绝计算（旧仓出 ``blocked``；本产品无降级态 → 退出码 2）。
2. **``ratio`` 恒为「作用 / 抗力」**：反向写法（抗力 ≥ 作用）只在 evidence 里保留原式，
   入账的 ratio 统一成作用/抗力，避免「有的行小于 1 合格、有的行大于 1 合格」。
3. **拒算不外流数值**：报错只出现键名与原因码。

依据口径（重要）：本器官是三个器官里**唯一能给出真条号**的——旧仓
``data/clauses/gb50017.json`` 的条号是逐条登记过的（11.2.1 / 11.2.2 / 11.4.1 /
11.4.2 / 7.2.1 / 7.2.2），本器官原样引用，不自造编号。
"""

from __future__ import annotations

from math import pi
from typing import Dict, Iterable, List, Mapping, Optional

from speccalc.core.data import load
from speccalc.core.ledger import OK, REJECTED, CalculationRecord, ContractError
from speccalc.core.registry import Pack, register

SLUG = "steel-member"
VERSION = "0.1.0"
DATA = load("steel-member.json")

CODE = DATA["code"]
STANDARD_VERSION = DATA["standard_version"]
CLAUSES: Dict[str, dict] = DATA["clauses"]
MODULES: Dict[str, dict] = DATA["modules"]
RATIO_TOL = float(DATA["constants"]["ratio_tol"])
NEED_ADJUST_FLOOR = float(DATA["constants"]["need_adjust_floor"])
FILLET_FACTOR = float(DATA["constants"]["fillet_effective_factor"])

REASON_NOT_VERIFIED = "source_not_confirmed"
REASON_VALUE_MISSING = "value_missing"
REASON_EVIDENCE_MISSING = "evidence_missing"
REASON_DESIGN_VALUE_MISSING = "design_value_missing"
REASON_MODULE_UNKNOWN = "module_unknown"


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------
def _require(mapping, key, where):
    if not isinstance(mapping, Mapping):
        raise ValueError("%s 必须是对象" % where)
    if key not in mapping or mapping[key] is None:
        raise ValueError("%s 缺少必填字段：%s" % (where, key))
    return mapping[key]


def _number(value, where):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s 必须是数值：%r" % (where, value))
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("%s 必须是有限数值：%r" % (where, value))
    return value


def _positive(value, where):
    number = _number(value, where)
    if number <= 0:
        raise ValueError("%s 必须为正：%r" % (where, number))
    return number


def _text(value, where):
    if value is None or not str(value).strip():
        raise ValueError("%s 不能为空" % where)
    return str(value)


def _values(subject: Mapping) -> Dict[str, dict]:
    """设计值/系数表：只认已核对来源。"""
    raw = _require(subject, "design_values", "subject")
    if not isinstance(raw, Mapping) or not raw:
        raise ValueError("design_values 必须是非空对象")
    out: Dict[str, dict] = {}
    for key, block in raw.items():
        if not isinstance(block, Mapping):
            raise ValueError("design_values.%s 必须是对象" % key)
        if str(block.get("status") or "") != "verified":
            raise ValueError("设计值 %s 未核对来源：status=%r（%s）"
                             % (key, block.get("status"), REASON_NOT_VERIFIED))
        if not block.get("evidence"):
            raise ValueError("设计值 %s 缺出处凭证（%s）" % (key, REASON_EVIDENCE_MISSING))
        if block.get("value") is None:
            raise ValueError("设计值 %s 缺数值（%s）" % (key, REASON_VALUE_MISSING))
        out[key] = {"value": _number(block["value"], "design_values.%s" % key),
                    "kind": str(block.get("kind") or ""),
                    "evidence": str(block["evidence"])}
    return out


def _value(values: Mapping, key: str) -> float:
    block = values.get(key)
    if block is None:
        raise ValueError("缺少设计值：%s（%s）" % (key, REASON_DESIGN_VALUE_MISSING))
    return block["value"]


# ---------------------------------------------------------------------------
# 账本行
# ---------------------------------------------------------------------------
def _row(item_id: str, ratio: float, message: str, clause_key: str, basis, evidence: Mapping):
    entry = CLAUSES[clause_key]
    ref = basis.ref(CODE, entry["clause"])
    verdict = REJECTED if ratio > 1.0 + RATIO_TOL else OK
    payload = {
        "formula": entry["topic"],
        "check": clause_key,
        "ratio": ratio,
        "ratio_tol": RATIO_TOL,
        "need_adjust": ratio > NEED_ADJUST_FLOOR,
        "verdict_rule": "ratio <= 1 + 1e-3 记 ok；否则 rejected（need_adjust 只作提示，不改结论）",
    }
    payload.update(evidence)
    return CalculationRecord(item_id=item_id, verdict=verdict, message=message,
                             basis=ref, evidence=payload)


def _ratio_check(item_id, demand, capacity, clause_key, basis, unit, formula, extra=None):
    """作用 / 抗力 的统一入账：ratio 恒为作用/抗力。"""
    ratio = demand / capacity
    evidence = {
        "demand": demand,
        "capacity": capacity,
        "unit": unit,
        "expression": formula,
    }
    if extra:
        evidence.update(extra)
    message = "%s：作用 %s %s / 抗力 %s %s = %.4f" % (
        item_id, _fmt(demand), unit, _fmt(capacity), unit, ratio)
    return _row(item_id, ratio, message, clause_key, basis, evidence)


def _fmt(value: float) -> str:
    return ("%.4f" % float(value)).rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# 五类验算
# ---------------------------------------------------------------------------
def _butt_weld(params, forces, values, basis, case_id):
    l_w = _positive(_require(params, "l_w", "params"), "params.l_w")
    t = _positive(_require(params, "t", "params"), "params.t")
    area = l_w * t
    out = []
    if forces.get("N") is not None:
        f_t_w = _value(values, "f_t_w")
        out.append(_ratio_check(
            "butt.tension", _number(forces["N"], "forces.N"), area * f_t_w, "butt.tension", basis, "N",
            "N / (l_w × t × f_t^w)", {"l_w": l_w, "t": t, "A_w": area,
                                      "limit_key": "f_t_w", "limit_value": f_t_w},
        ))
    if forces.get("V") is not None:
        f_v_w = _value(values, "f_v_w")
        out.append(_ratio_check(
            "butt.shear", _number(forces["V"], "forces.V"), area * f_v_w, "butt.shear", basis, "N",
            "V / (l_w × t × f_v^w)", {"l_w": l_w, "t": t, "A_w": area,
                                      "limit_key": "f_v_w", "limit_value": f_v_w},
        ))
    return out


def _fillet_weld(params, forces, values, basis, case_id):
    h_f = _positive(_require(params, "h_f", "params"), "params.h_f")
    l_w = _positive(_require(params, "l_w", "params"), "params.l_w")
    n_welds = _positive(_require(params, "n_welds", "params"), "params.n_welds")
    direction = _text(_require(params, "load_direction", "params"), "params.load_direction")
    if direction not in ("side", "front"):
        raise ValueError("params.load_direction 非法：%r（允许 side / front）" % (direction,))
    h_e = FILLET_FACTOR * h_f
    l_total = n_welds * l_w
    capacity_area = h_e * l_total
    demand = _number(_require(forces, "N", "forces"), "forces.N")
    f_f_w = _value(values, "f_f_w")
    if direction == "side":
        return [_ratio_check("fillet.side", demand, capacity_area * f_f_w, "fillet.side", basis, "N",
                             "N / (h_e × l_w总 × f_f^w)，h_e = 0.7 × h_f",
                             {"h_f": h_f, "h_e": _round(h_e), "n_welds": n_welds,
                              "l_w_total": l_total, "A_e": _round(capacity_area),
                              "limit_key": "f_f_w", "limit_value": f_f_w})]
    beta_f = _value(values, "beta_f")
    return [_ratio_check("fillet.front", demand, capacity_area * beta_f * f_f_w, "fillet.front",
                         basis, "N", "N / (β_f × h_e × l_w总 × f_f^w)，h_e = 0.7 × h_f",
                         {"h_f": h_f, "h_e": _round(h_e), "n_welds": n_welds,
                          "l_w_total": l_total, "A_e": _round(capacity_area), "beta_f": beta_f,
                          "limit_key": "f_f_w", "limit_value": f_f_w})]


def _bolt_normal(params, forces, values, basis, case_id):
    d = _positive(_require(params, "d", "params"), "params.d")
    count = _positive(_require(params, "bolt_count", "params"), "params.bolt_count")
    t_sum = _positive(_require(params, "t_sum", "params"), "params.t_sum")
    shear = _number(_require(forces, "V", "forces"), "forces.V")
    per_bolt = shear / count
    area = pi * d * d / 4.0
    f_v_b = _value(values, "f_v_b")
    f_c_b = _value(values, "f_c_b")
    records = [
        _ratio_check("bolt.shear", per_bolt, area * f_v_b, "bolt.shear", basis, "N",
                     "N_v / (A_s × f_v^b)，N_v = V / n，A_s = π d² / 4",
                     {"d": d, "bolt_count": count, "A_s": _round(area), "N_v": per_bolt,
                      "limit_key": "f_v_b", "limit_value": f_v_b}),
        _ratio_check("bolt.bearing", per_bolt, d * t_sum * f_c_b, "bolt.bearing", basis, "N",
                     "N_v / (d × Σt × f_c^b)",
                     {"d": d, "t_sum": t_sum, "N_v": per_bolt,
                      "limit_key": "f_c_b", "limit_value": f_c_b}),
    ]
    return records


def _bolt_hsb(params, forces, values, basis, case_id):
    n_f = _positive(_require(params, "n_f", "params"), "params.n_f")
    count = _positive(_require(params, "bolt_count", "params"), "params.bolt_count")
    shear = _number(_require(forces, "V", "forces"), "forces.V")
    per_bolt = shear / count
    k = _value(values, "k_hsb")
    mu = _value(values, "mu_hsb")
    preload = _value(values, "P_hsb")
    capacity = k * n_f * mu * preload
    return [_ratio_check("hsb.friction", per_bolt, capacity, "hsb.friction", basis, "N",
                         "N_v ≤ k × n_f × μ × P（ratio = N_v / 抗力）",
                         {"n_f": n_f, "bolt_count": count, "N_v": per_bolt, "k": k, "mu": mu,
                          "P": preload, "limit_key": "P_hsb", "limit_value": preload})]


def _column_buckling(params, forces, values, basis, case_id):
    area = _positive(_require(params, "A", "params"), "params.A")
    l_0x = _positive(_require(params, "l_0x", "params"), "params.l_0x")
    l_0y = _positive(_require(params, "l_0y", "params"), "params.l_0y")
    i_x = _positive(_require(params, "i_x", "params"), "params.i_x")
    i_y = _positive(_require(params, "i_y", "params"), "params.i_y")
    axial = _number(_require(forces, "N", "forces"), "forces.N")
    phi = _value(values, "phi")
    f_y = _value(values, "f_y")
    lambda_x = l_0x / i_x
    lambda_y = l_0y / i_y
    lam = max(lambda_x, lambda_y)
    records = [
        _ratio_check("column.stability", axial, phi * area * f_y, "column.stability", basis, "N",
                     "N / (φ × A × f)",
                     {"A": area, "phi": phi, "f": f_y, "lambda": lam}),
    ]
    lambda_max = _value(values, "lambda_max")
    ratio = lam / lambda_max
    records.append(_row(
        "column.slenderness", ratio,
        "长细比 λ = %s／容许 %s = %.4f（控制轴 %s）"
        % (_fmt(lam), _fmt(lambda_max), ratio, "x" if lambda_x >= lambda_y else "y"),
        "column.slenderness", basis,
        {"formula": CLAUSES["column.slenderness"]["topic"],
         "lambda_x": lambda_x, "lambda_y": lambda_y, "lambda": lam,
         "limit_key": "lambda_max", "limit_value": lambda_max,
         "expression": "λ = max(l_0x/i_x, l_0y/i_y)"},
    ))
    return records


def _round(value: float) -> float:
    return round(float(value), 6)


_HANDLERS = {
    "butt_weld": _butt_weld,
    "fillet_weld": _fillet_weld,
    "bolt_normal": _bolt_normal,
    "bolt_hsb_friction": _bolt_hsb,
    "column_buckling": _column_buckling,
}


# ---------------------------------------------------------------------------
# 器官入口
# ---------------------------------------------------------------------------
def evaluate(subject: Mapping, basis) -> Iterable[CalculationRecord]:
    if not isinstance(subject, Mapping):
        raise ValueError("subject 必须是 JSON 对象")
    module = _text(_require(subject, "module", "subject"), "subject.module")
    if module not in MODULES:
        raise ValueError("未知模块：%r（允许 %s，%s）" % (module, sorted(MODULES), REASON_MODULE_UNKNOWN))
    case_id = _text(_require(subject, "case_id", "subject"), "subject.case_id")
    params = _require(subject, "params", "subject")
    forces = _require(subject, "forces", "subject")
    if not isinstance(forces, Mapping):
        raise ValueError("forces 必须是对象")
    values = _values(subject)

    records = _HANDLERS[module](params, forces, values, basis, case_id)
    if not records:
        raise ValueError("模块 %s 的输入里没有任何可验算的内力（forces 至少要给一项）" % module)
    for record in records:
        record.evidence["module"] = module
        record.evidence["case_id"] = case_id
    return tuple(records)


register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary="钢结构验算：对接/角焊缝、普通/高强螺栓、轴压稳定与长细比（GB 50017-2017）",
        input_fields=("module", "case_id", "params", "forces", "design_values"),
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "evaluate", "MODULES", "CLAUSES"]