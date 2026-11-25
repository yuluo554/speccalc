"""器官：脚手架与模板支架（formwork-scaffold）。

迁自 target-map ③ 行（JGJ 130-2011 / JGJ 162-2008 / 住建部令第 37 号 /
建办质〔2018〕31号）。迁入后只保留**判定**这一层：参数卡解析、报告排版、
GUI、打包、合成数据生成全部舍弃（见 ``docs/formwork-scaffold.md``）。

一句话语义
    ``subject`` 给「模式 + 参数卡」，``basis`` 给「规范条号」，
    本器官算三类结论并逐条挂条款：
    - ``calc``   ：M-1~M-6 六个验算模块（立杆稳定 / 水平杆 / 连墙件 / 地基 / 模板支架）；
    - ``grade``  ：危大分级（非危大 / 危大 / 超过一定规模须专家论证）；
    - ``review`` ：构造限值核查 + 两张皮一致性 + 分级联动。

字段口径
    ``calc.card``   与旧仓参数卡同义（扁平键；见 docs 的字段表）。
    ``review.scheme`` / ``review.calcbook`` 用条目制：``params`` 为已解析取值，
    ``unknown`` 列低置信度/未解析槽位（宁缺勿错：进"待人工确认"不硬判）。

纪律
1. **数值只认已核对来源**：阈值条目 ``status`` 必须是「已核对」，否则
   ``ContractError``（退出码 3）；不把未核对数值渲染成合格。
2. **待人工确认不冒充结论**：分级参数缺失/条文未核对 → 记录 ``ok`` +
   ``evidence.status="pending"``，message 写明缺什么；**不猜值**。
3. **无依据不入账**：每条记录都经 ``basis.ref(code, clause)`` 取条款；
   条款库缺条 → ``ClauseMissing``（退出码 3），不自己造条号。
"""

from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from speccalc.core.data import load
from speccalc.core.ledger import OK, REJECTED, CalculationRecord, ContractError
from speccalc.core.registry import Pack, register

SLUG = "formwork-scaffold"
VERSION = "0.1.0"
DATA = load("formwork-scaffold.json")

CLAUSES: Dict[str, dict] = DATA["clauses"]
MODULES: Dict[str, dict] = DATA["modules"]
CONSTANTS: Dict[str, float] = DATA["constants"]
EPS = float(CONSTANTS["eps"])

MODE_CALC = "calc"
MODE_GRADE = "grade"
MODE_REVIEW = "review"
MODES = (MODE_CALC, MODE_GRADE, MODE_REVIEW)

LEVELS = ("none", "weida", "chaoguimo")


# ---------------------------------------------------------------------------
# 规则包（阈值 + 查表 + 核查规则），可整体替换以便测试"未核对硬拦截"
# ---------------------------------------------------------------------------
class Rules(object):
    """器官的规则包视图：所有数值取用都经过 ``threshold()`` 的已核对校验。"""

    def __init__(self, data: Mapping):
        self.data = data
        self.clauses = data["clauses"]
        self.tables = data["tables"]
        self.constants = data["constants"]
        self.grading = data["grading"]
        self.checks = data["checks"]
        self.consistency = data["consistency"]
        self.thresholds = dict(data["thresholds"])

    def threshold(self, threshold_id: str) -> Mapping:
        entry = self.thresholds.get(threshold_id)
        if entry is None:
            raise ContractError("规则包缺阈值条目：%s" % threshold_id)
        if entry.get("status") != "已核对":
            raise ContractError(
                "阈值 %s status=%s，不得进入计算路径"
                % (threshold_id, entry.get("status")))
        return entry

    def threshold_value(self, threshold_id: str) -> float:
        value = self.threshold(threshold_id)["value"]
        if isinstance(value, dict):
            raise ContractError("阈值 %s 是分支/结构值，须按键取用" % threshold_id)
        return float(value)

    def clause(self, key: str) -> Mapping:
        entry = self.clauses.get(key)
        if entry is None:
            raise ContractError("规则包缺条款键：%s" % key)
        return entry

    def ref(self, basis, key: str):
        entry = self.clause(key)
        return basis.ref(entry["code"], entry["clause"])


PACK = Rules(DATA)


# ---------------------------------------------------------------------------
# 通用校验
# ---------------------------------------------------------------------------
def _require(mapping: Mapping, key: str, where: str):
    if not isinstance(mapping, Mapping):
        raise ValueError("%s 必须是对象" % where)
    if key not in mapping or mapping[key] is None:
        raise ValueError("%s 缺少必填字段：%s" % (where, key))
    return mapping[key]


def _text(value, where: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError("%s 不能为空" % where)
    return str(value)


def _number(value, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("%s 必须是数值：%r" % (where, value))
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("%s 必须是有限数值：%r" % (where, value))
    return value


def _positive(value, where: str) -> float:
    number = _number(value, where)
    if number <= 0:
        raise ValueError("%s 必须为正：%r" % (where, number))
    return number


def _non_negative(value, where: str) -> float:
    number = _number(value, where)
    if number < 0:
        raise ValueError("%s 不得为负：%r" % (where, number))
    return number


def _enum(value, where: str, allowed: Sequence[str]) -> str:
    if value not in allowed:
        raise ValueError("%s 须为 %s 之一，得到 %r" % (where, list(allowed), value))
    return value


def _fmt(value: float) -> str:
    return ("%.4f" % float(value)).rstrip("0").rstrip(".")


def _round(value: float) -> float:
    return round(float(value), 6)


# ---------------------------------------------------------------------------
# 查表（表A.0.6 / 表A.0.1 / 表5.2.8 / 表A.0.5）
# ---------------------------------------------------------------------------
def _phi_table(tables: Mapping) -> Dict[int, float]:
    out = {}
    for row, values in tables["phi"]["rows"].items():
        base = int(row)
        for offset, value in enumerate(values):
            out[base + offset] = float(value)
    return out


def phi_of(tables: Mapping, lam: float) -> float:
    """λ → φ：λ=ceil 向上取整查离散档（禁插值）；λ>250 用 7320/λ²。"""
    if not lam > 0:
        raise ValueError("长细比 λ 必须为正数，得到 %r" % (lam,))
    if lam <= float(tables["phi"]["max_lambda"]):
        key = int(math.ceil(lam))
        return _phi_table(tables)[key]
    return float(tables["phi"]["over_250_numerator"]) / (lam * lam)


def _interp_1d(xs: Sequence[float], ys: Sequence[float], x: float) -> float:
    if x < xs[0] - EPS or x > xs[-1] + EPS:
        raise ValueError("值 %r 超出查表域 [%s, %s]" % (x, xs[0], xs[-1]))
    for index in range(len(xs) - 1):
        x0, x1 = xs[index], xs[index + 1]
        if x0 - EPS <= x <= x1 + EPS:
            if x1 == x0:
                return ys[index]
            ratio = (x - x0) / (x1 - x0)
            return ys[index] + ratio * (ys[index + 1] - ys[index])
    return ys[-1]


def gk_of(tables: Mapping, h: float, la: float, rows: str = "double") -> float:
    """表A.0.1：立杆每米结构自重 gk（域内按表注线性插入）。"""
    table = tables["gk"]
    if rows not in ("single", "double"):
        raise ValueError("脚手架排数须为 single/double，得到 %r" % (rows,))
    if not (h > 0 and la > 0):
        raise ValueError("步距/纵距必须为正数，得到 h=%r la=%r" % (h, la))
    h_rows = [float(x) for x in table["h_rows"]]
    la_cols = [float(x) for x in table["la_cols"]]
    if h < h_rows[0] - EPS or h > h_rows[-1] + EPS:
        raise ValueError("步距 %r 超出表A.0.1 域 [%s, %s]" % (h, h_rows[0], h_rows[-1]))
    if la < la_cols[0] - EPS or la > la_cols[-1] + EPS:
        raise ValueError("纵距 %r 超出表A.0.1 域 [%s, %s]" % (la, la_cols[0], la_cols[-1]))
    matrix = table[rows]
    column_values = []
    for la_key in la_cols:
        ys = [float(matrix[str(hh)][str(la_key)]) for hh in h_rows]
        column_values.append(_interp_1d(h_rows, ys, h))
    return _interp_1d(la_cols, column_values, la)


def mu_of(tables: Mapping, rows: str, wall_tie: str, lb: float) -> float:
    """表5.2.8：立杆计算长度系数 μ（离散档精确匹配，无插值注）。"""
    table = tables["mu"]
    if rows not in table:
        raise ValueError("脚手架排数须为 single/double，得到 %r" % (rows,))
    if wall_tie not in ("two_step_three_span", "three_step_three_span"):
        raise ValueError("连墙件布置非法：%r" % (wall_tie,))
    if rows == "single":
        if lb > 1.50 + EPS:
            raise ValueError("单排架立杆横距 ≤1.50m（表5.2.8），得到 %r" % (lb,))
        return float(table["single"]["1.5"][wall_tie])
    for key, entry in table["double"].items():
        if abs(lb - float(key)) < EPS:
            return float(entry[wall_tie])
    raise ValueError(
        "双排架立杆横距 %r 不在表5.2.8 离散档 %s 内（无插值注，须取表档值）"
        % (lb, sorted(float(k) for k in table["double"])))


def wind_phi_a05(tables: Mapping, h: float, la: float) -> float:
    """表A.0.5：敞开式脚手架挡风系数 φ（步距×纵距精确匹配）。"""
    table = tables["wind_phi_a05"]
    h_rows = [float(x) for x in table["h_rows"]]
    la_cols = [float(x) for x in table["la_cols"]]
    for index, h_key in enumerate(h_rows):
        if abs(h - h_key) < EPS:
            for column, la_key in enumerate(la_cols):
                if abs(la - la_key) < EPS:
                    return float(table["matrix"][index][column])
            raise ValueError("纵距 %r 不在表A.0.5 列档内" % (la,))
    raise ValueError("步距 %r 不在表A.0.5 行档内" % (h,))


# ---------------------------------------------------------------------------
# 参数卡校验（与旧仓 CardError 同口径：非法即拒收 → 退出码 2）
# ---------------------------------------------------------------------------
WALL_TIES = ("two_step_three_span", "three_step_three_span")
PIPE_SPECS = ("48.3x3.6",)
SCAFFOLD_STATES = ("enclosed_net", "semi_enclosed", "open")


def _loads(card: Mapping) -> Mapping:
    loads = _require(card, "loads", "荷载参数")
    if not isinstance(loads, Mapping):
        raise ValueError("loads 须为对象，得到 %r" % (loads,))
    return loads


def _board_layers(loads: Mapping) -> int:
    layers = loads.get("board_layers", 0)
    if isinstance(layers, bool) or not isinstance(layers, int) or layers < 0:
        raise ValueError("loads.board_layers 须为非负整数，得到 %r" % (layers,))
    return layers


def _common_scaffold(card: Mapping, require_cross: bool = True) -> dict:
    out = {
        "category": _enum(card.get("category"), "category",
                          ("coupler_steel_pipe_scaffold",)),
        "rows": _enum(card.get("rows"), "rows（单排 single/双排 double）",
                      ("single", "double")),
        "step_m": _positive(_require(card, "step_m", "几何参数"), "step_m"),
        "long_spacing_m": _positive(
            _require(card, "long_spacing_m", "几何参数"), "long_spacing_m"),
        "pipe_spec": _enum(card.get("pipe_spec", "48.3x3.6"),
                           "pipe_spec（暂只支持 48.3x3.6）", PIPE_SPECS),
    }
    if require_cross:
        out["cross_spacing_m"] = _positive(
            _require(card, "cross_spacing_m", "几何参数"), "cross_spacing_m")
    return out


def _wind_not_combined(card: Mapping, module_id: str) -> str:
    wind = card.get("wind", "不组合")
    if wind != "不组合":
        raise ValueError("%s 参数卡 wind 须为 \"不组合\"，组合风请用对应模块（得到 %r）"
                         % (module_id, wind))
    return wind


def _wind_dict(card: Mapping) -> dict:
    wind = _require(card, "wind", "组合风工况")
    if not isinstance(wind, Mapping):
        raise ValueError("组合风工况下 wind 须为对象（w0/mu_z/...），得到 %r" % (wind,))
    out = {}
    if wind.get("wk_kN_per_m2") is not None:
        out["wk_kN_per_m2"] = _positive(wind["wk_kN_per_m2"], "wind.wk_kN_per_m2")
        return out
    out["w0_kN_per_m2"] = _positive(
        _require(wind, "w0_kN_per_m2", "风荷载"), "wind.w0_kN_per_m2")
    out["mu_z"] = _positive(_require(wind, "mu_z", "风荷载"), "wind.mu_z")
    state = wind.get("scaffold_state", "enclosed_net")
    out["scaffold_state"] = _enum(state, "wind.scaffold_state", SCAFFOLD_STATES)
    out["back_wall"] = wind.get("back_wall")
    if wind.get("shape_mu_s") is not None:
        out["shape_mu_s"] = _positive(wind["shape_mu_s"], "wind.shape_mu_s")
    elif wind.get("shape_phi") is not None:
        out["shape_phi"] = _positive(wind["shape_phi"], "wind.shape_phi")
    if "shape_mu_s" not in out and "shape_phi" not in out and state != "open":
        raise ValueError("wind.shape_phi 缺失：enclosed_net/semi_enclosed 须显式给出挡风系数")
    return out


def _validate_m1(card: Mapping) -> dict:
    out = _common_scaffold(card)
    _wind_not_combined(card, "M-1")
    out["build_height_m"] = _positive(
        _require(card, "build_height_m", "M-1 需搭设高度"), "build_height_m")
    out["wall_tie"] = _enum(_require(card, "wall_tie", "M-1 需连墙件布置"),
                            "wall_tie", WALL_TIES)
    loads = _loads(card)
    out["loads"] = {
        "gk_struct_kN_per_m": (
            _positive(loads["gk_struct_kN_per_m"], "loads.gk_struct_kN_per_m")
            if loads.get("gk_struct_kN_per_m") is not None else None),
        "board_kN_per_m2": _non_negative(loads.get("board_kN_per_m2", 0.0),
                                         "loads.board_kN_per_m2"),
        "board_layers": _board_layers(loads),
        "rail_kN_per_m": _non_negative(loads.get("rail_kN_per_m", 0.0),
                                       "loads.rail_kN_per_m"),
        "safety_net_kN_per_m2": _non_negative(loads.get("safety_net_kN_per_m2", 0.0),
                                              "loads.safety_net_kN_per_m2"),
        "live_kN_per_m2": _positive(_require(loads, "live_kN_per_m2", "M-1 荷载"),
                                    "loads.live_kN_per_m2"),
    }
    return out


def _validate_m2(card: Mapping) -> dict:
    out = _common_scaffold(card)
    out["wind"] = _wind_dict(card)
    out["build_height_m"] = _positive(
        _require(card, "build_height_m", "M-2 需搭设高度"), "build_height_m")
    out["wall_tie"] = _enum(_require(card, "wall_tie", "M-2 需连墙件布置"),
                            "wall_tie", WALL_TIES)
    loads = _loads(card)
    out["loads"] = {
        "gk_struct_kN_per_m": (
            _positive(loads["gk_struct_kN_per_m"], "loads.gk_struct_kN_per_m")
            if loads.get("gk_struct_kN_per_m") is not None else None),
        "board_kN_per_m2": _non_negative(loads.get("board_kN_per_m2", 0.0),
                                         "loads.board_kN_per_m2"),
        "board_layers": _board_layers(loads),
        "rail_kN_per_m": _non_negative(loads.get("rail_kN_per_m", 0.0),
                                       "loads.rail_kN_per_m"),
        "safety_net_kN_per_m2": _non_negative(loads.get("safety_net_kN_per_m2", 0.0),
                                              "loads.safety_net_kN_per_m2"),
        "live_kN_per_m2": _positive(_require(loads, "live_kN_per_m2", "M-2 荷载"),
                                    "loads.live_kN_per_m2"),
    }
    return out


def _validate_m3(card: Mapping) -> dict:
    out = _common_scaffold(card)
    out["member"] = _enum(_require(card, "member", "M-3 需杆件类型"),
                          "member（cross=横向水平杆/long=纵向水平杆）",
                          ("cross", "long"))
    _wind_not_combined(card, "M-3")
    loads = _loads(card)
    out["loads"] = {
        "board_kN_per_m2": _non_negative(loads.get("board_kN_per_m2", 0.0),
                                         "loads.board_kN_per_m2"),
        "live_kN_per_m2": _positive(_require(loads, "live_kN_per_m2", "M-3 荷载"),
                                    "loads.live_kN_per_m2"),
    }
    return out


def _validate_m4(card: Mapping) -> dict:
    out = _common_scaffold(card, require_cross=False)
    out["wall_tie"] = _enum(_require(card, "wall_tie", "M-4 需连墙件布置"),
                            "wall_tie", WALL_TIES)
    out["tie_type"] = _enum(card.get("tie_type", "steel_pipe_coupler"),
                            "tie_type（暂只支持钢管扣件）", ("steel_pipe_coupler",))
    out["tie_length_m"] = _positive(
        _require(card, "tie_length_m", "M-4 需连墙杆长度"), "tie_length_m")
    if card.get("build_height_m") is not None:
        out["build_height_m"] = _positive(card["build_height_m"], "build_height_m")
    wind = _require(card, "wind", "M-4 风荷载")
    if not isinstance(wind, Mapping):
        raise ValueError("M-4 wind 须为对象（wk 或 w0/mu_z/...），得到 %r" % (wind,))
    out["wind"] = _wind_dict(card)
    return out


def _foundation(card: Mapping) -> dict:
    foundation = _require(card, "foundation", "地基参数")
    if not isinstance(foundation, Mapping):
        raise ValueError("foundation 须为对象，得到 %r" % (foundation,))
    pad = _require(foundation, "pad_m", "foundation 垫板/垫木尺寸")
    if (not isinstance(pad, (list, tuple)) or len(pad) != 2
            or any(isinstance(x, bool) or not isinstance(x, (int, float)) or x <= 0
                   for x in pad)):
        raise ValueError("foundation.pad_m 须为 [长m, 宽m] 两个正数，得到 %r" % (pad,))
    out = dict(foundation)
    out["pad_m"] = [float(pad[0]), float(pad[1])]
    if foundation.get("nk_kN") is not None:
        out["nk_kN"] = _positive(foundation["nk_kN"], "foundation.nk_kN")
    if foundation.get("n_design_kN") is not None:
        out["n_design_kN"] = _positive(foundation["n_design_kN"],
                                       "foundation.n_design_kN")
    return out


def _validate_m5(card: Mapping) -> dict:
    if card.get("category") != "coupler_steel_pipe_scaffold":
        raise ValueError("M-5 参数卡 category 须为 coupler_steel_pipe_scaffold，得到 %r"
                         % (card.get("category"),))
    foundation = _foundation(card)
    fgk = _require(foundation, "fgk_kPa", "M-5 地基承载力特征值")
    reduction = foundation.get("reduction")
    if reduction is None:
        raise ValueError("M-5 缺 foundation.reduction（回填土 0.4 / 天然地基 1.0）")
    foundation["fgk_kPa"] = _positive(fgk, "foundation.fgk_kPa")
    foundation["reduction"] = _positive(reduction, "foundation.reduction")
    foundation["soil_type"] = foundation.get("type", "天然地基")
    out = {
        "category": "coupler_steel_pipe_scaffold",
        "foundation": foundation,
        "pipe_spec": _enum(card.get("pipe_spec", "48.3x3.6"),
                           "pipe_spec（暂只支持 48.3x3.6）", PIPE_SPECS),
    }
    if "nk_kN" in foundation or "n_design_kN" in foundation:
        return out
    for key in ("build_height_m", "step_m", "long_spacing_m", "cross_spacing_m", "rows"):
        if card.get(key) is None:
            raise ValueError("M-5 缺 foundation.nk_kN，须提供完整架体参数（%s 等）现算"
                             % key)
    out["build_height_m"] = _positive(card["build_height_m"], "build_height_m")
    out["step_m"] = _positive(card["step_m"], "step_m")
    out["long_spacing_m"] = _positive(card["long_spacing_m"], "long_spacing_m")
    out["cross_spacing_m"] = _positive(card["cross_spacing_m"], "cross_spacing_m")
    out["rows"] = _enum(card["rows"], "rows（单排 single/双排 double）",
                        ("single", "double"))
    out["wall_tie"] = _enum(card.get("wall_tie", "two_step_three_span"),
                            "wall_tie", WALL_TIES)
    loads = _loads(card)
    out["loads"] = {
        "gk_struct_kN_per_m": (
            _positive(loads["gk_struct_kN_per_m"], "loads.gk_struct_kN_per_m")
            if loads.get("gk_struct_kN_per_m") is not None else None),
        "board_kN_per_m2": _non_negative(loads.get("board_kN_per_m2", 0.0),
                                         "loads.board_kN_per_m2"),
        "board_layers": _board_layers(loads),
        "rail_kN_per_m": _non_negative(loads.get("rail_kN_per_m", 0.0),
                                       "loads.rail_kN_per_m"),
        "safety_net_kN_per_m2": _non_negative(loads.get("safety_net_kN_per_m2", 0.0),
                                              "loads.safety_net_kN_per_m2"),
        "live_kN_per_m2": _non_negative(loads.get("live_kN_per_m2", 0.0),
                                        "loads.live_kN_per_m2"),
    }
    if out["loads"]["live_kN_per_m2"] <= 0 and out["loads"]["board_kN_per_m2"] <= 0:
        raise ValueError("M-5 现算路径下 live_kN_per_m2 与 board_kN_per_m2 不能同时为 0")
    return out


def _validate_m6(card: Mapping) -> dict:
    if card.get("category") != "formwork_support":
        raise ValueError("M-6 参数卡 category 须为 formwork_support，得到 %r"
                         % (card.get("category"),))
    if card.get("foundation") is not None:
        foundation = _foundation(card)
        if "n_design_kN" not in foundation and "nk_kN" not in foundation:
            raise ValueError("M-6 地基验算缺 foundation.n_design_kN（立柱传至垫木顶面设计值）")
        mf = foundation.get("mf")
        if mf is None:
            raise ValueError("M-6 地基验算缺 foundation.mf（表5.2.6 折减系数）")
        foundation["mf"] = _positive(mf, "foundation.mf")
        foundation["fak_kPa"] = _positive(
            _require(foundation, "fak_kPa", "M-6 地基土承载力"), "foundation.fak_kPa")
        return {"category": "formwork_support", "foundation": foundation}

    wind = card.get("wind", "不组合")
    if wind != "不组合" and not isinstance(wind, Mapping):
        raise ValueError("M-6 wind 须为 \"不组合\" 或风荷载对象，得到 %r" % (wind,))
    spacing = _require(card, "pole_spacing_m", "M-6 立杆间距")
    if (not isinstance(spacing, (list, tuple)) or len(spacing) != 2
            or any(isinstance(x, bool) or not isinstance(x, (int, float)) or x <= 0
                   for x in spacing)):
        raise ValueError("pole_spacing_m 须为 [la, lb] 两个正数，得到 %r" % (spacing,))
    loads = _loads(card)
    return {
        "category": "formwork_support",
        "step_m": _positive(_require(card, "step_m", "M-6 步距"), "step_m"),
        "pole_spacing_m": [float(spacing[0]), float(spacing[1])],
        "pipe_spec": _enum(card.get("pipe_spec", "48.3x3.6"),
                           "pipe_spec（暂只支持 48.3x3.6）", PIPE_SPECS),
        "slab_thickness_m": _positive(
            _require(card, "slab_thickness_m", "M-6 板厚"), "slab_thickness_m"),
        "story_height_m": _positive(card.get("story_height_m", 4.0), "story_height_m"),
        "wind": _wind_dict(card) if isinstance(wind, Mapping) else "不组合",
        "loads": {
            "g1k_kN_per_m2": _non_negative(
                _require(loads, "g1k_kN_per_m2", "M-6 荷载"), "loads.g1k_kN_per_m2"),
            "concrete_kN_per_m3": _positive(
                _require(loads, "concrete_kN_per_m3", "M-6 荷载"),
                "loads.concrete_kN_per_m3"),
            "rebar_kN_per_m3_slab": _non_negative(
                loads.get("rebar_kN_per_m3_slab", 0.0), "loads.rebar_kN_per_m3_slab"),
            "q1k_kN_per_m2": _non_negative(
                _require(loads, "q1k_kN_per_m2", "M-6 荷载"), "loads.q1k_kN_per_m2"),
        },
    }


_VALIDATORS = {
    "M-1": _validate_m1,
    "M-2": _validate_m2,
    "M-3": _validate_m3,
    "M-4": _validate_m4,
    "M-5": _validate_m5,
    "M-6": _validate_m6,
}


def detect_module(card: Mapping) -> str:
    """按参数卡内容自动识别验算模块（显式 module 优先于本函数）。"""
    if not isinstance(card, Mapping):
        raise ValueError("参数卡须为 JSON 对象，得到 %s" % type(card).__name__)
    category = card.get("category")
    if category == "formwork_support":
        return "M-6"
    if category != "coupler_steel_pipe_scaffold":
        raise ValueError("无法识别 category=%r（须为 coupler_steel_pipe_scaffold / "
                         "formwork_support）" % (category,))
    if card.get("foundation") is not None:
        return "M-5"
    if card.get("member") in ("cross", "long"):
        return "M-3"
    if card.get("tie_length_m") is not None or card.get("tie_type") is not None:
        return "M-4"
    if card.get("wind", "不组合") == "不组合":
        return "M-1"
    return "M-2"


# ---------------------------------------------------------------------------
# 验算：M-1 ~ M-6
# ---------------------------------------------------------------------------
def _section_props(rules: Rules) -> Tuple[float, float, float, float]:
    value = rules.threshold("T-JGJ130-section-props")["value"]
    return (float(value["A_mm2"]), float(value["I_mm4"]),
            float(value["W_mm3"]), float(value["i_mm"]))


def _steel_f130(rules: Rules) -> float:
    return rules.threshold_value("T-JGJ130-steel-design")


def _steel_f162(rules: Rules) -> float:
    return rules.threshold_value("T-JGJ162-steel-design")


def _coupler_rc(rules: Rules) -> float:
    return float(rules.threshold("T-JGJ130-coupler-capacity")["value"]["直角扣件抗滑"])


def _tie_n0(rules: Rules, rows: str) -> float:
    value = rules.threshold("T-JGJ130-tie-N0")["value"]
    return float(value["单排架" if rows == "single" else "双排架"])


def _partial_factors_130(rules: Rules) -> Tuple[float, float, float]:
    value = rules.threshold("T-JGJ130-partial-factors")["value"]
    return (float(value["永久荷载"]), float(value["可变荷载"]),
            float(value["挠度标准组合"]))


def _gamma0_162(rules: Rules) -> float:
    return float(rules.threshold("T-JGJ162-partial-factors")
                 ["value"]["结构重要性系数γ0"])


def _mu_s(wind: Mapping, h: float, la: float, rules: Rules,
          warnings: List[str]) -> float:
    """风荷载体型系数 μs（表4.2.6 / 4.2.7 / 表A.0.5）。"""
    if "shape_mu_s" in wind:
        return float(wind["shape_mu_s"])
    state = wind.get("scaffold_state", "enclosed_net")
    back_wall = wind.get("back_wall") or "全封闭墙"
    if "shape_phi" in wind:
        shape_phi = float(wind["shape_phi"])
    elif state == "open":
        shape_phi = wind_phi_a05(rules.tables, h, la)
    else:
        raise ValueError("wind.shape_phi 缺失且无法由表A.0.5 查取（state=%s）" % state)
    if state == "open":
        return 1.3 * shape_phi
    if state in ("enclosed_net", "semi_enclosed") and back_wall == "全封闭墙":
        if state == "enclosed_net" and shape_phi < 0.8:
            warnings.append("密目式安全立网全封闭脚手架挡风系数 φ 不宜小于 0.8"
                            "（JGJ130-4.2.7）")
        return 1.0 * shape_phi
    if back_wall in ("敞开框架开洞墙", "敞开框架、开洞墙"):
        return 1.3 * shape_phi
    raise ValueError("未支持的背靠墙面情形 %r（暂支持 全封闭墙/敞开框架开洞墙）"
                     % (back_wall,))


def _wk(card: Mapping, rules: Rules, warnings: List[str],
        h: float, la: float) -> Tuple[float, str]:
    wind = card["wind"]
    if "wk_kN_per_m2" in wind:
        return float(wind["wk_kN_per_m2"]), "输入值"
    mu_s = _mu_s(wind, h, la, rules, warnings)
    wk = float(wind["mu_z"]) * mu_s * float(wind["w0_kN_per_m2"])
    return wk, "μz·μs·w0（μs=%s）" % _fmt(mu_s)


def _axial_forces(card: Mapping, rules: Rules,
                  warnings: List[str]) -> Tuple[float, float, float, float]:
    """NG1k / NG2k / NQk 标准值（负担模型与旧仓算例真值库一致）。"""
    loads = card["loads"]
    h = card["step_m"]
    la = card["long_spacing_m"]
    lb = card["cross_spacing_m"]
    build_h = card["build_height_m"]
    gk = loads["gk_struct_kN_per_m"]
    if gk is None:
        gk = gk_of(rules.tables, h, la, card["rows"])
        warnings.append("未提供 loads.gk_struct_kN_per_m，已按表A.0.1 查取"
                        "（h=%s, la=%s, %s 排）" % (_fmt(h), _fmt(la), card["rows"]))
    ng1k = gk * build_h
    area = la * lb / 2.0
    ng2k = (loads["board_kN_per_m2"] * loads["board_layers"] * area
            + loads["rail_kN_per_m"] * loads["board_layers"] * la
            + loads["safety_net_kN_per_m2"] * la * build_h)
    nqk = loads["live_kN_per_m2"] * area
    return gk, ng1k, ng2k, nqk


def _slenderness(card: Mapping, rules: Rules) -> Tuple[float, float, float]:
    mu = mu_of(rules.tables, card["rows"], card["wall_tie"], card["cross_spacing_m"])
    l0_mm = float(rules.constants["k_length_add"]) * mu * card["step_m"] * 1000.0
    i_mm = _section_props(rules)[3]
    return mu, l0_mm, l0_mm / i_mm


def _check(item: str, expr: str, substituted: str, ratio: float, limit: float,
           clause_refs: Sequence[str]) -> dict:
    return {"item": item, "expr": expr, "substituted": substituted,
            "ratio": float(ratio), "limit": float(limit),
            "verdict": "pass" if ratio <= 1.0 else "fail",
            "clause_refs": list(clause_refs)}


def _result(module_id: str, checks: List[dict], detail: Mapping,
            warnings: Sequence[str]) -> dict:
    return {"module_id": module_id, "status": "ok", "checks": checks,
            "warnings": list(warnings), "detail": dict(detail)}


def calc_m1(card: Mapping, rules: Rules) -> dict:
    warnings: List[str] = []
    gk, ng1k, ng2k, nqk = _axial_forces(card, rules, warnings)
    gamma_g, gamma_q, _ = _partial_factors_130(rules)
    n_design = gamma_g * (ng1k + ng2k) + gamma_q * nqk
    mu, l0_mm, lam = _slenderness(card, rules)
    phi = phi_of(rules.tables, lam)
    a_mm2, _, _, _ = _section_props(rules)
    f = _steel_f130(rules)
    sigma = n_design * 1000.0 / (phi * a_mm2)
    ratio = sigma / f
    check = _check(
        "lizhigan_stability", "N/(φA) ≤ f",
        "N=%s kN, φ=%s, A=%s mm² → σ=%s N/mm² ≤ f=%s N/mm²"
        % (_fmt(n_design), _fmt(phi), _fmt(a_mm2), _fmt(sigma), _fmt(f)),
        ratio, f, ("JGJ130-5.2.6", "JGJ130-5.2.7", "JGJ130-5.2.8",
                   "JGJ130-A.0.6", "JGJ130-5.1.6", "JGJ130-B.0.1"))
    return _result("M-1", [check], {
        "gk_kN_per_m": gk, "NG1k_kN": ng1k, "NG2k_kN": ng2k, "NQk_kN": nqk,
        "N_design_kN": n_design, "mu": mu, "l0_mm": l0_mm, "lambda": lam,
        "phi": phi, "sigma_N_per_mm2": sigma, "f": f}, warnings)


def calc_m2(card: Mapping, rules: Rules) -> dict:
    warnings: List[str] = []
    gk, ng1k, ng2k, nqk = _axial_forces(card, rules, warnings)
    gamma_g, gamma_q, _ = _partial_factors_130(rules)
    wk, _note = _wk(card, rules, warnings, card["step_m"], card["long_spacing_m"])
    n_design = gamma_g * (ng1k + ng2k) + 0.9 * gamma_q * nqk
    h, la = card["step_m"], card["long_spacing_m"]
    mwk = wk * la * (h ** 2) / 10.0
    mw = 0.9 * 1.4 * mwk
    mu, l0_mm, lam = _slenderness(card, rules)
    phi = phi_of(rules.tables, lam)
    a_mm2, _, w_mm3, _ = _section_props(rules)
    f = _steel_f130(rules)
    sigma_axial = n_design * 1000.0 / (phi * a_mm2)
    sigma_bend = mw * 1e6 / w_mm3
    sigma = sigma_axial + sigma_bend
    ratio = sigma / f
    check = _check(
        "lizhigan_stability", "N/(φA) + Mw/W ≤ f",
        "N=%s kN, φ=%s, A=%s mm², Mw=%s kN·m, W=%s mm³ → σ=%s N/mm² ≤ f=%s N/mm²"
        % (_fmt(n_design), _fmt(phi), _fmt(a_mm2), _fmt(mw), _fmt(w_mm3),
           _fmt(sigma), _fmt(f)),
        ratio, f, ("JGJ130-5.2.6", "JGJ130-5.2.7", "JGJ130-5.2.8",
                   "JGJ130-A.0.6", "JGJ130-5.1.6", "JGJ130-B.0.1",
                   "JGJ130-4.2.5", "JGJ130-4.2.6"))
    return _result("M-2", [check], {
        "gk_kN_per_m": gk, "NG1k_kN": ng1k, "NG2k_kN": ng2k, "NQk_kN": nqk,
        "wk_kN_per_m2": wk, "N_design_kN": n_design, "Mwk_kNm": mwk, "Mw_kNm": mw,
        "mu": mu, "l0_mm": l0_mm, "lambda": lam, "phi": phi,
        "sigma_bend_N_per_mm2": sigma_bend, "sigma_N_per_mm2": sigma, "f": f},
        warnings)


def _line_loads(card: Mapping, rules: Rules) -> Tuple[float, float]:
    loads = card["loads"]
    la = card["long_spacing_m"]
    board, live = loads["board_kN_per_m2"], loads["live_kN_per_m2"]
    gamma_g, gamma_q, _ = _partial_factors_130(rules)
    return (board + live) * la, gamma_g * board * la + gamma_q * live * la


def calc_m3(card: Mapping, rules: Rules) -> dict:
    la, lb = card["long_spacing_m"], card["cross_spacing_m"]
    _, i_mm4, w_mm3, _ = _section_props(rules)
    f = _steel_f130(rules)
    rc = _coupler_rc(rules)
    qk, qd = _line_loads(card, rules)
    checks: List[dict] = []
    detail = {"qk_kN_per_m": qk, "qd_kN_per_m": qd}
    if card["member"] == "cross":
        span_mm = lb * 1000.0
        m_design = qd * (lb ** 2) / 8.0
        sigma = m_design * 1e6 / w_mm3
        checks.append(_check(
            "bending_strength", "M/W ≤ f",
            "M=q·l²/8=%s kN·m, W=%s mm³ → σ=%s N/mm² ≤ f=%s N/mm²"
            % (_fmt(m_design), _fmt(w_mm3), _fmt(sigma), _fmt(f)),
            sigma / f, f, ("JGJ130-5.2.1", "JGJ130-5.2.2",
                           "JGJ130-5.1.6", "JGJ130-B.0.1")))
        v = 5.0 * qk * (span_mm ** 4) / (384.0 * float(rules.constants["steel_e"])
                                         * i_mm4)
        v_allow = min(span_mm / 150.0, 10.0)
        checks.append(_check(
            "deflection", "v ≤ [v]",
            "v=5qk·l⁴/(384EI)=%s mm ≤ [v]=min(l/150,10mm)=%s mm"
            % (_fmt(v), _fmt(v_allow)),
            v / v_allow, v_allow,
            ("JGJ130-5.2.3", "JGJ130-5.1.8", "JGJ130-5.1.3")))
        detail.update({"M_design_kNm": m_design, "sigma_N_per_mm2": sigma,
                       "v_mm": v, "v_allow_mm": v_allow})
        r_force = qd * lb / 2.0
    else:
        p_design = qd * lb / 2.0
        m_design = 0.175 * p_design * la
        sigma = m_design * 1e6 / w_mm3
        checks.append(_check(
            "bending_strength", "M/W ≤ f",
            "M=0.175·P·la=%s kN·m（P=%s kN）, W=%s mm³ → σ=%s N/mm² ≤ f=%s N/mm²"
            % (_fmt(m_design), _fmt(p_design), _fmt(w_mm3), _fmt(sigma), _fmt(f)),
            sigma / f, f, ("JGJ130-5.2.1", "JGJ130-5.2.2",
                           "JGJ130-5.1.6", "JGJ130-B.0.1")))
        detail.update({"P_design_kN": p_design, "M_design_kNm": m_design,
                       "sigma_N_per_mm2": sigma})
        r_force = 1.15 * p_design
    checks.append(_check(
        "antislip", "R ≤ Rc",
        "R=%s kN ≤ Rc=%s kN（直角扣件抗滑）" % (_fmt(r_force), _fmt(rc)),
        r_force / rc, rc, ("JGJ130-5.2.5", "JGJ130-5.1.7")))
    detail.update({"R_kN": r_force, "Rc_kN": rc})
    return _result("M-3", checks, detail, [])


def _coverage(card: Mapping, rules: Rules,
              warnings: List[str]) -> Tuple[float, str]:
    spec = rules.threshold("T-JGJ130-walltie-spacing")["value"]
    rows = card["rows"]
    build_h = card.get("build_height_m")
    h, la = card["step_m"], card["long_spacing_m"]
    if rows == "double" and build_h is not None and build_h > 50.0:
        key = "双排悬挑_H>50m"
    elif rows == "double":
        key = "双排落地_H≤50m"
    else:
        key = "单排_H≤24m"
        if build_h is not None and build_h > 24.0:
            warnings.append("单排架搭设高度不应超过 24m（JGJ130-6.1.2），"
                            "连墙件覆盖面积仍按表6.4.2 单排档计")
    entry = spec[key]
    cap = float(entry["每根覆盖面积_m2"])
    vertical = 3.0 if str(entry["竖向"]).strip().startswith("3") else 2.0
    horizontal = 3.0 if str(entry["水平"]).strip().startswith("3") else 2.0
    aw = vertical * h * horizontal * la
    if build_h is None:
        warnings.append("未提供 build_height_m，按 %s 档取 Aw=min(%s·h×%s·la, %s m²)"
                        % (key, _fmt(vertical), _fmt(horizontal), cap))
    return min(aw, cap), key


def calc_m4(card: Mapping, rules: Rules) -> dict:
    warnings: List[str] = []
    aw, aw_key = _coverage(card, rules, warnings)
    wk, _note = _wk(card, rules, warnings, card["step_m"], card["long_spacing_m"])
    n0 = _tie_n0(rules, card["rows"])
    nlw = 1.4 * wk * aw
    nl = nlw + n0
    _, _, _, i_mm = _section_props(rules)
    a_mm2 = _section_props(rules)[0]
    l0_mm = card["tie_length_m"] * 1000.0
    lam = float(math.ceil(l0_mm / i_mm))
    phi = phi_of(rules.tables, lam)
    f = _steel_f130(rules)
    f85 = 0.85 * f
    sigma_strength = nl * 1000.0 / a_mm2
    sigma_stab = nl * 1000.0 / (phi * a_mm2)
    rc = _coupler_rc(rules)
    checks = [
        _check("tie_strength", "Nl/Ac ≤ 0.85f",
               "Nl=%s kN, Ac=%s mm² → σ=%s N/mm² ≤ 0.85f=%s N/mm²"
               % (_fmt(nl), _fmt(a_mm2), _fmt(sigma_strength), _fmt(f85)),
               sigma_strength / f85, f85,
               ("JGJ130-5.2.12", "JGJ130-5.2.13", "JGJ130-A.0.6", "JGJ130-5.1.6")),
        _check("tie_stability", "Nl/(φA) ≤ 0.85f",
               "Nl=%s kN, φ=%s（λ=%d）, A=%s mm² → σ=%s N/mm² ≤ 0.85f=%s N/mm²"
               % (_fmt(nl), _fmt(phi), int(lam), _fmt(a_mm2),
                  _fmt(sigma_stab), _fmt(f85)),
               sigma_stab / f85, f85,
               ("JGJ130-5.2.12", "JGJ130-5.2.13", "JGJ130-A.0.6", "JGJ130-5.1.6")),
        _check("antislip", "Nl ≤ Rc",
               "Nl=%s kN ≤ Rc=%s kN（直角扣件抗滑，钢管扣件连墙件）"
               % (_fmt(nl), _fmt(rc)),
               nl / rc, rc, ("JGJ130-5.2.15", "JGJ130-5.1.7")),
    ]
    return _result("M-4", checks, {
        "Aw_m2": aw, "Aw_rule": aw_key, "wk_kN_per_m2": wk, "Nlw_kN": nlw,
        "N0_kN": n0, "Nl_kN": nl, "l0_mm": l0_mm, "lambda": lam, "phi": phi,
        "sigma_strength_N_per_mm2": sigma_strength,
        "sigma_stab_N_per_mm2": sigma_stab, "f85_N_per_mm2": f85, "Rc_kN": rc},
        warnings)


def calc_m5(card: Mapping, rules: Rules) -> dict:
    foundation = card["foundation"]
    warnings: List[str] = []
    if "nk_kN" in foundation:
        nk = foundation["nk_kN"]
    elif "n_design_kN" in foundation:
        raise ValueError("M-5 需要轴力标准值 foundation.nk_kN（5.5.1 用标准组合）；"
                         "如只有设计值请补标准值或提供架体参数现算")
    else:
        _, ng1k, ng2k, nqk = _axial_forces(card, rules, warnings)
        nk = ng1k + ng2k + nqk
    pad_l, pad_w = foundation["pad_m"]
    area = pad_l * pad_w
    fgk = foundation["fgk_kPa"]
    reduction = foundation["reduction"]
    fg = fgk * reduction
    pk = nk / area
    return _result("M-5", [_check(
        "foundation_bearing", "pk=Nk/A ≤ fg",
        "Nk=%s kN, A=%s×%s=%s m² → pk=%s kPa ≤ fg=%s×%s=%s kPa"
        % (_fmt(nk), _fmt(pad_l), _fmt(pad_w), _fmt(area), _fmt(pk),
           _fmt(fgk), _fmt(reduction), _fmt(fg)),
        pk / fg, fg, ("JGJ130-5.5.1", "JGJ130-5.5.2"))],
        {"Nk_kN": nk, "A_m2": area, "pk_kPa": pk, "fg_kPa": fg,
         "fgk_kPa": fgk, "reduction": reduction}, warnings)


def _wk_direct(card: Mapping, rules: Rules, warnings: List[str],
               la: float) -> float:
    wind = card["wind"]
    if "wk_kN_per_m2" in wind:
        return float(wind["wk_kN_per_m2"])
    mu_s = _mu_s(wind, card["step_m"], la, rules, warnings)
    return float(wind["mu_z"]) * mu_s * float(wind["w0_kN_per_m2"])


def calc_m6(card: Mapping, rules: Rules) -> dict:
    if "foundation" in card:
        foundation = card["foundation"]
        n = foundation.get("n_design_kN")
        if n is None:
            raise ValueError("M-6 立柱地基需要轴向力设计值 foundation.n_design_kN（5.2.6）")
        pad_l, pad_w = foundation["pad_m"]
        area = pad_l * pad_w
        mf, fak = foundation["mf"], foundation["fak_kPa"]
        p = n / area
        limit = mf * fak
        return _result("M-6", [_check(
            "foundation_bearing", "p=N/A ≤ mf·fak",
            "N=%s kN, A=%s×%s=%s m² → p=%s kPa ≤ mf·fak=%s×%s=%s kPa"
            % (_fmt(n), _fmt(pad_l), _fmt(pad_w), _fmt(area), _fmt(p),
               _fmt(mf), _fmt(fak), _fmt(limit)),
            p / limit, limit, ("JGJ162-5.2.6",))],
            {"N_kN": n, "A_m2": area, "p_kPa": p, "mf": mf, "fak_kPa": fak}, [])

    warnings: List[str] = []
    step = card["step_m"]
    if step > float(rules.constants["m6_step_max"]) + EPS:
        warnings.append("步距 %s m 超过 JGJ162-5.2.5 扣件钢管立柱最大步距 1.8m"
                        "（T-JGJ162-column-step），计算仍按输入步距进行，构造整改见核查模块"
                        % _fmt(step))
    la, lb = card["pole_spacing_m"]
    loads = card["loads"]
    slab = card["slab_thickness_m"]
    ng = ((loads["g1k_kN_per_m2"] + loads["concrete_kN_per_m3"] * slab
           + loads["rebar_kN_per_m3_slab"] * slab) * la * lb)
    q1k = loads["q1k_kN_per_m2"]
    gamma0 = _gamma0_162(rules)
    a_mm2, _, w_mm3, i_mm = _section_props(rules)
    f = _steel_f162(rules)
    l0_mm = step * 1000.0
    lam = float(math.ceil(l0_mm / i_mm))
    phi = phi_of(rules.tables, lam)
    if card["wind"] == "不组合":
        n = gamma0 * (1.2 * ng + 1.4 * q1k * la * lb)
        sigma = n * 1000.0 / (phi * a_mm2)
        expr = "N/(φA) ≤ f"
        substituted = ("N=%s kN（γ0=%s）, φ=%s（λ=%d）, A=%s mm² → σ=%s N/mm² ≤ f=%s N/mm²"
                       % (_fmt(n), _fmt(gamma0), _fmt(phi), int(lam), _fmt(a_mm2),
                          _fmt(sigma), _fmt(f)))
        detail = {"NG_kN": ng, "N_design_kN": n, "l0_mm": l0_mm, "lambda": lam,
                  "phi": phi, "sigma_N_per_mm2": sigma, "f": f}
    else:
        wk = _wk_direct(card, rules, warnings, la)
        mwk = wk * la * (step ** 2) / 10.0
        mw = 0.9 ** 2 * 1.4 * mwk
        nqik = q1k * la * lb + mw / lb
        nw = gamma0 * (1.2 * ng + 0.9 * 1.4 * nqik)
        sigma = nw * 1000.0 / (phi * a_mm2) + mw * 1e6 / w_mm3
        expr = "Nw/(φA) + Mw/W ≤ f"
        substituted = ("Nw=%s kN（γ0=%s）, φ=%s（λ=%d）, A=%s mm², Mw=%s kN·m, W=%s mm³"
                       " → σ=%s N/mm² ≤ f=%s N/mm²"
                       % (_fmt(nw), _fmt(gamma0), _fmt(phi), int(lam), _fmt(a_mm2),
                          _fmt(mw), _fmt(w_mm3), _fmt(sigma), _fmt(f)))
        detail = {"NG_kN": ng, "wk_kN_per_m2": wk, "Mwk_kNm": mwk, "Mw_kNm": mw,
                  "NQik_kN": nqik, "Nw_kN": nw, "l0_mm": l0_mm, "lambda": lam,
                  "phi": phi, "sigma_N_per_mm2": sigma, "f": f}
    return _result("M-6", [_check(
        "column_stability", expr, substituted, sigma / f, f,
        ("JGJ162-5.2.5", "JGJ162-4.3.1", "JGJ162-4.2.3",
         "JGJ130-A.0.6", "JGJ162-A.1.1-1"))], detail, warnings)


_CALCS = {"M-1": calc_m1, "M-2": calc_m2, "M-3": calc_m3,
          "M-4": calc_m4, "M-5": calc_m5, "M-6": calc_m6}


def run_calc(module_id: str, card_data: Mapping, rules: Rules) -> dict:
    if module_id not in _CALCS:
        raise ValueError("未知验算模块 %r（可选：%s）" % (module_id, ", ".join(_CALCS)))
    validator = _VALIDATORS[module_id]
    card = validator(card_data)
    return _CALCS[module_id](card, rules)


# ---------------------------------------------------------------------------
# 危大分级（三值逻辑，不猜值）
# ---------------------------------------------------------------------------
_CMP_CHAIN_RE = re.compile(
    r"^(-?\d+(?:\.\d+)?|[A-Za-z_]\w*)\s*"
    r"(<=|>=|<|>|==|!=)\s*"
    r"(-?\d+(?:\.\d+)?|[A-Za-z_]\w*)"
    r"(?:\s*(<=|>=|<|>|==|!=)\s*(-?\d+(?:\.\d+)?|[A-Za-z_]\w*))?$")
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _resolve_operand(token: str, params: Mapping):
    token = token.strip()
    if _NUM_RE.match(token):
        return float(token)
    if token not in params or params[token] is None:
        return None
    value = params[token]
    if isinstance(value, bool):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cmp(left: float, op: str, right: float) -> bool:
    if op == "<=":
        return left <= right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == ">":
        return left > right
    if op == "==":
        return left == right
    return left != right


def _eval_atom(atom: str, params: Mapping):
    text = atom.strip()
    if text.startswith("!"):
        inner = text[1:].strip()
        if inner.startswith("(") and inner.endswith(")"):
            inner = inner[1:-1].strip()
        value = _eval_atom(inner, params)
        return None if value is None else (not value)
    if text in ("true", "True"):
        return True
    if text in ("false", "False"):
        return False
    match = _CMP_CHAIN_RE.match(text)
    if match:
        operands = [match.group(1), match.group(3)]
        operators = [match.group(2)]
        if match.group(4):
            operands.append(match.group(5))
            operators.append(match.group(4))
        values = [_resolve_operand(token, params) for token in operands]
        if any(value is None for value in values):
            return None
        ok = True
        for index, op in enumerate(operators):
            left, right = values[index], values[index + 1]
            if isinstance(left, bool) or isinstance(right, bool):
                return None
            ok = ok and _cmp(left, op, right)
        return ok
    if _IDENT_RE.match(text):
        if text not in params or params[text] is None:
            return None
        return bool(params[text])
    raise ValueError("无法解析分级条件原子 %r" % (text,))


def _eval_and(part: str, params: Mapping):
    results = [_eval_atom(atom, params) for atom in part.split("&&")]
    if False in results:
        return False
    if all(result is True for result in results):
        return True
    return None


def eval_cond(cond: str, params: Mapping):
    """清单条件表达式求值：|| / && / ! / 比较链 / 布尔参数（三值逻辑）。"""
    text = cond.strip()
    if text.startswith("false"):
        return False
    if text.startswith("true"):
        return True
    results = [_eval_and(part, params) for part in text.split("||")]
    if True in results:
        return True
    if all(result is False for result in results):
        return False
    return None


def recognize_item(rules: Rules, project_type: Optional[str]) -> Optional[str]:
    text = project_type or ""
    for item_id, keywords in rules.grading["type_keywords"]:
        if any(keyword in text for keyword in keywords):
            return item_id
    return None


def _find_item(rules: Rules, item_id: str) -> Optional[dict]:
    for item in rules.grading["items"]:
        if item["item_id"] == item_id:
            return item
    return None


def _pending(item: Optional[dict], note: str, item_id: Optional[str] = None,
             unknown: Optional[Sequence[str]] = None,
             project_type: Optional[str] = None) -> dict:
    return {"status": "pending", "item_id": item_id,
            "project_type": project_type if project_type is not None else
            (item["project_type"] if item else None),
            "note": note, "unknown_params": list(unknown or []),
            "clause": (item["levels"]["weida"]["clause"]
                       if item is not None else "31-scope")}


def judge(rules: Rules, item_id: str, params: Mapping) -> dict:
    """对已识别条目逐级判定（none→weida→chaoguimo，首个 True 生效）。"""
    item = _find_item(rules, item_id)
    if item is None:
        return _pending(None, "清单条目不存在：%s" % item_id,
                        item_id=item_id)
    if item.get("status") != "已核对" or not all(
            basis.get("status") == "已核对" for basis in item["basis"]):
        return _pending(item, "分级依据待核对，暂不出确定结论", item_id=item_id,
                        project_type=item["project_type"])
    unknown = [name for name in item["judge_params"]
               if name not in params or params[name] is None]
    results = {}
    for level in LEVELS:
        results[level] = eval_cond(item["levels"][level]["cond"], params)
    for level in ("chaoguimo", "weida", "none"):
        if results[level] is True:
            definition = item["levels"][level]
            primary = item["judge_params"][0] if item["judge_params"] else None
            return {
                "status": "definite",
                "item_id": item["item_id"],
                "project_type": item["project_type"],
                "level": level,
                "label": definition["label"],
                "duty": definition.get("duty"),
                "cond": definition["cond"],
                "rule_id": definition["rule_id"],
                "verdict": "pass" if level == "none" else "triggered",
                "param": primary,
                "actual": params.get(primary) if primary else None,
                "basis": [{"doc": entry["doc"], "excerpt": entry["excerpt"]}
                          for entry in item["basis"]],
                "clause": definition["clause"],
                "note": item.get("note"),
            }
    if any(result is None for result in results.values()):
        return _pending(item, "分级参数缺失，待人工确认：%s"
                        % (", ".join(unknown) or "条件含未解析参数"),
                        item_id=item_id, unknown=unknown,
                        project_type=item["project_type"])
    return _pending(item, "清单条件未覆盖当前取值（条件全为假）", item_id=item_id,
                    project_type=item["project_type"])


# ---------------------------------------------------------------------------
# 核查：构造限值 / 一致性 / 分级联动
# ---------------------------------------------------------------------------
class _RuleSkip(Exception):
    def __init__(self, reason: str):
        super(_RuleSkip, self).__init__(reason)
        self.reason = reason


class Card(object):
    """方案卡 / 验算书取值卡（只承载已解析取值与未知槽位）。"""

    def __init__(self, card_type: str, project_type: str = "",
                 params: Optional[Mapping] = None,
                 unknown: Optional[Sequence[str]] = None,
                 category: Optional[str] = None):
        if card_type not in ("scheme", "calcbook"):
            raise ValueError("card_type 须为 scheme/calcbook，得到 %r" % (card_type,))
        self.card_type = card_type
        self.project_type = project_type or ""
        self.category = category
        self.params = dict(params or {})
        self.unknown = set(unknown or ())

    def is_known(self, name: str) -> bool:
        return (name in self.params and self.params[name] is not None
                and name not in self.unknown)

    def value(self, name: str, default=None):
        if not self.is_known(name):
            return default
        return self.params[name]

    def to_dict(self) -> dict:
        return {"card_type": self.card_type, "project_type": self.project_type,
                "category": self.category, "params": dict(self.params),
                "unknown_slots": sorted(self.unknown)}


def _gate_passes(rule: Mapping, project_type: str) -> bool:
    return all(keyword in (project_type or "") for keyword in (rule.get("only_if") or []))


def _num(value: float) -> str:
    text = "%.4f" % float(value)
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def _compare(actual: float, op: str, limit: float) -> bool:
    if op == "<=":
        return actual <= limit + EPS
    if op == "<":
        return actual < limit + EPS
    if op == ">=":
        return actual >= limit - EPS
    if op == ">":
        return actual > limit - EPS
    if op == "==":
        return abs(actual - limit) <= EPS
    return abs(actual - limit) > EPS


_FORMULA_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*\*?\s*(h|la)$")
_FORMULA_PARAM = {"h": "step", "la": "long_spacing"}


def _eval_formula(raw: str, scheme: Card) -> float:
    match = _FORMULA_RE.match(str(raw).strip())
    if not match:
        raise _RuleSkip("限值表达式 %r 无法解析" % (raw,))
    factor = float(match.group(1))
    field = _FORMULA_PARAM[match.group(2)]
    if not scheme.is_known(field):
        raise _RuleSkip("限值 %r 依赖字段 %s 未解析，待人工确认" % (raw, field))
    return factor * float(scheme.value(field))


def _walltie_branch(spacing_table: Mapping, scheme: Card) -> str:
    rows = scheme.value("rows") if scheme.is_known("rows") else None
    height = scheme.value("build_height") if scheme.is_known("build_height") else None
    if rows == "double":
        if height is None:
            raise _RuleSkip("连墙件间距分支不可定：搭设高度未解析，待人工确认")
        return "双排悬挑_H>50m" if height > 50.0 + EPS else "双排落地_H≤50m"
    if rows == "single":
        if height is None:
            raise _RuleSkip("连墙件间距分支不可定：搭设高度未解析，待人工确认")
        if height > 24.0 + EPS:
            raise _RuleSkip("单排架 H>24m 超出表6.4.2 覆盖范围，待人工确认")
        return "单排_H≤24m"
    raise _RuleSkip("连墙件间距分支不可定：排数未解析，待人工确认")


def _resolve_limit(rule: Mapping, scheme: Card,
                   rules: Rules) -> Tuple[float, str]:
    ref = rule["limit_ref"]
    threshold = rules.threshold(ref)
    value = threshold["value"]
    key = rule.get("limit_key")
    if key is None:
        if isinstance(value, dict):
            raise ContractError("阈值 %s 为分支表，规则 %s 须给 limit_key"
                                % (ref, rule["rule_id"]))
        return float(value), ref
    if not isinstance(value, dict):
        raise ContractError("阈值 %s 非分支表，规则 %s 不应给 limit_key"
                            % (ref, rule["rule_id"]))
    branch_name = _walltie_branch(value, scheme)
    branch = value.get(branch_name)
    if branch is None or key not in branch:
        raise _RuleSkip("阈值 %s 分支 %s 缺键 %r，待人工确认"
                        % (ref, branch_name, key))
    raw = branch[key]
    if isinstance(raw, str):
        return (_eval_formula(raw, scheme),
                "%s.%s.%s=%s" % (ref, branch_name, key, raw))
    return float(raw), "%s.%s.%s=%s" % (ref, branch_name, key, raw)


def check_consistency(rule: Mapping, scheme: Card, calcbook: Card,
                      rules: Rules) -> Tuple[str, dict]:
    """两张皮：仅比对两侧都存在字段；缺失 → 待人工确认。"""
    param = rule["param"]
    if not scheme.is_known(param) or not calcbook.is_known(param):
        missing = [name for name, card in (("方案卡", scheme), ("验算书卡", calcbook))
                   if not card.is_known(param)]
        return ("confirmation", {
            "rule_id": rule["rule_id"], "name": rule.get("name"),
            "check_type": "consistency", "param": param,
            "reason": "%s缺少字段 %s，待人工确认" % ("与".join(missing), param)})
    scheme_value = float(scheme.value(param))
    calcbook_value = float(calcbook.value(param))
    config = rules.consistency
    tolerance = float(rule.get("tolerance", config["tolerances"].get(
        param, config["default_tolerance"])))
    delta = calcbook_value - scheme_value
    base = {
        "rule_id": rule["rule_id"], "name": rule.get("name"),
        "check_type": "consistency", "param": param,
        "scheme_value": scheme_value, "calcbook_value": calcbook_value,
        "delta": delta, "tolerance": tolerance,
        "clause_refs": rule.get("clause_refs", []), "advice": rule.get("advice"),
    }
    if abs(delta) <= tolerance + EPS:
        base.update({"verdict": "pass", "level": None,
                     "note": "两卡取值一致（容差 %.3f 内）" % tolerance,
                     "expr": "方案=%s vs 验算书=%s（|Δ|=%.3f ≤ 容差 %.3f）"
                             % (_fmt(scheme_value), _fmt(calcbook_value),
                                abs(delta), tolerance)})
        return ("finding", base)
    worse_sign = int(rule.get("worse_sign",
                              config["worse_sign"].get(param, +1)))
    scheme_worse = (scheme_value - calcbook_value) * worse_sign > 0
    module = config["param_modules"].get(param, "相关验算模块")
    if scheme_worse:
        base["level"] = "不合格"
        base["impact"] = "方案实况劣于验算书取值，实况未被验算覆盖（影响：%s）" % module
    else:
        base["level"] = "提示"
        base["impact"] = "验算书取值劣于方案实况（验算偏保守），两卡仍需统一（影响：%s）" % module
    base["verdict"] = "violation"
    base["note"] = "方案正文与验算书取值不一致；按影响方向定级（劣于=不合格）"
    base["expr"] = "方案=%s vs 验算书=%s（|Δ|=%.3f > 容差 %.3f）" % (
        _fmt(scheme_value), _fmt(calcbook_value), abs(delta), tolerance)
    return ("finding", base)


def _confirmation(rule: Mapping, param: Optional[str], reason: str) -> dict:
    return {"rule_id": rule.get("rule_id"), "name": rule.get("name"),
            "check_type": rule.get("check_type"), "param": param,
            "reason": reason}


def _run_threshold(rule: Mapping, scheme: Card, rules: Rules,
                   findings: List[dict], confirmations: List[dict]) -> None:
    param = rule["param"]
    computed = rule.get("computed")
    if computed:
        names = [name.strip() for name in computed.split("*")]
        missing = [name for name in names if not scheme.is_known(name)]
        if missing:
            confirmations.append(_confirmation(
                rule, param, "计算字段 %s 未解析，待人工确认" % ", ".join(missing)))
            return
        actual = 1.0
        for name in names:
            actual *= float(scheme.value(name))
    else:
        if not scheme.is_known(param):
            confirmations.append(_confirmation(
                rule, param, "参数 %s 未解析/低置信度，待人工确认" % param))
            return
        actual = float(scheme.value(param))
    try:
        limit, limit_source = _resolve_limit(rule, scheme, rules)
    except ContractError as exc:
        confirmations.append(_confirmation(rule, param, "限值依据不可用：%s" % exc))
        return
    except _RuleSkip as exc:
        confirmations.append(_confirmation(rule, param, exc.reason))
        return
    op = rule["op"]
    ok = _compare(actual, op, limit)
    findings.append({
        "rule_id": rule["rule_id"], "name": rule.get("name"),
        "check_type": "threshold", "param": param,
        "verdict": "pass" if ok else "violation",
        "level": None if ok else rule.get("level"),
        "expr": "%s %s %s" % (_num(actual), op, _num(limit)),
        "actual": actual, "op": op, "limit_value": limit,
        "limit_source": limit_source,
        "clause_refs": rule.get("clause_refs", []), "advice": rule.get("advice"),
    })


def _run_presence(rule: Mapping, scheme: Card, findings: List[dict],
                  confirmations: List[dict]) -> None:
    param = rule["param"]
    if not scheme.is_known(param):
        confirmations.append(_confirmation(
            rule, param, "参数 %s 未解析/低置信度，待人工确认" % param))
        return
    present = bool(scheme.value(param))
    findings.append({
        "rule_id": rule["rule_id"], "name": rule.get("name"),
        "check_type": "presence", "param": param,
        "verdict": "pass" if present else "violation",
        "level": None if present else rule.get("level"),
        "expr": "%s 在位=%s" % (param, "是" if present else "否"),
        "clause_refs": rule.get("clause_refs", []), "advice": rule.get("advice"),
    })


def _run_grading_rule(rule: Mapping, scheme: Card, grading_result: Mapping,
                      findings: List[dict], confirmations: List[dict]) -> None:
    require_level = rule.get("require_level")
    evidence_param = rule.get("evidence_param")
    if grading_result.get("status") == "pending":
        confirmations.append(_confirmation(
            rule, evidence_param, "分级判定待人工确认（%s），本条暂不执行"
            % grading_result.get("note")))
        return
    if grading_result.get("level") != require_level:
        findings.append({
            "rule_id": rule["rule_id"], "name": rule.get("name"),
            "check_type": "grading", "param": grading_result.get("param"),
            "verdict": "pass", "level": None,
            "expr": "当前分级=%s，不适用本条（要求=%s）"
                    % (grading_result.get("level"), require_level),
            "actual": grading_result.get("actual"),
            "clause_refs": rule.get("clause_refs", [])})
        return
    if not scheme.is_known(evidence_param):
        confirmations.append(_confirmation(
            rule, evidence_param, "方案未解析到%s关键词，待人工确认"
            % rule.get("evidence_label")))
        return
    evidenced = bool(scheme.value(evidence_param))
    findings.append({
        "rule_id": rule["rule_id"], "name": rule.get("name"),
        "check_type": "grading", "param": grading_result.get("param"),
        "evidence_param": evidence_param, "evidenced": evidenced,
        "verdict": "pass" if evidenced else "violation",
        "level": None if evidenced else rule.get("level"),
        "expr": "分级=%s（%s=%s）且方案%s%s" % (
            require_level, grading_result.get("param"),
            _num(grading_result.get("actual")),
            "已载明" if evidenced else "未载明", rule.get("evidence_label", "")),
        "actual": grading_result.get("actual"),
        "clause_refs": rule.get("clause_refs", []), "advice": rule.get("advice"),
    })


def run_checks(rules: Rules, scheme: Card, calcbook: Card,
               grading_result: Mapping) -> Tuple[List[dict], List[dict]]:
    """核查主管线：门控 → 条文纪律拦截 → 分派（与旧仓同口径）。"""
    findings: List[dict] = []
    confirmations: List[dict] = []
    for rule in rules.checks["rules"]:
        if rule.get("status") != "已核对":
            confirmations.append(_confirmation(
                rule, rule.get("param"),
                "规则 status=%s（未核对），不得执行" % rule.get("status")))
            continue
        if not _gate_passes(rule, scheme.project_type):
            continue
        check_type = rule["check_type"]
        if check_type == "threshold":
            _run_threshold(rule, scheme, rules, findings, confirmations)
        elif check_type == "presence":
            _run_presence(rule, scheme, findings, confirmations)
        elif check_type == "consistency":
            kind, payload = check_consistency(rule, scheme, calcbook, rules)
            (findings if kind == "finding" else confirmations).append(payload)
        elif check_type == "grading":
            _run_grading_rule(rule, scheme, grading_result, findings, confirmations)
        else:
            raise ContractError("未知 check_type %r" % (check_type,))
    return findings, confirmations


# ---------------------------------------------------------------------------
# 记录构造
# ---------------------------------------------------------------------------
_CALC_CLAUSE = {
    "M-1": {"lizhigan_stability": "m1.stability"},
    "M-2": {"lizhigan_stability": "m2.stability"},
    "M-3": {"bending_strength": "m3.bending", "deflection": "m3.deflection",
            "antislip": "m3.antislip"},
    "M-4": {"tie_strength": "m4.strength", "tie_stability": "m4.stability",
            "antislip": "m4.antislip"},
    "M-5": {"foundation_bearing": "m5.foundation"},
    "M-6": {"column_stability": "m6.column",
            "foundation_bearing": "m6.foundation"},
}


def _calc_records(module_id: str, result: Mapping, rules: Rules,
                  basis) -> List[CalculationRecord]:
    records = []
    for check in result["checks"]:
        key = _CALC_CLAUSE[module_id][check["item"]]
        verdict = OK if check["verdict"] == "pass" else REJECTED
        records.append(CalculationRecord(
            item_id="%s.%s" % (module_id, check["item"]),
            verdict=verdict,
            message="%s：%s" % (result["module_id"], check["substituted"]),
            basis=rules.ref(basis, key),
            evidence={"module": module_id, "check": check["item"],
                      "formula": check["expr"], "substituted": check["substituted"],
                      "ratio": check["ratio"], "limit": check["limit"],
                      "clause_refs": check["clause_refs"],
                      "detail": result["detail"], "warnings": result["warnings"]},
        ))
    return records


def _grading_record(rules: Rules, result: Mapping, basis) -> CalculationRecord:
    if result["status"] == "pending":
        return CalculationRecord(
            item_id="grading.pending", verdict=OK,
            message="危大分级待人工确认：%s" % result.get("note"),
            basis=rules.ref(basis, result.get("clause") or "31-scope"),
            evidence={"status": "pending", "item_id": result.get("item_id"),
                      "project_type": result.get("project_type"),
                      "unknown_params": result.get("unknown_params", []),
                      "note": result.get("note")},
        )
    return CalculationRecord(
        item_id="grading.%s" % result["item_id"], verdict=OK,
        message="%s → %s（%s）" % (result["project_type"], result["label"],
                                   result.get("cond")),
        basis=rules.ref(basis, result["clause"]),
        evidence={"status": "definite", "item_id": result["item_id"],
                  "project_type": result["project_type"],
                  "level": result["level"], "label": result["label"],
                  "duty": result.get("duty"), "cond": result.get("cond"),
                  "rule_id": result["rule_id"], "param": result.get("param"),
                  "actual": result.get("actual"),
                  "basis": result.get("basis", []), "note": result.get("note")},
    )


def _finding_record(rules: Rules, rule: Mapping, finding: Mapping,
                    basis) -> CalculationRecord:
    verdict = OK if finding["verdict"] == "pass" else REJECTED
    message = "%s：%s" % (finding.get("name") or rule.get("rule_id"),
                          finding.get("expr") or finding.get("note") or "")
    evidence = {"status": "definite", "rule_id": rule["rule_id"],
                "check_type": finding.get("check_type"),
                "param": finding.get("param"), "verdict": finding["verdict"],
                "level": finding.get("level"),
                "clause_refs": finding.get("clause_refs", []),
                "advice": finding.get("advice")}
    for key in ("actual", "op", "limit_value", "limit_source", "expr",
                "scheme_value", "calcbook_value", "delta", "tolerance",
                "impact", "note", "evidenced", "evidence_param"):
        if key in finding:
            evidence[key] = finding[key]
    return CalculationRecord(
        item_id="rule.%s" % rule["rule_id"], verdict=verdict, message=message,
        basis=rules.ref(basis, rule["basis"]), evidence=evidence)


def _confirmation_record(rules: Rules, rule: Mapping, confirmation: Mapping,
                         basis) -> CalculationRecord:
    return CalculationRecord(
        item_id="rule.%s" % rule["rule_id"], verdict=OK,
        message="%s：待人工确认——%s" % (rule.get("rule_id"),
                                        confirmation.get("reason")),
        basis=rules.ref(basis, rule["basis"]),
        evidence={"status": "pending", "rule_id": rule["rule_id"],
                  "check_type": confirmation.get("check_type"),
                  "param": confirmation.get("param"),
                  "reason": confirmation.get("reason")},
    )


# ---------------------------------------------------------------------------
# 器官入口
# ---------------------------------------------------------------------------
def _scheme_card(raw: Mapping, label: str) -> Card:
    if not isinstance(raw, Mapping):
        raise ValueError("%s 必须是对象" % label)
    project_type = raw.get("project_type")
    if project_type is not None:
        project_type = _text(project_type, "%s.project_type" % label)
    else:
        project_type = ""
    params_raw = raw.get("params") or {}
    if not isinstance(params_raw, Mapping):
        raise ValueError("%s.params 必须是对象" % label)
    params = {}
    for name, value in params_raw.items():
        if isinstance(value, Mapping) and "value" in value:
            params[name] = value["value"]
        else:
            params[name] = value
    unknown = raw.get("unknown") or []
    if not isinstance(unknown, (list, tuple)):
        raise ValueError("%s.unknown 必须是数组" % label)
    category = raw.get("category")
    if category is not None:
        category = _enum(category, "%s.category" % label,
                         ("coupler_steel_pipe_scaffold", "formwork_support"))
    kind = "calcbook" if label.endswith("calcbook") else "scheme"
    return Card(kind, project_type=project_type, params=params,
                unknown=unknown, category=category)


def _grade(subject: Mapping, rules: Rules) -> dict:
    grading = _require(subject, "grading", "subject")
    if not isinstance(grading, Mapping):
        raise ValueError("grading 必须是对象")
    if grading.get("item_id") is not None:
        item_id = _text(grading["item_id"], "grading.item_id")
    else:
        project_type = _text(_require(grading, "project_type", "grading"),
                             "grading.project_type")
        item_id = recognize_item(rules, project_type)
        if item_id is None:
            raise ValueError("工程类型未识别（无法匹配危大清单条目）：%r" % project_type)
    params = grading.get("params") or {}
    if not isinstance(params, Mapping):
        raise ValueError("grading.params 必须是对象")
    result = judge(rules, item_id, params)
    if result["status"] != "definite":
        raise ValueError("危大分级参数不足：%s（缺 %s）"
                         % (result.get("note"), ", ".join(result.get("unknown_params") or [])))
    return result


def evaluate(subject: Mapping, basis) -> Iterable[CalculationRecord]:
    if not isinstance(subject, Mapping):
        raise ValueError("subject 必须是 JSON 对象")
    mode = _enum(_require(subject, "mode", "subject"), "subject.mode", MODES)
    _text(_require(subject, "case_id", "subject"), "subject.case_id")
    rules = PACK

    if mode == MODE_CALC:
        calc = _require(subject, "calc", "subject")
        if not isinstance(calc, Mapping):
            raise ValueError("calc 必须是对象")
        card_data = _require(calc, "card", "calc")
        if not isinstance(card_data, Mapping):
            raise ValueError("calc.card 必须是对象")
        explicit = calc.get("module") or "auto"
        module_id = (detect_module(card_data) if explicit == "auto"
                     else _enum(explicit, "calc.module", tuple(_CALCS)))
        result = run_calc(module_id, card_data, rules)
        return tuple(_calc_records(module_id, result, rules, basis))

    if mode == MODE_GRADE:
        return (_grading_record(rules, _grade(subject, rules), basis),)

    review = _require(subject, "review", "subject")
    if not isinstance(review, Mapping):
        raise ValueError("review 必须是对象")
    scheme = _scheme_card(_require(review, "scheme", "review"), "review.scheme")
    calcbook_raw = review.get("calcbook") or {"params": {}}
    calcbook = _scheme_card(calcbook_raw, "review.calcbook")
    project_type = scheme.project_type
    item_id = recognize_item(rules, project_type)
    if item_id is None:
        grading_result = _pending(None, "工程类型未识别（无法匹配危大清单条目）",
                                  project_type=project_type)
    else:
        params = {name: value for name, value in scheme.params.items()
                  if name not in scheme.unknown}
        grading_result = judge(rules, item_id, params)
    records: List[CalculationRecord] = [_grading_record(rules, grading_result, basis)]
    findings, confirmations = run_checks(rules, scheme, calcbook, grading_result)
    for finding in findings:
        rule = _rule_by_id(rules, finding["rule_id"])
        records.append(_finding_record(rules, rule, finding, basis))
    for confirmation in confirmations:
        rule = _rule_by_id(rules, confirmation["rule_id"])
        records.append(_confirmation_record(rules, rule, confirmation, basis))
    return tuple(records)


def _rule_by_id(rules: Rules, rule_id: str) -> Mapping:
    for rule in rules.checks["rules"]:
        if rule["rule_id"] == rule_id:
            return rule
    raise ContractError("规则表缺 rule_id：%s" % rule_id)


register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary="脚手架与模板支架：JGJ 130/162 验算 + 危大分级 + 构造限值核查 + 两张皮一致性",
        input_fields=("mode", "case_id"),
        evaluate=evaluate,
    )
)

__all__ = [
    "SLUG", "VERSION", "CLAUSES", "MODULES", "Rules", "PACK",
    "evaluate", "run_calc", "detect_module", "judge", "eval_cond",
    "recognize_item", "run_checks", "check_consistency", "Card",
    "phi_of", "gk_of", "mu_of", "wind_phi_a05",
]