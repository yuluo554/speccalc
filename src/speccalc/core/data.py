"""包内数据装载：器官的规则/条款表随包分发，读取只走 ``importlib.resources``。

为什么单独一个模块：器官被禁止读文件（``ORGAN-PLAYBOOK`` §2）。这条禁令针对的是
**输入工件**（用户给的 JSON / DXF / CSV）——器官不得自己打开路径、不得猜目录、不得读
环境变量定位数据。但器官的**判据表**（监测项目字典、条款锚点、状态迁移表）必须有个
落盘处，且要能经 ``package-data`` 打进 wheel（§7.3 判据 4）。

折中办法就是这里：只有内核能碰包数据，且只碰 ``speccalc/data/`` 下**随包分发**的名字
——不接受绝对路径、不接受 ``..``、不读环境变量、不缓存到磁盘。器官在 import 时调用一次，
拿到的是不可变副本，判定过程里不再有任何 I/O。

确定性：``load`` 的返回值按 JSON 解析顺序构造；同名文件只读一次（进程内缓存），
因此同一进程内多次运行字节一致。
"""

from __future__ import annotations

import copy
import json
from importlib import resources
from typing import Any, Dict

#: 包内数据目录名（与 ``pyproject.toml`` 的 ``speccalc = ["data/*.json"]`` 对应）
DATA_ROOT = "data"

_CACHE: Dict[str, Any] = {}


class DataMissing(Exception):
    """包内数据文件不存在（打包漏了 ``data/`` 就是这一类）。"""


def _guard(name: str) -> str:
    """只接受 ``xxx.json`` 形态的包内名字，挡住路径穿越与绝对路径。"""
    if not name or name != name.strip():
        raise ValueError("包内数据名非法：%r" % (name,))
    if name.startswith(("/", "\\")) or ":" in name or ".." in name:
        raise ValueError("包内数据名非法（不接受路径）：%r" % (name,))
    if "/" in name or "\\" in name:
        raise ValueError("包内数据名非法（不接受子目录）：%r" % (name,))
    if not name.endswith(".json"):
        raise ValueError("包内数据名必须是 .json：%r" % (name,))
    return name


def load(name: str) -> Dict[str, Any]:
    """读 ``speccalc/data/<name>``，返回每次独立的副本（防器官之间互相改写）。"""
    key = _guard(name)
    if key not in _CACHE:
        try:
            target = resources.files("speccalc").joinpath(DATA_ROOT, key)
            text = target.read_text(encoding="utf-8")
        except (FileNotFoundError, ModuleNotFoundError) as exc:  # pragma: no cover - 打包缺陷
            raise DataMissing("包内数据缺失：%s（检查 package-data）" % key) from exc
        _CACHE[key] = json.loads(text)
    return copy.deepcopy(_CACHE[key])


def cached_names() -> list:
    """已装载过的包内数据名（供测试确认「同一进程只读一次」）。"""
    return sorted(_CACHE)