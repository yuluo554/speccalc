"""``pavement-mqi`` 测试套共用构造器（**不是**测试文件，不被收集）。

三个测试文件（``test_pavement_mqi_deduct.py`` / ``test_pavement_mqi_grade.py`` /
``test_pavement_mqi_contract.py``）共用这里的夹具，避免同一份系数格写三遍。

构造原则
- 系数格一律 ``status="verified"`` + ``value`` + ``evidence``（器官的硬门槛）；
- 分档表默认取 5 档 90/80/70/60/0（``lower_inclusive``）；
- 「让 PCI 正好等于某个值」用扣分反算：distress 权重 1.0 时
  ``PCI = 100 − ratio × qty / 几何分母 × 100``，
  故 ``qty = (100 − target) × 分母 / (100 × ratio)``。
"""

from __future__ import annotations

import importlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from speccalc.core import Basis, Clause  # noqa: E402
from speccalc.modules import load_builtin  # noqa: E402

load_builtin()
ORGAN = importlib.import_module("speccalc.modules.pavement-mqi")
SLUG = ORGAN.SLUG

JTG = "JTG 5210-2018"
SAMPLE = os.path.join(ROOT, "samples", "pavement-mqi", "s99-2022.json")
BASIS_FILE = os.path.join(ROOT, "samples", "basis.json")

KEYS = (
    "deduct_ratio.asphalt_distress", "deduct_ratio.cement_distress",
    "pci_component.ride_quality", "pci_component.rutting", "pci_component.skid_resistance",
    "pci_weight.asphalt", "pci_weight.cement",
    "grade_threshold.pci", "grade_threshold.mqi", "mqi_weight.pavement",
    "action_rule.maintenance_trigger",
)
BASIS = Basis(version="road-kit-20261125",
              clauses=tuple(Clause(code=JTG, clause=key, version="2018", text=key) for key in KEYS))

#: 旧仓夹具口径的扣分比率（沥青）
RATIOS = {
    "横向裂缝": {"轻": 0.4, "中": 0.8, "重": 1.2},
    "纵向裂缝": {"轻": 0.3, "中": 0.6, "重": 0.9},
    "车辙": {"轻": 0.5, "中": 1.0, "重": 1.5},
    "坑槽": {"轻": 0.8, "中": 1.6, "重": 2.4},
}
#: 水泥路面用另一套比率：证明器官取的是 ``deduct_ratio.cement_distress`` 而不是沥青那份
CEMENT_RATIOS = {
    "横向裂缝": {"轻": 0.6, "中": 1.1, "重": 1.7},
    "纵向裂缝": {"轻": 0.2, "中": 0.5, "重": 1.1},
    "车辙": {"轻": 0.4, "中": 0.9, "重": 1.3},
    "坑槽": {"轻": 1.0, "中": 2.0, "重": 3.0},
}
DENOMINATOR = {"m": "length_m", "m2": "length_m", "处": "panel_count"}

BANDS = {
    "boundary": "lower_inclusive",
    "bands": [{"grade": "优", "min": 90}, {"grade": "良", "min": 80},
              {"grade": "中", "min": 70}, {"grade": "次", "min": 60},
              {"grade": "差", "min": 0}],
}

WEIGHTS = {"distress": 0.35, "ride_quality": 0.35, "rutting": 0.2, "skid_resistance": 0.1}
DISTRESS_ONLY = {"distress": 1.0, "ride_quality": 0.0, "rutting": 0.0, "skid_resistance": 0.0}

DEFAULT_RULES = {"rules": [
    {"rule_id": "AR-60", "metric": "pci", "op": "lt", "threshold": 60,
     "action_class": "大修", "scale_band": "全幅"},
    {"rule_id": "AR-70", "metric": "pci", "op": "lt", "threshold": 70,
     "action_class": "中修", "scale_band": "分段"},
    {"rule_id": "AR-80", "metric": "pci", "op": "lt", "threshold": 80,
     "action_class": "小修", "scale_band": "点状"},
]}


# ---------------------------------------------------------------------------
# 构造器
# ---------------------------------------------------------------------------
def coef(key, value, status="verified", evidence="FIXTURE:kit"):
    return {"key": key, "status": status, "value": value, "evidence": evidence}


def coefficients(surface="asphalt", ratios=None, weights=None, pci_bands=None, mqi_bands=None,
                 rules=None, components=None):
    """一份完整的系数格（11 格里用得到的那 8 格 + 可选覆盖）。"""
    blocks = {
        "deduct_ratio.%s_distress" % surface: {
            "ratios": ratios if ratios is not None else (
                CEMENT_RATIOS if surface == "cement" else RATIOS),
            "denominator": dict(DENOMINATOR),
        },
        "pci_component.ride_quality": {"ideal_value": 10.0, "zero_value": 0.0},
        "pci_component.rutting": {"ideal_mm": 0.0, "zero_mm": 20.0},
        "pci_component.skid_resistance": {"ideal_value": 60.0, "zero_value": 0.0},
        "pci_weight.%s" % surface: {"weights": weights if weights is not None else dict(WEIGHTS)},
        "grade_threshold.pci": dict(pci_bands if pci_bands is not None else BANDS),
        "grade_threshold.mqi": dict(mqi_bands if mqi_bands is not None else BANDS),
        "mqi_weight.pavement": {"weights": {"pavement": 1.0}},
        "action_rule.maintenance_trigger": dict(rules if rules is not None else DEFAULT_RULES),
    }
    for key, value in (components or {}).items():
        blocks[key] = value
    return [coef(key, value) for key, value in blocks.items()]


def seg(segment_id="S-1", route_id="R1", length_m=1000.0, surface="asphalt",
        rqi=8.0, rut=5.0, skid=30.0, distresses=(), panel_count=500, **extra):
    segment = {
        "segment_id": segment_id, "route_id": route_id, "surface_type": surface,
        "length_m": length_m, "lane_count": 2, "width_m": 7.5, "panel_count": panel_count,
        "measured": {"rqi": rqi, "rut_depth_mm": rut, "skid": skid},
        "distresses": list(distresses),
    }
    segment.update(extra)
    return segment


def distress(kind="横向裂缝", severity="轻", quantity=100.0, unit="m"):
    return {"type": kind, "severity": severity, "quantity": quantity, "unit": unit}


def seg_with_pci(target, segment_id="S-1", route_id="R1", length_m=1000.0, surface="asphalt",
                 kind="横向裂缝", severity="轻", unit="m", panel_count=500):
    """构造一个 PCI 正好等于 ``target`` 的路段（只留 distress 权重，扣分反算数量）。

    几何分母取该路段**自己的** ``length_m`` / ``panel_count``（不是写死 1000/500），
    否则换长度后算出来的就不是 ``target`` 了。
    """
    ratios = CEMENT_RATIOS if surface == "cement" else RATIOS
    ratio = ratios[kind][severity]
    field = DENOMINATOR[unit]
    denominator = float(length_m) if field == "length_m" else float(panel_count)
    quantity = round((100.0 - target) * denominator / (100.0 * ratio), 6)
    segment = seg(segment_id=segment_id, route_id=route_id, length_m=length_m, surface=surface,
                  panel_count=panel_count)
    segment["measured"] = {}
    segment["distresses"] = [distress(kind, severity, quantity, unit)]
    return segment


def subject(segments, coefficient_list=None, minimum_grade="中", project="P", **extra):
    payload = {
        "project": project,
        "minimum_grade": minimum_grade,
        "segments": list(segments),
        "coefficients": coefficient_list if coefficient_list is not None else coefficients(),
    }
    payload.update(extra)
    return payload


def subject_for_pci(target, minimum_grade="中", surface="asphalt", **kwargs):
    """单路段 PCI = target 的 subject（配套 DISTRESS_ONLY 权重）。"""
    segment = seg_with_pci(target, surface=surface, **kwargs)
    return subject([segment], coefficients(surface=surface, weights=DISTRESS_ONLY),
                   minimum_grade=minimum_grade)


def run(payload, basis=BASIS):
    return tuple(ORGAN.evaluate(payload, basis))


def get(records, prefix):
    hits = [record for record in records if record.item_id.startswith(prefix + ".")]
    assert len(hits) == 1, [record.item_id for record in records]
    return hits[0]


def pci_of(payload):
    return get(run(payload), "pci").evidence["pci"]


def grade_of(target, boundary="lower_inclusive", minimum_grade="中"):
    """单路段 PCI = target 的 grade 记录。"""
    bands = dict(BANDS)
    bands["boundary"] = boundary
    payload = subject_for_pci(target, minimum_grade=minimum_grade)
    payload["coefficients"] = coefficients(weights=DISTRESS_ONLY, pci_bands=bands, mqi_bands=bands)
    return get(run(payload), "grade")


def action_of(target, rules=None, minimum_grade="中"):
    payload = subject_for_pci(target, minimum_grade=minimum_grade)
    payload["coefficients"] = coefficients(weights=DISTRESS_ONLY, rules=rules)
    return get(run(payload), "action")


def mqi_of(segments, minimum_grade="中", surface="asphalt", component_list=None, mqi_bands=None):
    if component_list is None:
        component_list = coefficients(surface=surface, weights=DISTRESS_ONLY, mqi_bands=mqi_bands)
    payload = subject(segments, component_list, minimum_grade=minimum_grade)
    return get(run(payload), "mqi")


def sample_subject():
    with open(SAMPLE, "r", encoding="utf-8") as handle:
        return json.load(handle)


def sample_basis():
    return Basis.from_json(BASIS_FILE)


__all__ = [
    "ORGAN", "SLUG", "JTG", "SAMPLE", "BASIS_FILE", "KEYS", "BASIS", "RATIOS",
    "CEMENT_RATIOS", "DENOMINATOR", "BANDS", "WEIGHTS", "DISTRESS_ONLY", "DEFAULT_RULES",
    "coef", "coefficients", "seg", "distress", "seg_with_pci", "subject", "subject_for_pci",
    "run", "get", "pci_of", "grade_of", "action_of", "mqi_of", "sample_subject",
    "sample_basis",
]