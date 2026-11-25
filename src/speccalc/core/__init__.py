"""speccalc 内核：计算书 + 条文库 + 器官注册表。

三条内核约束（违反即 ``ContractError``，进程退出码 3）：
1. 无规范条款依据不得入账（``ok`` / ``rejected`` 都一样）；
2. 器官不带自己的 CLI / 配置文件 / 输出排版；
3. 输出确定性：无时间戳、无绝对路径、字段顺序固定。
"""

from speccalc.core.basis import Basis, Clause, ClauseMissing
from speccalc.core.ledger import (
    BLOCKING_VERDICTS,
    EXIT_BLOCKED,
    EXIT_CONTRACT,
    EXIT_INPUT,
    EXIT_OK,
    OK,
    REJECTED,
    VERDICTS,
    CalculationRecord,
    ClauseRef,
    ContractError,
    Report,
)
from speccalc.core.registry import Pack, PackMissing, all_packs, get, load_entry_points, register

__all__ = [
    "Basis",
    "Clause",
    "ClauseMissing",
    "ClauseRef",
    "CalculationRecord",
    "Report",
    "ContractError",
    "Pack",
    "PackMissing",
    "register",
    "get",
    "all_packs",
    "load_entry_points",
    "OK",
    "REJECTED",
    "VERDICTS",
    "BLOCKING_VERDICTS",
    "EXIT_OK",
    "EXIT_BLOCKED",
    "EXIT_INPUT",
    "EXIT_CONTRACT",
]