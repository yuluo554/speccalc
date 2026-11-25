"""计算书：speccalc 的唯一输出模型（契约见 SKELETON-SPEC §3–§6）。

一条计算书行 = 一个计算项 + 一条规范条款依据。

本产品的口径比另外三个更严：**任何一条结论都必须挂依据**（``ok`` 也一样）。
理由：计算书里「算合格了」本身就是结论，凭空的合格和不合格一样不可复核。
所以 ``basis`` 缺失不是「降级」，而是 ``ContractError``（退出码 3）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

OK = "ok"
REJECTED = "rejected"
VERDICTS = (OK, REJECTED)
#: 会阻断的结论（`ok` 只记录、不阻断）
BLOCKING_VERDICTS = (REJECTED,)

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INPUT = 2
EXIT_CONTRACT = 3


class ContractError(Exception):
    """契约违约：无依据下结论、条款字段为空、结论取值非法。"""


@dataclass(frozen=True)
class ClauseRef:
    """规范条款引用：``code`` + ``clause`` + ``version``（SKELETON-SPEC §3）。

    三个字段都必填：**缺版本的条款不是依据**，算出来的结论不可复核。
    """

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
                raise ContractError("条款引用字段为空：%s" % name)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "clause": self.clause,
            "version": self.version,
            "text": self.text,
        }


@dataclass(frozen=True)
class CalculationRecord:
    """一条计算结论。

    ``item_id`` 是计算项（如 ``cover`` / ``crack-width``），与条款一起派生稳定的 ``id``；
    ``evidence`` 放算式与中间量（应机器可读：输入值、公式、限值、实算值）。
    """

    item_id: str
    verdict: str
    message: str
    basis: Optional[ClauseRef] = None
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id or not str(self.item_id).strip():
            raise ContractError("计算项 id 为空")
        if self.verdict not in VERDICTS:
            raise ContractError("非法结论：%s（允许 %s）" % (self.verdict, VERDICTS))
        if self.basis is None:
            raise ContractError("无规范条款依据不得入账（item=%s）" % (self.item_id,))

    @property
    def id(self) -> str:
        """稳定 id：由计算项 + 条款派生（同一算式重复跑得到同一个 id）。"""
        assert self.basis is not None  # __post_init__ 已保证
        return "%s@%s:%s" % (self.item_id, self.basis.code, self.basis.clause)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "item_id": self.item_id,
            "verdict": self.verdict,
            "message": self.message,
            "basis_ref": self.basis.as_dict() if self.basis is not None else None,
            "evidence": dict(self.evidence),
        }

    def as_line(self) -> str:
        where = (
            "%s %s（%s）"
            % (self.basis.code, self.basis.clause, self.basis.version)
            if self.basis is not None
            else "无依据"
        )
        return "[%s] %s — %s :: %s" % (self.verdict, self.item_id, self.message, where)


@dataclass(frozen=True)
class Report:
    """一次校核运行的完整计算书。"""

    product: str
    organ: str
    organ_version: str
    subject: str
    records: Tuple[CalculationRecord, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("product", self.product),
            ("organ", self.organ),
            ("organ_version", self.organ_version),
            ("subject", self.subject),
        ):
            if not value or not str(value).strip():
                raise ContractError("计算书表头字段为空：%s" % name)
        records = tuple(self.records)
        dup = _duplicate_ids(records)
        if dup:
            raise ContractError("计算书 id 冲突（同一计算项命中同一条款两次）：%s" % sorted(dup))
        object.__setattr__(self, "records", tuple(sorted(records, key=_sort_key)))

    def blocking(self) -> Tuple[CalculationRecord, ...]:
        return tuple(r for r in self.records if r.verdict in BLOCKING_VERDICTS)

    def summary(self) -> dict:
        counts = {verdict: 0 for verdict in VERDICTS}
        for record in self.records:
            counts[record.verdict] += 1
        return {"blocking": len(self.blocking()), "total": len(self.records), "verdicts": counts}

    def exit_code(self) -> int:
        return EXIT_BLOCKED if self.blocking() else EXIT_OK

    def as_dict(self) -> dict:
        return {
            "product": self.product,
            "organ": self.organ,
            "organ_version": self.organ_version,
            "subject": self.subject,
            "summary": self.summary(),
            "records": [record.as_dict() for record in self.records],
        }

    def as_lines(self) -> list:
        lines = ["%s :: %s %s :: %s" % (self.product, self.organ, self.organ_version, self.subject)]
        lines.extend(record.as_line() for record in self.records)
        summary = self.summary()
        lines.append(
            "合计 %d 条，阻断 %d 条（ok=%d rejected=%d）"
            % (
                summary["total"],
                summary["blocking"],
                summary["verdicts"][OK],
                summary["verdicts"][REJECTED],
            )
        )
        return lines


def _sort_key(record: CalculationRecord):
    basis = record.basis
    return (
        record.item_id,
        record.verdict,
        basis.code if basis is not None else "",
        basis.clause if basis is not None else "",
        record.message,
    )


def _duplicate_ids(records: Tuple[CalculationRecord, ...]):
    seen, dup = set(), set()
    for record in records:
        if record.id in seen:
            dup.add(record.id)
        seen.add(record.id)
    return dup