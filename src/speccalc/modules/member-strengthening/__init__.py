"""器官：既有混凝土构件加固验算与方案核查（member-strengthening）。

迁自 target-map ③ 行（仓库 #45）。迁入后只保留**判定层**：
公式引擎（4 模块）/ 方案规则引擎（4 条规则）/ GB 55021 检查单逐项判定。
文档解析（docx/PDF）、报告排版、GUI、打包、合成数据生成、条款复核元数据全部舍弃
（见 ``docs/member-strengthening.md`` 的处置表）。

一句话语义
    ``subject`` 给「模式 + 参数/方案卡」，``basis`` 给「规范条号」，
    本器官逐检查项产出计算书行：

    - ``calc``      ：CFRP 布 / 粘贴钢板 / 增大截面受弯、植筋锚固深度；
    - ``scheme``    ：参数卡 × 规则库（胶粘剂指标 / 植筋深度 / 先鉴定后加固 / 卸载构造）；
    - ``checklist`` ：GB 55021-2021 检查单已填项逐条判定。

纪律
1. **三态 → 二态**：旧仓「满足/通过」→ ``ok``；「需调整/不满足/不符合/疑似」→ ``rejected``；
   「待人工确认/待确认」→ ``ok`` + ``evidence.plan_verdict="needs_confirm"``（不猜值、不硬判）。
   旧仓 EVIDENCE 独立 finding 无条款号，新契约不允许无依据入账，改为污染规则整体降级。
2. **数值只认已核对表值**：查表值由 ``speccalc/data/member-strengthening.json`` 提供，条目
   ``status`` 必须是「已核对」，否则 ``ContractError``（退出码 3）；条文库缺条即 ``ClauseMissing``。
3. **ratio 恒为「作用 / 抗力」**：受弯 ``M/Mu``、植筋 ``ld_req/ld``；`<= 1` 合格。
   旧仓植筋的 ``ld/ld_req`` 只在 evidence 里保留原式，不用于新账本口径。
4. **无依据不入账**：每条记录都经 ``basis.ref(code, clause)`` 取依据；器官不读文件、不打印、
   不读时钟、不自带 CLI。
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from speccalc.core.data import load
from speccalc.core.ledger import OK, REJECTED, CalculationRecord, ContractError
from speccalc.core.registry import Pack, register

SLUG = "member-strengthening"
VERSION = "0.1.0"
DATA = load("member-strengthening.json")

CLAUSES: Dict[str, dict] = DATA["clauses"]
CONSTANTS: Dict[str, float] = DATA["constants"]
TABLES: Dict[str, dict] = DATA["tables"]
MODULES: Dict[str, dict] = DATA["modules"]
RULES: List[dict] = DATA["rules"]
CHECKLIST: List[dict] = DATA["checklist"]
INVENTORY: dict = DATA["clause_inventory"]

MODE_CALC = "calc"
MODE_SCHEME = "scheme"
MODE_CHECKLIST = "checklist"
MODES = (MODE_CALC, MODE_SCHEME, MODE_CHECKLIST)

PLAN_PASS = "pass"
PLAN_SUSPICIOUS = "suspicious"
PLAN_CONFIRM = "needs_confirm"
PLAN_FAIL = "fail"
PLAN_LABELS = {
    PLAN_FAIL: "不符合",
    PLAN_SUSPICIOUS: "疑似",
    PLAN_CONFIRM: "待人工确认",
    PLAN_PASS: "通过",
}
CHECKLIST_OPTIONS = ("符合", "不符合", "不适用", "待确认")


# ---------------------------------------------------------------------------
# 规则包视图（阈值/表值可整体替换，用于测试「未核对硬拦截」）
# ---------------------------------------------------------------------------
class Rules(object):
    """器官的规则包：所有数值与条款引用都经过已核对校验。"""

    def __init__(self, data: Mapping):
        self.data = data
        self.clauses = dict(data["clauses"])
        self.constants = dict(data["constants"])
        self.tables = dict(data["tables"])
        self.modules = dict(data["modules"])
        self.rules = list(data["rules"])
        self.checklist = list(data["checklist"])

    def clause(self, key: str) -> Mapping:
        entry = self.clauses.get(key)
        if entry is None:
            raise ContractError("规则包缺条款键：%s" % key)
        return entry

    def ref(self, basis, key: str):
        entry = self.clause(key)
        if entry.get("status") != "已核对":
            raise ContractError("条款 %s status=%s，不得进入计算路径"
                                % (key, entry.get("status")))
        return basis.ref(entry["code"], entry["clause"])

    def module(self, module_id: str) -> Mapping:
        entry = self.modules.get(module_id)
        if entry is None:
            raise ValueError("未知验算模块：%r（可用 %s）"
                             % (module_id, ", ".join(sorted(self.modules))))
        return entry

    def rule(self, rule_id: str) -> Mapping:
        for entry in self.rules:
            if entry["id"] == rule_id:
                return entry
        raise ContractError("规则包缺 rule_id：%s" % rule_id)

    def checklist_item(self, item_id: str) -> Mapping:
        for entry in self.checklist:
            if entry["item_id"] == item_id:
                return entry
        raise ValueError("检查单无此条目：%s" % item_id)


PACK = Rules(DATA)


# ---------------------------------------------------------------------------
# 通用校验与账本行
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


def _positive(value, where):
    number = _number(value, where)
    if number <= 0:
        raise ValueError("%s 必须为正：%r" % (where, number))
    return number


def _non_negative(value, where):
    number = _number(value, where)
    if number < 0:
        raise ValueError("%s 不得为负：%r" % (where, number))
    return number


def _check_range(sym, value, rng, problems):
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append("%s: 期望数值，得到 %s" % (sym, type(value).__name__))
        return
    if not math.isfinite(value):
        problems.append("%s 必须是有限数值：%r" % (sym, value))
        return
    exclusive = bool(rng.get("exclusive", False))
    lo, hi = rng.get("min"), rng.get("max")
    if lo is not None and (value < lo or (exclusive and value == lo)):
        problems.append("%s=%s 超出合法范围（下限 %s%s）"
                        % (sym, value, lo, "（不含）" if exclusive else ""))
    if hi is not None and (value > hi or (exclusive and value == hi)):
        problems.append("%s=%s 超出合法范围（上限 %s%s）"
                        % (sym, value, hi, "（不含）" if exclusive else ""))


def validate_params(params, schema):
    """按模块 schema 校验：缺字段/越界/类型逐项列出后一次抛出。"""
    if not isinstance(params, Mapping):
        raise ValueError("params 必须是对象")
    missing = [sym for sym, spec in schema.items()
               if spec.get("required", True) and sym not in params]
    problems = []
    if missing:
        problems.append("缺少参数: " + ", ".join(missing))
    for sym, spec in schema.items():
        if sym in params:
            _check_range(sym, params[sym], spec.get("range") or {}, problems)
    if problems:
        raise ValueError("参数卡校验失败: " + "；".join(problems))
    return params


def _fmt(value):
    return ("%.6f" % float(value)).rstrip("0").rstrip(".")


def _record(item_id, ok, ratio, message, clause_key, basis, pack, extra=None, formula=""):
    """统一账本行：ratio = 作用/抗力；ok 也必须挂依据。"""
    evidence = {
        "formula": formula,
        "ratio": ratio,
        "ratio_tol": float(pack.constants["ratio_tol"]),
        "verdict_rule": "作用/抗力 <= 1 + tol 记 ok；否则 rejected",
    }
    if extra:
        evidence.update(extra)
    verdict = OK if ok else REJECTED
    return CalculationRecord(
        item_id=item_id,
        verdict=verdict,
        message=message,
        basis=pack.ref(basis, clause_key),
        evidence=evidence,
    )


def _info_record(item_id, clause_key, message, basis, pack, extra, formula=""):
    """信息行（不设 ratio，不改退出码；仍需条款依据）。"""
    evidence = dict(extra)
    evidence["formula"] = formula
    evidence["plan_verdict"] = PLAN_PASS
    return CalculationRecord(item_id=item_id, verdict=OK, message=message,
                             basis=pack.ref(basis, clause_key), evidence=evidence)


# ---------------------------------------------------------------------------
# 规范查表（表值来自规则包，不写死在代码里）
# ---------------------------------------------------------------------------
def lookup_alpha_f(rho_te, rebar_rows, pack=PACK):
    table = pack.tables["alpha_f"]
    row = table["double_row"] if rebar_rows > 1 else table["single_row"]
    bands = table["rho_te_bands"]
    if rho_te <= bands[0]:
        return float(row[0]), False
    if rho_te >= bands[-1]:
        return float(row[-1]), False
    for i in range(len(bands) - 1):
        lo, hi = bands[i], bands[i + 1]
        if lo <= rho_te <= hi:
            t = (rho_te - lo) / (hi - lo)
            return float(row[i] + t * (row[i + 1] - row[i])), True
    raise AssertionError("unreachable")


def alpha_spt_from_table(cover_mm, stirrup_dia, d, pack=PACK):
    rows = pack.tables["alpha_spt"]["rows"]
    warnings = []
    if d <= 20.0:
        row_key, frac = "le20", 0.0
    elif d <= 25.0:
        row_key, frac = "le20", (d - 20.0) / 5.0
    elif d <= 32.0:
        row_key, frac = "d25", (d - 25.0) / 7.0
    else:
        raise ValueError("表15.2.3 仅覆盖 d≤32（更大直径请直接给定 alpha_spt）")
    if cover_mm <= 25.0:
        col = 1 if stirrup_dia >= 8 else 0
    elif cover_mm < 30.0:
        warnings.append("保护层 %.1fmm 介于 25/30 之间，保守取 c=25 列" % cover_mm)
        col = 1 if stirrup_dia >= 8 else 0
    elif cover_mm <= 30.0:
        col = 3 if stirrup_dia >= 8 else 2
    elif cover_mm < 35.0:
        warnings.append("保护层 %.1fmm 介于 30/35 之间，保守取 c=30 列" % cover_mm)
        col = 3 if stirrup_dia >= 8 else 2
    elif cover_mm <= 35.0:
        col = 4
        if stirrup_dia < 6:
            warnings.append("c=35 列要求箍筋≥6mm，实际 %.1fmm 超出表列，保守取 c=30/φ6 列" % stirrup_dia)
            col = 2
    else:
        col = 5
        if stirrup_dia < 6:
            warnings.append("c≥40 列要求箍筋≥6mm，实际 %.1fmm 超出表列，保守取 c=35 列" % stirrup_dia)
            col = 4
    lo = float(rows[row_key][col])
    if frac <= 0.0:
        return lo, warnings
    hi = float(rows["d25" if row_key == "le20" else "d32"][col])
    return lo + frac * (hi - lo), warnings


def fbd_from_table(adhesive_grade, s1, s2, d, fc_grade, pack=PACK):
    grade = str(adhesive_grade).strip().upper()
    key = str(fc_grade).strip().upper()
    warnings = []
    for row in reversed(pack.tables["fbd"]):  # 条件最严的行优先（fbd 更高）
        if grade == "B" and "B" not in row["grades"]:
            continue
        if s1 >= row["min_s1_over_d"] * d - 1e-9 and s2 >= row["min_s2_over_d"] * d - 1e-9:
            if key not in row["values"]:
                raise ValueError("表15.2.4 无该基材强度等级列：%s" % fc_grade)
            return float(row["values"][key]), warnings
    raise ValueError("表15.2.4 无满足的构造条件行（grade=%s, s1=%s, s2=%s, d=%s）"
                     % (grade, s1, s2, d))


def _alpha_spt_min(d, pack=PACK):
    if d <= 0:
        return None
    rows = pack.tables["alpha_spt"]["rows"]
    if d <= 20.0:
        lo_row = hi_row = rows["le20"]
        frac = 0.0
    elif d <= 25.0:
        lo_row, hi_row, frac = rows["le20"], rows["d25"], (d - 20.0) / 5.0
    elif d <= 32.0:
        lo_row, hi_row, frac = rows["d25"], rows["d32"], (d - 25.0) / 7.0
    else:
        return None
    return min(float(lo) + frac * (float(hi) - float(lo)) for lo, hi in zip(lo_row, hi_row))


def _fbd_max(grade, fc_grade, pack=PACK):
    if not grade or not fc_grade:
        return None
    key = str(fc_grade).strip().upper()
    values = []
    for row in pack.tables["fbd"]:
        if grade == "B" and "B" not in row["grades"]:
            continue
        if key in row["values"]:
            values.append(float(row["values"][key]))
    return max(values) if values else None


def solve_flexure_x(a_fc_b, t_net, k_coupling, eps_lag, h, f_full, eps_cu):
    """解式(10.2.3-2/3) 或式(9.2.3-2/3) 的受压区高度 x 与强度利用系数 ψ。"""
    b_coef = t_net - k_coupling * (eps_cu + eps_lag)
    c_coef = 0.8 * k_coupling * eps_cu * h
    disc = b_coef * b_coef + 4.0 * a_fc_b * c_coef
    x_uncapped = (b_coef + math.sqrt(disc)) / (2.0 * a_fc_b)
    eps_design = f_full / k_coupling
    psi_raw = (0.8 * eps_cu * h / x_uncapped - eps_cu - eps_lag) / eps_design
    if psi_raw < 0.0:
        return t_net / a_fc_b, 0.0
    if psi_raw <= 1.0:
        return x_uncapped, psi_raw
    return (t_net + f_full) / a_fc_b, 1.0


def solve_x_from_moment(a_fc_b, m_res, h):
    disc = h * h - 2.0 * m_res / a_fc_b
    if disc < 0.0:
        return None
    return h - math.sqrt(disc)


# ---------------------------------------------------------------------------
# 四个验算模块（数值与旧仓逐项一致；输出改为账本行）
# ---------------------------------------------------------------------------
def calc_cfrp(params, basis, pack=PACK):
    schema = pack.module("cfrp_beam_flexure")
    validate_params(params, schema["params"])
    b, h, fc = params["b"], params["h"], params["fc"]
    As, fy, Afe = params["As"], params["fy"], params["Afe"]
    M0, M = params["M0"], params["M"]
    ff, ef, a_s = params["ff"], params["ef"], params["as"]
    Asc = params.get("Asc", 0.0)
    ap = params.get("ap", 0.0)
    fyp = params.get("fyp", fy)
    xi_b = params.get("xi_b")
    alpha1 = params.get("alpha1", 1.0)
    Es = params.get("Es", float(pack.constants["es_default"]))
    rebar_rows = int(params.get("rebar_rows", 1))
    rho_te = params.get("rho_te")
    sigma_s0 = params.get("sigma_s0")
    eps_cu = float(pack.constants["eps_cu"])
    warnings = []
    h0 = h - a_s
    if h0 <= 0.0:
        raise ValueError("几何参数无效：h−as=%s ≤ 0" % h0)
    if Asc > 0.0 and ap <= 0.0:
        raise ValueError("提供 Asc 时必须同时提供 ap（a′）")
    if fc > float(pack.constants["fc_c50_limit"]) and "alpha1" not in params:
        warnings.append("fc 超过 C50，alpha1 应内插，当前默认 1.0 偏于不安全")
    if "Es" not in params:
        warnings.append("Es 未提供，默认取 2.0e5 MPa，请按实际钢筋牌号复核")

    alpha_f, interpolated = 0.0, False
    eps_f0 = 0.0
    if M0 > 0.0:
        if rho_te is None:
            rho_te = As / (0.5 * b * h)
            warnings.append("rho_te 未提供，按 Ate=0.5bh 计算")
        alpha_f, interpolated = lookup_alpha_f(rho_te, rebar_rows, pack)
        if interpolated:
            warnings.append("rho_te 落在表10.2.8 分档之间，alpha_f 线性内插")
        if sigma_s0 is not None and sigma_s0 <= 150.0 and rho_te <= 0.05:
            alpha_f *= float(pack.constants["alpha_f_adjust"])
            warnings.append("sigma_s0≤150MPa 且 rho_te≤0.05，alpha_f×0.9")
        eps_f0 = alpha_f * (M0 * 1.0e6) / (Es * As * h0)

    a_fc_b = alpha1 * fc * b
    t_net = fy * As - fyp * Asc
    m_res = M * 1.0e6 + fy * As * (h - h0) - fyp * Asc * (h - ap)
    x_m = solve_x_from_moment(a_fc_b, m_res, h)
    xi_bf = 0.85 * xi_b if xi_b is not None else None
    infeasible = False
    if xi_b is not None and (x_m is None or x_m > xi_bf * h0):
        infeasible = True
        warnings.append("需求受压区高度超出 xi_b,f·h0=%.2fmm（式10.2.2），方法不可行" % (xi_bf * h0))

    k_coupling = ff * Afe / ef
    f_full = ff * Afe
    x, psi_f = solve_flexure_x(a_fc_b, t_net, k_coupling, eps_f0, h, f_full, eps_cu)
    if x > h:
        infeasible = True
        warnings.append("受压区高度 x=%.2fmm 超过截面高度 h" % x)
    if Asc > 0.0 and x < 2.0 * ap:
        warnings.append("x<2a′（式10.2.3-4），按条文近似取 x=2a′ 重算承载力")
        x = 2.0 * ap

    mu = a_fc_b * x * (h - x / 2.0) + fyp * Asc * (h - ap) - fy * As * (h - h0)
    mu_knm = mu / 1.0e6
    afe_req = None
    if x_m is not None and not infeasible:
        psi_m_raw = (0.8 * eps_cu * h / x_m - eps_cu - eps_f0) / ef
        psi_m = min(max(psi_m_raw, 0.0), 1.0)
        afe_req = max((a_fc_b * x_m - t_net) / (psi_m * ff), 0.0) if psi_m > 0.0 else None

    increase = None
    x0 = t_net / a_fc_b
    increase_ok = True
    if xi_b is not None and x0 > xi_b * h0:
        warnings.append("原截面 x0>xi_b·h0，跳过 40% 提高幅度检查")
    elif Asc > 0.0 and x0 < 2.0 * ap:
        warnings.append("原截面 x0<2a′，跳过 40% 提高幅度检查")
    else:
        mu0 = a_fc_b * x0 * (h0 - x0 / 2.0) + fyp * Asc * (h0 - ap)
        increase = mu_knm / (mu0 / 1.0e6) - 1.0
        increase_ok = increase <= float(pack.constants["capacity_increase_max"])

    km = None
    nf, tf = params.get("nf"), params.get("tf")
    if nf is not None and tf is not None:
        km = min(1.16 - nf * params["Ecf"] * tf / 308000.0, 0.90)

    ratio = M / mu_knm if mu_knm > 0 else None
    ok = (not infeasible) and M <= mu_knm + 1e-9
    message = "M=%s kN·m / Mu=%s kN·m = %s（x=%s mm，ψf=%s）" % (
        _fmt(M), _fmt(mu_knm), _fmt(ratio) if ratio is not None else "无解",
        _fmt(x), _fmt(psi_f))
    if infeasible:
        message += "；需求受压区高度越限，粘贴纤维复合材加固不可行"
    records = [
        _record("cfrp.flexure", ok, ratio, message, "cfrp.10.2.3", basis, pack,
                {"module": "cfrp_beam_flexure", "M_kNm": M, "Mu_kNm": mu_knm,
                 "x_mm": x, "x_M_mm": x_m, "psi_f": psi_f, "Afe_req_mm2": afe_req,
                 "infeasible": infeasible, "warnings": warnings},
                "Mu = α1·fc0·b·x·(h−x/2) + f'y0·As0·(h−a′) − fy0·As0·(h−h0)")
    ]
    if xi_b is None:
        records.append(_info_record(
            "cfrp.xi-limit", "cfrp.10.2.2", "未提供 xi_b，跳过 ξb,f=0.85ξb 上限检查",
            basis, pack, {"checked": False, "xi_b": None, "xi_bf": None}))
    else:
        xi_ratio = x / (xi_bf * h0)
        xi_ok = x <= xi_bf * h0 + 1e-9 and (x_m is None or x_m <= xi_bf * h0 + 1e-9)
        records.append(_record(
            "cfrp.xi-limit", xi_ok, xi_ratio,
            "x=%s mm / ξb,f·h0=%s mm = %s" % (_fmt(x), _fmt(xi_bf * h0), _fmt(xi_ratio)),
            "cfrp.10.2.2", basis, pack,
            {"x_mm": x, "x_M_mm": x_m, "xi_b": xi_b, "xi_bf": xi_bf,
             "limit_mm": xi_bf * h0}))
    if increase is None:
        records.append(_info_record(
            "cfrp.capacity-increase", "cfrp.10.2.10", "原截面条件不满足近似前提，跳过 40% 提高幅度检查",
            basis, pack, {"checked": False, "increase": None}))
    else:
        inc_ratio = increase / float(pack.constants["capacity_increase_max"])
        records.append(_record(
            "cfrp.capacity-increase", increase_ok, inc_ratio,
            "提高幅度 %s%% / 限值 40%% = %s" % (_fmt(increase * 100.0), _fmt(inc_ratio)),
            "cfrp.10.2.10", basis, pack,
            {"increase": increase, "limit": float(pack.constants["capacity_increase_max"])}))
    records.append(_info_record(
        "cfrp.secondary-strain", "cfrp.10.2.8",
        "二次受力 αf=%s，εf0=%s（M0=%s kN·m）" % (_fmt(alpha_f), _fmt(eps_f0), _fmt(M0)),
        basis, pack, {"activated": M0 > 0.0, "alpha_f": alpha_f, "epsilon_f0": eps_f0,
                      "interpolated": interpolated},
        "εf0 = αf·M0k/(Es·As·h0)"))
    if km is not None:
        records.append(_info_record(
            "cfrp.km", "cfrp.10.2.4", "多层折减 km=%s（Af=Afe/km）" % _fmt(km),
            basis, pack, {"nf": nf, "tf": tf, "km": km, "Afe_mm2": Afe,
                          "Af_mm2": Afe / km}, "km = 1.16 − nf·Ef·tf/308000（≤0.90）"))
    return tuple(records)


def calc_steel_plate(params, basis, pack=PACK):
    schema = pack.module("steel_plate_flexure")
    validate_params(params, schema["params"])
    b, h, fc = params["b"], params["h"], params["fc"]
    As, fy, Ap, fp = params["As"], params["fy"], params["Ap"], params["fp"]
    M0, M = params["M0"], params["M"]
    a_s = params["as"]
    Asc = params.get("Asc", 0.0)
    Apc = params.get("Apc", 0.0)
    ap = params.get("ap", 0.0)
    fyp = params.get("fyp", fy)
    fpp = params.get("fpp", fp)
    xi_b = params.get("xi_b")
    alpha1 = params.get("alpha1", 1.0)
    Es = params.get("Es", float(pack.constants["es_default"]))
    Esp = params.get("Esp", float(pack.constants["esp_default"]))
    rebar_rows = int(params.get("rebar_rows", 1))
    rho_te = params.get("rho_te")
    sigma_s0 = params.get("sigma_s0")
    eps_cu = float(pack.constants["eps_cu"])
    warnings = []
    h0 = h - a_s
    if h0 <= 0.0:
        raise ValueError("几何参数无效：h−as=%s ≤ 0" % h0)
    if (Asc > 0.0 or Apc > 0.0) and ap <= 0.0:
        raise ValueError("提供 Asc 或 Apc 时必须同时提供 ap（a′）")
    if "Es" not in params:
        warnings.append("Es 未提供，默认取 2.0e5 MPa")
    if "Esp" not in params:
        warnings.append("Esp 未提供，默认取 2.06e5 MPa")

    alpha_sp, interpolated = 0.0, False
    eps_sp0 = 0.0
    if M0 > 0.0:
        if rho_te is None:
            rho_te = As / (0.5 * b * h)
            warnings.append("rho_te 未提供，按 Ate=0.5bh 计算")
        alpha_sp, interpolated = lookup_alpha_f(rho_te, rebar_rows, pack)
        if interpolated:
            warnings.append("rho_te 落在表9.2.9 分档之间，alpha_sp 线性内插")
        if sigma_s0 is not None and sigma_s0 <= 150.0 and rho_te <= 0.05:
            alpha_sp *= float(pack.constants["alpha_f_adjust"])
            warnings.append("sigma_s0≤150MPa 且 rho_te≤0.05，alpha_sp×0.9")
        eps_sp0 = alpha_sp * (M0 * 1.0e6) / (Es * As * h0)

    a_fc_b = alpha1 * fc * b
    t_net = fy * As - fyp * Asc - fpp * Apc
    m_res = M * 1.0e6 + fy * As * (h - h0) - fyp * Asc * (h - ap) - fpp * Apc * h
    x_m = solve_x_from_moment(a_fc_b, m_res, h)
    xi_bsp = 0.85 * xi_b if xi_b is not None else None
    infeasible = False
    if xi_b is not None and (x_m is None or x_m > xi_bsp * h0):
        infeasible = True
        warnings.append("需求受压区高度超出 xi_b,sp·h0=%.2fmm（式9.2.2），方法不可行" % (xi_bsp * h0))

    x, psi_sp = solve_flexure_x(a_fc_b, t_net, Esp * Ap, eps_sp0, h, fp * Ap, eps_cu)
    if x > h:
        infeasible = True
        warnings.append("受压区高度 x=%.2fmm 超过截面高度 h" % x)
    if (Asc > 0.0 or Apc > 0.0) and x < 2.0 * ap:
        warnings.append("x<2a′（式9.2.3-4），近似取 x=2a′ 重算承载力")
        x = 2.0 * ap

    mu = (a_fc_b * x * (h - x / 2.0) + fyp * Asc * (h - ap)
          + fpp * Apc * h - fy * As * (h - h0))
    mu_knm = mu / 1.0e6
    ap_req = None
    if x_m is not None and not infeasible:
        psi_m_raw = (0.8 * eps_cu * h / x_m - eps_cu - eps_sp0) * Esp / fp
        psi_m = min(max(psi_m_raw, 0.0), 1.0)
        ap_req = max((a_fc_b * x_m - t_net) / (psi_m * fp), 0.0) if psi_m > 0.0 else None

    increase = None
    x0 = (fy * As - fyp * Asc) / a_fc_b
    increase_ok = True
    if xi_b is not None and x0 > xi_b * h0:
        warnings.append("原截面 x0>xi_b·h0，跳过 40% 提高幅度检查")
    elif Asc > 0.0 and x0 < 2.0 * ap:
        warnings.append("原截面 x0<2a′，跳过 40% 提高幅度检查")
    else:
        mu0 = a_fc_b * x0 * (h0 - x0 / 2.0) + fyp * Asc * (h0 - ap)
        increase = mu_knm / (mu0 / 1.0e6) - 1.0
        increase_ok = increase <= float(pack.constants["capacity_increase_max"])

    ratio = M / mu_knm if mu_knm > 0 else None
    ok = (not infeasible) and M <= mu_knm + 1e-9
    message = "M=%s kN·m / Mu=%s kN·m = %s（x=%s mm，ψsp=%s）" % (
        _fmt(M), _fmt(mu_knm), _fmt(ratio) if ratio is not None else "无解",
        _fmt(x), _fmt(psi_sp))
    if infeasible:
        message += "；需求受压区高度越限，粘贴钢板加固不可行"
    records = [
        _record("plate.flexure", ok, ratio, message, "plate.9.2.3", basis, pack,
                {"module": "steel_plate_flexure", "M_kNm": M, "Mu_kNm": mu_knm,
                 "x_mm": x, "x_M_mm": x_m, "psi_sp": psi_sp, "Asp_req_mm2": ap_req,
                 "infeasible": infeasible, "warnings": warnings})
    ]
    if xi_b is None:
        records.append(_info_record(
            "plate.xi-limit", "plate.9.2.2", "未提供 xi_b，跳过 ξb,sp=0.85ξb 上限检查",
            basis, pack, {"checked": False, "xi_b": None, "xi_bsp": None}))
    else:
        xi_ratio = x / (xi_bsp * h0)
        xi_ok = x <= xi_bsp * h0 + 1e-9 and (x_m is None or x_m <= xi_bsp * h0 + 1e-9)
        records.append(_record(
            "plate.xi-limit", xi_ok, xi_ratio,
            "x=%s mm / ξb,sp·h0=%s mm = %s" % (_fmt(x), _fmt(xi_bsp * h0), _fmt(xi_ratio)),
            "plate.9.2.2", basis, pack,
            {"x_mm": x, "x_M_mm": x_m, "xi_b": xi_b, "xi_bsp": xi_bsp,
             "limit_mm": xi_bsp * h0}))
    if increase is None:
        records.append(_info_record(
            "plate.capacity-increase", "plate.9.2.11",
            "原截面条件不满足近似前提，跳过 40% 提高幅度检查",
            basis, pack, {"checked": False, "increase": None}))
    else:
        inc_ratio = increase / float(pack.constants["capacity_increase_max"])
        records.append(_record(
            "plate.capacity-increase", increase_ok, inc_ratio,
            "提高幅度 %s%% / 限值 40%% = %s" % (_fmt(increase * 100.0), _fmt(inc_ratio)),
            "plate.9.2.11", basis, pack,
            {"increase": increase, "limit": float(pack.constants["capacity_increase_max"])}))
    records.append(_info_record(
        "plate.secondary-strain", "plate.9.2.9",
        "二次受力 αsp=%s，εsp,0=%s（M0=%s kN·m）" % (_fmt(alpha_sp), _fmt(eps_sp0), _fmt(M0)),
        basis, pack, {"activated": M0 > 0.0, "alpha_sp": alpha_sp,
                      "epsilon_sp0": eps_sp0, "interpolated": interpolated},
        "εsp,0 = αsp·M0k/(Es·As·h0)"))
    return tuple(records)


def calc_section_enlarge(params, basis, pack=PACK):
    schema = pack.module("section_enlarge_flexure")
    validate_params(params, schema["params"])
    b, h, hf = params["b"], params["h"], params["hf"]
    fc = params["fc"]
    As, fy, As2, fy2 = params["As"], params["fy"], params["As2"], params["fy2"]
    a_s, a_s2 = params["as"], params["as2"]
    M0, M = params["M0"], params["M"]
    Asc = params.get("Asc", 0.0)
    ap = params.get("ap", 0.0)
    fyp = params.get("fyp", fy)
    alpha1 = params.get("alpha1", 1.0)
    beta1 = params.get("beta1", 0.8)
    Es = params.get("Es", float(pack.constants["es_default"]))
    xi_b0 = params.get("xi_b0")
    alpha_s = float(pack.constants["alpha_s"])
    eps_cu = float(pack.constants["eps_cu"])
    warnings = []
    h01 = h - a_s
    h0 = h + hf - a_s2
    if h01 <= 0.0 or h0 <= h01:
        raise ValueError("几何参数无效：h01=h−as=%.2f, h0=h+hf−as2=%.2f（加固后有效高度必须更大）"
                         % (h01, h0))
    if Asc > 0.0 and ap <= 0.0:
        raise ValueError("提供 Asc 时必须同时提供 ap（a′）")
    if "Es" not in params:
        warnings.append("Es 未提供，默认取 2.0e5 MPa")

    eps_s0 = (M0 * 1.0e6) / (0.85 * h01 * As * Es) if M0 > 0.0 else 0.0
    eps_s1 = (1.6 * h0 / h01 - 0.6) * eps_s0
    xi_b = beta1 / (1.0 + alpha_s * fy2 / (eps_cu * Es) + eps_s1 / eps_cu)

    a_fc_b = alpha1 * fc * b
    sigma_s0 = fy
    sigma_path = False
    x_lin = (fy * As + alpha_s * fy2 * As2 - fyp * Asc) / a_fc_b
    if xi_b0 is not None and x_lin / h01 > xi_b0:
        sigma_path = True
        b_coef = alpha_s * fy2 * As2 - fyp * Asc - As * Es * eps_cu
        c_coef = 0.8 * As * Es * eps_cu * h01
        x = (b_coef + math.sqrt(b_coef * b_coef + 4.0 * a_fc_b * c_coef)) / (2.0 * a_fc_b)
        raw = (0.8 * h01 / x - 1.0) * eps_cu * Es
        sigma_s0 = min(raw, fy)
        if sigma_s0 < raw:
            warnings.append("式(5.2.5) σs0 计算值超过 fy0，已按 fy0 封顶")
    else:
        x = x_lin
    infeasible = False
    if x > xi_b * h0:
        infeasible = True
        warnings.append("x=%.2fmm 超过 ξb·h0=%.2fmm（式5.2.3-3），超筋" % (x, xi_b * h0))
    if Asc > 0.0 and x < 2.0 * ap:
        warnings.append("x<2a′（式5.2.3-3），近似取 x=2a′ 重算承载力")
        x = 2.0 * ap

    fy0_eff = sigma_s0 if sigma_path else fy
    mu = (alpha_s * fy2 * As2 * (h0 - x / 2.0)
          + fy0_eff * As * (h01 - x / 2.0) + fyp * Asc * (x / 2.0 - ap))
    mu_knm = mu / 1.0e6
    ratio = M / mu_knm if mu_knm > 0 else None
    ok = (not infeasible) and M <= mu_knm + 1e-9
    records = [
        _record("enlarge.flexure", ok, ratio,
                "M=%s kN·m / Mu=%s kN·m = %s（x=%s mm，αs=%s）"
                % (_fmt(M), _fmt(mu_knm), _fmt(ratio) if ratio is not None else "无解",
                   _fmt(x), _fmt(alpha_s)),
                "enlarge.5.2.3", basis, pack,
                {"module": "section_enlarge_flexure", "M_kNm": M, "Mu_kNm": mu_knm,
                 "x_mm": x, "xi_b": xi_b, "infeasible": infeasible, "warnings": warnings})
    ]
    xi_ratio = x / (xi_b * h0)
    records.append(_record(
        "enlarge.xi-limit", x <= xi_b * h0 + 1e-9 and not infeasible, xi_ratio,
        "x=%s mm / ξb·h0=%s mm = %s" % (_fmt(x), _fmt(xi_b * h0), _fmt(xi_ratio)),
        "enlarge.5.2.3", basis, pack,
        {"x_mm": x, "xi_b": xi_b, "h0_mm": h0, "limit_mm": xi_b * h0}))
    if sigma_path:
        records.append(_info_record(
            "enlarge.sigma-s0", "enlarge.5.2.5",
            "x/h01>ξb0，按式(5.2.5) 以 σs0=%s MPa 替代 fy0" % _fmt(sigma_s0),
            basis, pack, {"xi_b0": xi_b0, "sigma_s0_MPa": sigma_s0,
                          "capped": any("封顶" in w for w in warnings)},
            "σs0=(0.8·h01/x−1)·εcu·Es ≤ fy0"))
    records.append(_info_record(
        "enlarge.secondary-strain", "enlarge.5.2.4",
        "初始应变 εs0=%s、εs1=%s；ξb=%s（M0=%s kN·m）"
        % (_fmt(eps_s0), _fmt(eps_s1), _fmt(xi_b), _fmt(M0)),
        basis, pack, {"activated": M0 > 0.0, "epsilon_s0": eps_s0,
                      "epsilon_s1": eps_s1, "xi_b": xi_b},
        "εs1=(1.6·h0/h01−0.6)·εs0；ξb=β1/(1+αs·fy/(εcu·Es)+εs1/εcu)"))
    return tuple(records)


def calc_post_rebar(params, basis, pack=PACK):
    schema = pack.module("post_rebar_anchor")
    validate_params(params, schema["params"])
    fc, fy, d, ld = params["fc"], params["fy"], params["d"], params["ld"]
    alpha_spt = params.get("alpha_spt")
    has_table_aspt = params.get("cover") is not None or params.get("stirrup_dia") is not None
    if alpha_spt is not None and has_table_aspt:
        raise ValueError("alpha_spt 与查表路径（cover/stirrup_dia）互斥")
    warnings = []
    if alpha_spt is None:
        if params.get("cover") is None or params.get("stirrup_dia") is None:
            raise ValueError("缺少 alpha_spt：请直接给定，或同时提供 cover 与 stirrup_dia")
        alpha_spt, tw = alpha_spt_from_table(params["cover"], params["stirrup_dia"], d, pack)
        warnings.extend(tw)
    fbd = params.get("fbd")
    has_table_fbd = params.get("adhesive_grade") is not None or params.get("s1") is not None
    if fbd is not None and has_table_fbd:
        raise ValueError("fbd 与查表路径（adhesive_grade/s1/s2/fc_grade）互斥")
    if fbd is None:
        need = ("adhesive_grade", "s1", "s2", "fc_grade")
        if any(params.get(k) is None for k in need):
            raise ValueError("缺少 fbd：请直接给定，或同时提供 adhesive_grade/s1/s2/fc_grade")
        grade_code = int(params["adhesive_grade"])
        if grade_code not in (1, 2):
            raise ValueError("adhesive_grade 仅支持 1（A 级）或 2（B 级）")
        fcg = int(params["fc_grade"])
        if fcg not in (20, 25, 30, 40, 60):
            raise ValueError("fc_grade 仅支持 20/25/30/40/60")
        fbd, tw = fbd_from_table("A" if grade_code == 1 else "B",
                                 params["s1"], params["s2"], d, "C%d" % fcg, pack)
        warnings.extend(tw)

    psi_br = params.get("psi_br", float(pack.constants["psi_br_default"]))
    psi_w = params.get("psi_w", float(pack.constants["psi_w_default"]))
    psi_T = params.get("psi_T", float(pack.constants["psi_T_default"]))
    psi_ae = params.get("psi_ae", float(pack.constants["psi_ae_default"]))
    for key in ("psi_br", "psi_w", "psi_T", "psi_ae"):
        if key not in params:
            warnings.append("%s 未提供，按规范下限取默认值" % key)
    fbd_used = fbd
    fc_grade = params.get("fc_grade")
    adjusted = False
    if params.get("fast_cure"):
        if fc_grade is not None and int(fc_grade) > 30:
            fbd_used = float(pack.constants["fbd_fast_cure_factor"]) * fbd
            adjusted = True
            warnings.append("基材>C30 且快固型胶粘剂，fbd×0.8（第15.2.4条）")
        elif fc_grade is None:
            warnings.append("声明快固型但未提供 fc_grade，未做 fbd×0.8 调整")
    ls = 0.2 * alpha_spt * d * fy / fbd_used
    psi_n = psi_br * psi_w * psi_T
    ld_req = psi_n * psi_ae * ls
    ratio = ld_req / ld
    ok = ld >= ld_req - 1e-9
    return (
        _record("anchor.depth", ok, ratio,
                "ld=%s mm / ld_req=ψN·ψae·ls=%s mm = %s（反向比值 ld/ld_req=%s）"
                % (_fmt(ld), _fmt(ld_req), _fmt(ratio), _fmt(ld / ld_req)),
                "anchor.15.2.2", basis, pack,
                {"module": "post_rebar_anchor", "ld_mm": ld, "ls_mm": ls,
                 "ld_required_mm": ld_req, "psi_N": psi_n, "psi_ae": psi_ae,
                 "alpha_spt": alpha_spt, "fbd_used_MPa": fbd_used, "warnings": warnings},
                "ld ≥ ψN·ψae·ls"),
        _info_record("anchor.fbd", "anchor.15.2.4",
                     "fbd=%s MPa（快固型调整%s）" % (_fmt(fbd_used), "已执行" if adjusted else "未执行"),
                     basis, pack, {"fbd_MPa": fbd, "fbd_used_MPa": fbd_used,
                                   "fast_cure": bool(params.get("fast_cure")), "adjusted": adjusted}),
        _info_record("anchor.psi", "anchor.15.2.5",
                     "ψN=ψbr·ψw·ψT=%s" % _fmt(psi_n), basis, pack,
                     {"psi_br": psi_br, "psi_w": psi_w, "psi_T": psi_T, "psi_N": psi_n},
                     "ψN = ψbr·ψw·ψT"),
        _info_record("anchor.ls", "anchor.15.2.3",
                     "基本锚固深度 ls=%s mm" % _fmt(ls), basis, pack,
                     {"alpha_spt": alpha_spt, "d_mm": d, "fy_MPa": fy,
                      "fbd_MPa": fbd_used, "ls_mm": ls},
                     "ls = 0.2·αspt·d·fy/fbd"),
    )


_CALCS = {
    "cfrp_beam_flexure": calc_cfrp,
    "steel_plate_flexure": calc_steel_plate,
    "section_enlarge_flexure": calc_section_enlarge,
    "post_rebar_anchor": calc_post_rebar,
}


def run_calc(module_id, params, basis, pack=PACK):
    handler = _CALCS.get(module_id)
    if handler is None:
        raise ValueError("未知验算模块：%r（可用 %s）"
                         % (module_id, ", ".join(sorted(_CALCS))))
    return handler(params, basis, pack)


# ---------------------------------------------------------------------------
# 方案规则层（参数卡由调用方给出；器官不解析 docx/PDF）
# ---------------------------------------------------------------------------
def _value_item(raw, where):
    if not isinstance(raw, Mapping):
        raise ValueError("%s 必须是对象" % where)
    quote = raw.get("quote")
    return {
        "kind": str(raw.get("kind") or ""),
        "value": raw.get("value"),
        "unit": raw.get("unit") or "",
        "label": raw.get("label") or "",
        "quote": quote or "",
        "para": raw.get("para"),
        "page": raw.get("page"),
        "where": where,
    }


def _value_number(item):
    if item["value"] is None:
        return None
    return _number(item["value"], item["where"] + ".value")


def make_card(raw, case_id=""):
    """把调用方给的结构化参数卡规范化；证据子串校验不通过 → 记录 issue。"""
    if not isinstance(raw, Mapping):
        raise ValueError("scheme 必须是对象")
    source_text = raw.get("source_text")
    if source_text is None or not isinstance(source_text, str):
        raise ValueError("scheme.source_text 必须是字符串（可为空=降级）")
    doc_name = _text(raw.get("doc_name") or case_id or "scheme", "scheme.doc_name")
    card = {
        "doc_name": doc_name,
        "source_text": source_text,
        "degraded": bool(raw.get("degraded", False)) or not source_text.strip(),
        "methods": [],
        "adhesive_indices": [],
        "anchor_depths": [],
        "design_params": [],
        "unloading": [],
        "appraisal_first": None,
        "notes": list(raw.get("notes") or []),
    }
    for key in ("methods", "adhesive_indices", "anchor_depths", "design_params", "unloading"):
        items = raw.get(key) or []
        if not isinstance(items, (list, tuple)):
            raise ValueError("scheme.%s 必须是数组" % key)
        if key == "methods":
            card[key] = [_value_item(item, "scheme.methods[%d]" % i)
                         for i, item in enumerate(items)]
        else:
            card[key] = [_value_item(item, "scheme.%s[%d]" % (key, i))
                         for i, item in enumerate(items)]
    appraisal = raw.get("appraisal_first")
    if appraisal is not None:
        card["appraisal_first"] = _value_item(appraisal, "scheme.appraisal_first")
    issues = []
    quoted = (card["methods"] + card["adhesive_indices"] + card["anchor_depths"]
              + card["design_params"] + card["unloading"])
    if card["appraisal_first"] is not None:
        quoted.append(card["appraisal_first"])
    for item in quoted:
        if item["quote"] and item["quote"] not in source_text:
            issues.append("%s[%s]: 摘录不是原文子串" % (item["where"], item["kind"] or "appraisal"))
    card["issues"] = issues + list(card["notes"])
    parts = [source_text] + [item["kind"] for item in card["methods"]]
    card["full_text"] = "\n".join(part for part in parts if part)
    return card


def _finding(rule_id, verdict, message, evidence):
    return {"rule_id": rule_id, "verdict": verdict, "message": message,
            "evidence": dict(evidence)}


def _gate_evidence(rule):
    return {"gate_keywords": list(rule["only_if_keywords"])}


def _design_param(card, kind):
    for item in card["design_params"]:
        if item["kind"] == kind:
            return item
    return None


def _grade_label(label):
    text = str(label or "").strip().upper()
    return text[:1] if text[:1] in ("A", "B") else None


def _check_adhesive(rule, card, pack):
    index_name = ""
    if "index=" in rule["target"]:
        index_name = rule["target"].split("index=", 1)[1].rstrip("]").strip()
    items = [item for item in card["adhesive_indices"]
             if not index_name or item["kind"] == index_name]
    if not items:
        return _finding(rule["id"], PLAN_FAIL,
                        rule["message"] + "（方案提及结构胶但未标注该指标值）",
                        _gate_evidence(rule))
    limits = pack.tables["adhesive_limits"]
    verdicts, messages, evidences = [], [], []
    for item in items:
        grade = _grade_label(item["label"])
        bounds = None
        if grade:
            values = []
            source = {}
            for key in ("steel_to_steel_shear_std_MPa_steel_pasting",
                        "steel_to_steel_shear_std_MPa_frp_pasting"):
                row = limits.get(key) or {}
                field = "grade_%s" % grade
                if field in row:
                    values.append(float(row[field]))
                    source[key] = row[field]
            if values:
                bounds = (min(values), max(values), source)
        ev = {"quote": item["quote"], "value": item["value"], "unit": item["unit"],
              "grade": grade}
        if bounds is None:
            verdicts.append(PLAN_CONFIRM)
            messages.append("%s=%s%s（等级%s）无法确定适用限值"
                            % (item["kind"], item["value"], item["unit"],
                               grade or "未标注"))
        else:
            lo, hi, source = bounds
            value = _value_number(item)
            ev.update({"limit_min": lo, "limit_max": hi, "limit_source": source})
            if value is None:
                verdicts.append(PLAN_CONFIRM)
                messages.append("%s 无有效数值" % item["kind"])
            elif value < lo:
                verdicts.append(PLAN_FAIL)
                messages.append("%s=%s%s 低于 %s级胶适用下限 %sMPa"
                                % (item["kind"], value, item["unit"], grade, lo))
            elif value >= hi:
                verdicts.append(PLAN_PASS)
                messages.append("%s=%s%s 不低于 %s级胶全部适用限值（上限 %sMPa）"
                                % (item["kind"], value, item["unit"], grade, hi))
            else:
                verdicts.append(PLAN_SUSPICIOUS)
                messages.append("%s=%s%s 介于 %s 档限值 %s~%sMPa 之间，疑似不足"
                                % (item["kind"], value, item["unit"], grade, lo, hi))
        evidences.append(ev)
    worst = next((v for v in (PLAN_FAIL, PLAN_SUSPICIOUS, PLAN_CONFIRM, PLAN_PASS)
                  if v in verdicts), PLAN_CONFIRM)
    evidence = {"items": evidences} if len(evidences) > 1 else (evidences[0] if evidences else {})
    return _finding(rule["id"], worst, "；".join(messages), evidence)


def _check_anchor_depth(rule, card, pack, basis):
    depths = card["anchor_depths"]
    if not depths:
        return _finding(rule["id"], PLAN_FAIL,
                        rule["message"] + "（方案未标注植筋/锚固深度）", _gate_evidence(rule))
    for key in rule["support_clause_keys"]:
        pack.ref(basis, key)  # 支撑条款任一缺失/未核对 → ClauseMissing / ContractError
    dia = _design_param(card, "植筋直径")
    grade_item = _design_param(card, "钢筋牌号")
    fc_item = _design_param(card, "混凝土强度等级")
    adh_item = _design_param(card, "胶粘剂等级")
    fy_item = _design_param(card, "钢筋强度设计值")
    missing = []
    d = _value_number(dia) if dia is not None else None
    if d is None:
        missing.append("植筋直径 d")
    fc_grade = "C%d" % int(_value_number(fc_item)) if fc_item is not None and fc_item["value"] is not None else None
    if fc_grade is None:
        missing.append("基材混凝土强度等级")
    adh_grade = _grade_label(adh_item["label"]) if adh_item is not None else None
    if adh_grade is None:
        missing.append("胶粘剂等级（A/B）")
    fy = _value_number(fy_item) if fy_item is not None and fy_item["value"] is not None else None
    fy_source = "方案标注钢筋强度设计值"
    if fy is None and grade_item is not None and grade_item["label"]:
        fy = pack.tables["rebar_fy"].get(grade_item["label"])
        if fy is not None:
            fy_source = "牌号 %s 按 GB50010-2010 4.2.3 映射" % grade_item["label"]
    if fy is None:
        missing.append("钢筋强度设计值 fy（牌号无法映射）")
    if missing:
        return _finding(rule["id"], PLAN_CONFIRM,
                        rule["message"] + "（无法建立需求下限，缺少：%s）" % "、".join(missing),
                        {"quote": depths[0]["quote"], "missing": missing})
    alpha_min = _alpha_spt_min(d, pack)
    fbd_top = _fbd_max(adh_grade, fc_grade, pack)
    if alpha_min is None or fbd_top is None:
        reason = ("植筋直径超出表15.2.3 范围" if alpha_min is None
                  else "表15.2.4 无 %s级胶/%s 列值" % (adh_grade, fc_grade))
        return _finding(rule["id"], PLAN_CONFIRM,
                        rule["message"] + "（无法建立需求下限：%s）" % reason,
                        {"quote": depths[0]["quote"]})
    ls_min = 0.2 * alpha_min * d * fy / fbd_top
    psi_w_min = float(pack.constants["psi_w_default"])
    ld_lower = 1.0 * psi_w_min * 1.0 * 1.0 * ls_min
    assumptions = [
        "αspt 取表15.2.3 该直径全列最小 %s" % _fmt(alpha_min),
        "fbd 取表15.2.4 %s级胶/%s 最高档 %sMPa" % (adh_grade, fc_grade, _fmt(fbd_top)),
        "ψbr=ψT=1.0、ψw=%s、ψae=1.0（规范下限）" % _fmt(psi_w_min),
        fy_source,
    ]
    verdicts, messages, evidences = [], [], []
    for item in depths:
        value = _value_number(item)
        ev = {"quote": item["quote"], "stated_mm": value,
              "ld_required_lower_mm": round(ld_lower, 2), "assumptions": assumptions}
        evidences.append(ev)
        if value is None:
            verdicts.append(PLAN_CONFIRM)
            messages.append("%s 锚固深度无有效数值" % item["kind"])
        elif value < ld_lower:
            verdicts.append(PLAN_FAIL)
            messages.append("%s锚固深度 %smm 低于最有利假设下限 %smm（式15.2.2-2）"
                            % (item["kind"], _fmt(value), _fmt(ld_lower)))
        else:
            verdicts.append(PLAN_PASS)
            messages.append("%s锚固深度 %smm 不低于最有利假设下限 %smm（筛查通过）"
                            % (item["kind"], _fmt(value), _fmt(ld_lower)))
    worst = next((v for v in (PLAN_FAIL, PLAN_SUSPICIOUS, PLAN_CONFIRM, PLAN_PASS)
                  if v in verdicts), PLAN_CONFIRM)
    evidence = {"items": evidences} if len(evidences) > 1 else (evidences[0] if evidences else {})
    return _finding(rule["id"], worst, "；".join(messages), evidence)


def _check_one(rule, card, pack, basis):
    if rule["status"] != "已核对":
        return _finding(rule["id"], PLAN_CONFIRM,
                        rule["message"] + "（规则依据未核对，不产生自动不符合）",
                        _gate_evidence(rule))
    if card["degraded"]:
        return _finding(rule["id"], PLAN_CONFIRM,
                        "方案文本解析失败/无可解析段落，整体降级待人工确认",
                        _gate_evidence(rule))
    target = rule["target"]
    if rule["check_type"] == "checklist" and target.startswith("appraisal_first"):
        ev = card["appraisal_first"]
        if ev is not None and ev["quote"] and ev["quote"] in card["source_text"]:
            return _finding(rule["id"], PLAN_PASS,
                            "方案含检测鉴定环节证据（先鉴定、后加固）",
                            {"quote": ev["quote"], "para": ev["para"]})
        return _finding(rule["id"], PLAN_FAIL,
                        rule["message"] + "（未检出鉴定结论/鉴定报告证据）",
                        _gate_evidence(rule))
    if rule["check_type"] == "param_required" and target.startswith("unloading"):
        for item in card["unloading"]:
            if item["quote"] and item["quote"] in card["source_text"]:
                return _finding(rule["id"], PLAN_PASS, "方案写明加固前卸载/支撑构造措施",
                                {"quote": item["quote"], "para": item["para"]})
        return _finding(rule["id"], PLAN_FAIL,
                        rule["message"] + "（门控命中加固方法但未检出卸载/支撑描述）",
                        _gate_evidence(rule))
    if rule["check_type"] == "param_range" and target.startswith("adhesive_indices"):
        return _check_adhesive(rule, card, pack)
    if rule["check_type"] == "param_range" and target.startswith("anchor_depths"):
        return _check_anchor_depth(rule, card, pack, basis)
    return _finding(rule["id"], PLAN_CONFIRM,
                    rule["message"] + "（目标暂不支持自动判定，请人工核对）",
                    _gate_evidence(rule))


def _scheme_record(rule, finding, basis, pack):
    verdict = finding["verdict"]
    ok = verdict not in (PLAN_FAIL, PLAN_SUSPICIOUS)
    evidence = dict(finding["evidence"])
    evidence.update({"rule_id": rule["id"], "category": rule["category"],
                     "plan_verdict": verdict, "plan_label": PLAN_LABELS[verdict],
                     "degraded": bool(evidence.get("degraded", False))})
    message = "[%s] %s" % (PLAN_LABELS[verdict], finding["message"])
    return _record("scheme.%s" % rule["id"], ok, None, message,
                   rule["clause_key"], basis, pack, evidence,
                   "规则 %s（%s）" % (rule["id"], rule["check_type"]))


def run_scheme(card, basis, pack=PACK):
    records = []
    for rule in pack.rules:
        if not any(keyword in card["full_text"] for keyword in rule["only_if_keywords"]):
            continue
        finding = _check_one(rule, card, pack, basis)
        if card["issues"]:
            # 防幻觉总闸：证据链被污染，该规则不产出自动合格/不符合结论。
            finding = _finding(rule["id"], PLAN_CONFIRM,
                               "抽取证据子串校验未通过，规则整体降级待人工确认",
                               dict(finding["evidence"], evidence_issues=list(card["issues"])))
        records.append(_scheme_record(rule, finding, basis, pack))
    return tuple(records)


# ---------------------------------------------------------------------------
# GB 55021 检查单逐项判定
# ---------------------------------------------------------------------------
def run_checklist(answers, basis, pack=PACK):
    if not isinstance(answers, Mapping):
        raise ValueError("checklist 必须是对象")
    known = {item["item_id"] for item in pack.checklist}
    unknown = sorted(set(answers) - known)
    if unknown:
        raise ValueError("检查单无此条目：%s" % ", ".join(unknown))
    records = []
    for item in pack.checklist:
        option = answers.get(item["item_id"], "待确认")
        if option not in CHECKLIST_OPTIONS:
            raise ValueError("检查项 %s 的判定非法：%r（允许 %s）"
                             % (item["item_id"], option, "/".join(CHECKLIST_OPTIONS)))
        if item["status"] != "已核对":
            raise ContractError("检查项 %s status=%s，不得进入判定路径"
                                % (item["item_id"], item["status"]))
        ok = option != "不符合"
        evidence = {"item_id": item["item_id"], "option": option,
                    "check_mode": item["check_mode"], "keywords": list(item["keywords"]),
                    "gist": item["gist"]}
        records.append(_record(
            "checklist.%s" % item["item_id"], ok, None,
            "%s：%s（%s）" % (item["item_id"], option, item["gist"][:48]),
            item["clause_key"], basis, pack, evidence, "GB 55021-2021 检查单"))
    return tuple(records)


# ---------------------------------------------------------------------------
# 器官入口
# ---------------------------------------------------------------------------
def evaluate(subject, basis):
    if not isinstance(subject, Mapping):
        raise ValueError("subject 必须是 JSON 对象")
    mode = _text(_require(subject, "mode", "subject"), "subject.mode")
    if mode not in MODES:
        raise ValueError("subject.mode 非法：%r（允许 %s）" % (mode, "/".join(MODES)))
    case_id = _text(_require(subject, "case_id", "subject"), "subject.case_id")
    if mode == MODE_CALC:
        calc = _require(subject, "calc", "subject")
        module_id = _text(_require(calc, "module", "calc"), "calc.module")
        params = _require(calc, "params", "calc")
        return run_calc(module_id, params, basis)
    if mode == MODE_SCHEME:
        card = make_card(_require(subject, "scheme", "subject"), case_id)
        return run_scheme(card, basis)
    return run_checklist(_require(subject, "checklist", "subject"), basis)


register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary="既有混凝土构件加固：CFRP/粘钢/增大截面/植筋验算 + 方案规则核查 + GB55021 检查单",
        input_fields=("mode", "case_id"),
        evaluate=evaluate,
    )
)

__all__ = [
    "SLUG", "VERSION", "DATA", "CLAUSES", "CONSTANTS", "TABLES", "MODULES",
    "RULES", "CHECKLIST", "INVENTORY", "Rules", "PACK", "evaluate",
    "run_calc", "run_scheme", "run_checklist", "make_card", "validate_params",
    "lookup_alpha_f", "alpha_spt_from_table", "fbd_from_table",
    "solve_flexure_x", "solve_x_from_moment",
]
