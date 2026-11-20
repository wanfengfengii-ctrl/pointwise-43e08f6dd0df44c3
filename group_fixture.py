import json
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.workbench import Workspace


SAMPLE_PATH = Path(__file__).with_name("samples") / "group_shift.json"


def load_sample():
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))


def prepare(work, sample):
    for test_id, rate, alpha in sample["protocols"]:
        work.register(sample["family_id"], sample["limit_bps"], test_id, Fraction(rate), alpha)
    for batch_id, trials in sample["batches"].items():
        work.seal(batch_id, trials)


def check_v1_sample(work, sample):
    prepare(work, sample)
    rows = []
    for test_id, batch_id, revision in sample["groups"]["ab"]:
        request_id = "single-" + test_id
        work.request(request_id, test_id, batch_id, revision)
        outcome = work.publish(request_id)
        assert outcome.status == "published"
        saved = work.read(outcome.report_id)
        draft = saved.record.draft
        rows.append((draft.test_id, saved.parent.batch_id, saved.parent.revision,
                     str(draft.p_value), draft.significant, draft.alpha_bps))
    assert rows == [("A", "wear-7", 1, "1/128", True, 100),
                    ("B", "wear-5", 1, "3/16", False, 200)]
    audit = work.audit(sample["family_id"])
    assert (audit.published_bps, audit.reserved_bps, audit.available_bps) == (300, 0, 200)
    return {"single_reports": rows, "published_bps": audit.published_bps,
            "available_bps": audit.available_bps}


def check_group_sample(work, sample):
    """Exercise the joint group signature on the shift sample."""
    prepare(work, sample)
    groups = sample["groups"]
    frozen = {}
    for group_id, members in groups.items():
        frozen[group_id] = work.request_group(group_id, members)
    replay = work.request_group("ab", list(reversed(groups["ab"])))
    assert replay == frozen["ab"]
    ab = work.publish_group("ab")
    assert ab.status == "published" and len(ab.report_ids) == 2
    rows = []
    for report_id in ab.report_ids:
        saved = work.read(report_id)
        draft = saved.record.draft
        rows.append((draft.test_id, saved.parent.batch_id, saved.parent.revision,
                     str(draft.p_value), draft.significant, draft.alpha_bps))
    assert rows == [("A", "wear-7", 1, "1/128", True, 100),
                    ("B", "wear-5", 1, "3/16", False, 200)]
    assert work.publish_group("bc").status == "conflict"
    assert work.publish_group("cd").status == "insufficient"
    audit = work.audit(sample["family_id"])
    assert (audit.published_bps, audit.reserved_bps, audit.available_bps) == (300, 0, 200)
    return {"group_reports": rows, "published_bps": audit.published_bps,
            "available_bps": audit.available_bps}


if __name__ == "__main__":
    with TemporaryDirectory(prefix="coating-group-sample-") as folder, Workspace(folder) as work:
        result = check_v1_sample(work, load_sample())
    with TemporaryDirectory(prefix="coating-group-sample-") as folder, Workspace(folder) as work:
        group_result = check_group_sample(work, load_sample())
    print(json.dumps({"single": result, "group": group_result}, sort_keys=True))
