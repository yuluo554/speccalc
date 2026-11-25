"""``steel-member`` 测试套共用构造器（**不是**测试文件，不被收集）。

9 条验算式各有自己的「作用 → 抗力」分母；本文件把每条验算式的
**抗力**（按手工算式算出）与**让它落在指定 ratio 上的作用**写在一处，
测试只负责断言 ratio / 结论 / 依据。

对抗力的来源（GB 50017-2017 的验算形态，数值全取夹具）：
- butt.tension   ``l_w×t×f_t^w``        = 200×10×175    = 350 000 N
- butt.shear     ``l_w×t×f_v^w``        = 200×10×100    = 200 000 N
- fillet.side    ``h_e×l_w总×f_f^w``    = 5.6×400×160   = 358 400 N
- fillet.front   ``β_f×h_e×l_w总×f_f^w``= 1.22×2240×160 = 437 248 N
- bolt.shear     ``A_s×f_v^b``（单栓）  = π×20²/4×140
- bolt.bearing   ``d×Σt×f_c^b``（单栓） = 20×20×305    = 122 000 N
- hsb.friction   ``k×n_f×μ×P``（单栓）  = 0.9×2×0.45×155 000 = 125 550 N
- column.stability ``φ×A×f``            = 0.75×5000×305 = 1 143 750 N
- column.slenderness ``λ ≤ λ_max``      = 100/150
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from math import pi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from speccalc.core import Basis, Clause  # noqa: E402
from speccalc.modules import load_builtin  # noqa: E402

load_builtin()
ORGAN = importlib.import_module("speccalc.modules.steel-member")
SLUG = ORGAN.SLUG

CODE = "GB 50017-2017"
SAMPLE = os.path.join(ROOT, "samples", "steel-member", "a2-fillet-weld.json")
BASIS_FILE = os.path.join(ROOT, "samples", "basis.json")
CLAUSE_NUMBERS = ("11.2.1", "11.2.2", "11.4.1", "11.4.2", "7.2.1", "7.2.2")
BASIS = Basis(version="steel-kit-20261125",
              clauses=tuple(Clause(code=CODE, clause=number, version="2017", text=number)
                            for number in CLAUSE_NUMBERS))

DESIGN = {
    "f_t_w": 175.0, "f_v_w": 100.0, "f_f_w": 160.0, "beta_f": 1.22,
    "f_v_b": 140.0, "f_c_b": 305.0, "k_hsb": 0.9, "mu_hsb": 0.45,
    "P_hsb": 155000.0, "f_y": 305.0, "phi": 0.75, "lambda_max": 150.0,
}
DESIGN_KEYS = tuple(DESIGN)

BUTT = {"l_w": 200.0, "t": 10.0}
FILLET_SIDE = {"h_f": 8.0, "l_w": 200.0, "n_welds": 2, "load_direction": "side"}
FILLET_FRONT = {"h_f": 8.0, "l_w": 200.0, "n_welds": 2, "load_direction": "front"}
BOLT = {"d": 20.0, "bolt_count": 4.0, "t_sum": 20.0}
HSB = {"n_f": 2.0, "bolt_count": 4.0}
COLUMN = {"A": 5000.0, "l_0x": 6000.0, "l_0y": 6000.0, "i_x": 80.0, "i_y": 60.0}

BOLT_AREA = pi * 20.0 * 20.0 / 4.0
BOLT_SHEAR_CAPACITY = BOLT_AREA * 140.0        # 单栓抗剪
BOLT_BEARING_CAPACITY = 20.0 * 20.0 * 305.0    # 单栓承压
HSB_CAPACITY = 0.9 * 2.0 * 0.45 * 155000.0     # 单栓摩擦
COLUMN_CAPACITY = 0.75 * 5000.0 * 305.0        # 轴压稳定
SLENDERNESS_ALLOWABLE = 150.0

#: check → (module, params, 单值作用键, 该键对应的抗力, 作用是否按「栓数」分摊)
_CHECKS = {
    "butt.tension": ("butt_weld", BUTT, "N", 350000.0, False),
    "butt.shear": ("butt_weld", BUTT, "V", 200000.0, False),
    "fillet.side": ("fillet_weld", FILLET_SIDE, "N", 358400.0, False),
    "fillet.front": ("fillet_weld", FILLET_FRONT, "N", 437248.0, False),
    "bolt.shear": ("bolt_normal", BOLT, "V", BOLT_SHEAR_CAPACITY, True),
    "bolt.bearing": ("bolt_normal", BOLT, "V", BOLT_BEARING_CAPACITY, True),
    "hsb.friction": ("bolt_hsb_friction", HSB, "V", HSB_CAPACITY, True),
    "column.stability": ("column_buckling", COLUMN, "N", COLUMN_CAPACITY, False),
    "column.slenderness": ("column_buckling", COLUMN, "N", SLENDERNESS_ALLOWABLE, False),
}
CHECKS = tuple(_CHECKS)
SPEC = _CHECKS

#: check → 该验算式引用的条号
CLAUSE_OF = {
    "butt.tension": "11.2.1", "butt.shear": "11.2.1",
    "fillet.side": "11.2.2", "fillet.front": "11.2.2",
    "bolt.shear": "11.4.1", "bolt.bearing": "11.4.1",
    "hsb.friction": "11.4.2",
    "column.stability": "7.2.1", "column.slenderness": "7.2.2",
}
#: check → 该验算式绑定的设计值键（承载力里的那个量）
LIMIT_KEY = {
    "butt.tension": "f_t_w", "butt.shear": "f_v_w",
    "fillet.side": "f_f_w", "fillet.front": "f_f_w",
    "bolt.shear": "f_v_b", "bolt.bearing": "f_c_b",
    "hsb.friction": "P_hsb",
    "column.slenderness": "lambda_max",
}


# ---------------------------------------------------------------------------
# 构造器
# ---------------------------------------------------------------------------
def dv(**overrides):
    values = {key: {"kind": "standard_value", "status": "verified", "value": value,
                    "evidence": "FIXTURE:kit"}
              for key, value in DESIGN.items()}
    for key, value in overrides.items():
        if isinstance(value, dict):
            values[key] = value
        elif value is None:
            values.pop(key, None)
        else:
            values[key] = {"kind": "standard_value", "status": "verified", "value": value,
                           "evidence": "FIXTURE:kit"}
    return values


def subject(module, params, forces, values=None, case_id="CASE-1"):
    return {"case_id": case_id, "module": module, "params": params, "forces": forces,
            "design_values": values if values is not None else dv()}


def run(payload, basis=BASIS):
    return tuple(ORGAN.evaluate(payload, basis))


def row(module, params, forces, check, values=None, basis=BASIS):
    hits = [record for record in run(subject(module, params, forces, values), basis)
            if record.evidence["check"] == check]
    assert len(hits) == 1, [record.item_id for record in hits]
    return hits[0]


# ---------------------------------------------------------------------------
# 让某条验算式落在指定 ratio 上
# ---------------------------------------------------------------------------
def payload_for(check, ratio=1.0, values=None):
    """构造一条使目标验算式 ratio = ratio 的 subject（其余行落在安全侧）。"""
    module, params, force_key, capacity, per_bolt = _CHECKS[check]
    params = dict(params)
    if check == "column.slenderness":
        # λ = max(l_0x/i_x, l_0y/i_y) = 6000/i_y；让它等于 ratio × λ_max
        params["i_y"] = 6000.0 / (SLENDERNESS_ALLOWABLE * ratio)
        forces = {"N": 0.0}
    elif check == "column.stability":
        forces = {"N": capacity * ratio}
    elif per_bolt:
        forces = {force_key: float(params["bolt_count"]) * capacity * ratio}
    else:
        forces = {force_key: capacity * ratio}
    return subject(module, params, forces, values)


def row_for(check, ratio=1.0, values=None, basis=BASIS):
    payload = payload_for(check, ratio, values)
    return row(payload["module"], payload["params"], payload["forces"], check, values, basis)


def basis_without(number):
    return Basis(version="thin", clauses=tuple(
        Clause(code=CODE, clause=other, version="2017", text=other)
        for other in CLAUSE_NUMBERS if other != number))


def sample_subject():
    with open(SAMPLE, "r", encoding="utf-8") as handle:
        return json.load(handle)


def sample_basis():
    return Basis.from_json(BASIS_FILE)


__all__ = [
    "ORGAN", "SLUG", "CODE", "SAMPLE", "BASIS_FILE", "CLAUSE_NUMBERS", "BASIS", "DESIGN",
    "DESIGN_KEYS", "BUTT", "FILLET_SIDE", "FILLET_FRONT", "BOLT", "HSB", "COLUMN", "CHECKS",
    "SPEC", "CLAUSE_OF", "LIMIT_KEY", "BOLT_AREA", "BOLT_SHEAR_CAPACITY",
    "BOLT_BEARING_CAPACITY", "HSB_CAPACITY", "COLUMN_CAPACITY", "SLENDERNESS_ALLOWABLE",
    "dv", "subject", "run", "row", "payload_for", "row_for", "basis_without", "sample_subject",
    "sample_basis",
]