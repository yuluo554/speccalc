"""器官：基坑监测数据判读（excavation-monitor）。

迁自 target-map ③ 行（模块 2 报警判定 + 模块 3 频率时效检核）。
迁入后只保留**判定**这一层：不再有台账、导入、报表、界面、打包——那些是外壳，
`ORGAN-PLAYBOOK` §2 明确禁止器官自带。

一句话语义
    subject 给「工程 + 轮次 + 测点（含已核对的累计/速率控制值）+ 逐轮累计变化量」，
    basis 给「GB 50497-2019 的报警值 / 监测频率条款」，
    本器官算出：每条（测点 × 项目 × 轮次）处在哪个状态、靠哪条判据得出、算式与中间量。

三条纪律（与旧仓一致，本产品更严的地方写在括号里）
1. **控制值只认已核对来源**：``kind`` ∈ {design_value, standard_value, user_input} 且
   ``status=verified`` 且有 ``evidence`` 与单位。旧仓此时出「待定值」并 rc=1；
   本产品没有降级态（``docs/speccalc.md`` §4），改判**输入不合法**（rc=2）——
   宁可拒绝计算，也不把「没核对」渲染成「合格」。
2. **单位写错不得供货**：累计量单位必须等于字典单位，速率单位必须是「字典单位 + /d」，
   否则按输入不合法拒算（旧仓 reason=``unit_inconsistent``）。
3. **未闭环期间状态保持**：``alarm`` / ``alarm_confirmed`` 的后继里没有 ``normal``；
   数值回落不能替用户消警，回落事实由 evidence 的 ``fell_back`` 如实显示。

依据口径：``clause`` 字段取旧仓 ``data/clauses/register.json`` 的**登记键**（如
``alarm-values``），不是条号——旧仓 5 条登记项的 ``clause_no`` 全为 null（未取得官方
原文页，按纪律不凭记忆填写）。器官因此不复述不存在的条号；条文库给出该键的
``version`` 与 ``text``，三定位字段照样填得满。详见 ``docs/excavation-monitor.md``。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from speccalc.core.data import load
from speccalc.core.ledger import OK, REJECTED, CalculationRecord, ContractError
from speccalc.core.registry import Pack, register

SLUG = "excavation-monitor"
VERSION = "0.1.0"
DATA = load("excavation-monitor.json")

GE_EPS = float(DATA["constants"]["ge_eps"])
RATE_UNIT_SUFFIX = DATA["constants"]["rate_unit_suffix"]
ITEMS: Dict[str, dict] = {item["code"]: item for item in DATA["items"]}
STATES = DATA["states"]
UNCLOSED = frozenset(STATES["unclosed"])
TRANSITIONS: Dict[str, frozenset] = {
    state: frozenset(targets) for state, targets in STATES["transitions"].items()
}
ALARM_RULES = DATA["rules"]["alarm"]
FREQ_RULES = DATA["rules"]["frequency"]
BANDS: Tuple[dict, ...] = tuple(FREQ_RULES["interval_bands"])
CONTROL_KINDS = frozenset(DATA["input_contract"]["control_value"]["kind"])

BASIS_CUM = "cumulative"
BASIS_RATE = "rate"
BASIS_BOTH = "both"
BASIS_NONE = "none"

#: 输入不合法原因码（与旧仓 ``pmc.contract.thresholds`` 的原因码对齐，便于对账）
REASON_NO_SOURCE = "no_source"
REASON_NOT_VERIFIED = "source_not_confirmed"
REASON_VALUE_MISSING = "value_missing"
REASON_EVIDENCE_MISSING = "evidence_missing"
REASON_UNIT_MISSING = "unit_missing"
REASON_UNIT_INCONSISTENT = "unit_inconsistent"
REASON_WINDOW_UNCONFIGURED = "window_unconfigured"

GAP_NO_OBSERVATION = "no_effective_observation"
GAP_MARKED_MISSING = "missing_flag_marked"
GAP_ROUND_NOT_IMPORTED = "round_not_imported"

CATEGORY_OVER_INTERVAL = "over_interval"
CATEGORY_STALE_FREQUENCY = "stale_frequency"


# ---------------------------------------------------------------------------
# 输入校验：宁可拒算，不猜
# ---------------------------------------------------------------------------
def _require(mapping: Mapping, key: str, where: str):
    if not isinstance(mapping, Mapping):
        raise ValueError("%s 必须是对象" % where)
    if key not in mapping:
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
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("%s 必须是有限数值：%r" % (where, value))
    return value


def _day(text: str) -> int:
    try:
        year, month, day = (int(part) for part in str(text).split("-"))
        return date(year, month, day).toordinal()
    except (ValueError, TypeError):
        raise ValueError("observed_on 必须形如 YYYY-MM-DD：%r" % (text,))


def _item(item_code: str, where: str) -> dict:
    item = ITEMS.get(item_code)
    if item is None:
        raise ValueError("%s 的监测项目 %r 不在字典里（字典 %d 项）" % (where, item_code, len(ITEMS)))
    return item


def _control(point: Mapping, basis_name: str, item: dict, where: str) -> Optional[dict]:
    """取一条控制值。

    返回 ``None`` 表示**该判据在该测点没登记控制值**——旧仓的口径是「还没轮到第二档」，
    不是「待定」：这条判据整条不参与判定（``pmc/alarm/engine.py::archive_threshold``）。
    登记了但字段不全/单位不对，才是输入不合法：宁可拒算，不给错数。
    """
    control = point.get("control") or {}
    if not isinstance(control, Mapping):
        raise ValueError("%s 的 control 必须是对象" % where)
    block = control.get(basis_name)
    if block is None:
        return None
    if not isinstance(block, Mapping):
        raise ValueError("%s 的 control.%s 必须是对象" % (where, basis_name))

    kind = str(block.get("kind") or "")
    if kind not in CONTROL_KINDS:
        raise ValueError("%s control.%s 的来源非法：%r（%s）" % (where, basis_name, kind, REASON_NO_SOURCE))
    if str(block.get("status") or "") != "verified":
        raise ValueError(
            "%s control.%s 未核对来源：status=%r（%s）"
            % (where, basis_name, block.get("status"), REASON_NOT_VERIFIED)
        )
    if block.get("value") is None:
        raise ValueError("%s control.%s 缺数值（%s）" % (where, basis_name, REASON_VALUE_MISSING))
    if not block.get("evidence"):
        raise ValueError("%s control.%s 缺出处凭证（%s）" % (where, basis_name, REASON_EVIDENCE_MISSING))
    unit = block.get("unit")
    if not unit:
        raise ValueError("%s control.%s 缺单位（%s）" % (where, basis_name, REASON_UNIT_MISSING))

    expected = item["unit"] if basis_name == BASIS_CUM else "%s%s" % (item["unit"], RATE_UNIT_SUFFIX)
    if str(unit) != expected:
        raise ValueError(
            "%s control.%s 单位不一致：应为 %s，实为 %s（%s）"
            % (where, basis_name, expected, unit, REASON_UNIT_INCONSISTENT)
        )
    return {
        "value": _number(block["value"], "%s control.%s.value" % (where, basis_name)),
        "unit": expected,
        "kind": kind,
        "status": "verified",
        "evidence": str(block["evidence"]),
    }


def _rounds(subject: Mapping) -> Dict[int, dict]:
    raw = subject.get("rounds")
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ValueError("rounds 必须是数组")
    out: Dict[int, dict] = {}
    for entry in raw:
        index = _number(_require(entry, "index", "rounds[]"), "rounds[].index")
        if index != int(index):
            raise ValueError("rounds[].index 必须是整数：%r" % (index,))
        index = int(index)
        if index in out:
            raise ValueError("轮次重复：R%d" % index)
        out[index] = {
            "index": index,
            "observed_on": _text(_require(entry, "observed_on", "rounds[]"), "rounds[].observed_on"),
            "day": _day(entry["observed_on"]),
            "scheduled": bool(entry.get("scheduled", True)),
            "intensified": bool(entry.get("intensified", False)),
            "excavation_depth_m": entry.get("excavation_depth_m"),
            "condition_code": entry.get("condition_code"),
        }
    return out


def _observations(point: Mapping, where: str) -> Dict[int, dict]:
    raw = point.get("observations")
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise ValueError("%s 的 observations 必须是数组" % where)
    out: Dict[int, dict] = {}
    for entry in raw:
        index = _number(_require(entry, "round", "%s observations[]" % where), "%s observations[].round" % where)
        if index != int(index):
            raise ValueError("%s observations[].round 必须是整数：%r" % (where, index))
        index = int(index)
        if index in out:
            raise ValueError("%s R%d 观测重复" % (where, index))
        missing = bool(entry.get("missing", False))
        value = entry.get("value")
        out[index] = {
            "round": index,
            "missing": missing,
            "value": None if (missing or value is None) else _number(value, "%s R%d value" % (where, index)),
        }
    return out


def _dispositions(subject: Mapping) -> Dict[Tuple[str, str, int], str]:
    raw = subject.get("dispositions") or []
    if not isinstance(raw, list):
        raise ValueError("dispositions 必须是数组")
    out: Dict[Tuple[str, str, int], str] = {}
    for entry in raw:
        key = (
            _text(_require(entry, "point", "dispositions[]"), "dispositions[].point"),
            _text(_require(entry, "item", "dispositions[]"), "dispositions[].item"),
            int(_number(_require(entry, "round", "dispositions[]"), "dispositions[].round")),
        )
        kind = _text(_require(entry, "kind", "dispositions[]"), "dispositions[].kind")
        if kind not in ("handle", "confirm"):
            raise ValueError("dispositions[].kind 非法：%r（允许 handle / confirm）" % (kind,))
        if key in out:
            raise ValueError("处置记录重复：%s %s R%d" % key)
        out[key] = kind
    return out


# ---------------------------------------------------------------------------
# 判定内核（搬自 pmc/alarm/engine.py 的双控合成与状态机）
# ---------------------------------------------------------------------------
def _applicable_bases(item: dict) -> Tuple[str, ...]:
    control_kind = item["control_kind"]
    bases = []
    if control_kind in ALARM_RULES["cumulative"]["applies_to"]:
        bases.append(BASIS_CUM)
    if control_kind in ALARM_RULES["rate"]["applies_to"]:
        bases.append(BASIS_RATE)
    return tuple(bases)


def _max_window_slope(
    values: Mapping[int, float],
    rounds: Mapping[int, dict],
    round_index: int,
    window_days: float,
) -> Optional[float]:
    """窗口内到本轮的最大变化速率；窗口内没有更早读数时返回 None。"""
    here = rounds[round_index]
    best: Optional[float] = None
    for other_index in sorted(rounds):
        if other_index >= round_index or other_index not in values:
            continue
        gap_days = float(here["day"] - rounds[other_index]["day"])
        if gap_days <= 0.0 or gap_days > window_days:
            continue
        slope = abs(values[round_index] - values[other_index]) / gap_days
        if best is None or slope > best:
            best = slope
    return best


def _settle(
    hits: Sequence[str], previous_state: Optional[str], prewarning_hit: bool
) -> Tuple[str, str]:
    """返回 (本轮判据, 本轮基础状态)；粘性与未闭环保持都在这里。"""
    previous_open = previous_state is not None and previous_state in UNCLOSED
    if hits:
        trigger = BASIS_BOTH if len(hits) > 1 else hits[0]
        if previous_open:
            return trigger, previous_state
        return trigger, "alarm"
    if previous_open:
        #: 未闭环期间状态保持：报警已发出，没有处置记录就不能改判「正常」
        return BASIS_NONE, previous_state
    if prewarning_hit:
        return BASIS_NONE, "prewarning"
    return BASIS_NONE, "normal"


def _can_transition(frm: str, to: str) -> bool:
    return to in TRANSITIONS.get(frm, frozenset())


def _record(item_id: str, verdict: str, message: str, basis, evidence: Mapping) -> CalculationRecord:
    return CalculationRecord(item_id=item_id, verdict=verdict, message=message, basis=basis, evidence=evidence)


def _clause_ref(basis, key: str):
    entry = DATA["clauses"][key]
    return basis.ref(entry["code"], entry["clause"])


def _judge_point(
    point: Mapping,
    item: dict,
    rounds: Mapping[int, dict],
    dispositions: Mapping[Tuple[str, str, int], str],
    window_days: Optional[float],
    prewarning_ratio: Optional[float],
    basis,
) -> Tuple[List[CalculationRecord], Dict[int, str]]:
    code = _text(_require(point, "code", "points[]"), "points[].code")
    where = "测点 %s（%s）" % (code, item["code"])
    controls = {}
    for basis_name in _applicable_bases(item):
        resolved = _control(point, basis_name, item, where)
        if resolved is not None:
            controls[basis_name] = resolved
    if not controls:
        raise ValueError(
            "%s 的 control 里没有任何已核对的控制值：先登记累计控制值或速率控制值" % where
        )
    observations = _observations(point, where)
    if observations and not rounds:
        raise ValueError("%s 有观测但 subject 没给 rounds：轮次与观测日期是判定的锚点" % where)

    # 速率判据要么有窗口，要么整条判据不成立：不给窗口就不出结论，也不拿 0 天当窗口
    if BASIS_RATE in controls and not window_days:
        raise ValueError("%s 需要速率窗口：subject.rate_window_days 缺失或非正（%s）"
                         % (where, REASON_WINDOW_UNCONFIGURED))

    present = {
        index: observations[index]
        for index in sorted(observations)
        if not observations[index]["missing"]
        and observations[index]["value"] is not None
        and index in rounds
    }
    values = {index: present[index]["value"] for index in present}

    clause = _clause_ref(basis, ALARM_RULES["cumulative"]["clause"])
    records: List[CalculationRecord] = []
    states: Dict[int, str] = {}
    previous_state: Optional[str] = None
    origin_round: Optional[int] = None
    origin_trigger = BASIS_NONE

    for index in sorted(present):
        value = values[index]
        hits: List[str] = []
        rate_value: Optional[float] = None
        cum = controls.get(BASIS_CUM)
        if cum is not None and abs(value) >= cum["value"] - GE_EPS:
            hits.append(BASIS_CUM)
        rate = controls.get(BASIS_RATE)
        if rate is not None:
            rate_value = _max_window_slope(values, rounds, index, float(window_days))
            if rate_value is not None and rate_value >= rate["value"] - GE_EPS:
                hits.append(BASIS_RATE)

        prewarning_hit = False
        if prewarning_ratio is not None and cum is not None and not hits:
            prewarning_hit = abs(value) + GE_EPS >= float(prewarning_ratio) * cum["value"]

        trigger, base_state = _settle(hits, previous_state, prewarning_hit)
        state = base_state
        disposition = dispositions.get((code, item["code"], index))
        if disposition == "handle":
            if not (base_state in UNCLOSED or base_state == "alarm_handled"):
                raise ContractError(
                    "处置记录指向未报警的判定行：%s R%d %s（状态 %s）" % (code, index, item["code"], base_state)
                )
            state = "alarm_handled"
        elif disposition == "confirm":
            if not (base_state in UNCLOSED or base_state == "alarm_handled"):
                raise ContractError(
                    "处置记录指向未报警的判定行：%s R%d %s（状态 %s）" % (code, index, item["code"], base_state)
                )
            state = "alarm_confirmed"
        if previous_state is not None and not _can_transition(previous_state, base_state):
            #: 旧仓两段校验：先看「上一轮 -> 本轮基础状态」，再看「基础状态 -> 处置后状态」。
            #: 只比处置后状态会把 alarm_handled -> alarm(处置后仍 handled) 这类合法路径误判非法。
            raise ContractError(
                "非法状态迁移：%s R%d %s 轮次间 %s -> %s" % (code, index, item["code"], previous_state, base_state)
            )
        if state != base_state and not _can_transition(base_state, state):
            raise ContractError(
                "非法状态迁移：%s R%d %s 处置把 %s 改成了 %s" % (code, index, item["code"], base_state, state)
            )

        continuing = state in UNCLOSED and previous_state is not None and previous_state in UNCLOSED
        if state not in UNCLOSED:
            origin_round = None
            origin_trigger = BASIS_NONE
            carried = False
        elif continuing:
            carried = True
        else:
            origin_round = index
            origin_trigger = trigger
            carried = False
        row_trigger = trigger if trigger != BASIS_NONE else origin_trigger

        states[index] = state
        verdict = REJECTED if state in UNCLOSED else OK
        fell_back = (
            state in UNCLOSED
            and cum is not None
            and abs(value) < cum["value"] - GE_EPS
        )
        message = _message(state, value, cum, rate_value, rate, prewarning_hit)
        evidence = {
            "formula": "|value_cum| >= cum_limit；max_window_slope >= rate_limit；预警：|value_cum| >= ratio × cum_limit",
            "point": code,
            "item_code": item["code"],
            "round": index,
            "observed_on": rounds[index]["observed_on"],
            "state": state,
            "trigger_basis": row_trigger,
            "unclosed": state in UNCLOSED,
            "unclosed_carried": bool(carried),
            "first_alarm_round": origin_round,
            "fell_back": bool(fell_back),
            "value_cum": value,
            "cumulative": None
            if cum is None
            else {
                "limit": cum["value"],
                "unit": cum["unit"],
                "hit": BASIS_CUM in hits,
                "source": cum["kind"],
                "evidence": cum["evidence"],
            },
            "rate": None
            if rate is None
            else {
                "limit": rate["value"],
                "unit": rate["unit"],
                "actual": rate_value,
                "hit": BASIS_RATE in hits,
                "source": rate["kind"],
                "evidence": rate["evidence"],
                "window_days": float(window_days),
            },
            "prewarning_ratio": prewarning_ratio if prewarning_hit else None,
            "clause_ids": [ALARM_RULES["cumulative"]["clause"], ALARM_RULES["rate"]["clause"]],
        }
        records.append(_record("%s.%s@R%d" % (code, item["code"], index), verdict, message, clause, evidence))
        previous_state = state

    return records, states


def _message(state: str, value: float, cum: Optional[dict], rate_value: Optional[float],
             rate: Optional[dict], prewarning_hit: bool) -> str:
    parts = ["累计变化量 %s%s" % (_fmt(value), cum["unit"] if cum else "")]
    if cum is not None:
        parts.append("控制值 %s（%s）" % (_fmt(cum["value"]), "达" if abs(value) >= cum["value"] - GE_EPS else "未达"))
    if rate is not None and rate_value is not None:
        parts.append(
            "速率 %s%s/d（控制值 %s，%s）"
            % (_fmt(rate_value), rate["unit"].replace(RATE_UNIT_SUFFIX, ""), _fmt(rate["value"]),
               "达" if rate_value >= rate["value"] - GE_EPS else "未达")
        )
    label = {
        "normal": "正常",
        "prewarning": "预警",
        "alarm": "报警（未闭环）",
        "alarm_confirmed": "报警已确认（未闭环）",
        "alarm_handled": "报警已闭环",
    }.get(state, state)
    suffix = "；达预警比例" if prewarning_hit else ""
    return "%s：%s%s" % (label, "，".join(parts), suffix)


def _fmt(value: float) -> str:
    text = "%.4f" % float(value)
    return text.rstrip("0").rstrip(".") if "." in text else text


# ---------------------------------------------------------------------------
# 频率与时效检核（搬自 pmc/compliance/auditor.py）
# ---------------------------------------------------------------------------
def _interval_band(depth) -> Optional[dict]:
    """按开挖深度取间隔上限档：取最浅的「depth_max >= depth」，更深走兜底档。"""
    if depth is None:
        return next((band for band in BANDS if band["depth_max"] is None), None)
    depth = _number(depth, "rounds[].excavation_depth_m")
    candidates = [band for band in BANDS if band["depth_max"] is not None and band["depth_max"] >= depth]
    if candidates:
        return sorted(candidates, key=lambda band: band["depth_max"])[0]
    return next((band for band in BANDS if band["depth_max"] is None), None)


def _interval_limits(subject: Mapping) -> Dict[str, dict]:
    block = subject.get("frequency") or {}
    if not isinstance(block, Mapping):
        raise ValueError("frequency 必须是对象")
    raw = block.get("interval_limits") or []
    if not isinstance(raw, list):
        raise ValueError("frequency.interval_limits 必须是数组")
    known = {band["id"] for band in BANDS}
    out: Dict[str, dict] = {}
    for entry in raw:
        band_id = _text(_require(entry, "band", "frequency.interval_limits[]"), "interval_limits[].band")
        if band_id not in known:
            raise ValueError("未知的间隔档位：%r（已知 %s）" % (band_id, sorted(known)))
        if str(entry.get("status") or "") != "verified":
            raise ValueError(
                "%s 未核对来源：status=%r（%s）" % (band_id, entry.get("status"), REASON_NOT_VERIFIED)
            )
        if not entry.get("evidence"):
            raise ValueError("%s 缺出处凭证（%s）" % (band_id, REASON_EVIDENCE_MISSING))
        out[band_id] = {
            "max_interval_days": _number(
                _require(entry, "max_interval_days", "frequency.interval_limits[]"),
                "%s.max_interval_days" % band_id,
            ),
            "kind": _text(entry.get("kind") or "", "%s.kind" % band_id),
            "evidence": str(entry["evidence"]),
        }
    return out


def _enabled(key: str, flags: Optional[Sequence[str]]) -> bool:
    return flags is None or key in flags


def _active_on(point: Mapping, day: int) -> bool:
    """测点生效区间（可选 ``active_from`` / ``active_to``，闭区间，YYYY-MM-DD）。"""
    start = point.get("active_from")
    end = point.get("active_to")
    if start is not None and day < _day(start):
        return False
    if end is not None and day > _day(end):
        return False
    return True


def _frequency_records(
    subject: Mapping,
    rounds: Mapping[int, dict],
    points: Sequence[Mapping],
    observations: Mapping[str, Mapping[int, dict]],
    states: Mapping[str, Mapping[int, str]],
    basis,
) -> List[CalculationRecord]:
    block = subject.get("frequency")
    if block is None:
        return ()
    if not rounds:
        raise ValueError("启用 frequency 时必须给 rounds（排定轮次是频率检核的锚点）")
    flags = block.get("enabled") if isinstance(block, Mapping) else None
    if isinstance(flags, str) or (flags is not None and not isinstance(flags, list)):
        raise ValueError("frequency.enabled 必须是数组")
    limits = _interval_limits(subject)

    missed_clause = _clause_ref(basis, FREQ_RULES["missed"]["clause"])
    interval_clause = _clause_ref(basis, FREQ_RULES["interval"]["clause"])
    intensify_rule = FREQ_RULES["intensify-after-alarm"]
    intensify_clause = _clause_ref(basis, intensify_rule["clause"])

    scheduled = [rounds[index] for index in sorted(rounds) if rounds[index]["scheduled"]]
    out: List[CalculationRecord] = []

    # 1) 漏测：整轮一行都没入库只出一条工程级结论；否则逐测点比 missing 标记
    if _enabled("missed", flags):
        for round_row in scheduled:
            index = round_row["index"]
            active_points = [point for point in points if _active_on(point, round_row["day"])]
            gaps = []
            present = 0
            for point in active_points:
                code = point["_code"]
                observation = observations[code].get(index)
                if observation is None:
                    gaps.append({"point": code, "gap": GAP_NO_OBSERVATION})
                    continue
                present += 1
                if observation["missing"]:
                    gaps.append({"point": code, "gap": GAP_MARKED_MISSING})
            evidence = {
                "formula": "排定轮次缺少链上有效读数即漏测",
                "round": index,
                "observed_on": round_row["observed_on"],
                "points_expected": len(active_points),
                "rows_present": present,
            }
            if gaps and present == 0:
                evidence["gap"] = GAP_ROUND_NOT_IMPORTED
                out.append(_record(
                    "freq.missed@R%d" % index, REJECTED,
                    "R%d（%s）整轮无观测：应核实是没测还是没导入" % (index, round_row["observed_on"]),
                    missed_clause, evidence))
            elif gaps:
                evidence["gap"] = "point_level"
                evidence["missing_points"] = gaps
                out.append(_record(
                    "freq.missed@R%d" % index, REJECTED,
                    "R%d 有 %d 个测点缺测（应核实 %d 个）" % (index, len(gaps), len(active_points)),
                    missed_clause, evidence))
            else:
                out.append(_record(
                    "freq.missed@R%d" % index, OK,
                    "R%d 排定轮次 %d 个测点均有有效读数" % (index, len(active_points)),
                    missed_clause, evidence))

    # 2) 间隔：逐对相邻排定轮次，按后一轮生效工况的深度取上限档
    if _enabled("interval", flags):
        for previous, current in zip(scheduled, scheduled[1:]):
            gap_days = float(current["day"] - previous["day"])
            band = _interval_band(current["excavation_depth_m"])
            if band is None:  # pragma: no cover - 兜底档一定存在
                raise ValueError("no_applicable_interval_band")
            limit = limits.get(band["id"])
            if limit is None:
                raise ValueError(
                    "R%d 需要间隔上限但未给已核对值：%s（%s）"
                    % (current["index"], band["id"], REASON_VALUE_MISSING)
                )
            over = gap_days > limit["max_interval_days"]
            changed = (
                previous["condition_code"] is not None
                and current["condition_code"] is not None
                and previous["condition_code"] != current["condition_code"]
            )
            evidence = {
                "formula": "gap_days <= max_interval_days（按后一轮生效工况的开挖深度取档）",
                "from_round": previous["index"],
                "to_round": current["index"],
                "gap_days": gap_days,
                "band": band["id"],
                "depth_max": band["depth_max"],
                "excavation_depth_m": current["excavation_depth_m"],
                "max_interval_days": limit["max_interval_days"],
                "category": (CATEGORY_STALE_FREQUENCY if (over and changed) else CATEGORY_OVER_INTERVAL),
                "condition_changed": bool(changed),
                "source": limit["kind"],
                "evidence": limit["evidence"],
            }
            item_id = "freq.interval@R%d->R%d" % (previous["index"], current["index"])
            if over:
                label = "工况变更后仍按旧频率" if changed else "观测间隔超上限"
                out.append(_record(
                    item_id, REJECTED,
                    "%s：R%d→R%d 间隔 %s 天 > 上限 %s 天（%s）"
                    % (label, previous["index"], current["index"], _fmt(gap_days),
                       _fmt(limit["max_interval_days"]), band["id"]),
                    interval_clause, evidence))
            else:
                out.append(_record(
                    item_id, OK,
                    "R%d→R%d 间隔 %s 天 ≤ 上限 %s 天（%s）"
                    % (previous["index"], current["index"], _fmt(gap_days),
                       _fmt(limit["max_interval_days"]), band["id"]),
                    interval_clause, evidence))

    # 3) 报警后加密观测：上一轮存在未闭环报警时，本轮必须带加密标记
    if _enabled("intensify-after-alarm", flags):
        ordered = [rounds[index] for index in sorted(rounds)]
        for previous, current in zip(ordered, ordered[1:]):
            unclosed = sorted(
                {"%s.%s" % (point["_code"], point["_item"]) for point in points
                 if states.get(point["_code"], {}).get(previous["index"]) in UNCLOSED}
            )
            if not unclosed:
                continue
            evidence = {
                "formula": "上一轮存在未闭环报警 -> 本轮 intensified 必须为真",
                "round": current["index"],
                "previous_round": previous["index"],
                "unclosed_points": unclosed,
                "intensified": bool(current["intensified"]),
                "clause_ids": list(intensify_rule["clause_ids"]),
            }
            item_id = "freq.intensify@R%d" % current["index"]
            if current["intensified"]:
                out.append(_record(
                    item_id, OK,
                    "R%d 报警后已加密观测（未闭环 %d 处）" % (current["index"], len(unclosed)),
                    intensify_clause, evidence))
            else:
                out.append(_record(
                    item_id, REJECTED,
                    "R%d 上一轮有未闭环报警（%d 处）但未加密观测" % (current["index"], len(unclosed)),
                    intensify_clause, evidence))
    return out


# ---------------------------------------------------------------------------
# 器官入口
# ---------------------------------------------------------------------------
def evaluate(subject: Mapping, basis) -> Iterable[CalculationRecord]:
    """算出计算书：报警判定（每测点×项目×轮次）+ 频率时效（每轮/每对轮次）。"""
    if not isinstance(subject, Mapping):
        raise ValueError("subject 必须是 JSON 对象")
    project = _text(_require(subject, "project", "subject"), "subject.project")
    raw_points = _require(subject, "points", "subject")
    if not isinstance(raw_points, list) or not raw_points:
        raise ValueError("points 必须是非空数组")
    prewarning_ratio = subject.get("prewarning_ratio")
    if prewarning_ratio is not None:
        prewarning_ratio = _number(prewarning_ratio, "subject.prewarning_ratio")
        if not 0.0 < prewarning_ratio <= 1.0:
            raise ValueError("prewarning_ratio 必须在 (0, 1]：%r" % (prewarning_ratio,))
    window_days = subject.get("rate_window_days")
    if window_days is not None:
        window_days = _number(window_days, "subject.rate_window_days")
        if window_days <= 0:
            raise ValueError("rate_window_days 必须为正（%s）" % REASON_WINDOW_UNCONFIGURED)

    rounds = _rounds(subject)
    dispositions = _dispositions(subject)
    points: List[Mapping] = []
    observations: Dict[str, Dict[int, dict]] = {}
    records: List[CalculationRecord] = []
    states: Dict[str, Dict[int, str]] = {}

    seen = set()
    for raw in raw_points:
        if not isinstance(raw, Mapping):
            raise ValueError("points[] 必须是对象")
        code = _text(_require(raw, "code", "points[]"), "points[].code")
        item_code = _text(_require(raw, "item_code", "points[]"), "points[].item_code")
        item = _item(item_code, "测点 %s" % code)
        if (code, item_code) in seen:
            raise ValueError("测点重复：%s / %s" % (code, item_code))
        seen.add((code, item_code))
        point_records, point_states = _judge_point(
            raw, item, rounds, dispositions, window_days, prewarning_ratio, basis
        )
        records.extend(point_records)
        anchor = dict(raw)
        anchor["_code"] = code
        anchor["_item"] = item_code
        points.append(anchor)
        observations[code] = _observations(raw, "测点 %s（%s）" % (code, item_code))
        states[code] = point_states

    records.extend(
        _frequency_records(subject, rounds, points, observations, states, basis)
    )
    if not records:
        raise ValueError(
            "工程 %s 在给定输入上没有任何可判行：至少要有带有效读数的测点，或启用 frequency" % project
        )
    return tuple(records)


register(
    Pack(
        slug=SLUG,
        version=VERSION,
        summary="基坑监测数据判读：双控报警（累计/速率/预警比例）+ 频率时效检核",
        input_fields=("project", "points"),
        evaluate=evaluate,
    )
)

__all__ = ["SLUG", "VERSION", "evaluate", "ITEMS", "BANDS"]