# 器官 · excavation-monitor（基坑监测数据判读）

> 溯源：迁自 target-map ③ 行（模块 2 报警判定 + 模块 3 频率时效检核）
> 迁入版本：`0.1.0` · 迁入日 2026-11-25 · 判据表放 `src/speccalc/data/excavation-monitor.json`

## 1. 它算什么

给定**一个工程的逐轮监测数据**和**一本条文库**，算出两件事：

1. **双控报警判定**：每个（测点 × 监测项目 × 轮次）处在哪个状态，靠哪条判据得出，
   累计量与速率的实算值各自离控制值多远；
2. **频率与时效检核**：排定轮次有没有漏测、相邻轮次间隔有没有超上限、工况变更后有没有
   仍按旧频率、报警后有没有加密观测。

它不算的：监测数据解析（CSV/XLSX 入库是旧仓模块 1，属输入侧，本器官只吃已结构化的
subject）、台账落库、报表与界面。这些在 `ORGAN-PLAYBOOK` §2 里明确不许器官自带。

```console
speccalc list
speccalc check excavation-monitor --input samples/excavation-monitor/zhdq.json \
        --basis samples/basis.json
```

## 2. 输入（subject）

`input_fields = ("project", "points")`。其余字段可选，但启用对应判据时必填。

| 字段 | 必填 | 含义 |
|---|---|---|
| `project` | ✔ | 工程编码（只进 evidence 与报错，不参与计算） |
| `points[]` | ✔ | 测点数组；每项见下 |
| `rounds[]` | 有观测时必填 | 排定轮次：`index` / `observed_on`（`YYYY-MM-DD`）/ 可选 `scheduled` / `intensified` / `excavation_depth_m` / `condition_code` |
| `prewarning_ratio` | 可选 | 预警比例（(0,1]）。不给就不判预警，状态只会是 `normal` / `alarm` |
| `rate_window_days` | 有速率控制值时必填 | 速率窗口天数（>0） |
| `dispositions[]` | 可选 | 处置记录：`point` / `item` / `round` / `kind ∈ {handle, confirm}` |
| `frequency` | 可选 | 启用频率检核：`interval_limits[]` + 可选 `enabled[]` |

`points[]` 一项：

```json
{
  "code": "SYN-TH-18",
  "item_code": "top_h_disp",
  "control": {
    "cumulative": {"kind": "design_value", "status": "verified",
                   "value": 25.0, "unit": "mm", "evidence": "设计文件 SYN-JK-2026-0001"},
    "rate":       {"kind": "design_value", "status": "verified",
                   "value": 1.5, "unit": "mm/d", "evidence": "设计文件 SYN-JK-2026-0001"}
  },
  "observations": [
    {"round": 9,  "value": 26.1},
    {"round": 11, "value": 27.4},
    {"round": 12, "value": 27.9, "missing": false}
  ],
  "active_from": "2026-01-01"
}
```

- `item_code` 必须在字典里（14 项，见 `data/excavation-monitor.json`）：字典决定**单位和判据适用范围**
  （`control_kind = dual` 判累计+速率，`cumulative` 只判累计）。
- `observations[].value` 是**累计变化量**（旧仓 `observation.value_cum`），不是本次读数。
- `control.<basis>` **整块缺省** = 该判据未登记 → 该判据不参与判定（旧仓「还没轮到第二档」）。
  登记了但 `kind` / `status` / `value` / `unit` / `evidence` 不全，或单位不对 → **拒绝计算**（退出码 2）。

### 控制值只认已核对来源

| 检查 | 不满足时 |
|---|---|
| `kind ∈ {design_value, standard_value, user_input}` | `ValueError`（`no_source`） |
| `status == "verified"` | `ValueError`（`source_not_confirmed`） |
| `value` 是有限数 | `ValueError`（`value_missing`） |
| `unit` 非空，且累计量 = 字典单位、速率 = 字典单位 + `/d` | `ValueError`（`unit_missing` / `unit_inconsistent`） |
| `evidence` 非空 | `ValueError`（`evidence_missing`） |

> 旧仓在同样情形下输出「待定值（undetermined）」并落 `退出码 1`。本产品**没有降级态**
> （`docs/speccalc.md` §4），所以改成**拒绝计算（退出码 2）**：宁可不出结论，
> 也不把「没核对」渲染成合格。

## 3. 规则

### 3.1 双控报警（旧 `pmc/alarm/engine.py`）

| 判据 | 算式 | 触发条件 |
|---|---|---|
| 累计量 | `abs(value_cum) >= cum_limit - eps` | 达到控制值即报警（含等号） |
| 速率 | `max_window_slope >= rate_limit - eps` | 窗口内**到本轮**的最大斜率 |
| 预警 | `abs(value_cum) + eps >= ratio × cum_limit` | 未达报警值才算预警 |

- `eps = 1e-9`（旧仓 `GE_EPS`）：落盘值与阈值都是小数级，浮点尾差不得改变结论。
- 速率窗口：`gap_days = round[i] - round[j]`，只取 `0 < gap_days <= window_days` 的更早轮次；
  窗口内没有可用先前读数 → 该轮速率判据无实算值（不是 0，不参与触发）。
- 触发判据：命中一条记 `cumulative` / `rate`，两条都命中记 `both`。

### 3.2 状态机（旧 `pmc/contract/status.py`）

```
normal        ─┬─> prewarning ─┬─> alarm ─┬─> alarm_confirmed ─┐
               │               │          └─> alarm_handled ───┴─> normal …
               └───────────────┴──────────────┘
```

| 状态 | 含义 | 本产品 verdict |
|---|---|---|
| `normal` | 未达任何控制线 | `ok` |
| `prewarning` | 达预警比例、未达报警值 | `ok` |
| `alarm` | 达控制值、未闭环 | **`rejected`** |
| `alarm_confirmed` | 已确认、未闭环 | **`rejected`** |
| `alarm_handled` | 已处置（闭环） | `ok` |

- **未闭环粘性**：`alarm` / `alarm_confirmed` 的后继里没有 `normal`。数值回落不消警，
  回落事实写在 `evidence.fell_back`，延续写在 `evidence.unclosed_carried`，
  首报轮次写在 `evidence.first_alarm_round`（延续期间不往后推）。
- 非法迁移（含处置把 `normal` 改成已确认）→ `ContractError`（退出码 3）。
- 缺测轮次（`missing=true` 或 `value=null`）**不出行**，状态机跳过它（旧仓同口径）。

### 3.3 频率与时效（旧 `pmc/compliance/auditor.py`）

| 规则 | 粒度 | 判据 |
|---|---|---|
| `missed` | 每排定轮次 | 该轮该测点链上无有效读数即漏测；**整轮一行都没有**只出一条工程级结论（`gap=round_not_imported`），不逐测点刷屏 |
| `interval` | 每对相邻轮次 | `gap_days <= max_interval_days`；上限按**后一轮**的开挖深度取档（≤5 m / ≤10 m / 兜底） |
| `intensify-after-alarm` | 每轮次 | 上一轮存在未闭环报警 → 本轮 `intensified` 必须为真 |

- 工况变更（`condition_code` 变了）且间隔仍超限 → `evidence.category = "stale_frequency"`，
  否则 `over_interval`。**同一次间隔只归一个类别**（旧仓原话：「不重复计数」），
  因此旧仓 `FREQ-CONDITION-CHANGE` 与 `FREQ-MAX-INTERVAL-*` 在账本上合成一条记录。
- 间隔上限是**标准值**：本器官不带任何数值，必须由 subject 的 `frequency.interval_limits[]`
  以 `status=verified` + `evidence` 给出；缺档、缺值、`status != verified` → 拒绝计算。
- `frequency.enabled` 缺省 = 四条全开。

## 4. 输出（计算书）

一条记录 = 一个（测点 × 项目 × 轮次）的报警状态，或一条频率/时效结论。

```json
{
  "id": "SYN-TH-18.top_h_disp@R11@GB 50497-2019:alarm-values",
  "item_id": "SYN-TH-18.top_h_disp@R11",
  "verdict": "rejected",
  "message": "报警（未闭环）：累计变化量 30mm，控制值 25（达），速率 1.6mm/d（控制值 1.5，达）",
  "basis_ref": {"code": "GB 50497-2019", "clause": "alarm-values", "version": "2019", "text": "…"},
  "evidence": {
    "state": "alarm", "trigger_basis": "both", "unclosed": true,
    "first_alarm_round": 9, "fell_back": false,
    "cumulative": {"limit": 25.0, "unit": "mm", "hit": true,
                   "source": "user_input", "evidence": "FIXTURE-GRADE:…"},
    "rate": {"limit": 1.5, "unit": "mm/d", "actual": 1.6, "hit": true, "window_days": 5.0},
    "clause_ids": ["alarm-values", "alarm-values"]
  }
}
```

频率记录的 `item_id` 形如 `freq.missed@R11` / `freq.interval@R9->R11` / `freq.intensify@R12`。

### 依据口径（重要）

`clause` 字段取旧仓 `data/clauses/register.json` 的**登记键**（`alarm-values`、
`monitoring-frequency`、`MOHURD-37`），**不是条号**。原因：旧仓 5 条登记项的
`clause_no` 全为 `null` —— GB 50497-2019 没有官方可直连的条文原文页，条号未经逐字核对，
旧仓的纪律是「不凭记忆填写」。本器官沿用它：不复述不存在的条号，条文库给出该键对应的
`version` 与 `text`，`code + clause + version` 三定位字段照样填得满。

> 这条是**跨产品口径问题**，已写进交付报告的「未解问题」：若要求真实条号，
> 需先取得官方原文并核对，否则这三个器官都无法给出条号级依据。

## 5. 与旧仓的差异（逐条，均为「本产品更严」）

| 旧行为 | 本产品 | 原因 |
|---|---|---|
| 阈值未核对 → `undetermined` + 退出码 1 | 拒绝计算 + 退出码 2 | 本产品无降级态（`docs/speccalc.md` §4） |
| 一条判定行可带多条 `clause_ids` | 一条记录挂一条主依据，全量键写 `evidence.clause_ids` | 账本字段 `basis_ref` 是单条引用 |
| `prewarning` 规则无条款 | 并入报警值条款的记录，比例值与出处写 evidence | `ok` 也必须挂依据 |
| 点生效区间来自 DB 的 `point.active_from/to` | subject 的 `active_from` / `active_to` | 无 DB 层 |
| 工况档案另有 `working_condition` 表 | `rounds[].condition_code` + `excavation_depth_m` | 同上，压平到轮次 |

## 6. 测试与判据

`tests/test_excavation_monitor.py`（103 条：语义与契约 + 旧仓对账）+
`tests/test_excavation_monitor_matrix.py`（219 条：字典 14 项 × 判据 × 两态、状态迁移表、
间隔三档 × 四条规则、原因码、包数据不变量）。合计 **322 个 `def test_`**。

其中 `test_sample_*` 是**旧仓对账**：输入 `samples/excavation-monitor/zhdq.json` 由旧仓自身命令链
（`pmc init` → `pmc synth --db` → `pmc import` R09/R11/R12）建出的台账导出，控制值取旧仓
`tests/fixtures/point_grades.json` 的夹具档位（`kind=user_input`，`evidence` 前缀
`FIXTURE-GRADE`，明确写「非设计文件值、非规范条文值」）。对账结果：

| 项 | 旧仓 `pmc check --round 11` | 本器官同数据 |
|---|---|---|
| 判定行数 | 196 | 196 |
| `normal` / `ok` | 194 | 194 |
| `alarm` / `rejected` | 2（`SYN-TH-03`、`SYN-TH-18`，均 `top_h_disp`） | 2（同两点） |
| `SYN-TH-18` 首报轮次 | R9 | R9 |
| `SYN-TH-03` 首报轮次 | R11 | R11 |
| 退出码 | 1 | 1 |

`samples/` 里的输入是**夹具档位**，只证明判定通路与旧引擎逐行一致，不构成任何规范依据。

## 7. 判据 1 的分母与脚手架测试处置表

`ORGAN-PLAYBOOK` §3.0：判据 1 的分母 = 旧仓 `tests/` 中**文件名**不匹配
`cli|gui|packaging|audit|desensit|guard|bench|infra|export|version|license|generat|docs?_|health|release|selftest|smoke`
的文件实跑用例数。

| 项 | 值 |
|---|---|
| 旧仓判定层文件 | **24** 个（静态 268 个 `def test_`） |
| 旧仓判定层实跑 | **315 passed**（`.venv/Scripts/python.exe -m pytest <24 个文件> -q`） |
| 本器官实跑 | **322 passed**（两个测试文件） |
| 差值 | **+7** |

### 被剔除的 12 个脚手架测试文件（逐项处置）

| 旧仓文件 | 静态 | 处置 | 接管方 / 舍弃理由 |
|---|---:|---|---|
| `test_cli_m1.py` | 13 | 舍弃 | 器官不得自带 CLI（`ORGAN-PLAYBOOK` §2）。CLI 面由产品唯一入口 `speccalc` 接管，本仓 `tests/test_speccalc_contract.py` 已有 `list` / `check` / `--json` / 退出码的契约测试 |
| `test_cli_m2.py` | 8 | 舍弃 | 同上；其中「判定结果打印格式」属于输出排版，按契约由内核 `Report.as_lines()` 统一，不允许器官自定义 |
| `test_cli_m3.py` | 16 | 舍弃 | 同上；其中「两站对照锁结论方向」是 CLI 编排级夹具，等价的判定差异已由本器官的 `test_multi_point_isolation_of_states` / `test_multi_point_alarm_does_not_leak_across_items` 覆盖 |
| `test_cli_surface.py` | 13 | 舍弃 | 同上；命令面清单（`selfcheck/init/dict/rulesets/synth/import/ledger/check/audit/bench/report/gui`）在新产品里收缩为 `list` / `check` 两条，逐条对账见 `docs/speccalc.md` §2 |
| `test_compliance_auditor.py` | 22 | **接管** | 文件名含 `audit` 被规则剔除，但内容是模块 3 的判定语义 → 已迁入：`missed` / `interval` / `condition-change` / `intensify-after-alarm` 四类规则 + 深度分档，见本页 §3.3 与矩阵文件 H 段 |
| `test_eol_guard.py` | 4 | 舍弃 | 行尾/文本守卫属于仓库级门（`.gitattributes` + CI），器官不碰文件系统，本仓的 EOL 门在 `.github/workflows/ci.yml` |
| `test_m4_bench.py` | 21 | 舍弃 | 基准评测是产品级指标门（golden 位级对账），器官无 golden 目录、无报告通道；等价能力只剩「同一输入两次运行字节一致」，由 `test_sample_json_is_byte_identical_across_runs` 守 |
| `test_m5_gui.py` | 11 | 舍弃 | org 不允许带界面（§2）。旧仓 PySide6 五页签在新产品里没有对应物 |
| `test_m5_packaging.py` | 11 | 舍弃 | 打包门由产品仓接管：`code/backend/tests/test_packaging.py`（真构建 wheel + 临时 venv + 仓库外验证资产）+ 本页 §8 的判据 4 |
| `test_m6_desensitize.py` | 9 | 舍弃 | 脱敏是 traceproof 的执行约束（`SKELETON-SPEC` §4.4），speccalc 不产会话正文；旧仓的「报告里不得出现个人标记」随报告模块一并舍弃 |
| `test_packaging.py` | 11 | 舍弃 | 同 `test_m5_packaging.py`：产品级 `pip wheel` 门接管 |
| `test_synth_generator.py` | 22 | 舍弃 | 合成数据生成器会写盘（器官不读文件、器官不写文件，§2）。等价物是冻结的 `samples/excavation-monitor/zhdq.json`，其内容由旧仓生成器产出后一次性入仓 |

> 注：`test_ci_workflow.py`（9）、`test_layering.py`（3）、`test_readme_honesty.py`（7）、
> `test_self_reported_counts.py`（5）、`test_ignore_scan_sync.py`（7）等按**文件名**未命中剔除
> 正则，因此计入判定层分母；但它们同样是产品级门（CI / 分层 / README 计数），移植到器官内
> 无意义。本器官把分母补到 322（>315）覆盖的是**判定语义**，这 31 条不计入新器官的实现，
> 由产品仓自己的门接管（README 自述门、`.github/workflows/ci.yml`、`tests/test_speccalc_contract.py`）。

## 8. 判据 4（`pip wheel` 后 `data/` 进包，实测）

2026-11-25 三器官全部迁入后重测（wheel 0.1.1，`--no-deps --no-build-isolation`）：

```console
$ python -m pip wheel . --no-deps --no-build-isolation -w /tmp/speccalc-wheel
Successfully built construction-drawing-plan-checker
$ python -c "import zipfile; …"
speccalc entries: 15        ← 器官 1 迁入时为 11
   speccalc/__init__.py   speccalc/cli.py   speccalc/py.typed
   speccalc/core/{__init__,basis,data,ledger,registry}.py
   speccalc/data/excavation-monitor.json
   speccalc/data/pavement-mqi.json
   speccalc/data/steel-member.json          ← data/ 3 个条目
   speccalc/modules/__init__.py
   speccalc/modules/{excavation-monitor,pavement-mqi,steel-member}/__init__.py
$ <temp venv>/pip install <wheel> && speccalc check excavation-monitor …   # rc=1，587 条
```

解包到中立目录后 `speccalc list` 能列出 3 个器官，说明 `data/` 确实随包分发
（`core/data.py` 走 `importlib.resources`，不读仓库路径）。