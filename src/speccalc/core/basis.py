"""规范条文库：``code + clause + version`` 的唯一来源。

条文库按版本登记。器官只能通过 ``Basis.ref(code, clause)`` 取依据；取不到就是
``ClauseMissing``（条文库缺条款 -> 契约违约，退出码 3），**不许自己造条款**。

单条条款**必须带自己的版本**：basis_ref 要能回答「按哪一版规范算的」，
而同一本计算书会同时引多本规范（GB / JGJ / 地方标准），版本不能统一成一个。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from speccalc.core.ledger import ClauseRef, ContractError


class ClauseMissing(Exception):
    """条文库里没有这条条款。"""


@dataclass(frozen=True)
class Clause:
    """一条规范条款。三个定位字段必填（缺版本 = 依据不可复核）。"""

    code: str
    clause: str
    version: str
    text: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("code", self.code),
            ("clause", self.clause),
            ("version", self.version),
        ):
            if value is None or not str(value).strip():
                raise ContractError("条款字段为空：%s" % name)

    @property
    def key(self) -> tuple:
        return (self.code, self.clause)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "clause": self.clause,
            "version": self.version,
            "text": self.text,
        }


class Basis:
    """一个版本下的条文集合（= 规范包）。

    ``version`` 是条文库自身版本（不是单条规范版本）；单条条款带自己的规范版本，
    两者不必相同 —— 这一点与 clauseproof 的条文库相反（那里条款版本必须等于库版本）。
    """

    def __init__(self, version: str, clauses: Iterable[Clause] = ()) -> None:
        if not version or not str(version).strip():
            raise ContractError("条文库版本为空（依据包版本缺失）")
        self._version = version
        self._clauses: Dict[tuple, Clause] = {}
        for clause in clauses:
            if clause.key in self._clauses:
                raise ContractError("条款重复：%s %s" % (clause.code, clause.clause))
            self._clauses[clause.key] = clause

    # ------------------------------------------------------------------ 构造
    @classmethod
    def empty(cls, version: str = "0") -> "Basis":
        return cls(version=version, clauses=())

    @classmethod
    def from_dict(cls, data: dict) -> "Basis":
        version = data.get("version")
        raw = data.get("clauses", [])
        if not isinstance(raw, list):
            raise ContractError("clauses 必须是数组")
        clauses = [
            Clause(
                code=item.get("code", ""),
                clause=item.get("clause", ""),
                version=item.get("version", ""),
                text=item.get("text", ""),
            )
            for item in raw
        ]
        return cls(version=version, clauses=clauses)

    @classmethod
    def from_json(cls, path: str) -> "Basis":
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    # ------------------------------------------------------------------ 查询
    @property
    def version(self) -> str:
        return self._version

    def __len__(self) -> int:
        return len(self._clauses)

    def clause_keys(self) -> List[str]:
        return ["%s %s" % key for key in sorted(self._clauses)]

    def clause(self, code: str, clause: str) -> Optional[Clause]:
        return self._clauses.get((code, clause))

    def require(self, code: str, clause: str) -> Clause:
        found = self.clause(code, clause)
        if found is None:
            raise ClauseMissing("条文库 %s 无此条款：%s %s" % (self._version, code, clause))
        return found

    def ref(self, code: str, clause: str) -> ClauseRef:
        """给器官用的唯一取依据入口。"""
        found = self.require(code, clause)
        return ClauseRef(
            code=found.code,
            clause=found.clause,
            version=found.version,
            text=found.text,
        )

    def as_dict(self) -> dict:
        return {
            "version": self._version,
            "clauses": [self._clauses[key].as_dict() for key in sorted(self._clauses)],
        }