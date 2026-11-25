"""入口面防回退门（轨AD · 2026-11-25）。

锁一件事：``[project.scripts]`` 只允许「产品入口 + 至多 1 个过渡旧入口」。
上限由 ``TRANSITION_UNTIL`` 决定：**截止日（含当日）前 ≤ 2，之后 = 1**。
无论哪个时期，``PRODUCT_ENTRY`` 必须在册。

截止日 = **2026-11-30**（用户 2026-11-25 裁决）。截止日次日起，本门要求只剩产品入口；
旧条目未删即红——这是**有意的截止压力**，不是恒红门：
删掉 ``construction-check = "app.cli:main"`` 后本门自动转绿（届时 `[project.scripts]` 只剩 1 条）。

口径与负控记录：``records/old-entry-retirement-20261125.md``（轨AD）。
负控在本文件末尾：合成「3 条入口」→ 红；合成「1 条」→ 绿；截止后「2 条」→ 红。
"""

from __future__ import annotations

import os
from datetime import date, timedelta

TRANSITION_UNTIL = "2026-11-30"
PRODUCT_ENTRY = "speccalc"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYPROJECT = os.path.join(ROOT, "pyproject.toml")


def parse_script_entries(text):
    """从 pyproject 文本里取出 ``[project.scripts]`` 的键名（保持声明顺序）。

    不依赖 tomllib：本仓 CI 有 Python 3.10 腿，而 tomllib 需要 3.11+。
    只认「裸键 = 值」的行，注释与其它小节一律跳过。
    """
    entries = []
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_section = line == "[project.scripts]"
            continue
        if not in_section or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip().strip('"').strip("'")
        if key:
            entries.append(key)
    return entries


def allowed_entries(today):
    """截止日（含当日）前 2，之后 1。"""
    return 2 if today <= date.fromisoformat(TRANSITION_UNTIL) else 1


def check_entries(entries, today):
    """返回违规说明列表；空列表 = 通过。"""
    problems = []
    allowed = allowed_entries(today)
    if not entries:
        problems.append("入口数为 0：产品必须至少有一个可执行入口")
    elif PRODUCT_ENTRY not in entries:
        problems.append("缺少产品入口 %r（现有 %r）" % (PRODUCT_ENTRY, entries))
    if len(entries) > allowed:
        problems.append(
            "入口数 %d > 上限 %d（截止日 %s；现有 %r）"
            % (len(entries), allowed, TRANSITION_UNTIL, entries)
        )
    return problems


def gate_report(pyproject_path, today):
    """对一个 pyproject 文件跑门。返回违规说明列表（空 = 绿）。"""
    with open(pyproject_path, encoding="utf-8") as handle:
        return check_entries(parse_script_entries(handle.read()), today)


# ---------------------------------------------------------------- 实况断言


def test_live_pyproject_passes_gate():
    assert gate_report(PYPROJECT, date.today()) == []


def test_live_pyproject_declares_product_entry():
    with open(PYPROJECT, encoding="utf-8") as handle:
        entries = parse_script_entries(handle.read())
    assert PRODUCT_ENTRY in entries, entries


# ---------------------------------------------------------------- 门的负控


def test_negative_control_three_entries_is_red():
    text = (
        "[project]\nname = 'x'\n\n"
        "[project.scripts]\n"
        'a = "a.cli:main"\n'
        'b = "b.cli:main"\n'
        'c = "c.cli:main"\n'
    )
    entries = parse_script_entries(text)
    assert entries == ["a", "b", "c"], entries
    assert check_entries(entries, date(2026, 11, 25)) != []


def test_negative_control_single_product_entry_is_green():
    text = '[project.scripts]\n%s = "speccalc.cli:main"\n' % PRODUCT_ENTRY
    assert check_entries(parse_script_entries(text), date(2026, 11, 25)) == []


def test_deadline_bites_after_transition_until():
    two = [PRODUCT_ENTRY, "construction-check"]
    on_deadline = date.fromisoformat(TRANSITION_UNTIL)
    assert check_entries(two, on_deadline) == []
    assert check_entries(two, on_deadline + timedelta(days=1)) != []
    assert check_entries([PRODUCT_ENTRY], on_deadline + timedelta(days=1)) == []


def test_empty_section_is_red():
    assert check_entries([], date(2026, 11, 25)) != []