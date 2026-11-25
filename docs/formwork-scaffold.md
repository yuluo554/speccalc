# formwork-scaffold · 脚手架与模板支架

> 迁自 target-map ③ 行。旧仓是「脚手架/模板支架安全验算 + 专项方案文本核查 + 危大分级」
> 桌面工具；本器官只保留**判定层**：参数卡进、计算书出。文档解析、报告排版、GUI、
> 打包、合成数据生成全部舍弃（见 §6 处置表）。

## 1. 一句话语义

`subject` 给「模式 + 参数卡」，`basis` 给「规范条号」，本器官算三类结论并逐条挂条款：

| 模式 | 做什么 | 输入键 |
|---|---|---|
| `calc` | M-1~M-6 六个验算模块 | `calc.module` + `calc.card` |
| `grade` | 危大分级（非危大 / 危大 / 超一定规模） | `grading.item_id` 或 `grading.project_type` + `grading.params` |
| `review` | 构造限值核查 + 两张皮一致性 + 分级联动 | `review.scheme` + `review.calcbook` |

`mode` / `case_id` 必填；其余键按模式取用。任何一条结论都必须经
`basis.ref(code, clause)` 取到条款——条文库缺条即 `ClauseMissing`（退出码 3）。

## 2. 输入

### 2.1 `calc.card`（与旧仓参数卡同义）

| 模块 | 必填字段 | 可选/缺省 |
|---|---|---|
| M-1 | `category=coupler_steel_pipe_scaffold`、`rows`、`build_height_m`、`step_m`、`long_spacing_m`、`cross_spacing_m`、`wall_tie`、`loads.live_kN_per_m2` | `pipe_spec`=`48.3x3.6`、`loads.gk_struct_kN_per_m`（缺省按表A.0.1 查）、`loads.board_*`/`rail_*`/`safety_net_*`=0、`wind`=`不组合` |
| M-2 | 同 M-1，且 `wind` 为对象（`wk_kN_per_m2` 或 `w0/mu_z/...`） | `shape_phi`/`shape_mu_s`（敞开式可缺省，按表A.0.5 查） |
| M-3 | 同 M-1 + `member`（`cross`/`long`） | `loads.board_kN_per_m2`=0 |
| M-4 | `category`、`rows`、`step_m`、`long_spacing_m`、`wall_tie`、`tie_length_m`、`wind`（对象） | `build_height_m`（缺省按双排落地档，并记 warning）、`tie_type`=`steel_pipe_coupler` |
| M-5 | `category`、`foundation.pad_m`、`foundation.fgk_kPa`、`foundation.reduction`；`foundation.nk_kN` 或完整架体参数 | `foundation.type` |
| M-6 | 立柱：`category=formwork_support`、`step_m`、`pole_spacing_m`、`slab_thickness_m`、`loads.g1k/concrete/rebar/q1k`；地基：`foundation.pad_m`、`n_design_kN`、`mf`、`fak_kPa` | `story_height_m`=4.0、`wind`=`不组合` |

### 2.2 `grading.params`

| 条目 | 判定参数 | 阈值（原文措辞 → 比较符） |
|---|---|---|
| 落地式钢管脚手架 | `build_height` | 24m 及以上 → `>=24`；50m 及以上 → `>=50` |
| 附着式升降脚手架 | `lift_height` | 类型即危大；150m 及以上 → 超规模 |
| 悬挑式脚手架 | `segment_height` | 类型即危大；20m 及以上 → 超规模 |
| 高处作业吊篮 / 卸料平台 / 异型脚手架 / 工具式模板 | — | 类型即危大；31号文附件2 无对应超规模条目 |
| 混凝土模板支撑 | `support_height` / `support_span` / `total_load_design` / `linear_load_design` / `independent_member` | 危大 5 条件 `或`（5m / 10m / 10kN·m⁻² / 15kN·m⁻¹ / 相对独立）；超规模 4 条件 `或`（8m / 18m / 15kN·m⁻² / 20kN·m⁻¹） |
| 承重支撑体系 | `single_point_load` | 类型即危大；7kN 及以上 → 超规模 |

### 2.3 `review.scheme` / `review.calcbook`

```json
{
  "project_type": "某工程 落地式扣件钢管脚手架专项施工方案",
  "category": "coupler_steel_pipe_scaffold",
  "params": {"build_height": 12.0, "step": 1.5, "long_spacing": 1.5,
             "cross_spacing": 1.05, "wall_tie_v": 3.0, "wall_tie_h": 4.5,
             "rows": "double", "scissor_brace": true,
             "expert_review": false, "special_plan": true},
  "unknown": []
}
```

`unknown` 列「解析失败/低置信度」槽位；`params` 里同时出现也按未知处理（宁缺勿错）。
`calcbook` 只有 `params`（与方案卡同名字段才比对）。

## 3. 规则

### 3.1 验算（6 模块 11 条检查）

| 模块 | 检查项 | 算式 | 条款（`basis_ref`） |
|---|---|---|---|
| M-1 | `lizhigan_stability` | `N/(φA) ≤ f`，`N=1.2(NG1k+NG2k)+1.4ΣNQk` | JGJ 130-2011 5.2.6（附 5.2.7/5.2.8/A.0.6/5.1.6/B.0.1） |
| M-2 | `lizhigan_stability` | `N/(φA)+Mw/W ≤ f`，`Mw=0.9×1.4·wk·la·h²/10` | JGJ 130-2011 5.2.6（附 4.2.5/4.2.6） |
| M-3 | `bending_strength` / `deflection` / `antislip` | 横向：`M=qd·lb²/8`、`v=5qk·l⁴/(384EI)`；纵向：`M=0.175·P·la`；`R ≤ Rc` | 5.2.1 / 5.2.3 / 5.2.5 |
| M-4 | `tie_strength` / `tie_stability` / `antislip` | `Nl/Ac`、`Nl/(φA) ≤ 0.85f`、`Nl ≤ Rc`；`Nl=1.4·wk·Aw+N0` | 5.2.12 / 5.2.12 / 5.2.15（Aw 见 6.4.2） |
| M-5 | `foundation_bearing` | `pk=Nk/A ≤ fg=fgk·reduction` | 5.5.1 |
| M-6 | `column_stability` / `foundation_bearing` | `N/(φA) ≤ f=215`（组合风另加 `Mw/W`）；`p=N/A ≤ mf·fak` | JGJ 162-2008 5.2.5 / 5.2.6 |

`ratio` 一律「作用 / 抗力」，`ratio ≤ 1.0` 记 `ok`，否则 `rejected`。
查表口径：φ 按 `λ=ceil(l0/i)` 查离散档（禁插值），λ>250 用 `7320/λ²`；
gk 表内线性插入；μ 与表A.0.5 精确匹配。

### 3.2 危大分级（9 条目）

清单随包（`data/formwork-scaffold.json` → `grading.items`），每条目三级条件为
清单自带字符串，由三值求值器执行（`||` / `&&` / `!` / 比较链 / 布尔参数）：

- `True` → 出确定结论（按 `chaoguimo → weida → none` 取首个真）；
- `None`（参数缺失）→ `pending`，**不猜值**；
- `False` 全假 → `pending`（清单条件未覆盖）。

条目级 `status` 与 `basis[*].status` 必须全为「已核对」，否则 `pending`。

### 3.3 构造限值核查（12 条规则）

| 规则 | 类型 | 门控 `only_if` | 限值来源 |
|---|---|---|---|
| `R-step-limit` / `R-step-limit-20` | threshold | 扣件 + 落地式 | 1.8m / 2.0m（表6.1.1-1、表A.0.1） |
| `R-walltie-vspacing` / `-hspacing` / `-area` | threshold | 扣件 | 表6.4.2 分支（`3h`/`2h`、`3la`、40/27 m²） |
| `R-brace-presence` | presence | 扣件 | 6.6.2 |
| `R-formwork-step-limit` | threshold | 模板 | JGJ 162 5.2.5（1.8m） |
| `R-consistency-step` / `-long-spacing` / `-cross-spacing` | consistency | — | 37号令第十六条 |
| `R-grading-expert-review` / `R-grading-special-plan` | grading | — | 37号令第十二条 / 第十一条 |

`limit_ref` 指向阈值表条目，**限值不写死**；阈值条目 `status≠已核对` 即拦截为
「待人工确认」，不执行、不硬判。参数化限值（`3h`/`3la`）由卡内 `step`/`long_spacing` 现算。

### 3.4 两张皮一致性

只比对两侧都存在的字段；容差：长度类 0.01m、搭设高度 0.05m。
超容差后按安全方向定级：方案实况劣于验算书 → 不合格；优于 → 提示。
**两方向 verdict 都是 `rejected`**（旧仓真值口径：两方向均进违规清单，方向只决定 level）。

## 4. 输出示例

```console
$ speccalc check formwork-scaffold --input samples/formwork-scaffold/calc-example.json \
        --basis samples/formwork-scaffold/basis.json
speccalc :: formwork-scaffold 0.1.0 :: calc-example.json
[ok] M-1.lizhigan_stability — M-1：N=5.4288 kN, φ=0.186, A=506 mm² → σ=57.682 N/mm² ≤ f=205 N/mm² :: JGJ 130-2011 5.2.6（2011）
合计 1 条，阻断 0 条（ok=1 rejected=0）          # 退出码 0

$ speccalc check formwork-scaffold --input samples/formwork-scaffold/grade-example.json \
        --basis samples/formwork-scaffold/basis.json
[ok] grading.pan-luodi-gangguan-24 — 落地式钢管脚手架工程… → 超过一定规模的危大工程（build_height >= 50） :: 建办质〔2018〕31号 附件2 四（一）（2018）
合计 1 条，阻断 0 条（ok=1 rejected=0）          # 退出码 0（分级触发不是「不合格」）

$ speccalc check formwork-scaffold --input samples/formwork-scaffold/review-example.json \
        --basis samples/formwork-scaffold/basis.json
[ok] grading.pan-luodi-gangguan-24 — … → 非危大（build_height < 24） :: 建办质〔2018〕31号 附件1 四（一）（2018）
[ok] rule.R-brace-presence — 剪刀撑设置措施必须在方案中载明：scissor_brace 在位=是 :: JGJ 130-2011 6.6.2（2011）
[ok] rule.R-consistency-step — 验算书步距取值与方案正文一致：方案=1.5 vs 验算书=1.5（|Δ|=0.000 ≤ 容差 0.010） :: 住房城乡建设部令第 37 号 第十六条（2018）
…
合计 12 条，阻断 0 条（ok=12 rejected=0）
```

`rejected` 出现在：验算 `ratio>1`、构造超限、必备措施缺失、两张皮超容差、
超规模未载明专家论证 / 危大未载明专项方案。`--json` 输出见 `SKELETON-SPEC` §6。

## 5. 四项判据（实测 2026-11-25）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 旧仓判定层实跑 passed ≥ | **X = 195**（新 D1/D18；15 文件；输出 `1 failed, 195 passed in 2.63s`；唯一 failure 是本机 ignored 文件 CRLF 的 `test_eol_gate`，非仓缺陷） | **过**：新器官 **272 passed**（272 ≥ 195） |
| 3 | 用例数 ≥ X + AST 函数数 ≥ 旧层 | 旧层 15 文件 / AST 函数 **126**；新器官 3 文件 / AST 函数 **272** / 用例 **272** | **过**（口径乙）：272 ≥ 126、272 ≥ 195；文件数按域记：旧 15 → 新 3（calc+data / grading / review） |
| 2 | README 示例同参数 rc 相同 | 旧例：`data/examples/EX-lizhigan-nw-001.json` 的 `input_card` 存为参数卡 → `.venv/Scripts/sfc calc <卡> --data-dir data`：**rc 0**；新：`speccalc check formwork-scaffold --input samples/formwork-scaffold/calc-example.json --basis samples/formwork-scaffold/basis.json`：**rc 0**，`substituted` 字符串逐字相同（`N=5.4288 kN, φ=0.186, A=506 mm² → σ=57.682 N/mm² ≤ f=205 N/mm²`） | **过**：0 = 0。另测不合格路径：旧实现 rc 0 / 新 rc 1，**接受为口径差**（见 §7.1） |
| 4 | `pip wheel` 后 `speccalc/data/` 进包 | `%TEMP%` 副本 `/tmp/speccalc-wheel-f0HQvJ`：`pip wheel --no-deps --no-build-isolation` → `speccalc-0.1.1-py3-none-any.whl`；`speccalc/data/` **4 个**：`excavation-monitor.json` 6830 / `formwork-scaffold.json` **65480** / `pavement-mqi.json` 5322 / `steel-member.json` 3602 字节；`formwork-scaffold.json` sha256 `6ae210f3…5f75f` 与源文件一致；另有 `app/_data/` 9 条（旧包资产） | **过**：`data/` 非空且含本器官包 |

### 5.1 X 的组成（新 D1 + D18）

判定层 = 文件名不匹配 `cli|gui|packaging|audit|desensit|guard|bench|infra|export|version|license|generat|docs?_|health|release|selftest|smoke|parse|report|input|output|web|panel` 的测试文件。
**D18 相对旧 D1 新增剔除** `parse|report` 四个文件（`test_parse_degrade` 10 / `test_parse_scheme` 6 / `test_report_calc` 5 / `test_report_check` 6，共 27 条）；旧 D1 的 222 → 新 195（差 27）。

| 文件 | collect-only | 域 | 本器官是否复刻 |
|---|---:|---|---|
| `test_grading.py` | 47 | 危大分级 | 复刻（边界值全组） |
| `test_engine_card_sweep.py` | 33 | 参数卡拒收 + 单调性 | 复刻 |
| `test_rules_checks.py` | 21 | 构造限值/门控/一致性 | 复刻 |
| `test_engine_regression.py` | 17 | 13 例算例真值 | 复刻（13 例样例随仓） |
| `test_engine_tables.py` | 12 | 四张查表 | 复刻 |
| `test_engine_gate.py` | 11 | 待核对硬拦截 | 复刻（规则包可替换） |
| `test_clause_library.py` | 7 | 条款/阈值结构纪律 | 复刻为数据形状检查 |
| `test_examples_truth.py` | 6 | 真值库自洽 | 复刻 |
| `test_consistency.py` | 6 | 两张皮方向定级 | 复刻 |
| `test_clause_review.py` | 5 | 复核元数据 | 舍弃（见 §6：不以文件元数据入器官） |
| `test_synth_freeze.py` | 11 | 合成数据字节冻结 | 不复刻（D1 未剔除；属数据生成，器官无此职责） |
| `test_frozen_data_dir.py` | 10 | 数据目录查找 | 不复刻（器官只走包内 `speccalc/data/`） |
| `test_m3_synthetic_eval.py` | 4 | 解析+核查基准 | 不复刻（解析侧已剔除） |
| `test_ci_workflow.py` | 4 | CI YAML | 不复刻（产品级 CI 门接管） |
| `test_eol_gate.py` | 2 | 仓库 EOL 纪律 | 不复刻（产品级仓库门接管；本机 1 条因 ignored 文件 CRLF 失败） |

> 后 5 个文件（31 条）落在 X 里是因为文件名不含 D1/D18 排除词；它们不是器官判定层。
> 本器官用 272 条**判定**用例满足 `≥195`，不靠复刻这 31 条脚手架用例凑分母。

## 6. 脚手架测试处置表（D1/D18 剔除的每个文件）

| 被剔除文件 | 域 | 处置（由谁接管 / 为何舍弃） |
|---|---|---|
| `test_cli.py` | CLI | 产品级入口门接管：新入口只有 `list`/`check`（`tests/test_entry_surface.py` + `tests/test_speccalc_contract.py`）；旧子命令不迁 |
| `test_cli_calc.py` | CLI | 同上：`sfc calc` 子命令属旧产品外壳，器官不接受命令行 |
| `test_cli_check.py` | CLI | 同上：`sfc check` 的解析/报告参数不迁 |
| `test_cli_report.py` | CLI | 同上；报告导出由旧包 `code/backend/app` 保留，不进器官 |
| `test_cli_bench.py` | CLI/基准 | 同上；基准属产品级，不进器官 |
| `test_gui.py` | GUI | 产品不提供 GUI；器官禁止输出排版（`SKELETON-SPEC` §2）→ 舍弃 |
| `test_packaging.py` | 打包 | 产品级打包门接管：`code/backend/tests/test_packaging.py`（`-m packaging`）+ 本页判据 4 |
| `test_desensitize_audit.py` | 审计 | 产品级脱敏/审计门（宿主仓）接管；与验算判定无关 → 舍弃 |
| `test_license_metadata.py` | license | 产品级 license 门接管 → 舍弃 |
| `test_version.py` | version | 产品级 `--version` / `pyproject.toml` 门接管 → 舍弃 |
| `test_bench_suites.py` | bench | 产品级基准；器官只做确定性判定 → 舍弃（13 例真值回归由器官测试接管） |
| `test_parse_degrade.py` | 输入侧解析 | **D18 新增剔除**：解析要读文件/猜目录，与「器官不读文件」冲突；旧包解析保留 |
| `test_parse_scheme.py` | 输入侧解析 | **D18 新增剔除**：同上；方案卡由调用方解析成 `params` 后传入 |
| `test_report_calc.py` | 输出侧报告 | **D18 新增剔除**：报告排版是产品外壳；器官只产 `CalculationRecord` |
| `test_report_check.py` | 输出侧报告 | **D18 新增剔除**：同上 |

## 7. 与旧仓的口径差

1. **不合格路径的退出码**：旧 `sfc calc` 的实现在 `check.verdict=fail` 时仍返回 **0**
   （源码只在 `status=blocked` 时返回 1；这与旧 README 自述的「1=降级完成（含违规）」不一致）。
   新契约按 `SKELETON-SPEC` §5 映射：任一 `rejected` → **1**。判据 2 采用通过型示例（0=0）；
   不合格路径记本口径差，**接受，不加兼容 rc**。
2. **「依据未核对」的状态**：旧仓出 `blocked`（rc 1，计算书带 status_note）。
   speccalc 没有降级态：阈值条目 `status≠已核对` → `ContractError`（**rc 3**），
   不产出任何带病数值。review 模式下逐条规则被拦截 → `ok` + `evidence.status="pending"`。
3. **分级参数缺失**：旧仓返回 `pending`（rc 0，另有 confirmations）。本器官：
   `grade` 模式缺参数 → 输入不合法（**rc 2**）；`review` 模式 → `grading.pending` 记录
   （`ok` + `pending`），规则照常执行，缺槽位逐条记 `pending`。
4. **工程类型未识别**：`grade` 模式 → rc 2；`review` 模式 → `grading.pending`，依据挂
   「31号文 第一条（范围对照）」。
5. **不迁的层**：文档解析（docx/PDF 文本）、报告导出（docx）、GUI、PyInstaller 打包、
   合成方案生成器与 12 份 fixture、条款库复核元数据（`meta.review`）。本器官的规则包
   只保留**判定所需**的阈值/清单/公式，不保留复核日期与出处 URL（那是产品级台账）。
6. **数据形状**：旧仓阈值/清单是 `data/knowledge/clauses/*.json` 多文件；本器官合并为
   单个 `speccalc/data/formwork-scaffold.json`（41 条款 + 36 阈值 + 9 条目 + 12 规则 +
   4 张查表），由 `package-data` 打进 wheel。数值逐值搬运，未改。

## 8. 测试与来源

- `tests/test_formwork_scaffold.py`：数据形状 / 四张查表 / 参数卡拒收 / M-1~M-6 / 13 例真值 / 记录形态。
- `tests/test_formwork_scaffold_grading.py`：9 条目边界 / 类型识别 / 三值逻辑 / grade 记录。
- `tests/test_formwork_scaffold_review.py`：规则表 / 门控 / 一致性 / 未核对拦截 / review 记录 / CLI 退出码。
- 13 例算例真值随仓：`samples/formwork-scaffold/examples/`（只读拷贝，未改数值）。
- 判据 2 的输入：`samples/formwork-scaffold/calc-example.json`（= `EX-lizhigan-nw-001` 的 `input_card`）；
  条文库：`samples/formwork-scaffold/basis.json`（38 条唯一 `code+clause`，由规则包条款键生成）。

> **本批偏差（D16）**：本器官在 `01-运维-2611` 会话里进入产品仓完成（**仓外编辑**），
> 非产品仓会话；用户 2026-11-25 书面覆盖 D14。供审计复核。