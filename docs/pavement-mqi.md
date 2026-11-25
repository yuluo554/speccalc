# 器官 · pavement-mqi（公路技术状况评定）

> 溯源：迁自 target-map ③ 行（JTG 5210-2018 口径）
> 迁入版本：`0.1.0` · 迁入日 2026-11-25 · 判据表放 `src/speccalc/data/pavement-mqi.json`

## 1. 它算什么

给定**路段实测与破损明细**和**一本条文库**，算四类结论：

| 计算项 | 公式 | 依据 |
|---|---|---|
| `pci.<路段>` | `PCI = Σ 权重 × 分项得分`；`distress = 100 − Σ(比率 × 数量/几何分母 × 100)` | `pci_weight.<surface>` |
| `grade.<路段>` | 按 `grade_threshold.pci` 的 bands + boundary 查档（优/良/中/次/差） | `grade_threshold.pci` |
| `action.<路段>` | `IF 指标 op 阈值 THEN 工程类别 + 规模档` | `action_rule.maintenance_trigger` |
| `mqi.<路线>` | `MQI = Σ(长度 × PCI)/Σ 长度`（首期只有 pavement 分项，partial） | `mqi_weight.pavement` |

不算的：数据导入、台账、报表导出、GUI、打包——旧仓这些层的测试处置见 §4。

```console
speccalc check pavement-mqi --input samples/pavement-mqi/s99-2022.json \
        --basis samples/basis.json
```

## 2. 输入（subject）

`input_fields = ("project", "minimum_grade", "segments", "coefficients")`

```json
{
  "project": "S99-2022",
  "minimum_grade": "中",
  "segments": [{
    "segment_id": "S99-A1", "route_id": "S99", "surface_type": "asphalt",
    "length_m": 1000.0, "panel_count": 500,
    "measured": {"rqi": 7.4, "rut_depth_mm": 6.0, "skid": 48.0},
    "distresses": [{"type": "横向裂缝", "severity": "轻", "quantity": 60.0, "unit": "m"}]
  }],
  "coefficients": [
    {"key": "pci_weight.asphalt", "status": "verified", "evidence": "…",
     "value": {"weights": {"distress": 0.35, "ride_quality": 0.35, "rutting": 0.2, "skid_resistance": 0.1}}}
  ]
}
```

**系数格只认已核对来源**：`status == "verified"` + `value` + `evidence`，缺一即拒绝计算（退出码 2）。
旧仓此时出 `blocked`（退出码 1）；本产品无降级态（`docs/speccalc.md` §4），故改为拒算。

分项得分（`pci_component.*`）：

| 分项 | 算式 | 系数键 |
|---|---|---|
| 行驶质量 | `100 × (RQI − zero) / (ideal − zero)` | `pci_component.ride_quality` |
| 车辙 | `100 × (zero_mm − 深度) / (zero_mm − ideal_mm)`（越小越好） | `pci_component.rutting` |
| 抗滑 | `100 × (指标 − zero) / (ideal − zero)` | `pci_component.skid_resistance` |

三者都钳在 `[0, 100]`；**权重为 0 的分项不需要实测值**，也绝不按 100 分补齐。

## 3. 判定口径

- `grade.*`：`rejected` ⇔ 等级序位低于 `minimum_grade`（基线由项目给定，subject 必填）。
- `action.*`：`rejected` ⇔ 有对策规则命中（`lt/le/gt/ge` 四种比较符，先命中者生效）。
- `mqi.*`：`rejected` ⇔ MQI 等级低于基线。
- `pci.*`：恒 `ok`（它是一条算式入账，不是合格判定）；判合格看 `grade.*`。

## 4. 脚手架测试处置表（判据 1 的分母）

`ORGAN-PLAYBOOK` §3.0 的判定层 = 文件名不匹配
`cli|gui|packaging|audit|desensit|guard|bench|infra|export|version|license|generat|docs?_|health|release|selftest|smoke`。

| 项 | 值 |
|---|---|
| 旧仓判定层文件 | 21 个（静态 291 个 `def test_`） |
| 旧仓判定层实跑 | **370 passed**（本机 3.12 / pytest 8.4.2，JUnit：370 passed / 0 failed / 0 skipped） |
| 本器官实跑 | **412 passed**（4 个测试文件 / 412 个 `def test_`） |
| 差值 | **+42（≥ 分母，过）** |

被剔除的 7 个文件：

| 旧仓文件 | 静态 | 处置 | 接管方 / 舍弃理由 |
|---|---:|---|---|
| `test_cli_contract.py` | 18 | 舍弃 | 器官不得自带 CLI；命令面收缩为 `speccalc list` / `check`，由 `tests/test_speccalc_contract.py` 守 |
| `test_cli_zip_shape.py` | 5 | 舍弃 | PyInstaller 产物形态，器官无打包面 |
| `test_m1_generator.py` | 17 | 舍弃 | 合成数据生成器写盘；等价物是冻结的 `samples/pavement-mqi/s99-2022.json` |
| `test_m4_cli.py` | 12 | 舍弃 | `aggregate` / `compare` 的 CLI 编排；数值语义已由本器官的 `mqi.*` 覆盖 |
| `test_m5_bench.py` | 31 | 舍弃 | 基准四态指标与 README 表同源门，属产品级指标通道 |
| `test_m6_gui.py` | 17 | 舍弃 | GUI 七页签，器官不带界面 |
| `test_release_redlines.py` | 10 | 舍弃 | 发布红线（夹具不进交付面、许可证、测试计数），由产品仓发布流程接管 |

> 分母里另有 12 个文件按名字未命中剔除正则，但内容同样是产品级脚手架
> （`test_data_paths` 6 / `test_gates_*` 24 / `test_ledger_structure` 11 /
> `test_m1_pipeline` 34 / `test_m6_report` 22 / `test_placeholder_registry` 13 /
> `test_privacy_whitelist` 7 / `test_readme_test_count` 1 / `test_determinism_rng` 10 /
> `test_m2_assess` 17，合计 145 条）。其中 `test_m1_pipeline`（CSV 导入与八类校验）与
> `test_m6_report`（报表导出）在新契约下没有落点（器官不读文件、不出报表）。

## 5. 判据 1 的达成与测试构成

本器官 **412 passed ≥ X=370**（过）。构成：

| 测试文件 | 条数 | 域 |
|---|---:|---|
| `tests/test_pavement_mqi.py` | 146 | 迁入批次：注册 / 台账 / 扣分 / 分项 / 权重 / 分档 / 对策 / MQI / 契约 / 样例 |
| `tests/test_pavement_mqi_deduct.py` | 90 | 扣分算术：水泥路面 4 类型 × 3 程度、单位分母 4 × 3 × 2、钳位与逐行舍入、分项得分含界两侧、权重容差、系数块形状 |
| `tests/test_pavement_mqi_grade.py` | 100 | 5 档 PCI × 5 个项目基线的两态矩阵（25）、两种含界口径的档位边沿、自定义分档表、四种比较符 × pci/mqi、路线 MQI 长度加权与两态、依据缺失 |
| `tests/test_pavement_mqi_contract.py` | 76 | 输入原因码（顶层 / 路段 / 系数格）、记录形态与计算书、确定性、CLI 五个退出码、样例手算复现、器官台账 |

新增的 266 条按「每条判据形态 × ok / rejected 两态 + 边沿」写，不重复断言同一个数：
同一档位的「含界 / 不含界」两侧、权重和为 1 的 ±2e-6、扣分恰好 100 与超出 100、
MQI 的 3 段长度加权与 2 条路线分流都是各自独立的期望值。

`tests/pavement_mqi_kit.py` 是共用夹具（不是测试文件，不被收集）。

### 5.1 本批顺带加固的四处输入形状

原实现遇到「系数块里 `ratios` / `denominator` / `weights` / `rules` 形状不对」会抛
`AttributeError`（不是 `ValueError`），车辙的 `zero_mm == ideal_mm` 会抛 `ZeroDivisionError`；
两种都会绕过 CLI 的 `rc 2` 口径。本批改成显式 `ValueError`（`_mapping` 守卫 + 车辙分母守卫），
并各留一条测试钉住。

### 5.2 未强制复核的 7 条锚点（需主对话定）

台账登记 11 条条款锚点，但只有 4 条真正走 `basis.ref`：`pci_weight.<surface>`、
`grade_threshold.pci`、`action_rule.maintenance_trigger`、`mqi_weight.pavement`。
另外 7 条（`deduct_ratio.*_distress`、`pci_component.*`）只出现在 `evidence.clause_ids` 里，
**条文库缺它们也不会报 `ClauseMissing`**——因为对应的比率/端点值由 subject 的「已核对系数格」提供。

两种口径都说得通，但要拍板：是「系数格自带出处凭证即可，条款锚点只做台账」，
还是「引用了哪条就得在 basis 里复核哪条（缺即 rc 3）」。后者要改器官行为，本批没动。

### 5.3 判据 3 的口径（轨AD · 2026-11-25 已拍板：口径乙·功能）

判据 3 的字面要求是「测试文件数与函数数 ≥ 旧仓判定层对应数」。用户 2026-11-25 选定 **口径乙（功能）**：

- **函数数按条计（AST）**：本器官 **412**（146 + 76 + 90 + 100）≥ 旧仓判定层 **291** → **过**；实跑 **412** 用例。
- **文件数按域计**：本器官 **4 个域文件** / 旧仓 21 个文件。**容器数不等于覆盖数**——旧仓那 21 个里
  12 个是 gate / paths / readme-count / privacy 这类仓库级脚手架（见 §4 注），逐个对应成新仓文件
  只会增加容器、不增加覆盖。故文件数**不作为判据**，只作记录。

（口径统一说明见 `records/criterion-verdicts-20261125.md`。）

### 5.4 判据 2 的对比口径（rc 相同，但输入不是同一份）

判据 2 的旧侧命令是旧仓 README 原文
`rmqc --db ledger.sqlite assess --year 2022`（**rc 1**：4/4 路段 blocked，系数全 pending）；
新侧 `speccalc check pavement-mqi --input samples/pavement-mqi/s99-2022.json --basis …`
**rc 1**（4/7 rejected）。rc 相同，但两侧数据不同源，原因要写清：

| 项 | 旧仓 CSV（`data/raw/S99-2022.csv`） | 新仓样例（`samples/pavement-mqi/s99-2022.json`） |
|---|---|---|
| 路段数 | 4（S99-A1…A4） | 2（A1/A2） |
| RQI 刻度 | **0–100**（A1 实测 `rqi=63.2`、SFC `89.7`） | **0–10**（A1 `rqi=7.4`），端点由系数格 `pci_component.*` 给定 |
| 扣分比率来源 | 内置规则集 15 格，14 格 `pending`、`values=null` | 旧仓 `tests/fixtures/pci-fixture-asphalt.json` 夹具口径 |

由此带出一条**口径冲突**：旧 CSV 的 RQI/SFC 是 0–100 刻度，本器官的分项端点完全由
subject 的系数格定义；把旧 CSV 原值直接喂给本器官（配夹具端点 10/0、60/0）会全部饱和到 100 分。
要不要在器官层做刻度校验（例如 actual 超出 `[zero, ideal]` 区间即判输入不合法），
本批没动，留作决定。