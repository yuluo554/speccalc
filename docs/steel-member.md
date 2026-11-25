# 器官 · steel-member（钢结构验算）

> 溯源：迁自 target-map ③ 行（GB 50017-2017）
> 迁入版本：`0.1.0` · 迁入日 2026-11-25 · 判据表放 `src/speccalc/data/steel-member.json`

## 1. 它算什么

按模块跑验算式，每条一个账本行：

| 模块 | 验算式 | `ratio` = 作用 ÷ 抗力 | 依据条号 |
|---|---|---|---|
| `butt_weld` | `N / (l_w·t·f_t^w)`、`V / (l_w·t·f_v^w)` | 应力比 | **11.2.1** |
| `fillet_weld` | `N / (h_e·l_w总·f_f^w)`（侧面）、`N / (β_f·h_e·l_w总·f_f^w)`（正面），`h_e = 0.7·h_f` | 应力比 | **11.2.2** |
| `bolt_normal` | `N_v / (A_s·f_v^b)`、`N_v / (d·Σt·f_c^b)`，`A_s = πd²/4`，`N_v = V/n` | 承载力比 | **11.4.1** |
| `bolt_hsb_friction` | `N_v / (k·n_f·μ·P)` | 承载力比 | **11.4.2** |
| `column_buckling` | `N / (φ·A·f)`、`λ / λ_max`，`λ = max(l_0x/i_x, l_0y/i_y)` | 稳定比 / 长细比 | **7.2.1 / 7.2.2** |

```console
speccalc check steel-member --input samples/steel-member/a2-fillet-weld.json \
        --basis samples/basis.json
```

## 2. 判定口径

- `ratio <= 1 + 1e-3` → `ok`；否则 `rejected`（旧仓 `RATIO_TOL=1e-3`）。
- `ratio > 0.95` → `evidence.need_adjust = true`（旧仓 `NEED_ADJUST_FLOOR`），**只作提示，不改结论**。
- 本器官是三个器官里**唯一能引真条号**的：`clause` 取旧仓 `data/clauses/gb50017.json` 的
  `clause_no` 原值，不自造编号。

## 3. 输入（subject）

`input_fields = ("module", "case_id", "params", "forces", "design_values")`

```json
{
  "case_id": "A2-fillet-weld", "module": "fillet_weld",
  "params": {"h_f": 8.0, "l_w": 200.0, "n_welds": 2, "load_direction": "side"},
  "forces": {"N": 400000.0},
  "design_values": {
    "f_f_w": {"kind": "standard_value", "status": "verified", "value": 160.0, "evidence": "…"}
  }
}
```

**只用得到的设计值才必填**：`butt.tension` 要 `f_t_w`，`fillet.front` 还要 `beta_f`，
`column_buckling` 要 `phi`/`f_y`/`lambda_max`。缺 → 拒绝计算（`design_value_missing`，退出码 2）。

## 4. 脚手架测试处置表（判据 1 的分母）

| 项 | 值 |
|---|---|
| 旧仓判定层文件 | 18 个（静态 216 个 `def test_`） |
| 旧仓判定层实跑 | **253 passed**（本机 3.12 / pytest 8.4.2，JUnit：253 passed / 0 failed / 0 skipped） |
| 本器官实跑 | **279 passed**（3 个测试文件 / 279 个 `def test_`） |
| 差值 | **+26（≥ 分母，过）** |

> 本页此前写「245 tests（1 skipped → 244 passed）」是上一会话的错数：按 §3.0 的文件名单
> 实跑是 **253 passed、零跳过**，与 `ORGAN-PLAYBOOK` §3.0 的 X 一致。

被剔除的 8 个文件：

| 旧仓文件 | 静态 | 处置 | 接管方 / 舍弃理由 |
|---|---:|---|---|
| `test_bench.py` | 7 | 舍弃 | 基准分母只含 verified 的指标门，属产品级指标通道；其「blocked 不得静默算 pass」的语义已由本器官的 `design_value` 门覆盖（旧 blocked → 新 rc 2） |
| `test_eol_guard.py` | 2 | 舍弃 | 仓库行尾门，器官不碰文件系统 |
| `test_gui_contract.py` | 12 | 舍弃 | GUI 与 CLI 逐字一致，器官不带界面 |
| `test_gui_pages.py` | 19 | 舍弃 | 五页签与「界面不自行计算」门，同上 |
| `test_packaging.py` | 15 | 舍弃 | 冻结子进程 / data 白名单 / dist 审计，由产品仓打包门接管 |
| `test_release_audit.py` | 7 | 舍弃 | 发布脱敏扫描，属产品发布流程 |
| `test_run_cli.py` | 14 | 舍弃 | `sdc run` / `bench` 退出码与 `--json` 形状，由 `tests/test_speccalc_contract.py` + 本器官的 CLI 用例接管 |
| `test_text_cli.py` | 13 | 舍弃 | parse / check / checklist / bench 子命令面，器官无 CLI |

> 分母里另有 9 个文件按名字未命中剔除正则但同属脚手架：
> `test_ci_workflow` 9 / `test_clause_review` 6 / `test_engine_fixtures` 5 /
> `test_fingerprint` 6 / `test_kb_gate` 8 / `test_kb_schema` 22 / `test_parse` 17 /
> `test_real_data` 8 / `test_selfcheck` 17 / `test_suite` 17 / `test_synth` 14 /
> `test_tech_report` 7（合计 136 条）。其中 `test_kb_schema`（条款/公式/表/符号 schema）、
> `test_parse`（docx→IR）、`test_synth`（合成语料生成）在新契约下没有落点：
> 知识库由 `--basis` 取代，解析与生成都要读写文件。

## 5. 判据 1 的达成与测试构成

本器官 **279 passed ≥ X=253**（过）。构成：

| 测试文件 | 条数 | 域 |
|---|---:|---|
| `tests/test_steel_member.py` | 109 | 迁入批次：注册 / 条号锚点 / 5 模块 × 9 验算式 / 容差 / 输入契约 / 样例 |
| `tests/test_steel_member_checks.py` | 84 | **9 条验算式 × 9 个状态**：ratio=1、1.0005（容差内）、1.002（超容差）、need_adjust 0.96 / 0.90、条号、绑定的设计值键、抽掉条号即 `ClauseMissing`、作用与抗力入账值 |
| `tests/test_steel_member_params.py` | 86 | 几何参数逐字段缺失 / 为 0 / 为负、内力缺失 / 非数值 / 非有限值、12 个设计值键逐个缺失、模块声明与产出账本行一致、CLI 三档退出码、样例手算 |

`tests/steel_member_kit.py` 是共用夹具（不是测试文件，不被收集）。

9 条验算式的抗力分母在 `steel_member_kit.py` 顶部逐条写了手工算式（`l_w×t×f_t^w` 等），
测试只断言 ratio / 结论 / 依据，不重复实现公式。

### 5.1 判据 3 的口径（轨AD · 2026-11-25 已拍板：口径乙·功能）

判据 3 的字面要求是「测试文件数与函数数 ≥ 旧仓判定层对应数」。用户 2026-11-25 选定 **口径乙（功能）**：

- **函数数按条计（AST）**：本器官 **279**（109 + 84 + 86）≥ 旧仓判定层 **216** → **过**；实跑 **279** 用例。
- **文件数按域计**：本器官 **3 个域文件** / 旧仓 18 个文件。**容器数不等于覆盖数**——旧仓那 18 个里
  9 个是 kb-schema / parse / synth / ci / selfcheck 这类知识库与解析脚手架（见 §4 注），本器官用
  `--basis` 取代了知识库，给它们各建一个空壳文件只会增加容器、不增加覆盖。故文件数**不作为判据**，只作记录。

（口径统一说明见 `records/criterion-verdicts-20261125.md`。）

### 5.2 判据 2 的对比口径（rc 相同，但旧 case 不能逐字段重放）

旧仓 README 原文 `py -3.8 -X utf8 -m sdc run --module fillet_weld --case data/examples/A2-fillet-weld.json`
**rc 1**（`结论：blocked（拒算（数据未核对））`）；新侧 `speccalc check steel-member
--input samples/steel-member/a2-fillet-weld.json --basis …` **rc 1**（`rejected`，ratio 1.1161）。rc 相同。

但旧 case **不是逐字段可重放的**：它的几何参数是顶层平铺（`h_f/l_w/n_welds/load_direction`）、
方向是中文「侧面」、内力是 `420 kN`（`units.force=kN`），还带 `steel_grade/quality_class/t_min/
thickness_group` 四个选材字段；本器官的契约是 `params`/`forces` 成块、方向枚举 `side|front`、
一律 SI（N / mm）、选材由 `design_values` 以「已核对」形态提供（§3）。把旧 case 的数值
（`l_w=240`、`N=420000`）配上夹具已核对设计值重放，新器官给出 **rc 0**（ratio 0.9766 → `ok`，
`need_adjust=true`）——与旧侧 rc 1 不同，差异原因就是**「未核对 → 不出数（旧 rc 1）」被换成了
「未核对 → 拒算（新 rc 2）；已核对 → 出数（新 rc 0/1）」**。这是口径变更，不是回归；
判据 2 用新仓样例对账时 rc 相同（1 = 1）。

### 5.3 `kind` 字段：台账声明必填，代码未校验（需主对话定）

`src/speccalc/data/steel-member.json` 的 `input_contract.design_value.required` 写的是
`["kind","status","value","evidence"]`，但 `_values()` 只校验后三项，`kind` 只被读进 evidence
（缺了也给算）。旧仓样例与现有夹具都带 `kind`，所以两种口径都能跑；
但「声明必填」与「实际不校验」不一致，本批没有改代码（会连带影响 pavement-mqi 的系数格契约与
146+ 条既有夹具），留作口径决定。