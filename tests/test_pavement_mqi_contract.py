"""``pavement-mqi`` · 输入契约 / 记录形态 / CLI / 样例 / 台账。

器官的纪律在这几层留数：
- 输入不合法一律 ``ValueError``（CLI 映射 rc 2），契约违约一律 ``ClauseMissing`` /
  ``ContractError``（CLI 映射 rc 3）；
- ``ok`` 与 ``rejected`` 都挂 ``code + clause + version``；
- 同一输入两次运行字节一致（无时钟、无环境变量、无绝对路径）；
- 样例 ``samples/pavement-mqi/s99-2022.json`` 的每个数都能手算复现。

不使用 ``parametrize``（``test_self_reported_numbers`` 的自指门按 ``def test_`` 计数）。
"""

from __future__ import annotations

import io
import json
import sys

import pytest

from pavement_mqi_kit import (
    BASIS_FILE,
    DISTRESS_ONLY,
    JTG,
    KEYS,
    SAMPLE,
    SLUG,
    coefficients,
    coef,
    distress,
    get,
    run,
    sample_basis,
    sample_subject,
    seg,
    subject,
    subject_for_pci,
)
from speccalc import cli
from speccalc.core import EXIT_BLOCKED, EXIT_CONTRACT, EXIT_INPUT, EXIT_OK, OK, REJECTED, Report
from speccalc.core.data import load as load_data


def _file(tmp_path, payload, name="in.json"):
    target = tmp_path / name
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(target)


# ---------------------------------------------------------------------------
# A. 输入契约：subject 顶层
# ---------------------------------------------------------------------------
def test_missing_project_is_refused():
    payload = subject([seg()])
    del payload["project"]
    with pytest.raises(ValueError, match="project"):
        run(payload)


def test_empty_project_is_refused():
    with pytest.raises(ValueError, match="project 不能为空"):
        run(subject([seg()], project=""))


def test_missing_minimum_grade_is_refused():
    payload = subject([seg()])
    del payload["minimum_grade"]
    with pytest.raises(ValueError, match="minimum_grade"):
        run(payload)


def test_empty_minimum_grade_is_refused():
    with pytest.raises(ValueError, match="minimum_grade 不能为空"):
        run(subject([seg()], minimum_grade=""))


def test_missing_segments_is_refused():
    payload = subject([seg()])
    del payload["segments"]
    with pytest.raises(ValueError, match="segments"):
        run(payload)


def test_segments_not_list_is_refused():
    payload = subject([seg()])
    payload["segments"] = "S-1"
    with pytest.raises(ValueError, match="segments 必须是"):
        run(payload)


def test_segment_without_segment_id_is_refused():
    segment = seg()
    del segment["segment_id"]
    with pytest.raises(ValueError, match="segment_id"):
        run(subject([segment]))


def test_empty_segment_id_is_refused():
    with pytest.raises(ValueError, match="segment_id 不能为空"):
        run(subject([_blank_segment("segment_id")]))


def test_segment_without_surface_type_is_refused():
    segment = seg()
    del segment["surface_type"]
    with pytest.raises(ValueError, match="surface_type"):
        run(subject([segment]))


def test_empty_surface_type_is_refused():
    with pytest.raises(ValueError, match="surface_type 不能为空"):
        run(subject([_blank_segment("surface_type")]))


def test_segment_without_length_is_refused():
    segment = seg()
    del segment["length_m"]
    with pytest.raises(ValueError, match="length_m"):
        run(subject([segment]))


def test_length_must_be_numeric():
    with pytest.raises(ValueError, match="length_m 必须是数值"):
        run(subject([seg(length_m="1000")]))


def test_length_boolean_is_refused():
    with pytest.raises(ValueError, match="length_m 必须是数值"):
        run(subject([seg(length_m=True)]))


def test_length_infinite_is_refused():
    with pytest.raises(ValueError, match="有限数值"):
        run(subject([seg(length_m=float("inf"))]))


def test_length_nan_is_refused():
    with pytest.raises(ValueError, match="有限数值"):
        run(subject([seg(length_m=float("nan"))]))


def test_empty_route_id_is_refused():
    with pytest.raises(ValueError, match="route_id 不能为空"):
        run(subject([_blank_segment("route_id")]))


def test_unknown_surface_has_no_weight_block():
    with pytest.raises(ValueError, match="pci_weight.concrete"):
        run(subject([seg(surface="concrete")]))


def test_measured_none_falls_back_to_empty_and_refuses():
    segment = seg()
    segment["measured"] = None
    with pytest.raises(ValueError, match="rqi"):
        run(subject([segment]))


def test_measured_extra_keys_are_ignored():
    segment = seg()
    segment["measured"]["iri"] = 3.0
    assert get(run(subject([segment])), "pci").evidence["pci"] == pytest.approx(83.0)


def test_segment_without_distress_rows_is_accepted():
    segment = seg()
    del segment["distresses"]
    assert get(run(subject([segment])), "pci").evidence["deducted_total"] == 0.0


# ---------------------------------------------------------------------------
# B. 输入契约：系数格
# ---------------------------------------------------------------------------
def test_coefficient_entry_not_object_is_refused():
    with pytest.raises(ValueError, match="coefficients\\[\\] 必须是对象"):
        run(subject([seg()], ["deduct_ratio.asphalt_distress"]))


def test_coefficient_without_key_is_refused():
    blocks = coefficients()
    blocks[0] = {"status": "verified", "value": {}, "evidence": "x"}
    with pytest.raises(ValueError, match="缺少必填字段：key"):
        run(subject([seg()], blocks))


def test_coefficient_empty_key_is_refused():
    blocks = coefficients()
    blocks[0] = coef("", blocks[0]["value"])
    with pytest.raises(ValueError, match="coefficients\\[\\].key 不能为空"):
        run(subject([seg()], blocks))


def test_coefficient_located_status_is_refused():
    blocks = coefficients()
    blocks[0] = coef(blocks[0]["key"], blocks[0]["value"], status="located")
    with pytest.raises(ValueError, match="source_not_confirmed"):
        run(subject([seg()], blocks))


def test_coefficient_status_missing_is_refused():
    blocks = coefficients()
    blocks[0] = {"key": blocks[0]["key"], "value": blocks[0]["value"], "evidence": "x"}
    with pytest.raises(ValueError, match="source_not_confirmed"):
        run(subject([seg()], blocks))


def test_extra_unused_coefficient_is_allowed():
    blocks = coefficients()
    blocks.append(coef("grade_threshold.extra", {"boundary": "lower_inclusive", "bands": []}))
    assert get(run(subject([seg()], blocks)), "pci").evidence["pci"] == pytest.approx(83.0)


def test_duplicate_segment_id_across_routes_is_refused():
    with pytest.raises(ValueError, match="路段重复"):
        run(subject([seg("S-1", "R1"), seg("S-1", "R2")]))


# ---------------------------------------------------------------------------
# C. 记录形态与计算书
# ---------------------------------------------------------------------------
def test_record_id_is_item_at_code_colon_clause():
    record = get(run(subject([seg()])), "pci")
    assert record.id == "pci.S-1@%s:pci_weight.asphalt" % JTG


def test_every_record_carries_code_clause_version():
    for record in run(subject([seg()])):
        assert record.basis.code == JTG
        assert record.basis.clause
        assert record.basis.version == "2018"


def test_record_message_is_never_empty():
    assert all(record.message.strip() for record in run(subject([seg()])))


def test_report_sorts_records_by_item_id():
    records = run(subject([seg("S-1"), seg("S-2")]))
    report = Report(product="speccalc", organ=SLUG, organ_version="0.1.0", subject="in.json",
                    records=tuple(reversed(records)))
    assert [record.item_id for record in report.records] == sorted(
        record.item_id for record in records)


def test_report_summary_counts_match_records():
    records = run(subject([seg("S-1"), seg("S-2")]))
    summary = Report(product="speccalc", organ=SLUG, organ_version="0.1.0", subject="in.json",
                     records=records).summary()
    assert summary["total"] == len(records)
    assert summary["blocking"] == sum(1 for record in records if record.verdict == REJECTED)
    assert summary["verdicts"][OK] + summary["verdicts"][REJECTED] == len(records)


def test_report_exit_code_is_zero_without_blocking_records():
    payload = subject_for_pci(95.0, minimum_grade="差")
    payload["coefficients"] = coefficients(weights=DISTRESS_ONLY, rules={"rules": []})
    report = Report(product="speccalc", organ=SLUG, organ_version="0.1.0", subject="in.json",
                    records=run(payload))
    assert report.exit_code() == EXIT_OK


def test_report_exit_code_is_one_with_blocking_records():
    report = Report(product="speccalc", organ=SLUG, organ_version="0.1.0", subject="in.json",
                    records=run(subject_for_pci(50.0)))
    assert report.exit_code() == EXIT_BLOCKED


def test_record_as_dict_is_json_serialisable():
    payload = [record.as_dict() for record in run(subject([seg()]))]
    assert json.loads(json.dumps(payload, ensure_ascii=False))


def test_record_evidence_has_no_paths_or_timestamps():
    text = json.dumps([record.as_dict() for record in run(subject([seg()]))], ensure_ascii=False)
    assert "\\\\" not in text
    assert "2026-" not in text
    assert "T00:" not in text


# ---------------------------------------------------------------------------
# D. 确定性
# ---------------------------------------------------------------------------
def test_subject_key_order_does_not_change_records():
    payload = subject([seg()])
    reordered = {key: payload[key] for key in reversed(list(payload))}
    assert [record.as_dict() for record in run(payload)] == [
        record.as_dict() for record in run(reordered)]


def test_segment_order_does_not_change_verdicts_or_values():
    forward = run(subject([seg("S-1"), seg("S-2")]))
    backward = run(subject([seg("S-2"), seg("S-1")]))
    left = {record.item_id: (record.verdict, record.message) for record in forward}
    right = {record.item_id: (record.verdict, record.message) for record in backward}
    assert left == right


def test_two_runs_produce_identical_json(tmp_path, capsys):
    target = _file(tmp_path, subject([seg()]))
    args = ["check", SLUG, "--input", target, "--basis", BASIS_FILE, "--json"]
    cli.main(args)
    first = capsys.readouterr().out
    cli.main(args)
    assert capsys.readouterr().out == first


def test_input_path_is_not_echoed_into_stdout(tmp_path, capsys):
    target = _file(tmp_path, subject([seg()]))
    cli.main(["check", SLUG, "--input", target, "--basis", BASIS_FILE, "--json"])
    out = capsys.readouterr().out
    assert str(tmp_path) not in out
    assert "in.json" in out


# ---------------------------------------------------------------------------
# E. CLI
# ---------------------------------------------------------------------------
def test_cli_list_json_lists_three_organs(capsys):
    assert cli.main(["list", "--json"]) == EXIT_OK
    packs = json.loads(capsys.readouterr().out)
    slugs = [pack["slug"] for pack in packs]
    assert slugs == sorted(slugs)
    assert SLUG in slugs
    assert all(set(pack) == {"slug", "version", "summary", "input_fields"} for pack in packs)


def test_cli_check_ok_subject_returns_zero(tmp_path, capsys):
    payload = subject_for_pci(95.0, minimum_grade="差")
    payload["coefficients"] = coefficients(weights=DISTRESS_ONLY, rules={"rules": []})
    assert cli.main(["check", SLUG, "--input", _file(tmp_path, payload),
                     "--basis", BASIS_FILE]) == EXIT_OK
    assert "[rejected]" not in capsys.readouterr().out


def test_cli_check_rejected_subject_returns_one(tmp_path):
    assert cli.main(["check", SLUG, "--input", _file(tmp_path, subject_for_pci(50.0)),
                     "--basis", BASIS_FILE]) == EXIT_BLOCKED


def test_cli_check_reads_stdin(monkeypatch, capsys):
    payload = json.dumps(subject_for_pci(50.0), ensure_ascii=False)
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    assert cli.main(["check", SLUG, "--input", "-", "--basis", BASIS_FILE]) == EXIT_BLOCKED
    assert "speccalc :: " + SLUG in capsys.readouterr().out


def test_cli_check_json_summary_matches_records(tmp_path, capsys):
    cli.main(["check", SLUG, "--input", _file(tmp_path, subject([seg()])),
              "--basis", BASIS_FILE, "--json"])
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["total"] == len(report["records"])
    assert report["product"] == "speccalc"
    assert report["organ"] == SLUG
    assert report["organ_version"] == "0.1.0"


def test_cli_missing_input_file_is_rc2(tmp_path):
    assert cli.main(["check", SLUG, "--input", str(tmp_path / "nope.json"),
                     "--basis", BASIS_FILE]) == EXIT_INPUT


def test_cli_invalid_json_is_rc2(tmp_path):
    target = tmp_path / "bad.json"
    target.write_text("{not json", encoding="utf-8")
    assert cli.main(["check", SLUG, "--input", str(target), "--basis", BASIS_FILE]) == EXIT_INPUT


def test_cli_non_object_subject_is_rc2(tmp_path):
    payload = _file(tmp_path, [seg()])
    assert cli.main(["check", SLUG, "--input", payload, "--basis", BASIS_FILE]) == EXIT_INPUT


def test_cli_missing_required_field_is_rc2(tmp_path):
    payload = _file(tmp_path, {"project": "P"})
    assert cli.main(["check", SLUG, "--input", payload, "--basis", BASIS_FILE]) == EXIT_INPUT


def test_cli_unknown_organ_is_rc3(tmp_path):
    payload = _file(tmp_path, subject([seg()]))
    assert cli.main(["check", "no-such-organ", "--input", payload,
                     "--basis", BASIS_FILE]) == EXIT_CONTRACT


def test_cli_without_basis_is_rc3(tmp_path):
    payload = _file(tmp_path, subject([seg()]))
    assert cli.main(["check", SLUG, "--input", payload]) == EXIT_CONTRACT


def test_cli_missing_basis_file_is_rc2(tmp_path):
    payload = _file(tmp_path, subject([seg()]))
    assert cli.main(["check", SLUG, "--input", payload,
                     "--basis", str(tmp_path / "nope.json")]) == EXIT_INPUT


def test_cli_basis_without_version_is_rc3(tmp_path):
    payload = _file(tmp_path, subject([seg()]))
    basis = _file(tmp_path, {"version": "", "clauses": []}, "basis.json")
    assert cli.main(["check", SLUG, "--input", payload, "--basis", basis]) == EXIT_CONTRACT


def test_cli_input_error_reports_reason_code(tmp_path, capsys):
    payload = _file(tmp_path, subject([seg()], coefficients=[]))
    assert cli.main(["check", SLUG, "--input", payload, "--basis", BASIS_FILE]) == EXIT_INPUT
    assert "coefficients" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# F. 样例端到端（S99-2022）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def sample_records():
    return {record.item_id: record for record in run(sample_subject(), sample_basis())}


def test_sample_produces_two_segments_and_one_route(sample_records):
    assert sorted(sample_records) == [
        "action.S99-A1", "action.S99-A2", "grade.S99-A1", "grade.S99-A2",
        "mqi.S99", "pci.S99-A1", "pci.S99-A2"]


def test_sample_a1_deduct_total_is_14_4(sample_records):
    assert sample_records["pci.S99-A1"].evidence["deducted_total"] == pytest.approx(14.4)


def test_sample_a1_contributions_are_two_rows(sample_records):
    rows = sample_records["pci.S99-A1"].evidence["contributions"]
    assert [(row["type"], row["deducted"]) for row in rows] == [("横向裂缝", 2.4), ("车辙", 12.0)]


def test_sample_a1_pci_is_77_86(sample_records):
    assert sample_records["pci.S99-A1"].evidence["pci"] == pytest.approx(77.86)


def test_sample_a2_pci_is_31_33(sample_records):
    """A2：横向裂缝重 260 m / 500 m → 62.4；坑槽重 12 处 / 250 → 11.52；合计 73.92。"""
    assert sample_records["pci.S99-A2"].evidence["pci"] == pytest.approx(31.33)


def test_sample_a2_grade_is_bad(sample_records):
    assert sample_records["grade.S99-A2"].evidence["grade"] == "差"


def test_sample_a2_action_is_major_repair(sample_records):
    assert sample_records["action.S99-A2"].evidence["action"]["action_class"] == "大修"


def test_sample_a1_action_is_minor_repair(sample_records):
    assert sample_records["action.S99-A1"].evidence["action"]["action_class"] == "小修"


def test_sample_route_mqi_is_62_35(sample_records):
    """(1000×77.86 + 500×31.33) / 1500 = 62.35。"""
    assert sample_records["mqi.S99"].evidence["mqi"] == pytest.approx(62.35)


def test_sample_route_grade_is_poor(sample_records):
    assert sample_records["mqi.S99"].evidence["grade"] == "次"


def test_sample_has_four_blocking_records(sample_records):
    assert sum(1 for record in sample_records.values() if record.verdict == REJECTED) == 4


def test_sample_basis_clause_version_is_per_clause(sample_records):
    """条文库自身版本是 ``speccalc-samples-20261125``，条款版本是 2018——两者不同。"""
    assert sample_records["pci.S99-A1"].basis.version == "2018"


def test_sample_cli_json_summary(tmp_path, capsys):
    assert cli.main(["check", SLUG, "--input", SAMPLE, "--basis", BASIS_FILE, "--json"]) == EXIT_BLOCKED
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["total"] == 7
    assert report["summary"]["blocking"] == 4


# ---------------------------------------------------------------------------
# G. 器官台账（src/speccalc/data/pavement-mqi.json）
# ---------------------------------------------------------------------------
def test_data_source_points_at_target_map():
    assert load_data("pavement-mqi.json")["source"]["target_map"] == "迁自 target-map ③ 行"


def test_data_notice_says_coefficients_are_not_moved():
    assert "系数" in load_data("pavement-mqi.json")["notice"]
    assert "pending" in load_data("pavement-mqi.json")["notice"]


def test_data_constants_are_floor_ceiling_digits():
    constants = load_data("pavement-mqi.json")["constants"]
    assert constants == {"score_floor": 0.0, "score_ceiling": 100.0, "round_digits": 2}


def test_data_clause_anchor_key_equals_registration_clause():
    clauses = load_data("pavement-mqi.json")["clauses"]
    for key, entry in clauses.items():
        assert entry["clause"] == key


def test_data_all_clause_anchors_use_one_code():
    assert {entry["code"] for entry in load_data("pavement-mqi.json")["clauses"].values()} == {JTG}


def test_data_declares_eleven_anchors_matching_kit():
    assert set(load_data("pavement-mqi.json")["clauses"]) == set(KEYS)


def test_data_input_contract_requires_verified_only():
    contract = load_data("pavement-mqi.json")["input_contract"]["coefficient"]
    assert contract["status"] == ["verified"]
    assert set(contract["required"]) == {"kind", "status", "value", "evidence"}


def test_data_measured_contract_names_three_measurements():
    text = load_data("pavement-mqi.json")["input_contract"]["measured"]
    for name in ("rqi", "rut_depth_mm", "skid"):
        assert name in text


def test_data_clause_no_discipline_is_explicit():
    discipline = load_data("pavement-mqi.json")["clause_no_discipline"]
    assert "系数键" in discipline["clause_field"]
    assert discipline["open_question"]


# ---------------------------------------------------------------------------
# 内部小工具
# ---------------------------------------------------------------------------
def _blank_segment(field):
    segment = seg()
    segment[field] = ""
    return segment