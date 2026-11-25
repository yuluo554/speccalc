"""speccalc 内核契约测试（Stage 1 · 骨架）。

锁四件事：
1. **无规范条款依据不得入账**（`ok` 也一样，不只是 `rejected`）；
2. 条款三定位字段（code / clause / version）缺一即契约违约；
3. 计算书确定性（同一输入两次运行字节一致，无时间戳/绝对路径）；
4. 退出码 0/1/2/3 的边界（含「条文库缺条款 -> 3」这条 §5 口径）。
"""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from speccalc import cli  # noqa: E402
from speccalc.core import (  # noqa: E402
    EXIT_BLOCKED,
    EXIT_CONTRACT,
    EXIT_INPUT,
    EXIT_OK,
    OK,
    REJECTED,
    Basis,
    CalculationRecord,
    Clause,
    ClauseMissing,
    ClauseRef,
    ContractError,
    Pack,
    Report,
    all_packs,
    get,
    register,
)
from speccalc.modules import BUILTIN_MODULES, load_builtin  # noqa: E402

REF = ClauseRef(code="GB 50010-2010", clause="8.2.1", version="2015年版", text="保护层厚度")


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------
def _noop_evaluate(subject, basis):
    return ()


def test_register_and_get_pack():
    pack = Pack(
        slug="probe-alpha",
        version="0.0.1",
        summary="测试用器官",
        input_fields=("spec",),
        evaluate=_noop_evaluate,
    )
    assert register(pack) is pack
    assert get("probe-alpha") is pack
    slugs = [p.slug for p in all_packs()]
    assert slugs == sorted(slugs), "all_packs 必须按 slug 排序"
    assert "probe-alpha" in slugs


def test_duplicate_register_is_rejected():
    register(
        Pack(slug="probe-dup", version="1", summary="x", input_fields=("a",), evaluate=_noop_evaluate)
    )
    with pytest.raises(ValueError):
        register(
            Pack(
                slug="probe-dup",
                version="2",
                summary="重复",
                input_fields=("a",),
                evaluate=_noop_evaluate,
            )
        )


def test_pack_rejects_bad_slug_and_empty_fields():
    with pytest.raises(ValueError):
        Pack(slug="Bad Slug", version="1", summary="x", input_fields=("a",), evaluate=_noop_evaluate)
    with pytest.raises(ValueError):
        Pack(slug="probe-beta", version="1", summary="x", input_fields=(), evaluate=_noop_evaluate)
    with pytest.raises(ValueError):
        Pack(slug="probe-beta", version="", summary="x", input_fields=("a",), evaluate=_noop_evaluate)


def test_missing_pack_is_reported():
    from speccalc.core import PackMissing

    with pytest.raises(PackMissing):
        get("no-such-pack")


def test_builtin_manifest_is_sorted_and_loadable():
    assert list(BUILTIN_MODULES) == sorted(BUILTIN_MODULES)
    load_builtin()


# --------------------------------------------------------------------------
# 计算书：无依据不得入账（ok 也一样）
# --------------------------------------------------------------------------
def test_record_without_basis_is_contract_violation_for_both_verdicts():
    with pytest.raises(ContractError):
        CalculationRecord(item_id="cover", verdict=OK, message="算合格了")
    with pytest.raises(ContractError):
        CalculationRecord(item_id="cover", verdict=REJECTED, message="算不过")


def test_illegal_verdict_is_rejected():
    with pytest.raises(ContractError):
        CalculationRecord(item_id="x", verdict="maybe", message="x", basis=REF)


def test_clause_ref_rejects_any_empty_field():
    for kwargs in (
        {"code": "", "clause": "8.2.1", "version": "2015年版"},
        {"code": "GB 50010-2010", "clause": "", "version": "2015年版"},
        {"code": "GB 50010-2010", "clause": "8.2.1", "version": ""},
    ):
        with pytest.raises(ContractError):
            ClauseRef(**kwargs)


def test_record_id_is_derived_from_item_and_clause():
    first = CalculationRecord(item_id="cover", verdict=OK, message="a", basis=REF)
    second = CalculationRecord(item_id="cover", verdict=REJECTED, message="b", basis=REF)
    other = CalculationRecord(
        item_id="cover",
        verdict=OK,
        message="a",
        basis=ClauseRef(code="GB 50010-2010", clause="8.2.1", version="2010年版"),
    )
    assert first.id == second.id == "cover@GB 50010-2010:8.2.1", "id 只看计算项+条款，不看结论"
    assert other.id == first.id, "改版本不改定位（版本在 basis_ref 里回报）"


def test_report_is_deterministic_and_sorted():
    records = (
        CalculationRecord(item_id="zeta", verdict=OK, message="第二条", basis=REF),
        CalculationRecord(item_id="alpha", verdict=REJECTED, message="第一条", basis=REF),
    )
    report = Report(product="speccalc", organ="o", organ_version="1", subject="s", records=records)
    assert [r.item_id for r in report.records] == ["alpha", "zeta"]
    first = json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=False)
    second = json.dumps(report.as_dict(), ensure_ascii=False, sort_keys=False)
    assert first == second
    assert set(report.as_dict()) == {
        "product",
        "organ",
        "organ_version",
        "subject",
        "summary",
        "records",
    }


def test_report_exit_code_and_summary():
    blocking = Report(
        product="speccalc",
        organ="o",
        organ_version="1",
        subject="s",
        records=(CalculationRecord(item_id="x", verdict=REJECTED, message="x", basis=REF),),
    )
    assert blocking.exit_code() == EXIT_BLOCKED
    assert blocking.summary()["blocking"] == 1

    clean = Report(
        product="speccalc",
        organ="o",
        organ_version="1",
        subject="s",
        records=(CalculationRecord(item_id="x", verdict=OK, message="x", basis=REF),),
    )
    assert clean.exit_code() == EXIT_OK, "ok 不阻断"
    assert clean.summary()["verdicts"] == {OK: 1, REJECTED: 0}


def test_report_rejects_duplicate_record_ids():
    record = CalculationRecord(item_id="x", verdict=OK, message="x", basis=REF)
    with pytest.raises(ContractError):
        Report(product="speccalc", organ="o", organ_version="1", subject="s", records=(record, record))


# --------------------------------------------------------------------------
# 条文库
# --------------------------------------------------------------------------
def test_basis_from_dict_and_ref():
    basis = Basis.from_dict(
        {
            "version": "2026.1",
            "clauses": [
                {
                    "code": "GB 50010-2010",
                    "clause": "8.2.1",
                    "version": "2015年版",
                    "text": "保护层厚度",
                }
            ],
        }
    )
    assert len(basis) == 1
    ref = basis.ref("GB 50010-2010", "8.2.1")
    assert ref.version == "2015年版", "条款自带版本，不被条文库版本覆盖"
    assert ref.text == "保护层厚度"
    assert basis.clause_keys() == ["GB 50010-2010 8.2.1"]


def test_basis_keeps_multiple_code_versions():
    """同一本计算书会同时引多本规范（不同版本），版本不能统一成一个。"""
    basis = Basis(
        version="2026.1",
        clauses=(
            Clause(code="GB 50010-2010", clause="8.2.1", version="2015年版"),
            Clause(code="JGJ 3-2010", clause="3.1.2", version="2010年版"),
        ),
    )
    assert basis.ref("GB 50010-2010", "8.2.1").version == "2015年版"
    assert basis.ref("JGJ 3-2010", "3.1.2").version == "2010年版"


def test_basis_missing_clause():
    basis = Basis.empty(version="2026.1")
    with pytest.raises(ClauseMissing):
        basis.ref("GB 50010-2010", "8.2.1")


def test_basis_rejects_empty_version_duplicates_and_missing_clause_version():
    with pytest.raises(ContractError):
        Basis(version="")
    with pytest.raises(ContractError):
        Basis(
            version="2026.1",
            clauses=(
                Clause(code="GB 50010-2010", clause="8.2.1", version="2015年版"),
                Clause(code="GB 50010-2010", clause="8.2.1", version="2010年版"),
            ),
        )
    with pytest.raises(ContractError):
        Clause(code="GB 50010-2010", clause="8.2.1", version="")


def test_basis_as_dict_roundtrip():
    basis = Basis(
        version="2026.1",
        clauses=(Clause(code="GB 50010-2010", clause="8.2.1", version="2015年版"),),
    )
    assert Basis.from_dict(basis.as_dict()).clause_keys() == ["GB 50010-2010 8.2.1"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _probe_evaluate(subject, basis):
    clause = basis.clause("GB 50010-2010", "8.2.1")
    limit = 25.0
    cover = float(subject.get("cover_mm", 0))
    record = CalculationRecord(
        item_id="cover",
        verdict=OK if cover >= limit else REJECTED,
        message="保护层 %smm %s %smm" % (cover, "≥" if cover >= limit else "<", limit),
        basis=basis.ref("GB 50010-2010", "8.2.1") if clause is not None else None,
        evidence={
            "formula": "cover >= c_min",
            "actual": cover,
            "limit": limit,
            "clause_text": clause.text if clause is not None else "",
        },
    )
    return (record,)


def _strict_evaluate(subject, basis):
    """条文库是硬依赖：取不到条款就让 ``ClauseMissing`` 冒到 CLI（退出码 3）。"""
    return (
        CalculationRecord(
            item_id="cover",
            verdict=OK,
            message="x",
            basis=basis.ref("GB 50010-2010", "8.2.1"),
        ),
    )


@pytest.fixture(scope="module", autouse=True)
def probe_pack():
    register(
        Pack(
            slug="demo-probe",
            version="0.0.1",
            summary="契约测试用器官（非真实规范）",
            input_fields=("cover_mm",),
            evaluate=_probe_evaluate,
        )
    )
    register(
        Pack(
            slug="demo-strict",
            version="0.0.1",
            summary="硬依赖条文库的器官（取不到条款即违约）",
            input_fields=("cover_mm",),
            evaluate=_strict_evaluate,
        )
    )


def _basis_file(tmp_path, with_clause=True, version=True):
    payload = {"version": "2026.1"} if version else {}
    if with_clause:
        payload["clauses"] = [
            {"code": "GB 50010-2010", "clause": "8.2.1", "version": "2015年版", "text": "保护层厚度"}
        ]
    path = tmp_path / "basis.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_cli_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert "speccalc" in capsys.readouterr().out


def test_cli_list(capsys):
    assert cli.main(["list"]) == EXIT_OK
    assert "demo-probe" in capsys.readouterr().out
    assert cli.main(["list", "--json"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)


def test_cli_unknown_pack_is_contract_error(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"cover_mm": 30}), encoding="utf-8")
    assert cli.main(["check", "no-such", "--input", str(target)]) == EXIT_CONTRACT
    assert "PackMissing" in capsys.readouterr().err


def test_cli_missing_input_file_is_input_error(capsys, tmp_path):
    assert cli.main(["check", "demo-probe", "--input", str(tmp_path / "nope.json")]) == EXIT_INPUT


def test_cli_missing_required_field_is_input_error(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"other": 1}), encoding="utf-8")
    assert cli.main(["check", "demo-probe", "--input", str(target)]) == EXIT_INPUT
    assert "cover_mm" in capsys.readouterr().err


def test_cli_clause_missing_is_contract_error(capsys, tmp_path):
    """§5：条文库缺条款 -> 退出码 3。"""
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"cover_mm": 30}), encoding="utf-8")
    assert (
        cli.main(
            [
                "check",
                "demo-strict",
                "--input",
                str(target),
                "--basis",
                str(_basis_file(tmp_path, with_clause=False)),
            ]
        )
        == EXIT_CONTRACT
    )
    assert "ClauseMissing" in capsys.readouterr().err


def test_cli_basis_without_version_is_contract_error(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"cover_mm": 30}), encoding="utf-8")
    assert (
        cli.main(
            [
                "check",
                "demo-probe",
                "--input",
                str(target),
                "--basis",
                str(_basis_file(tmp_path, version=False)),
            ]
        )
        == EXIT_CONTRACT
    )
    assert "条文库版本为空" in capsys.readouterr().err


def test_cli_end_to_end_blocking_and_deterministic(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"cover_mm": 18}), encoding="utf-8")
    basis_path = _basis_file(tmp_path)

    assert (
        cli.main(["check", "demo-probe", "--input", str(target), "--basis", str(basis_path), "--json"])
        == EXIT_BLOCKED
    )
    first = capsys.readouterr().out
    assert str(tmp_path) not in first, "输出不得含绝对路径"
    payload = json.loads(first)
    assert payload["summary"]["blocking"] == 1
    assert payload["records"][0]["basis_ref"]["code"] == "GB 50010-2010"
    assert payload["records"][0]["basis_ref"]["clause"] == "8.2.1"
    assert payload["records"][0]["basis_ref"]["version"] == "2015年版"

    cli.main(["check", "demo-probe", "--input", str(target), "--basis", str(basis_path), "--json"])
    assert capsys.readouterr().out == first, "同一输入两次运行必须字节一致"


def test_cli_pass_path_exits_zero(capsys, tmp_path):
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"cover_mm": 30}), encoding="utf-8")
    assert (
        cli.main(["check", "demo-probe", "--input", str(target), "--basis", str(_basis_file(tmp_path))])
        == EXIT_OK
    )
    assert "ok" in capsys.readouterr().out


def test_cli_stdin_input(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"cover_mm": 18})))
    assert (
        cli.main(
            ["check", "demo-probe", "--input", "-", "--basis", str(_basis_file(tmp_path)), "--json"]
        )
        == EXIT_BLOCKED
    )
    assert json.loads(capsys.readouterr().out)["subject"] == "<stdin>"


def test_cli_without_basis_is_contract_error(capsys, tmp_path):
    """本产品比另外三个更严：没有条文库就不出结论（不是降级，是违约）。"""
    target = tmp_path / "input.json"
    target.write_text(json.dumps({"cover_mm": 30}), encoding="utf-8")
    assert cli.main(["check", "demo-probe", "--input", str(target)]) == EXIT_CONTRACT
    assert "依据" in capsys.readouterr().err