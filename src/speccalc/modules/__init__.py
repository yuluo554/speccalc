"""器官目录：每个器官一个子包 ``<slug>/``，导入时向注册表登记自己的 ``Pack``。

**显式清单，不用 pkgutil 扫描**：扫描式加载会把「某个器官忘了登记」变成静默空跑，
而显式清单在导入失败时立刻红。当前清单：``excavation-monitor`` / ``pavement-mqi`` /
``steel-member``（三个器官均迁自 target-map ③ 行）。

新增器官的三步（SKELETON-SPEC §1/§2）：

1. 在 ``speccalc/modules/<slug>/__init__.py`` 里 ``register(Pack(...))``；
2. 把模块名加进下面的 ``BUILTIN_MODULES``（字典序）；
3. 补 ``tests/test_<slug>.py`` 与 ``docs/<slug>.md``（输入 / 规则 / 输出示例）。
"""

from __future__ import annotations

import importlib
from typing import Tuple

#: 已迁入的内置器官模块名（相对 ``speccalc.modules``）。按 slug 字典序维护。
BUILTIN_MODULES: Tuple[str, ...] = (
    "excavation-monitor",
    "pavement-mqi",
    "steel-member",
)


def load_builtin() -> None:
    """导入全部内置器官模块（每个模块在 import 时登记自己的 Pack）。"""
    for name in BUILTIN_MODULES:
        importlib.import_module("speccalc.modules." + name)