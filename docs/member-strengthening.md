# member-strengthening · 既有混凝土构件加固

> 迁自 target-map ③ 行（仓库 #45：`10-06-structural-strengthening-checker`，HEAD `602dd7d`）。
> 旧仓是「构件加固验算 + 方案文本核查 + GB 55021 检查单 + 报告/GUI/打包」桌面工具；
> 本器官只保留**判定层**：公式引擎、方案规则引擎、检查单逐项判定。
> 文档解析、报告排版、GUI、打包、合成数据生成、条款复核元数据全部舍弃（见 §6）。

## 1. 一句话语义

`subject` 给「模式 + 参数/方案卡」，`basis` 给「规范条号」；本器官逐检查项产出计算书行。
每条结论都经 `basis.ref(code, clause)` 取依据；条款缺失即 `ClauseMissing`（退出码 3）。

| 模式 | 做什么 | 输入键 |
|---|---|---|
| `calc` | 4 个验算模块：CFRP 布 / 粘贴钢板 / 增大截面受弯、植筋锚固深度 | `calc.module` + `calc.params` |
| `scheme` | 参数卡 × 规则库：胶粘剂指标 / 植筋深度 / 先鉴定后加固 / 卸载构造 | `scheme`（结构化参数卡） |
| `checklist` | GB 55021-2021 检查单已填项逐条判定 | `checklist`（`item_id → 选项`） |

`mode` / `case_id` 必填。`ratio` 恒为**作用 / 抗力**（受弯 `M/Mu`、植筋 `ld_req/ld`），
`<= 1` 记 `ok`；旧仓植筋的 `ld/ld_req` 只在 evidence 里保留。

## 2. 输入

### 2.1 `calc.params`

参数 schema 逐项搬自旧仓 `CalcModule.param_schema`（含义 / 单位 / 范围 / 可选性），
落在包内 `speccalc/data/member-strengthening.json → modules[*].params`：

| 模块 | 必填（节选） | 可选 | 缺省纪律 |
|---|---|---|---|
| `cfrp_beam_flexure` | `b,h,fc,As,fy,Afe,Ecf,M0,M,ff,ef,as` | `Asc,ap,fyp,xi_b,alpha1,Es,rho_te,rebar_rows,sigma_s0,nf,tf` | `Es=2e5` 等缺省值附 warning；`xi_b` 缺省则跳过 `ξb,f` 上限检查 |
| `steel_plate_flexure` | `b,h,fc,As,fy,Ap,fp,M0,M,as` | `Asc,Apc,ap,fyp,xi_b,alpha1,Es,Esp,rho_te,rebar_rows,sigma_s0` | `Esp=2.06e5` 缺省附 warning |
| `section_enlarge_flexure` | `b,h,bf,hf,fc,fc2,As,fy,As2,fy2,as,as2,M0,M` | `Asc,ap,fyp,alpha1,beta1,Es,xi_b0` | 受拉区加固，`fc2` 只记录不进正截面计算 |
| `post_rebar_anchor` | `fc,fy,d,ld` | `alpha_spt` 或 `cover+stirrup_dia`；`fbd` 或 `adhesive_grade+s1+s2+fc_grade`；`psi_br,psi_w,psi_T,psi_ae,fast_cure` | 两条查表路径各自互斥；缺省系数按规范下限并记 warning |

非有限数（NaN/Inf）、布尔代替数值、越界值均在计算前拒绝（退出码 2）。

### 2.2 `scheme`

参数卡由调用方提供（器官不解析 docx/PDF）；抽取值带 `quote`，`quote` 必须是
`source_text` 子串，否则证据链污染 → 该规则整体降级「待人工确认」。

```json
{
  "mode": "scheme", "case_id": "SCHEME-1",
  "scheme": {
    "doc_name": "某加固方案.docx",
    "source_text": "本加固方案采用碳纤维布加固梁…结构胶采用 A 级胶粘剂：钢对钢拉伸抗剪强度标准值 15.8MPa。植筋锚固深度设计值 320mm…",
    "appraisal_first": {"quote": "检测鉴定结论：已进行安全性鉴定并出具鉴定报告", "para": 1},
    "unloading": [{"kind": "卸载", "quote": "加固前卸载：设置临时支撑并卸除活荷载"}],
    "adhesive_indices": [{"kind": "钢对钢拉伸抗剪强度标准值", "value": 15.8, "unit": "MPa",
                          "label": "A", "quote": "钢对钢拉伸抗剪强度标准值 15.8MPa"}],
    "anchor_depths": [{"kind": "植筋", "value": 320, "unit": "mm", "quote": "锚固深度设计值 320mm"}],
    "design_params": [
      {"kind": "植筋直径", "value": 12, "unit": "mm"},
      {"kind": "钢筋牌号", "label": "HRB400"},
      {"kind": "混凝土强度等级", "value": 40, "unit": "C"},
      {"kind": "胶粘剂等级", "label": "A"}
    ]
  }
}
```

`source_text` 为空（或显式 `degraded:true`）→ 全部命中规则整体降级，绝不产生自动「不符合」。

### 2.3 `checklist`

`checklist` 为 11 个 `item_id → 选项` 的对象；选项只允许
`符合 / 不符合 / 不适用 / 待确认`，缺项按 `待确认` 处理。

## 3. 规则

### 3.1 验算（4 模块，逐项账本行）

| 模块 | 账本项 | 算式 | 条款（`basis_ref`） |
|---|---|---|---|
| CFRP 布 | `cfrp.flexure` | `Mu = α1·fc0·b·x·(h−x/2) + f'y0·A's0·(h−a′) − fy0·As0·(h−h0)`；`ratio=M/Mu` | GB 50367-2013 10.2.3 |
| | `cfrp.xi-limit` | `ξb,f=0.85ξb`；`x ≤ ξb,f·h0` | 10.2.2 |
| | `cfrp.capacity-increase` | `(Mu−Mu0)/Mu0 ≤ 40%` | 10.2.10 |
| | `cfrp.secondary-strain` / `cfrp.km` | `εf0=αf·M0k/(Es·As·h0)`；`km=1.16−nf·Ef·tf/308000≤0.90` | 10.2.8 / 10.2.4 |
| 粘贴钢板 | `plate.flexure` / `plate.xi-limit` / `plate.capacity-increase` / `plate.secondary-strain` | 式(9.2.3-1~4) / `ξb,sp=0.85ξb` / 式(9.2.11) / 式(9.2.9) | 9.2.3 / 9.2.2 / 9.2.11 / 9.2.9 |
| 增大截面 | `enlarge.flexure` / `enlarge.xi-limit` / `enlarge.sigma-s0` / `enlarge.secondary-strain` | 式(5.2.3-1~3) / `2a′≤x≤ξb·h0` / `σs0=(0.8h01/x−1)εcu·Es≤fy0` / 式(5.2.4) | 5.2.3 / 5.2.3 / 5.2.5 / 5.2.4 |
| 植筋锚固 | `anchor.depth` / `.fbd` / `.psi` / `.ls` | `ld ≥ ψN·ψae·ls`；`ls=0.2αspt·d·fy/fbd`；`ψN=ψbr·ψw·ψT` | 15.2.2 / 15.2.4 / 15.2.5 / 15.2.3 |

查表（αf 表10.2.8/9.2.9、αspt 表15.2.3、fbd 表15.2.4、ff 表4.3.4、Ef/εf 表4.3.5、
fy 表4.2.3-1）与胶限值（GB 55021 表B.0.2）逐值搬运到 `data/member-strengthening.json`，
由测试锁死与旧仓条款库一致。条目 `status≠已核对` → `ContractError`（退出码 3）。

### 3.2 方案规则（4 条，类目门控互斥）

| 规则 | 类型 | 门控词 | 判定 |
|---|---|---|---|
| `R-ADH-001` | `param_range` | 结构胶/胶粘剂/植筋胶… | `v < min(粘贴钢材/纤维胶 A/B 档)` → 不符合；`≥ max` → 通过；中间 → 疑似（阻断）；等级未标注 → 待确认 |
| `R-ANCH-001` | `param_range` | 锚固深度/植筋深度… | `ld < 最有利假设下限`（αspt 取全列最小、fbd 取最高档、ψ 取规范下限）→ 不符合；否则筛查通过 |
| `R-APP-001` | `checklist` | 加固方案/加固设计/加固施工 | 有鉴定证据 → 通过；无 → 不符合（GB 55021 1.0.3） |
| `R-CONST-001` | `param_required` | 增大截面/粘贴钢板/碳纤维 | 有卸载/支撑证据 → 通过；无 → 不符合（GB 55021 6.1.5） |

证据子串不通过 → 规则整体「待人工确认」；这比旧仓（额外产出无条款号的 EVIDENCE
finding、同时保留原判定）更保守，见 §7。

### 3.3 三态 → 二态

| 旧仓 | 本产品 | `rejected` |
|---|---|---|
| 满足 / 通过 | `ok` | 否 |
| 需调整 / 不满足 / 不符合 / 疑似 | `rejected` | 是（`evidence.plan_verdict` 保留原态） |
| 待人工确认 / 待确认 | `ok` + `plan_verdict=needs_confirm` | 否（不猜值） |

## 4. 输出示例

```console
$ speccalc check member-strengthening --input samples/member-strengthening/cfrp-case-cf-001-p.json \
        --basis samples/member-strengthening/basis.json
speccalc :: member-strengthening 0.1.0 :: cfrp-case-cf-001-p.json
[ok] cfrp.capacity-increase — 提高幅度 14.796815% / 限值 40% = 0.36992 :: GB 50367-2013 10.2.10（2013）
[ok] cfrp.flexure — M=180 kN·m / Mu=244.023568 kN·m = 0.737634（x=179.424091 mm，ψf=0.405687） :: GB 50367-2013 10.2.3（2013）
[ok] cfrp.secondary-strain — 二次受力 αf=0，εf0=0（M0=0 kN·m） :: GB 50367-2013 10.2.8（2013）
[ok] cfrp.xi-limit — x=179.424091 mm / ξb,f·h0=204.7395 mm = 0.876353 :: GB 50367-2013 10.2.2（2013）
合计 4 条，阻断 0 条（ok=4 rejected=0）          # 退出码 0

$ speccalc check member-strengthening --input samples/member-strengthening/scheme-example.json \
        --basis samples/member-strengthening/basis.json
[ok] scheme.R-ADH-001 — [通过] 钢对钢拉伸抗剪强度标准值 15.8MPa 不低于 A 级胶全部适用限值（上限 15MPa）
[ok] scheme.R-ANCH-001 — [通过] 植筋锚固深度 320mm 不低于最有利假设下限 190.08mm（筛查通过）
[ok] scheme.R-APP-001 — [通过] 方案含检测鉴定环节证据（先鉴定、后加固）
[ok] scheme.R-CONST-001 — [通过] 方案写明加固前卸载/支撑构造措施
合计 4 条，阻断 0 条                              # 退出码 0
```

## 5. 四项判据（实测 2026-11-25）

| # | 判据 | 实测 | 结论 |
|---|---|---|---|
| 1 | 新用例 ≥ X | **X = 76**（新 D1/D18，9 文件，`76 passed in 1.69s`）；新器官 **137 passed**（137 ≥ 76） | **过** |
| 2 | README 示例同参数 rc 相同 | 旧仓 README 的 `ssc calc <module> --input x.json` 用 `data/cases/flexure_cases.json` 的 `CF-001-P` 参数卡实跑：`py -3.12 -m structural_strengthening_checker calc cfrp_beam_flexure --input <参数卡>` → **rc 0**，`Mu=244.02356775216916`、`x=179.42409144534952`、`ψf=0.4056871584895591`；新入口 `speccalc check member-strengthening --input samples/member-strengthening/cfrp-case-cf-001-p.json --basis samples/member-strengthening/basis.json` → **rc 0**，三个数值逐值一致 | **过**（0 = 0） |
| 3 | 用例数 ≥ X + AST 函数数 ≥ 旧层（口径乙） | 旧层 11 文件 / AST 函数 **83**；新器官 1 文件 / 函数 **137** / 用例 **137**；文件数按域只记录（旧 11 → 新 1，覆盖 calc/scheme/checklist 三域） | **过**：137 ≥ 83、137 ≥ 76 |
| 4 | `pip wheel` 后 `data/` 进包 | `%TEMP%` 副本 `/tmp/speccalc-wheel-T6bu4X`（`mktemp -d "$TEMP/speccalc-wheel-XXXXXX"`）：`py -3.12 -m pip wheel --no-deps --no-build-isolation .` → `speccalc-0.1.1-py3-none-any.whl`；`speccalc/data/` **5 件**：`excavation-monitor.json` 6830 / `formwork-scaffold.json` 65480 / **`member-strengthening.json` 43638** / `pavement-mqi.json` 5322 / `steel-member.json` 3602 字节；新文件 sha256 `b11d33ada9be9242f3cf4f197e7ed0472be61dae32698a6c4e7db741a7b9a60c` 与源文件逐字节一致，产品仓未被构建污染 | **过** |

### 5.1 X 的组成（新 D1 + D18）与口径差

D18 判定层正则：`cli|gui|packaging|audit|desensit|guard|bench|infra|export|version|license|generat|docs?_|health|release|selftest|smoke|parse|report|input|output|web|panel`，按**测试文件名**子串匹配。

旧 D1 X = **95**（11 文件，`stage2-speccalc-x-20261125.md` §3）；D18 新增剔除
`test_parsing.py`(12) + `test_report.py`(7) = 19 条 → **新 X = 76**（9 文件）。

| 文件 | 用例 | 域 | 在 X 里 | 本器官是否复刻 |
|---|---:|---|---|---|
| `test_engine_gating.py` | 18 | 条款门控 / 注册表 / 参数校验 | 是 | 复刻（data 状态门 + 输入校验 + thin basis） |
| `test_checking.py` | 16 | 方案规则三级判定 / 证据 | 是 | 复刻（4 规则 + 证据污染降级） |
| `test_calc_modules.py` | 10 | 查表 / 三态 / 结果形状 | 是 | 复刻（4 表 + 4 模块账本行） |
| `test_clauses.py` | 7 | 条款库 schema / 门控 | 是 | 复刻（40 条款键 + 已核对门） |
| `test_m1_data.py` | 6 | 条款/规则/检查单/算例库数据守门 | 是 | 复刻（inventory 52/51/1 + 表值对账） |
| `test_review_anchor.py` | 4 | 条款复核锚（next_review） | 是 | **未复刻**：复核日期属产品级条款台账，器官不携带元数据（§6） |
| `test_param_sweep.py` | 2 | seed 参数扫描位级锁 | 是 | 复刻（seed=20261005 × 12 × 4，金标准哈希） |
| `test_datagen.py` | 7 | 脚手架：合成方案数据生成 | 是（文件名不含排除词） | **未复刻**，见下方冲突说明 |
| `test_lazy_deps.py` | 6 | 脚手架：可选依赖探测 | 是（文件名不含排除词） | **未复刻**，见下方冲突说明 |
| `test_parsing.py` | 12 | 输入侧 docx/PDF 解析 | **否**（D18 `parse`） | 舍弃（器官不读文件） |
| `test_report.py` | 7 | 输出侧 docx 报告 | **否**（D18 `report`） | 舍弃（器官不排版） |

**冲突如实登记**：新 X = 76 里仍有 **13 条不属于器官判定域**的脚手架用例
（`test_datagen.py` 7 条合成方案生成 + `test_lazy_deps.py` 6 条可选依赖探测）。
D1/D18 是按文件名的子串规则，`datagen` 不匹配 `generat`，`lazy_deps` 也不匹配任何排除词，
所以它们**留在 X 里**。本器官**不硬复刻**这 13 条；判定域仍按已吸收器官的口径
（旧台账「判定域 ≈ 63」= 18+16+10+7+6+4+2）做，另用 137 条真实判定用例满足 `≥ 76`。
即：X 分母含 13 条不该覆盖的用例，这是**口径差**，已按用户要求登记，未改 D1、未伪造测试。

## 6. 脚手架测试处置表（被 D1/D18 剔除的每个文件）

| 被剔除文件 | 域 | 处置（由谁接管 / 为何舍弃） |
|---|---|---|
| `test_bench.py` | 基准 | 产品级基准门；器官只做确定性判定，不跑基准套件 |
| `test_bench_cli_gate.py` | 基准 + CLI | 同上；CLI 由产品唯一入口 `speccalc list/check` 接管 |
| `test_cli.py` | CLI | 产品级入口门（`tests/test_entry_surface.py` / `test_speccalc_contract.py`）；器官不带 CLI |
| `test_eol_guard.py` | 仓库 EOL 纪律 | 产品级仓库门接管；与验算判定无关 |
| `test_gui.py` | GUI | 产品不提供 GUI；`SKELETON-SPEC` §2 禁止器官输出排版 |
| `test_packaging.py` | 打包 | 产品级打包门 + 本页判据 4（在 `%TEMP%` 副本 `pip wheel`） |
| `test_project_guards.py` | 项目守门 | 产品级仓库门接管；不进器官 |
| `test_version_single_source.py` | 版本单一来源 | 产品级 `--version` / `pyproject.toml` 门接管 |
| `test_parsing.py` | 输入侧（D18 新增） | docx/PDF 解析要读文件、猜目录；旧包解析层保留，器官只收结构化参数卡 |
| `test_report.py` | 输出侧（D18 新增） | docx 报告排版是产品外壳；器官只产 `CalculationRecord` |

**未剔除但也不复刻**（见 §5.1 冲突）：`test_datagen.py`（合成方案生成器，属输入工件生产）、
`test_lazy_deps.py`（可选依赖探测，属产品外壳）；两者留在 X 里，由本器官的 137 条判定用例
在数量上覆盖，不在职责上覆盖。

## 7. 与旧仓的口径差

1. **三态 → 二态**：旧 `需调整/不满足/不符合/疑似` 在旧仓是不同级别；本产品只有 `ok/rejected`，
   前三者一律 `rejected`，原态存 `evidence.plan_verdict`。`needs_confirm/待确认` 记 `ok`，不阻断。
2. **EVIDENCE finding**：旧仓对「摘录非原文子串」额外产出无条款号的 `EVIDENCE` finding，同时
   保留原判定；本产品「无依据不得入账」，改为该规则整体降级 `needs_confirm`，不再产出无条款行。
3. **植筋 ratio 方向**：旧仓 `ld/ld_req ≥ 1` 合格；本产品统一为 `ld_req/ld ≤ 1`，原式存 message/evidence。
4. **条文未核对**：旧仓 `ClauseNotVerifiedError` → 一般错误 rc 1；本产品同样情形
   （条款缺 / status=未核对）→ `ClauseMissing`/`ContractError` rc 3，无降级态。
5. **检查单**：旧仓 `--interactive/--fill/docx` 是人机交互与排版；本器官只做「已填选项」的逐项判定，
   未填按 `待确认` 记 `ok`。复核日期（`next_review`）不进器官，留在产品级条款台账。
6. **数值出处**：旧仓条款库 52 条（51 已核对、1 待核对 `JGJ145-2013-6.3`）；本器官只登记
   判定所需 40 个条款键（全部已核对），待核对项只作为熔断留痕记录在 `clause_inventory`。

## 8. 测试与来源

- `tests/test_member_strengthening.py`：137 条用例 / 137 个 `def test_`（无 parametrize）。
- 判据 2 的输入：`samples/member-strengthening/cfrp-case-cf-001-p.json`（从旧仓 `CF-001-P` 参数卡只读拷贝）；
  条文库 `samples/member-strengthening/basis.json`（40 个唯一 `code+clause`）。
- 其余样例：`post-rebar-case-pr-001.json` / `scheme-example.json` / `checklist-example.json`。
- 包内数据：`src/speccalc/data/member-strengthening.json`（43638 B，见 §5 判据 4）。

> **本批偏差（D16）**：本器官在 `01-运维-2611` 会话里进入产品仓/来源仓完成（**仓外编辑**），
> 与轨AD §九.1 同类；宿主 `MIMOSA_GIT_GATE_MODE=warn` 不阻断，按 D16 要求在此登记供审计复核。
> 来源仓未改动、未提交；43/44/46 及其已吸收器官逻辑未改动。
