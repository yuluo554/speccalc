# `hazard-scheme-check` · 危大工程专项施工方案合规校核

> 迁自 target-map ③ 行（来源仓 `weida-plan-review`，旧 HEAD `0cad8a5`）。
> 本页写输入 / 规则 / 输出示例 / 四项判据逐行 / 脚手架处置 / 与旧仓口径差。
> 器官目录：`src/speccalc/modules/hazard-scheme-check/`；规则包：`src/speccalc/data/hazard-scheme-check.json`。

## 1. 一句话语义

`subject` 给「方案类别 + 参数卡 +（可选）文档骨架」，`basis` 给规范条款，
本器官按 **29 条规则**（深基坑 19 + 高支模 10）逐条产出计算书行：

- **参数规则**（必填 / 阈值 / 区间 / 枚举）读参数卡；
- **程序规则**（专家论证 / 监测 / 专项方案名目）与**章节齐套规则**读文档骨架；
- 每条结论都挂 `code + clause + version`；同一参数多个取值不硬判，记 `needs_confirm`。

旧仓是「规则优先 + LLM 兜底」的危大方案审查系统；本器官**只迁判定层**，
docx/PDF 解析、LLM 抽取、Web 面板、报告排版、基准与数据生成全部留在器官外（见 §6）。

## 2. 输入

### 2.1 顶层字段（CLI 必填：`case_id` / `category` / `cards`）

```json
{
  "case_id": "gen-0001-deep-pit",
  "category": "deep_pit",
  "cards": [ { "param_id": "dp.excavation_depth", "value": 4.6, "unit": "m" } ],
  "document": { "sections": ["一、工程概况", "5.2 监测方案"], "lines": ["基坑开挖深度为4.6m。"] }
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `case_id` | 字符串 | 是 | 非空；只进 evidence，不参与判定 |
| `category` | 字符串 | 是 | `deep_pit`（深基坑）或 `formwork_support`（高支模） |
| `cards` | 数组 | 是 | 参数卡；未知 `param_id` 被忽略（旧仓同口径） |
| `document` | 对象 | 否 | `{sections, lines}`；缺省时程序性/章节规则不判定（旧仓 skipped 口径） |

### 2.2 参数卡

```json
{
  "param_id": "dp.retaining.displacement",
  "name": "支护结构顶部水平位移控制值",
  "value": 35.0,
  "unit": "mm",
  "text_value": null,
  "raw_text": "水平位移控制值为35mm",
  "evidence": { "line_text": "支护结构顶部水平位移控制值为35mm。" }
}
```

- `param_id` 必填非空；`value` 必须有限数值、`text_value` 必须是字符串；
- 数值规则只读 `value`；枚举规则只读 `text_value`；必填规则接受任一取值；
- `evidence.line_text` 原样写进结论，保证每条结论可回溯方案原文。

规则消费的 8 个参数：

| param_id | 含义 | 类型 |
|---|---|---|
| `dp.excavation_depth` | 基坑开挖深度 | 数值 + 程序触发 |
| `dp.support_type` | 支护形式 | 枚举 |
| `dp.safety_grade` | 侧壁安全等级 | 枚举 |
| `dp.retaining.displacement` | 位移控制值 | 数值 |
| `dp.monitoring.frequency` | 监测频率 | 数值 |
| `fs.support.height` | 模板支撑搭设高度 | 数值 + 程序触发 |
| `fs.pole.spacing` | 立杆间距 | 数值 |
| `fs.formwork.type` | 支撑体系类型 | 枚举 |

### 2.3 文档骨架

```json
{
  "sections": ["一、工程概况", {"title": "5.2 监测方案"}],
  "lines": ["基坑开挖深度为4.6m。", {"text": "本方案已组织专家论证。"}]
}
```

`sections` / `lines` 的元素接受字符串或对象（`title` / `text`），便于把输入侧解析器的
输出直接喂进来。器官本身不打开文件、不解析 docx/PDF、不读环境变量。

## 3. 规则

### 3.1 29 条规则（逐字段迁入，阈值未改）

**深基坑（19 条）**

| 规则 | 类型 | 参数 | 判定 |
|---|---|---|---|
| R-DP-001 | required | `dp.excavation_depth` | 无卡 → 不符合 |
| R-DP-002 | required | `dp.support_type` | 无卡 → 不符合 |
| R-DP-003 | required | `dp.safety_grade` | 无卡 → 不符合 |
| R-DP-004 | required | `dp.retaining.displacement` | 无卡 → 不符合 |
| R-DP-021 | threshold_max | `dp.retaining.displacement` | `<= 30 mm`（示例阈值） |
| R-DP-022 | within_range | `dp.retaining.displacement` | `[5,100] mm`（sanity） |
| R-DP-031 | threshold_min | `dp.monitoring.frequency` | `>= 1 次/d`（示例阈值） |
| R-DP-032 | required | `dp.monitoring.frequency` | 无卡 → 不符合 |
| R-DP-041 | enum | `dp.safety_grade` | `一级/二级/三级` |
| R-DP-042 | enum | `dp.support_type` | 11 种常见选型（整理版，非穷举） |
| R-DP-051 | checklist_section | `doc.sections` | 9 项必备章节 |
| R-DP-052 | checklist_section | `doc.sections` | 监测方案章节 |
| R-DP-061 | threshold_min | `dp.monitoring.frequency` | `>= 2 次/d`（示例阈值） |
| R-DP-062 | threshold_min | `dp.retaining.displacement` | `>= 5 mm`（sanity） |
| R-DP-063 | within_range | `dp.excavation_depth` | `[2,50] m`（sanity） |
| R-DP-072 | threshold_max | `dp.monitoring.frequency` | `<= 24 次/d`（sanity） |
| R-DP-073 | threshold_max | `dp.retaining.displacement` | `<= 500 mm`（sanity） |
| R-DP-101 | conditional_program | `dp.excavation_depth` | `>=5m` → 全文须含「专家论证」 |
| R-DP-103 | conditional_program | `dp.excavation_depth` | `>=3m` → 全文须含「监测」 |

**高支模（10 条）**

| 规则 | 类型 | 参数 | 判定 |
|---|---|---|---|
| R-FS-001 | required | `fs.support.height` | 无卡 → 不符合 |
| R-FS-002 | required | `fs.support.height` | 无卡 → 不符合（与 001 同口径） |
| R-FS-003 | required | `fs.pole.spacing` | 无卡 → 不符合 |
| R-FS-004 | required | `fs.formwork.type` | 无卡 → 不符合 |
| R-FS-012 | within_range | `fs.support.height` | `[2,30] m`（sanity） |
| R-FS-031 | threshold_max | `fs.pole.spacing` | `<= 1.2 m`（示例阈值） |
| R-FS-041 | enum | `fs.formwork.type` | `扣件式/盘扣式/碗扣式/门式` |
| R-FS-051 | checklist_section | `doc.sections` | 9 项必备章节 |
| R-FS-101 | conditional_program | `fs.support.height` | `>=8m` → 全文须含「专家论证」 |
| R-FS-102 | conditional_program | `fs.support.height` | `>=5m` → 全文须含「专项施工方案」 |

### 3.2 三态 → 二态

| 旧仓结果 | 新账本 | 说明 |
|---|---|---|
| `pass` | `ok` | — |
| `fail`（标准依据） | `rejected` | 唯一阻断级 |
| `fail`（`basis_kind=sanity`） | `ok` + `plan_verdict=needs_confirm` | 非规范条款不阻断（§7.2） |
| `manual`（数值多值冲突） | `ok` + `plan_verdict=needs_confirm` | 不猜值、不硬判 |
| 文档缺失时的程序/章节规则 | 不入账（skipped） | 旧仓同口径 |

### 3.3 依据口径

- **23 条标准依据**：建办质〔2018〕31号 / 住建部令第37号 / JGJ 120-2012 /
  GB 50497-2019 / JGJ 162-2008；条款 label 全部取自源仓 `article_no` 或规则 `quote`，
  含「（条号待核对）」字样的原样保留，**没有新造条号**。
- **6 条工程合理性校核**：`code` 明确写「工程合理性校核（非规范条款）」，
  `basis_kind=sanity`，失败只记 `needs_confirm`，不把内部阈值冒充规范。
- **29 条规则全部 `status=待核对`**（源仓原状态）：写进 `evidence.source_status`，
  本器官不声称任何阈值已核对。
- 去重后 19 条 `(code, clause)` 依据，样例条文库 `samples/hazard-scheme-check/basis.json`；
  缺任一条 → `ClauseMissing`（退出码 3）。

## 4. 输出示例

### 4.1 旧 README 示例重放：`gen_0001.docx` → 参数卡 → 18 条结论

```console
$ speccalc check hazard-scheme-check \
      --input samples/hazard-scheme-check/gen-0001-deep-pit.json \
      --basis samples/hazard-scheme-check/basis.json
speccalc :: hazard-scheme-check 0.1.0 :: gen-0001-deep-pit.json
[ok]       R-DP-001 — 已提取到 dp.excavation_depth：4.6m :: 建办质〔2018〕31号 内容清单（条号待核对）（2018）
[rejected] R-DP-021 — 实测 35mm，要求 <= 30mm；… :: GB 50497-2019 第8章（待核对）（2019）
[rejected] R-DP-031 — 实测 0.5次/d，要求 >= 1次/d；… :: GB 50497-2019 第7章（待核对）（2019）
[rejected] R-DP-061 — 实测 0.5次/d，要求 >= 2次/d；… :: GB 50497-2019 第7章（待核对）（2019）
…（其余 14 条 ok）
合计 18 条，阻断 3 条（ok=15 rejected=3）    # 退出码 1
```

`--json` 的 `summary` 为
`{"blocking": 3, "total": 18, "verdicts": {"ok": 15, "rejected": 3}}`；
每条记录含 `basis_ref {code, clause, version, text}` 与
`evidence {rule_id, check_type, param, actual, limit, unit, plan_verdict, source_status, threshold_status, evidence_line}`。

### 4.2 高支模样例（手写合成，`formwork-high.json`）

```console
$ speccalc check hazard-scheme-check \
      --input samples/hazard-scheme-check/formwork-high.json \
      --basis samples/hazard-scheme-check/basis.json
… [rejected] R-FS-031 — 实测 1.5m，要求 <= 1.2m；…
… [rejected] R-FS-051 — 缺少章节/内容：应急处置措施；…
合计 10 条，阻断 2 条（ok=8 rejected=2）     # 退出码 1
```

`R-FS-101`（8.5m → 专家论证）与 `R-FS-102`（≥5m → 专项施工方案）均通过；
`R-FS-041` 枚举「扣件式」通过。样例说明：**该文件是手写合成样例，不是真实项目**。

## 5. 四项判据（逐条实测）

| # | 判据 | 实测 | 结论 |
|---:|---|---|---|
| 1 | 旧仓判定层实跑用例数 **≥** 基线 | 新 D1/D18 实跑 **68 passed + 4 skipped**（7 文件 / 72 collected）；新器官实跑 **188 passed** | **过**（188 ≥ 68） |
| 2 | README 示例命令 **rc 相同** | 旧 `py -m planguard check data/samples/gen_0001.docx --report output` → **rc 1**（「总体结论: 不合规」）；新 `speccalc check hazard-scheme-check --input …gen-0001-deep-pit.json --basis …basis.json` → **rc 1**（18 条/阻断 3 条，同样 R-DP-021/031/061） | **过**（rc 1 = 1；输入形态差异见 §7.1） |
| 3 | 用例数 / 函数数 **≥** 旧层（口径乙） | 用例 **188 ≥ 68**；AST 函数 **188 ≥ 86**（旧层按旧记录 86；本次实测 7 文件 72 / 8 文件 107，取保守门槛 86）；文件数旧 7 → 新 1（**只记录**） | **过** |
| 4 | `pip wheel` 后 `data/` **进包** | `%TEMP%` 副本构建 `speccalc-0.1.1-py3-none-any.whl`（873154 B）；`speccalc/data/` **6 件**；解包后 `speccalc list` 列出 **6 个器官**，`check hazard-scheme-check` 实测 rc 1 | **过** |

### 5.1 X 的逐文件清单（新 D1 = 旧 D1 + D18）

**命令**（来源仓，只读；`PYTHONDONTWRITEBYTECODE=1` 防写旧仓 `__pycache__`）：

```bash
cd D:/ProgramData/zcode/09-26-weida-plan-review
PYTHONDONTWRITEBYTECODE=1 py -3.12 -m pytest \
  tests/test_basis_schema.py tests/test_ci_workflow.py tests/test_m3.py \
  tests/test_m4.py tests/test_m5.py tests/test_pdf.py tests/test_rule_inventory.py \
  -q -p no:cacheprovider
# → 68 passed, 4 skipped, 1 warning in 9.79s
```

| 文件 | collected | passed | skipped | 域 | 新 X 里 | 处置 |
|---|---:|---:|---:|---|---|---|
| `test_m3.py` | 16 | 16 | 0 | 判定（规则引擎） | **是** | **复刻**（阈值/区间/枚举/程序/章节/门控） |
| `test_m4.py` | 17 | 17 | 0 | 知识库 + LLM + 基准（判定相邻） | **是** | **部分复刻**：确定性结论不变性由本器官覆盖；LLM/知识库/基准不迁 |
| `test_m5.py` | 16 | 16 | 0 | **Web 面板（GUI 级）** | **是**（文件名不含 `web/panel/gui`） | **未复刻**：器官不提供 Web；由产品旧包 Web 保留 |
| `test_pdf.py` | 6 | 2 | **4** | **输入侧 PDF 解析** | **是**（文件名不含 `input/parse`） | **未复刻**：器官不解析 PDF；4 条 skipped 也仍在 X 外 |
| `test_rule_inventory.py` | 6 | 6 | 0 | 规则清单治理 | **是** | **复刻为数据契约**（29 = 19+10、依据状态） |
| `test_basis_schema.py` | 6 | 6 | 0 | 依据 schema | **是** | **复刻为条款三定位 + 待核对状态** |
| `test_ci_workflow.py` | 5 | 5 | 0 | **CI 脚手架** | **是**（`ci` 不是排除词 `cli`） | **未复刻**：由产品 CI（`.github/workflows/ci.yml`）接管 |
| **新 X 合计** | **72** | **68** | **4** | — | — | — |
| `test_parse.py` | 14 | 13 | 1 | 输入侧解析 | **否**（命中 D18 `parse`） | **D18 剔出**；未复刻 |
| `test_eol_guard.py` | 5 | — | — | 产品级 EOL 门 | 否（旧 D1 `guard`） | 舍弃：产品级文本门，speccalc 未设同类门 |
| `test_smoke.py` | 13 | — | — | 旧包 CLI/Web 冒烟 | 否（旧 D1 `smoke`） | 舍弃：由 `tests/test_entry_surface.py` + CI 接管 |
| `test_version_single_source.py` | 3 | — | — | 版本单一来源 | 否（旧 D1 `version`） | 舍弃：该门守旧包版本单一来源；speccalc 当前 `__init__.__version__`（0.1.0.dev0）与 `pyproject`（0.1.1）并存，**未设同类门**（遗留，不在本器官范围） |

> **旧 D1 值（保留作对照，不删除）**：8 文件 / 86 collected / **81 passed + 5 skipped**。
> D18 机械重算后：**68 passed + 4 skipped**。差 13 passed + 1 skipped = `test_parse.py`。
> **口径差（如实登记）**：新 X 仍含 **16 条 Web 面板 + 5 条 CI + 2 条 PDF 输入侧**（共 23 条），
> 以及 `test_m4` 里知识库/LLM/基准相邻用例；器官**不复刻**这些产品级路径，
> 但判据 1 的机械 X 仍按 68 满足，未改 D1、未删旧仓文件。

## 6. 脚手架测试处置表（D1 / D18 逐文件）

| 被剔除文件 | 用例 | 域 | 处置（由谁接管 / 为何舍弃） |
|---|---:|---|---|
| `test_parse.py` | 14（13p+1s） | 输入侧 docx 解析 | **D18 新增剔除**（`parse`）。器官不读文件；输入由外部解析器产出参数卡（`samples/hazard-scheme-check/gen-0001-deep-pit.json` 即旧解析器一次只读产物） |
| `test_eol_guard.py` | 5 | 产品级 EOL 门 | 舍弃：旧仓的文本 EOL 守门属产品级；speccalc 未设同类门 |
| `test_smoke.py` | 13 | 旧包 CLI/Web 冒烟 | 舍弃：由 `tests/test_entry_surface.py`（入口门）与产品 CI 接管 |
| `test_version_single_source.py` | 3 | 版本单一来源 | 舍弃：由 `tests/test_speccalc_contract.py` 的版本断言接管 |
| `test_m5.py`（**未剔，仍在 X**） | 16 | Web 面板 | 未复刻：器官不带 GUI/输出排版（SKELETON-SPEC §2）；旧包 Web 保留 |
| `test_pdf.py`（**未剔，仍在 X**） | 6（2p+4s） | 输入侧 PDF | 未复刻：器官不解析 PDF；4 条依赖缺失的 skip 也仍在 X 外 |
| `test_ci_workflow.py`（**未剔，仍在 X**） | 5 | CI 脚手架 | 未复刻：由产品 CI 工作流接管（文件名 `ci` 不匹配 `cli`） |

## 7. 与旧仓的口径差

### 7.1 输入形态：docx/PDF → 参数卡 + 文档骨架

旧示例是「docx 进、报告出」；D18 把输入侧解析剔出判定层后，新器官的输入是
**参数卡 + 文档骨架 JSON**。`samples/hazard-scheme-check/gen-0001-deep-pit.json`
由旧仓 `DocxParser + extract_cards` 对 `data/samples/gen_0001.docx` **只读**生成，
因此判定层的三张失败规则与旧报告完全一致（R-DP-021 / R-DP-031 / R-DP-061），rc 同为 1。
**不可逐字段重放的部分**：docx 排版、页眉页脚、表格合并等解析细节；器官不承担这些。

### 7.2 非规范条款不阻断

源仓 6 条「工程合理性校核」规则（R-DP-022/062/063/072/073/FS-012）中，
R-DP-022 与 R-FS-012 在旧仓是 `强制/error`。本器官统一按 `basis_kind=sanity` 处理：
失败 → `ok + needs_confirm`，**不产生阻断**。理由：这些阈值是源仓自己的示例值，
不是规范原文；用内部阈值做阻断会违反「不许自己造条款」。
该差异不影响旧 README 示例的 rc（该示例的阻断来自 R-DP-021/031/061，均有标准代码依据）。

### 7.3 三态与格式

- `manual` → `needs_confirm`（不猜值）；旧仓仅数值多值冲突产生 `manual`，本器官同口径。
- 枚举规则：旧仓每条卡片一条 finding，本器官保留；多条时 `item_id` 加 `#1/#2`
  以规避计算书 id 冲突。
- 枚举 advice 的 `{value}` 占位符：旧仓不替换，本器官替换（仅消息文本，不改判定）。
- 旧仓 `Finding` 的 `basis` 是纯文本；新契约要求 `code + clause + version`，
  因此条款 label 取源仓 `article_no` / `quote`，缺条号时显式写「（条号待核对）」。

### 7.4 X 组成（判据 1）

新 X = **68 passed**：判定 45（m4 17 + m3 16 + rule_inventory 6 + basis_schema 6）
+ Web 16 + CI 5 + PDF 输入侧 2；另有 4 条 PDF skip 不计入 passed。
旧 D1 X = 81 passed + 5 skipped（8 文件）。**未使用 45 的估算值**；
估算 67 也因 `test_parse` 实为 13 passed + 1 skipped 而不成立，实跑为 68。

## 8. 测试与来源

- 新测试：`tests/test_hazard_scheme_check.py`，**188 个顶层 `test_` 函数 / 188 条实跑用例**，
  不使用 `parametrize`（自指门口径）。
- 覆盖：注册与数据契约 / 输入校验 / required / 阈值 / 区间 / 枚举 / 程序性 /
  章节齐套 / `only_if_text` 门控 / 多值冲突 / 记录形态与确定性 / CLI 退出码 / 两个样例端到端。
- 来源仓只读：`weida-plan-review` HEAD `0cad8a5`；未改、未删、未提交旧仓；
  生成脚本在运维工作区 `scripts/build_hazard_scheme_check_data_20261125.py`。
- **D16 仓外编辑**：本器官的改动在 `01-运维-2611` 会话里 `cd` 进产品仓完成，
  供审计复核。