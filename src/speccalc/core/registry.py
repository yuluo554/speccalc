"""器官注册表：一个器官（module）= 一份声明，不是一个小框架。

器官只允许声明四件事：slug、版本、摘要、输入字段，外加一个 ``evaluate`` 函数。
slug 全局唯一；重复注册默认报错（防两个器官抢同一入口）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence, Tuple

from speccalc.core.basis import Basis
from speccalc.core.ledger import CalculationRecord

SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
ENTRY_POINT_GROUP = "speccalc.modules"


class PackMissing(Exception):
    """注册表里没有这个器官。"""


@dataclass(frozen=True)
class Pack:
    """一个校核器官。"""

    slug: str
    version: str
    summary: str
    input_fields: Tuple[str, ...]
    evaluate: Callable[[Mapping, Basis], Iterable[CalculationRecord]]

    def __post_init__(self) -> None:
        if not SLUG_PATTERN.match(self.slug or ""):
            raise ValueError("器官 slug 非法（要求 ^[a-z][a-z0-9-]*$）：%r" % (self.slug,))
        for name, value in (("version", self.version), ("summary", self.summary)):
            if not value or not str(value).strip():
                raise ValueError("器官字段为空：%s" % name)
        if not self.input_fields:
            raise ValueError("器官 %s 未声明输入字段" % self.slug)
        if not callable(self.evaluate):
            raise ValueError("器官 %s 的 evaluate 不可调用" % self.slug)

    def as_dict(self) -> dict:
        return {
            "slug": self.slug,
            "version": self.version,
            "summary": self.summary,
            "input_fields": list(self.input_fields),
        }


_REGISTRY: dict = {}


def register(pack: Pack, replace: bool = False) -> Pack:
    """注册一个器官；重复注册默认报错。"""
    if not isinstance(pack, Pack):
        raise ValueError("register 只接受 Pack 实例")
    if pack.slug in _REGISTRY and not replace:
        raise ValueError("器官重复注册：%s" % pack.slug)
    _REGISTRY[pack.slug] = pack
    return pack


def get(slug: str) -> Pack:
    try:
        return _REGISTRY[slug]
    except KeyError:
        raise PackMissing("未注册的器官：%s" % slug)


def all_packs() -> Sequence[Pack]:
    """按 slug 排序返回全部器官（顺序确定，输出可复现）。"""
    return tuple(_REGISTRY[slug] for slug in sorted(_REGISTRY))


def load_entry_points(group: str = ENTRY_POINT_GROUP) -> Sequence[Pack]:
    """从 entry points 加载外部器官（供 pip 安装的器官包使用）。"""
    from importlib.metadata import entry_points

    try:
        entries = entry_points(group=group)
    except TypeError:  # 9.x 早期实现不接受 group 关键字
        entries = entry_points().get(group, [])
    loaded = []
    for entry in entries:
        pack = entry.load()()
        loaded.append(register(pack))
    return tuple(loaded)