# speccalc · 内核契约（Stage 1）

> 本页是 `src/speccalc/` 的唯一说明处。契约字段、退出码、目录形状与
> `clauseproof` / `byteproof` / `traceproof` 共用一份 `SKELETON-SPEC`；本页只写
> **speccalc 自己的那一列**（计算书 + 规范条款）。

## 1. 这个产品回答什么

给定构件参数和一本（或多本）规范条文，**算一遍**并输出计算书：
每条结论 = 一个计算项 + 一条规范条款 + 算式与中间量。

它不做的事：不带自己的 CLI、不读时钟、不联网、不修改输入工件。
器官（module）只声明怎么算、拿哪条条款，不决定怎么打印。

## 2. 唯一入口

```text
speccalc list                          # 列出器官（slug / 版本 / 摘要）
speccalc check <slug> --input <file>   # 跑一个器官
speccalc check <slug> --input -        # stdin
speccalc --version
```

器官签名固定：

```python
evaluate(subject: Mapping, basis: Basis) -> Iterable[CalculationRecord]
```

- `subject`：输入 JSON 对象（器官在自己的 `input_fields` 里声明必填键）；
- `basis`：条文库（`Basis`），器官只能通过 `basis.ref(code, clause)` 取依据。

## 3. 计算书（本产品的 record 类型）

| 字段 | 含义 |
|---|---|
| `id` | 稳定键：`<item_id>@<code>:<clause>`（版本不进 id，改版本不改定位） |
| `verdict` | `ok` / `rejected` |
| `message` | 人读结论（含实算值与限值） |
| `basis_ref` | `{code, clause, version, text}` |
| `evidence` | 算式与中间量：`formula` / `input` / `actual` / `limit`…… |

`rejected` 是唯一阻断级；`ok` 只记录，但**同样必须有依据**。

## 4. 三条内核约束（违反即退出码 3）

1. **无依据不得入账**：`ok` 与 `rejected` 一样，`basis` 缺失即 `ContractError`
   ——计算书里「算合格了」本身就是结论，凭空的合格与不合格一样不可复核。
2. **条款三定位字段必填**：`code` / `clause` / `version` 缺一即 `ContractError`
   （缺版本的条款不是依据）。因此本产品**没有「降级」态**：缺版本的依据根本无法入账，
   比 §4.2 的降级更严。
3. **输出确定性**：`--json` 无时间戳、无绝对路径、字段顺序固定；同一输入两次运行字节一致。

## 5. 退出码

| 码 | 含义 | 本产品的触发点 |
|---|---|---|
| 0 | 无阻断性结论 | 全部 `ok` |
| 1 | 存在阻断性结论 | 至少一条 `rejected` |
| 2 | 输入不合法 | 输入文件缺失/非法 JSON/缺 `input_fields` 声明键 |
| 3 | 契约违约 | 无依据入账、条文库版本缺失、条款缺失（`ClauseMissing`）、器官不存在 |

## 6. 加一个器官

```text
src/speccalc/modules/<slug>/__init__.py   # register(Pack(slug=..., version=..., summary=...,
                                          #              input_fields=(...), evaluate=...))
src/speccalc/modules/__init__.py          # 把模块名加进 BUILTIN_MODULES（显式清单）
tests/test_<slug>.py                      # 该器官的无损测试
docs/<slug>.md                            # 输入 / 规则 / 算式 / 输出示例
```

**显式清单而不是扫描**：扫描式加载会把「器官忘了登记」变成静默空跑。

## 7. 过渡期布局（与 SKELETON-SPEC §8 对应）

| 项 | 现状 | 过渡安排 |
|---|---|---|
| 新包 | `src/speccalc/` | 本页所写的新内核 |
| 旧包 | `code/backend/app` | 原样保留，器官逐个迁出后再删 |
| 打包 | `pyproject.toml` 双根：`"" -> code/backend`、`"speccalc" -> src/speccalc` | setuptools 的 `get_package_dir` 按最长前缀回溯，子包解析正确（`pip wheel` 实测：`speccalc/` 下 15 个条目，其中 `data/` 4 个器官数据文件 `excavation-monitor.json` / `formwork-scaffold.json` / `pavement-mqi.json` / `steel-member.json`，解包后 `speccalc list` 能列出 4 个器官 = 数据确实来自包内） |
| `setup.py` | 仍在，`build_py` 钩子把运行期资产铺进 `app/_data/` | **保留一版过渡**；新器官的 `data/` 由 `package-data` 的 `speccalc = ["py.typed", "data/*.json"]` 收 |

## 8. 示例（已迁入 3 个器官）

```console
$ speccalc list
excavation-monitor           0.1.0      基坑监测数据判读：双控报警（累计/速率/预警比例）+ 频率时效检核
formwork-scaffold            0.1.0      脚手架与模板支架：JGJ 130/162 验算 + 危大分级 + 构造限值核查 + 两张皮一致性
pavement-mqi                 0.1.0      公路技术状况评定：PCI / 路况等级 / 养护对策 / 路线 MQI（JTG 5210-2018 口径）
steel-member                 0.1.0      钢结构验算：对接/角焊缝、普通/高强螺栓、轴压稳定与长细比（GB 50017-2017）

$ speccalc check no-such --input samples/basis.json
PackMissing: 未注册的器官：no-such          # 退出码 3

$ speccalc check excavation-monitor --input samples/excavation-monitor/zhdq.json \
        --basis samples/basis.json
… 合计 587 条，阻断 5 条（ok=582 rejected=5）   # 退出码 1
```

器官表按 `_workspace/target-map-20261125.tsv` 的 ③speccalc 行逐个补齐，每个器官一页
`docs/<slug>.md`（输入 / 规则 / 输出示例 / 与旧仓的差异）。当前已迁入：

| slug | 溯源 | 文档 |
|---|---|---|
| `excavation-monitor` | 迁自 target-map ③ 行 | [`excavation-monitor.md`](excavation-monitor.md) |
| `formwork-scaffold` | 迁自 target-map ③ 行 | [`formwork-scaffold.md`](formwork-scaffold.md) |
| `pavement-mqi` | 迁自 target-map ③ 行 | [`pavement-mqi.md`](pavement-mqi.md) |
| `steel-member` | 迁自 target-map ③ 行 | [`steel-member.md`](steel-member.md) |