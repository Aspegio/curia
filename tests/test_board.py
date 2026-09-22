"""`curia board`: judgment on a repo's open beads, as proposals a person
approves. Every test either leaves jev off or replaces curia.jev (with_jev);
conftest's no_network guard fails any test that reaches the network. The
boards are synthetic, and the one "name" the screen knows is invented and
hashed here."""
import csv
import hashlib
import json
import subprocess

import pytest

from test_cli import E, git_repo
from test_jev import choice, jev_key_on, noul, score, with_jev

INVENTED_NAME = "zorbaville"
DIGESTS = [hashlib.sha256(INVENTED_NAME.encode()).hexdigest()]


def row(bid, title, body="", **extra):
    r = {"id": bid, "title": title, "description": f"## Summary\n{title}.\n\n## Technical\n{body}",
         "status": "open", "issue_type": "task", "priority": 2, "created_at": "2026-09-01T00:00:00Z",
         "labels": [], "dependencies": []}
    r.update(extra)
    return r


BOARD = [
    row("al-aaa1", "Crane load table reads the wrong column", "crane load column"),
    row("al-bbb2", "Load table for cranes reads the wrong column", "load column crane",
        created_at="2026-09-05T00:00:00Z"),
    row("al-ccc3", "Spares approval columns drop the currency marker", "spares"),
    row("al-ddd4", "Rotate the gateway secret before the release", "rotate it"),
    row("al-aaa1.1", "Crane load table column fix, first shift", "crane load column"),
]


def commit_board(estate, rows, *subjects):
    """The rows as alpha's committed export, with a commit per subject after it."""
    src = estate.root / "alpha"
    (src / ".beads" / "issues.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    git_repo(src)
    for s in subjects:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(src), "commit", "-q",
                        "--allow-empty", "-m", s], check=True)
    return src


def set_meta(estate, text):
    p = estate.dir / "estate.toml"
    p.write_text(p.read_text() + "\n" + text + "\n")


def name_digests(estate, digests=DIGESTS, write=True):
    """repos.toml names alpha's name digest file; write=False leaves it missing."""
    p = estate.dir / "repos.toml"
    p.write_text(p.read_text().replace('[repos.alpha]\n', '[repos.alpha]\nname_digests = "names.json"\n'))
    if write:
        (estate.root / "alpha" / "names.json").write_text(json.dumps({"digests": digests}))


def set_thresholds(curia, estate, model=None, **th):
    d = estate.dir / "brain" / "board" / "alpha"
    d.mkdir(parents=True, exist_ok=True)
    (d / "thresholds.json").write_text(json.dumps({"questions_version": curia.BOARD_QUESTIONS,
                                                   "jev_model": model or curia.JEV_MODEL, "thresholds": th}))


def judge(name, texts):
    """Twins read the wrong column; a history saying CLOSED is landed."""
    if name == "same":
        return 0.95 if all("wrong column" in t for t in texts) else 0.05
    if name == "landed":
        return 0.9 if "CLOSED" in " ".join(texts) else 0.1
    return None


def board_jev(curia, estate, monkeypatch, verdict=judge):
    """Jev on, and replaced: item i's answer to question `name` is
    verdict(name, the item's texts), or a plain default. Returns the calls."""
    def answer(state, questions, why):
        assert why.startswith("board:alpha:")
        out = {}
        for qid, spec in questions.items():
            i, name = qid.split("_", 1)
            entry = state["entries"][i]
            v = verdict(name, list(entry.values()) if isinstance(entry, dict) else [entry])
            if spec["type"] == "noul":
                out[qid] = noul(0.1 if v is None else v)
            elif spec["type"] == "choice":
                out[qid] = choice(v or "none", 0.9)
            else:
                out[qid] = score(1.0 if v is None else v)
        return out
    return with_jev(curia, estate, monkeypatch, answer)


def propose(cli, estate, *args):
    rc, out, err = cli(*E(estate), "board", "propose", "--repo", "alpha", *args)
    assert rc == 0, err
    report = out.split("report: ", 1)[1].split("\n", 1)[0]
    with open(estate.dir / "brain" / "board" / "alpha" / "proposals.tsv", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    return open(report).read(), [(r["action"], r["bead"], r["target"]) for r in rows], err


# ------------------------------------------------------------ jev off, on, failing

def test_judgment_refuses_with_jev_off_and_reads_nothing_while_sample_and_emit_still_work(curia, cli, estate,
                                                                                         monkeypatch):
    commit_board(estate, BOARD)
    for args in (["propose"], ["calibrate", "sheet.csv"], ["check", "--title", "Crane load table"]):
        rc, out, err = cli(*E(estate), "board", *args, "--repo", "alpha")
        assert rc == 2 and "needs jev" in err and "nothing was read" in err, args
    assert not (estate.dir / "brain" / "board").exists()
    jev_key_on(estate)
    monkeypatch.setenv("CURIA_JEV", "off")   # one command told to ask nothing
    rc, _, err = cli(*E(estate), "board", "propose", "--repo", "alpha")
    assert rc == 2 and "needs jev" in err
    rc, out, err = cli(*E(estate), "board", "sample", "--repo", "alpha")
    assert rc == 0, err
    sheet = next((estate.dir / "brain" / "board" / "alpha").glob("labels-*.csv"))
    ids = {r["a"] for r in csv.DictReader(sheet.open())} | {r["b"] for r in csv.DictReader(sheet.open())}
    assert "al-aaa1" in ids and "al-ddd4" not in ids          # a fenced bead is not on the sheet either
    assert "no name screen ran" in out and "1 fenced bead(s) left off" in out
    tsv = estate.dir / "brain" / "board" / "alpha" / "proposals.tsv"
    tsv.write_text("\t".join(curia.BOARD_PROPOSAL_COLUMNS) + "\ny\tduplicate\tal-bbb2\tal-aaa1\t0.9\tt\n")
    rc, out, err = cli(*E(estate), "board", "emit", "--repo", "alpha")
    assert rc == 0 and out.splitlines()[1:] == ["bd duplicate al-bbb2 --of al-aaa1"]


def test_propose_asks_through_jev_and_writes_a_report_and_proposals(curia, cli, estate, monkeypatch):
    commit_board(estate, BOARD, "abc: beads: al-bbb2 CLOSED", "def: al-ccc3 CLOSED")
    set_meta(estate, 'board_summary_heading = "## Summary"')
    set_thresholds(curia, estate, same=0.8, landed=0.8)
    calls = board_jev(curia, estate, monkeypatch)
    report, proposals, err = propose(cli, estate)
    # clustered first: al-bbb2 is closed as al-aaa1's duplicate, so it is not also closed as landed
    assert proposals == [("close-landed", "al-ccc3", ""), ("duplicate", "al-bbb2", "al-aaa1")]
    assert {c["why"] for c in calls} == {"board:alpha:pairs", "board:alpha:landed", "board:alpha:beads"}
    assert not any(c["cache"] for c in calls)
    sent = json.dumps([c["state"] for c in calls])
    assert "gateway secret" not in sent and "wrong column" in sent
    for c in calls:   # the text judged is in the state, never in the instructions
        assert not any(b["title"] in json.dumps(c["questions"]) for b in BOARD)
    assert "- 1 bead(s) never asked about: word secret" in report
    assert "- no name screen ran: repos.toml names no name_digests for alpha" in report
    assert "| close-landed | al-ccc3 |" in report and "UNCALIBRATED" in report   # part, acceptance, startable
    gi = (estate.dir / "brain" / "board" / "alpha" / ".gitignore").read_text()
    assert gi == "*\n!.gitignore\n!thresholds.json\n"
    assert err == ""


def test_no_answer_is_said_and_proposes_nothing_and_a_refused_key_stops_the_asking(curia, cli, estate, monkeypatch):
    commit_board(estate, BOARD)
    set_thresholds(curia, estate, same=0.5)

    def down(state, questions, why):
        curia.JEV_ERROR = "HTTP 503"
        return None
    calls = with_jev(curia, estate, monkeypatch, down)
    report, proposals, err = propose(cli, estate, "--passes", "pairs,beads")
    assert proposals == [] and "item(s): not answered: HTTP 503" in report
    assert "jev unavailable for" in err and "HTTP 503" in err
    assert len(calls) == 2   # one request a pass: a failure that is not a refusal does not stop the next

    def refused(state, questions, why):
        curia.JEV_ERROR = "HTTP 402: Insufficient credits"
        return None
    calls = with_jev(curia, estate, monkeypatch, refused)
    report, proposals, err = propose(cli, estate, "--passes", "pairs,beads")
    assert len(calls) == 1 and proposals == []
    assert "item(s): not asked: jev refused (HTTP 402: Insufficient credits)" in report


def test_check_is_the_duplicate_check_at_the_door(curia, cli, estate, monkeypatch):
    commit_board(estate, BOARD)
    calls = board_jev(curia, estate, monkeypatch)
    rc, out, err = cli(*E(estate), "board", "check", "--repo", "alpha", "--title", "Crane table reads the wrong column",
                       "--description", "the load column")
    assert rc == 0, err
    lines = out.splitlines()
    assert lines[0].startswith("p_same 0.95") and ("al-aaa1" in lines[0] or "al-bbb2" in lines[0])
    assert all(c["why"] == "board:alpha:check" for c in calls) and len(calls) == 1
    assert not any("al-ddd4" in x for x in lines)   # fenced: never a candidate
    rc, out, _ = cli(*E(estate), "board", "check", "--repo", "alpha", "--title", "Rotate the crane secret")
    assert rc == 0 and out.startswith("draft not checked: its text is on the never-sent list (word secret)")
    assert len(calls) == 1
    monkeypatch.setattr(curia, "jev", lambda *a, **k: None)
    rc, out, err = cli(*E(estate), "board", "check", "--repo", "alpha", "--title",
                       "Crane table reads the wrong column again")   # a new draft: nothing cached to answer it
    assert rc == 0 and out.startswith("p_same n/a") and "jev unavailable" in err


# ------------------------------------------------------------------- the fences

def test_the_asker_rereads_the_label_fence_for_a_plain_worded_bead(curia, estate, monkeypatch):
    calls = board_jev(curia, estate, monkeypatch)
    (labelled,) = curia.board_beads(estate, [row("al-sec1", "Tighten the crane drive guard", labels=[" Security"])])
    (plain,) = curia.board_beads(estate, [row("al-abc2", "A plain entry")])
    screen = curia.board_screen(estate, "alpha")
    assert screen.bead(labelled) == "label security"
    asker = curia.BoardAsker(estate, "alpha", screen)
    assert asker.ask("beads", [([labelled], [])]) == [None]
    assert asker.ask("pairs", [([plain, labelled], [])]) == [None]
    assert calls == [] and asker.skipped == {"excluded: label security": 2}


def test_unscreened_evidence_is_stopped_at_the_asker(curia, estate, monkeypatch):
    calls = board_jev(curia, estate, monkeypatch)
    asker = curia.BoardAsker(estate, "alpha", curia.board_screen(estate, "alpha"))
    subjects = ["abc1234 2026-09-10 al-ccc3 landed with the credentials rotation"]
    tri = curia.board_triage(estate, asker, BOARD, subjects, ["landed"])
    assert tri.landed == [] and calls == []
    assert asker.skipped == {"excluded: word credential": 1}   # the plural is caught too


def test_calibrate_never_sends_a_fenced_bead(curia, cli, estate, monkeypatch, tmp_path):
    commit_board(estate, [*BOARD, row("al-sec1", "Tighten the crane drive guard", labels=["security"]),
                          row("al-com2", "Crane drive guard wording", labels=["commercial"])],
                 "al-sec1 CLOSED")
    set_meta(estate, 'board_exclude_labels = ["security", "commercial"]')
    calls = board_jev(curia, estate, monkeypatch)
    sheet = tmp_path / "labels.csv"
    with sheet.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(curia.BOARD_SHEET_COLUMNS)
        w.writerow(["same", "al-sec1", "al-aaa1", "0.5", "", "", "y"])
        w.writerow(["same", "al-aaa1", "al-com2", "0.5", "", "", "n"])
        w.writerow(["landed", "al-sec1", "", "", "", "", "y"])
        w.writerow(["same", "al-aaa1", "al-bbb2", "0.9", "", "", "y"])
        w.writerow(["same", "al-aaa1", "al-zzz9", "0.9", "", "", "y"])   # not on the open board
        w.writerow(["same", "al-aaa1", "al-ccc3", "0.1", "", "", ""])    # not labelled
    rc, out, err = cli(*E(estate), "board", "calibrate", str(sheet), "--repo", "alpha")
    assert rc == 0, err
    sent = json.dumps([c["state"] for c in calls])
    assert "drive guard" not in sent and len(calls) == 1 and len(calls[0]["state"]["entries"]) == 1
    assert all(c["why"] == "board:alpha:calibrate" for c in calls)
    assert "Not scored (excluded: label security): 2." in out and "Not scored (excluded: label commercial): 1." in out
    assert "Labelled rows not on the open board: 1." in out and "## same: 1 labelled, 1 yes" in out
    assert f'"jev_model": "{curia.JEV_MODEL}"' in out and "| 0.90 | 1 | 1.000 | 1.000 |" in out


def test_a_name_digest_hit_is_never_sent_and_a_named_set_that_does_not_load_fails_closed(curia, cli, estate,
                                                                                      monkeypatch):
    commit_board(estate, [*BOARD, row("al-cus1", f"Crane load table for {INVENTED_NAME.title()} Works")])
    name_digests(estate)
    calls = board_jev(curia, estate, monkeypatch)
    report, _, _ = propose(cli, estate)
    assert "- 1 bead(s) never asked about: name digest" in report and "- name screen: names.json, 1 digest(s)" in report
    assert INVENTED_NAME not in json.dumps([c["state"] for c in calls]).lower()
    assert curia.BoardScreen([], [], frozenset(), "").text("a plain entry") is not None   # an empty set passes nothing
    # missing, empty, no digests key, and a name written in plain (it would screen nothing)
    for payload in (None, {"digests": []}, {}, {"digests": [DIGESTS[0], INVENTED_NAME]}):
        (estate.root / "alpha" / "names.json").unlink(missing_ok=True)
        if payload is not None:
            (estate.root / "alpha" / "names.json").write_text(json.dumps(payload))
        n = len(calls)
        before = sorted((estate.dir / "brain" / "board" / "alpha").iterdir())
        for args in (["propose"], ["sample"], ["check", "--title", "Crane load table"],
                     ["calibrate", "sheet.csv"]):
            rc, _, err = cli(*E(estate), "board", *args, "--repo", "alpha")
            assert rc == 2 and "fails closed" in err, (payload, args)
        assert len(calls) == n and sorted((estate.dir / "brain" / "board" / "alpha").iterdir()) == before
        rc, out, err = cli(*E(estate), "board", "emit", "--repo", "alpha")   # emit sends nothing: it still works
        assert rc == 0 and out.startswith("# 0 approved row(s)"), err


def test_the_name_screen_reads_commit_lines_words_split_by_punctuation_and_the_window_as_sent(curia, estate,
                                                                                             monkeypatch):
    name_digests(estate, digests=[*DIGESTS, hashlib.sha256(b"zorba ville").hexdigest()])
    calls = board_jev(curia, estate, monkeypatch)
    est = curia.Estate(estate.dir)   # repos.toml moved on disk
    screen = curia.board_screen(est, "alpha")
    asker = curia.BoardAsker(est, "alpha", screen)
    tri = curia.board_triage(est, asker, BOARD, [f"abc1234 2026-09-10 al-ccc3 CLOSED for {INVENTED_NAME.upper()}-Works"],
                             ["landed"])
    assert tri.landed == [] and asker.skipped == {"excluded: name digest": 1}
    plain, split = curia.board_beads(est, [row("al-p1", "Crane load table reads the wrong column"),
                                           row("al-p2", "Load table for cranes at Zorba-Ville reads the wrong column")])
    assert asker.ask("pairs", [([plain, split], [])]) == [None]
    # a first paragraph over the window is cut inside a word: the whole title holds "<name>x", the window the name
    title = "a-" * 1495 + INVENTED_NAME + "x more"
    (cut,) = curia.board_beads(est, [row("al-cut1", title)])
    assert cut.window.endswith(INVENTED_NAME) and screen.text(cut.text) is None
    assert screen.bead(cut) == "name digest" and asker.ask("beads", [([cut], [])]) == [None]
    assert calls == []


# -------------------------------------------------------------------- the board

def test_the_prefilter_pairs_reworded_twins_and_never_a_parent_and_child_or_a_dependency(curia, estate):
    stop = curia.board_stop(estate)
    pairs = {(p.a.id, p.b.id) for p in curia.board_pairs(curia.board_beads(estate, BOARD), stop, min_similarity=0.3)}
    assert ("al-aaa1", "al-bbb2") in pairs
    assert ("al-aaa1", "al-aaa1.1") not in pairs
    assert not any("al-ccc3" in pair for pair in pairs)
    linked = [dict(r) for r in BOARD]
    linked[1]["dependencies"] = json.dumps([{"issue_id": "al-bbb2", "depends_on_id": "al-aaa1"}])
    pairs = {(p.a.id, p.b.id) for p in curia.board_pairs(curia.board_beads(estate, linked), stop)}
    assert ("al-aaa1", "al-bbb2") not in pairs


def test_the_board_is_the_committed_export_never_the_working_tree(curia, cli, estate, monkeypatch):
    src = commit_board(estate, BOARD)
    (src / ".beads" / "issues.jsonl").write_text(json.dumps(row("al-new1", "Only on disk")) + "\n")
    board_jev(curia, estate, monkeypatch)
    report, _, _ = propose(cli, estate, "--passes", "beads")
    assert "5 open bead(s), read from main at " in report and "al-new1" not in report
    p = estate.dir / "repos.toml"
    p.write_text(p.read_text().replace('integration_branch = "main"\nrelease_branch', 'integration_branch = "trunk"\nrelease_branch'))
    rc, _, err = cli(*E(estate), "board", "sample", "--repo", "alpha")
    assert rc == 2 and "no beads export committed at trunk" in err


def test_a_history_that_will_not_read_stops_the_landed_pass(curia, cli, estate, monkeypatch):
    commit_board(estate, BOARD)
    board_jev(curia, estate, monkeypatch)
    real = curia.git

    def git(args, cwd, check=True):
        if args[0] == "log":
            return subprocess.CompletedProcess(args, 128, "", "fatal: bad revision")
        return real(args, cwd, check)
    monkeypatch.setattr(curia, "git", git)
    rc, _, err = cli(*E(estate), "board", "propose", "--repo", "alpha", "--passes", "landed")
    assert rc == 2 and "git log main failed" in err and "fatal: bad revision" in err
    assert not list((estate.dir / "brain" / "board" / "alpha").glob("*-report.md"))
    report, _, _ = propose(cli, estate, "--passes", "beads")   # a run that reads no history does not care
    assert "Board triage - alpha" in report


def test_the_id_pattern_does_not_read_a_child_as_its_parent_and_a_wide_sha_stays_whole(curia, estate, monkeypatch):
    subjects = ["abc1234 2026-09-10 beads: al-aaa1.1 CLOSED", "def5678 2026-09-09 Merge (al-aaa1: load column)",
                "fed4321 2026-09-08 xal-aaa1 is another board's bead"]
    evidence = curia.board_evidence("al-aaa1", subjects)
    assert "def5678" in evidence and "abc1234" not in evidence and "fed4321" not in evidence
    assert "abc1234" in curia.board_evidence("al-aaa1.1", subjects)
    wide = ["983b831c8 2026-09-21 Merge (al-ccc3: currency marker) CLOSED"]
    assert curia.board_evidence("al-ccc3", wide).startswith("983b831c8 2026-09-21 Merge")
    board_jev(curia, estate, monkeypatch)
    asker = curia.BoardAsker(estate, "alpha", curia.board_screen(estate, "alpha"))
    tri = curia.board_triage(estate, asker, BOARD, wide, ["landed"])
    (proposal,) = curia.board_proposals(tri, {"landed": 0.8})
    assert (proposal.bead, proposal.note) == ("al-ccc3", "983b831c8")


# -------------------------------------------------------------------- proposals

def test_no_threshold_means_no_proposal_however_sure_the_model_is(curia, estate, monkeypatch):
    board_jev(curia, estate, monkeypatch)
    asker = curia.BoardAsker(estate, "alpha", curia.board_screen(estate, "alpha"))
    tri = curia.board_triage(estate, asker, BOARD, ["abc1234 2026-09-10 al-ccc3 CLOSED"], ["pairs", "landed", "beads"])
    assert tri.pairs and tri.landed and curia.board_proposals(tri, {}) == []
    report = curia.board_report(estate, "alpha", tri, {}, asker, "main at abc", [])
    assert "UNCALIBRATED" in report and "al-bbb2" in report and "None. A question proposes only once" in report


def answers(same, pick="none", p_part=0.1):
    return {"same": {"p": same}, "part": {"pick": pick, "p": p_part}}


def beads(curia, estate, *specs):
    return curia.board_beads(estate, [row(bid, title, created_at=f"2026-09-0{n}T00:00:00Z", **extra)
                                      for n, (bid, title, extra) in enumerate(specs, 1)])


def test_a_duplicate_cluster_closes_each_bead_once_into_one_survivor(curia, estate):
    a, b, c, e = beads(curia, estate, ("al-aaa1", "Load column", {}), ("al-bbb2", "Load column again", {}),
                       ("al-ccc3", "Load column once more", {}), ("al-eee5", "Crane data tables", {}))
    P = curia.BoardPair
    tri = curia.BoardTriage(pairs=[(P(a, b, 0.9), answers(0.99)), (P(a, c, 0.9), answers(0.99)),
                                   (P(b, c, 0.9), answers(0.99)),
                                   (P(c, e, 0.4), answers(0.05, "first_in_second", 0.95)),   # names one closed: dropped
                                   (P(a, e, 0.4), answers(0.05, "first_in_second", 0.9))])   # the survivor: stands
    got = curia.board_proposals(tri, {"same": 0.8, "part": 0.8})
    assert [(p.action, p.bead, p.target) for p in got] == [
        ("duplicate", "al-bbb2", "al-aaa1"), ("duplicate", "al-ccc3", "al-aaa1"), ("reparent", "al-aaa1", "al-eee5")]
    closed = {p.bead for p in got if p.action == "duplicate"}
    assert len({p.bead for p in got}) == len(got) and not closed & {p.target for p in got}


def test_a_chained_cluster_names_the_survivor_and_says_via_whom(curia, estate):
    a, b, c = beads(curia, estate, ("al-aaa1", "Load column", {}), ("al-bbb2", "Load column again", {}),
                    ("al-ccc3", "Load column once more", {}))
    tri = curia.BoardTriage(pairs=[(curia.BoardPair(b, c, 0.9), answers(0.97)),
                                   (curia.BoardPair(a, b, 0.9), answers(0.92))])
    got = curia.board_proposals(tri, {"same": 0.8})
    assert [(p.bead, p.target) for p in got] == [("al-ccc3", "al-aaa1"), ("al-bbb2", "al-aaa1")]
    assert got[0].note.startswith("via al-bbb2") and not got[1].note.startswith("via")


def test_new_parents_never_give_a_bead_two_or_make_a_loop_or_move_a_child_or_an_epic(curia, estate):
    a, b, c, d, e = beads(curia, estate, ("al-aaa1", "Load column", {}), ("al-bbb2", "Crane data tables", {}),
                          ("al-ccc3", "Crane report tables", {}), ("al-ddd4.1", "A child", {}),
                          ("al-eee5", "An epic", {"issue_type": "epic"}))
    P = curia.BoardPair
    tri = curia.BoardTriage(pairs=[(P(a, b, 0.4), answers(0.05, "first_in_second", 0.95)),   # a under b
                                   (P(a, c, 0.4), answers(0.05, "first_in_second", 0.9)),    # a again: no
                                   (P(b, c, 0.4), answers(0.05, "first_in_second", 0.9)),    # b under c
                                   (P(a, c, 0.4), answers(0.05, "second_in_first", 0.85)),   # c under a: a loop
                                   (P(d, c, 0.4), answers(0.05, "first_in_second", 0.9)),    # a child bead: no
                                   (P(e, c, 0.4), answers(0.05, "first_in_second", 0.9))])   # an epic: no
    got = curia.board_proposals(tri, {"part": 0.8})
    assert [(p.bead, p.target) for p in got] == [("al-aaa1", "al-bbb2"), ("al-bbb2", "al-ccc3")]


def test_work_in_progress_is_the_bead_kept(curia, estate, monkeypatch):
    board = [dict(r) for r in BOARD]
    board[1]["status"] = "in_progress"
    board_jev(curia, estate, monkeypatch)
    asker = curia.BoardAsker(estate, "alpha", curia.board_screen(estate, "alpha"))
    tri = curia.board_triage(estate, asker, board, [], ["pairs"])
    (p,) = curia.board_proposals(tri, {"same": 0.8})
    assert (p.bead, p.target) == ("al-aaa1", "al-bbb2")


def test_flags_read_the_labels_a_bead_carries(curia, estate):
    set_meta(estate, 'board_summary_heading = "## Summary"\nboard_waiting_labels = ["requires-design"]')
    est = curia.Estate(estate.dir)
    waiting, designing = curia.board_beads(est, [row("al-fff6", "Ask the desk", labels=["needs-human"]),
                                                  row("al-hhh8", "Draw it", labels=["requires-design"])])
    (bare,) = curia.board_beads(est, [{**row("al-ggg7", "Ask the desk"), "description": "x"}])
    ans = {"acceptance": {"p": 0.9}, "startable": {"p": 0.1}, "size": {"value": 3.8}}
    at = {"acceptance": 0.5, "startable": 0.4}
    assert curia.board_flags(est, waiting, ans, at) == ["sized in weeks and not an epic: split"]
    assert curia.board_flags(est, designing, ans, at) == ["sized in weeks and not an epic: split"]
    assert curia.board_flags(est, bare, ans, at) == [
        "no summary", "reads as waiting on a person, but carries no waiting label",
        "sized in weeks and not an epic: split"]
    ans["startable"]["p"] = 0.9
    assert "reads as startable, but carries a waiting label" in curia.board_flags(est, waiting, ans, at)


# ------------------------------------------------------ the cache, the model, the batches

def test_a_second_run_asks_only_what_changed(curia, cli, estate, monkeypatch):
    commit_board(estate, BOARD)
    first = board_jev(curia, estate, monkeypatch)
    propose(cli, estate, "--passes", "pairs,beads")
    assert first
    commit_board(estate, [*BOARD, row("al-eee5", "Filter cloth life note is missing from the annexure")])
    second = board_jev(curia, estate, monkeypatch)
    propose(cli, estate, "--passes", "beads")
    assert len(second) == 1 and list(second[0]["state"]["entries"].values())[0].startswith("Filter cloth")


def test_a_jev_model_move_misses_the_cache_and_drops_the_thresholds(curia, cli, estate, monkeypatch):
    commit_board(estate, BOARD)
    first = board_jev(curia, estate, monkeypatch)
    set_thresholds(curia, estate, same=0.8)
    report, proposals, err = propose(cli, estate, "--passes", "pairs,beads")
    asked = sum(len(c["state"]["entries"]) for c in first)
    assert "- thresholds: same 0.8" in report and proposals == [("duplicate", "al-bbb2", "al-aaa1")]
    set_meta(estate, 'jev_model = "vendor/next-model"')
    again = board_jev(curia, estate, monkeypatch)
    report, proposals, err = propose(cli, estate, "--passes", "pairs,beads")
    assert sum(len(c["state"]["entries"]) for c in again) == asked > 4   # every item asked afresh
    assert proposals == [] and "run calibrate again" in err and "thresholds.json ignored" in report
    set_thresholds(curia, estate, model="vendor/next-model", same=0.8)
    (estate.dir / "brain" / "board" / "alpha" / "thresholds.json").write_text(
        (estate.dir / "brain" / "board" / "alpha" / "thresholds.json").read_text().replace(
            curia.BOARD_QUESTIONS, "older-words"))
    report, _, err = propose(cli, estate, "--passes", "beads")
    assert "measured against questions 'older-words'" in err


def sent_size(curia, call):
    """The body jev() would send, as it measures it."""
    return len(json.dumps({"model": curia.JEV_MODEL, "state": call["state"], "questions": call["questions"]}))


def test_requests_are_batched_to_fit_one_judgment(curia, cli, estate, monkeypatch):
    many = [row(f"al-{n:03d}x", f"Entry number {n} about topic {n}", "word " * 560) for n in range(20)]
    commit_board(estate, many)
    calls = board_jev(curia, estate, monkeypatch)
    propose(cli, estate, "--passes", "beads")
    assert sum(len(c["state"]["entries"]) for c in calls) == 20 and len(calls) < 20
    for c in calls:
        assert len(c["state"]["entries"]) <= curia.BOARD_BATCH
        assert sent_size(curia, c) <= curia.JEV_CHARS


def test_an_item_too_long_for_one_request_is_not_sent_and_says_so(curia, estate, monkeypatch):
    """A window is cut in characters, and a character outside the basic plane is twelve once escaped:
    a pair of such windows is past JEV_CHARS on its own, and is left out rather than sent."""
    calls = board_jev(curia, estate, monkeypatch)
    asker = curia.BoardAsker(estate, "alpha", curia.board_screen(estate, "alpha"))
    wide = [curia.Bead(f"al-w{n}", f"Wide {n}", "\U0001F600" * 2990) for n in range(2)]
    plain = curia.board_beads(estate, BOARD[:2])
    got = asker.ask("pairs", [(wide, []), (plain, [])])
    assert got[0] is None and got[1] is not None and len(calls) == 1
    assert asker.skipped == {f"too long for one request (over {curia.JEV_CHARS} characters as sent)": 1}
    assert all(sent_size(curia, c) <= curia.JEV_CHARS for c in calls)


def test_the_repo_is_the_one_you_are_in_unless_named(curia, cli, estate, monkeypatch, tmp_path):
    src = commit_board(estate, BOARD)
    monkeypatch.chdir(src)
    rc, out, err = cli(*E(estate), "board", "sample")
    assert rc == 0 and "brain/board/alpha/labels-" in out, err
    monkeypatch.chdir(tmp_path)
    rc, _, err = cli(*E(estate), "board", "sample")
    assert rc == 2 and "name it with --repo" in err


# ------------------------------------------------------------------------- emit

def test_emit_prints_only_the_approved_rows(curia, cli, estate):
    tsv = estate.dir / "brain" / "board" / "alpha" / "proposals.tsv"
    tsv.parent.mkdir(parents=True)
    proposals = [curia.BoardProposal("duplicate", "al-bbb2", "al-aaa1", 0.95, "t"),
                 curia.BoardProposal("reparent", "al-ccc3", "al-aaa1", 0.9, "t"),
                 curia.BoardProposal("close-landed", "al-eee5", "", 0.9, "abc1234 983b831c8")]
    tsv.write_text("\t".join(curia.BOARD_PROPOSAL_COLUMNS) + "\n"
                   + "".join(f"{ok}\t{p.action}\t{p.bead}\t{p.target}\t{p.p}\t{p.note}\n"
                             for ok, p in zip(("y", "", "Yes"), proposals)))
    rc, out, err = cli(*E(estate), "board", "emit", "--repo", "alpha")
    assert rc == 0, err
    day = out.splitlines()[2].split("board triage ", 1)[1].split(" ", 1)[0]
    assert out.splitlines()[0].startswith("# 2 approved row(s) of ")
    assert out.splitlines()[1:] == ["bd duplicate al-bbb2 --of al-aaa1",
                                    f"bd close al-eee5 --reason 'landed; board triage {day} (abc1234 983b831c8)'"]


@pytest.mark.parametrize("bad", [
    "y\tduplicate\tal-bbb2; rm -rf x\tal-aaa1\t0.9\tt",
    "y\tduplicate\tzz-bbb2\tal-aaa1\t0.9\tt",                  # another repo's prefix
    'y\tclose-landed\tal-eee5\t\t0.9\tabc"); echo pwned #',
    "y\tclose-landed\tal-eee5\t\t0.9\tLoad table for cranes",
    "y\tclose-landed\tal-eee5\t\t0.9\t",
    "y\tclose-landed\tal-eee5\tal-aaa1\t0.9\tabc1234",
    "y\tduplicate\tal-bbb2\t\t0.9\tt",
    "y\treparent\tal-bbb2\t\t0.9\tt",
    "y\tdelete\tal-bbb2\t\t0.9\tt",
    "y\tduplicate\tal-bbb2\tal-aaa1\t0.9\tt\ny\treparent\tal-bbb2\tal-ccc3\t0.9\tt",    # one bead, two rows
    "y\tduplicate\tal-bbb2\tal-aaa1\t0.9\tt\ny\treparent\tal-ccc3\tal-bbb2\t0.9\tt",    # closed, and a target
])
def test_emit_refuses_a_row_it_did_not_write_and_prints_nothing(curia, cli, estate, tmp_path, bad):
    sheet = tmp_path / "approved.tsv"
    sheet.write_text("\t".join(curia.BOARD_PROPOSAL_COLUMNS) + "\ny\tduplicate\tal-ddd4\tal-aaa1\t0.9\tt\n"
                     + bad + "\n")
    rc, out, err = cli(*E(estate), "board", "emit", str(sheet), "--repo", "alpha")
    assert rc == 2 and out == "" and ("refusing" in err or "unknown action" in err)


def test_operating_table_and_window_cut(curia):
    table = {at: (n, pr, rc) for at, n, pr, rc in
             curia.board_operating([(0.9, True), (0.8, False), (0.6, True), (0.2, False)])}
    assert table[0.5] == (3, 0.667, 1.0) and table[0.85] == (1, 1.0, 0.5)
    assert curia.cut_window("first paragraph\n\n" + "second " * 30, 40) == "first paragraph"
    assert len(curia.cut_window("word " * 50, 42)) <= 42


def test_a_board_report_is_the_record_and_the_sheets_are_a_persons_to_mark(curia, cli, estate, monkeypatch):
    monkeypatch.setenv("CURIA_SEAT", "muse")
    monkeypatch.setenv("CURIA_ESTATE", str(estate.dir))
    home = estate.dir / "brain" / "board" / "alpha"

    def guard(path):
        return cli("hook", "record-guard", stdin=json.dumps({"tool_name": "Write", "tool_input": {"file_path": str(path)},
                                                              "cwd": str(estate.root)}))[0]
    assert guard(home / "2026-09-22T000000Z-report.md") == 2
    assert [guard(home / f) for f in ("proposals.tsv", "labels-2026-09-22.csv", "thresholds.json")] == [0, 0, 0]
