"""The mechanism against a scratch estate. Every test here runs the real CLI
in-process with claude replaced; see conftest.py."""
import datetime as dt
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

UTC = dt.timezone.utc


def E(estate):
    return ["--estate", str(estate.dir)]


def result_json(text, **extra):
    d = {"type": "result", "is_error": False, "result": text, "session_id": "sess-1",
         "total_cost_usd": 0.5, "num_turns": 7, "duration_ms": 120000}
    d.update(extra)
    return json.dumps(d)


def completed(cmd, rc, stdout, stderr=""):
    return subprocess.CompletedProcess(cmd, rc, stdout, stderr)


FULL_HANDOFF = """# Handoff - Muse, 2026-01-01

## Where things stand
Nothing much.

## Beads touched
- none

## Decisions and why
None.

## Loose ends and what next
1. Wake up.

## For the principal
Nothing.

## Notes to self
Fine.
"""


# ------------------------------------------------------------------ clock

def test_session_log_stamps_each_event_when_it_happens(curia, estate, monkeypatch):
    sd = estate.seat_dir("muse")
    t1 = dt.datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(curia, "now", lambda: t1)
    curia.log_session(sd, "start", "account=a")
    assert curia.stamp() == "2026-01-01T100000Z" and curia.today() == "2026-01-01"
    monkeypatch.setattr(curia, "now", lambda: t1 + dt.timedelta(hours=2, days=1))
    curia.log_session(sd, "end", "rc=0")
    assert curia.today() == "2026-01-02"
    events = curia.session_events(sd)
    assert [e[1] for e in events] == ["2026-01-01T10:00:00+00:00", "2026-01-02T12:00:00+00:00"]
    assert events[0] == ("start", "2026-01-01T10:00:00+00:00", "account=a")


# ------------------------------------------------------------------ estate

def test_repo_here_picks_the_most_specific_repo(estate, monkeypatch):
    monkeypatch.chdir(estate.root / "alpha" / "sub")
    assert estate.repo_here() == "nested"
    monkeypatch.chdir(estate.root / "alpha")
    assert estate.repo_here() == "alpha"
    monkeypatch.chdir(estate.root.parent)
    assert estate.repo_here() is None


def test_fill_placeholders_leaves_other_braces_alone(curia):
    out = curia.fill_placeholders('Review {repo} on {date}: {"json": 1} and {not_set} {}', {"repo": "x", "date": "d"})
    assert out == 'Review x on d: {"json": 1} and {not_set} {}'


# ---------------------------------------------------------------- accounts

def test_fallback_chain_and_limit_markers(curia, cli, estate):
    assert curia.walk_chain(estate, "a") == ("a", [])
    rc, out, _ = cli(*E(estate), "limit", "a", "--hours", "1")
    assert rc == 0 and "falls back to 'b'" in out.replace("fall back to", "falls back to")
    free, limited = curia.walk_chain(estate, "a")
    assert free == "b" and [n for n, _ in limited] == ["a"]
    cli(*E(estate), "limit", "b", "--hours", "1")
    free, limited = curia.walk_chain(estate, "a")
    assert free is None and [n for n, _ in limited] == ["a", "b"]
    rc, _, err = cli(*E(estate), "launch", "muse")
    assert rc == 2 and "every account in the chain" in err
    cli(*E(estate), "limit", "a", "--clear")
    assert curia.walk_chain(estate, "a")[0] == "a"
    # an expired marker is removed on read
    curia.mark_limited(estate, "b", curia.now() - dt.timedelta(minutes=1))
    assert curia.account_limited(estate, "b") is None
    assert not curia.limit_marker(estate, "b").exists()


@pytest.mark.parametrize("banner, expect", [
    ("You've hit your session limit · resets 4:30pm (Europe/London)", (2026, 6, 1, 16, 30, "Europe/London")),
    ("resets 5am", (2026, 6, 2, 5, 0, "UTC")),          # 05:00 is past at 12:00, so tomorrow
    ("limit reached, resets at 16:30", (2026, 6, 1, 16, 30, "UTC")),
    ("resets in 3 hours", None),
    ("resets 2026 something", None),                    # no minutes, no am/pm
    ("resets 4pm (Nowhere/Land)", None),                # unknown zone: use the default hours
])
def test_limit_reset_parsing(curia, monkeypatch, banner, expect):
    monkeypatch.setattr(curia, "now", lambda: dt.datetime(2026, 6, 1, 12, 0, tzinfo=UTC))
    got = curia.limit_reset(banner)
    if expect is None:
        assert got is None
        return
    y, mo, d, h, mi, zone = expect
    assert got.tzinfo is UTC
    assert got.astimezone(ZoneInfo(zone)).replace(tzinfo=None) == dt.datetime(y, mo, d, h, mi)


def test_limit_banner_detection_needs_the_banner(curia):
    assert curia.looks_limited("You've hit your session limit · resets 4:30pm")
    assert curia.looks_limited("You've hit your weekly limit")
    assert curia.looks_limited("Claude usage limit reached")
    assert curia.looks_limited("You're out of usage credits. Switch to another model, or manage usage credits")
    assert not curia.looks_limited("Reviewed the rate limiter PR; all good")


# ----------------------------------------------------------------- handoff

def test_handoff_done_wants_every_section_then_begin_archives(cli, estate):
    sd = estate.seat_dir("muse")
    rc, _, err = cli(*E(estate), "handoff", "muse", "--done")
    assert rc == 2 and "missing or too short" in err
    (sd / "handoff.md").write_text("# Handoff\n\n## Where things stand\nA lot happened, honestly quite a lot.\n")
    rc, _, err = cli(*E(estate), "handoff", "muse", "--done")
    assert rc == 2 and "lacks the section(s): Beads touched" in err and "Notes to self" in err
    (sd / "handoff.md").write_text(FULL_HANDOFF)
    rc, out, err = cli(*E(estate), "handoff", "muse", "--done")
    assert rc == 0, err
    assert (sd / "RESTART").exists()
    assert [e[0] for e in __import__("curia_cli").session_events(sd)] == ["handoff"]
    rc, out, _ = cli(*E(estate), "handoff", "muse", "--begin")
    assert rc == 0 and str(sd / "handoff.md") in out
    assert not (sd / "handoff.md").exists()
    assert len(list((sd / "history").iterdir())) == 1
    # a placeholder note is not archived
    (sd / "handoff.md").write_text("_No handoff yet._")
    cli(*E(estate), "handoff", "muse", "--begin")
    assert len(list((sd / "history").iterdir())) == 1


# ------------------------------------------------------------------ launch

def test_launch_records_session_clears_stale_restart_and_loops(curia, cli, estate, monkeypatch, tmp_path):
    sd = estate.seat_dir("muse")
    calls, primes = [], []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        calls.append((cmd, cwd, env))
        prime = Path(cmd[cmd.index("--append-system-prompt-file") + 1])
        primes.append(prime)
        assert "Charter of muse" in prime.read_text()
        if len(calls) == 1:
            (sd / "RESTART").touch()   # the first session hands off
        return 0

    monkeypatch.setattr(curia, "invoke_claude", fake)
    (sd / "RESTART").touch()           # stale, from some earlier session
    rc, out, err = cli(*E(estate), "launch", "muse", "--loop", "--say", "good evening")
    assert rc == 0, err
    assert "cleared a stale RESTART" in out and "relaunching" in out
    assert len(calls) == 2 and not (sd / "RESTART").exists()
    cmd, cwd, env = calls[0]
    assert cmd[:2] == ["claude", "--name"] and cmd[-1] == "good evening"
    assert "--session-id" in cmd and "--settings" in cmd and "--model" in cmd
    assert "PreCompact" in cmd[cmd.index("--settings") + 1]
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "acct-a") and env["CURIA_SEAT"] == "muse"
    assert cwd == estate.root
    assert all(not p.exists() for p in primes)   # temp primes are removed
    events = curia.session_events(sd)
    assert [e[0] for e in events] == ["start", "end", "start", "end"]
    sid = re.search(r"session=(\S+)", events[0][2]).group(1)
    assert sid == cmd[cmd.index("--session-id") + 1] and f"session={sid}" in events[1][2]
    assert "rc=0" in events[1][2]


def test_launch_in_a_repo_starts_there_and_refuses_fleet(curia, cli, estate, monkeypatch):
    monkeypatch.chdir(estate.root / "alpha" / "sub")
    rc, out, _ = cli(*E(estate), "launch", "muse", "--print-cmd")
    assert rc == 0 and f"cwd={estate.root / 'alpha' / 'sub'}" in out
    rc, out, _ = cli(*E(estate), "launch", "muse", "--print-cmd", "--repo", "alpha")
    assert f"cwd={estate.root / 'alpha'}" in out
    rc, _, err = cli(*E(estate), "launch", "worker")
    assert rc == 2 and "fleet seat" in err


def test_looped_launch_waits_out_a_spent_chain(curia, cli, estate, monkeypatch):
    sd = estate.seat_dir("muse")
    for acct in ("a", "b"):
        curia.mark_limited(estate, acct, curia.now() + dt.timedelta(hours=3))
    slept = []

    def fake_sleep(secs):
        slept.append(secs)
        for acct in ("a", "b"):
            curia.limit_marker(estate, acct).unlink(missing_ok=True)

    monkeypatch.setattr(curia.time, "sleep", fake_sleep)
    monkeypatch.setattr(curia, "invoke_claude", lambda cmd, cwd, env, timeout=None, capture=False, watch=None: 0)
    rc, out, err = cli(*E(estate), "launch", "muse", "--loop")
    assert rc == 0, err
    assert len(slept) == 1 and 3 * 3600 - 120 < slept[0] < 3 * 3600 + 120
    assert "waits until" in err
    assert [e[0] for e in curia.session_events(sd)] == ["wait", "start", "end"]


def test_ingest_goes_through_launch(cli, estate):
    rc, out, err = cli(*E(estate), "ingest", "--print-cmd", "--repo", "alpha")
    assert rc == 0, err
    assert "CURIA_SEAT=clerk" in out and f"cwd={estate.root / 'alpha'}" in out
    assert "file there unless" in out


# --------------------------------------------------------------------- run

def test_run_headless_records_the_session_and_orders_a_journal(curia, cli, estate, monkeypatch, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text('Review {repo} on {date}, {"json": 1}, {leaf}\n')
    seen = {}

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        assert capture and timeout == 3600
        prompt = cmd[cmd.index("-p") + 1]
        seen["prompt"] = prompt
        journal = Path(re.search(r"journal entry .*? to `([^`]+)`", prompt, re.S).group(1))
        journal.write_text("# 2026-01-01, reviewing alpha\nDid the thing; one nit remains.\n")
        prime = Path(cmd[cmd.index("--append-system-prompt-file") + 1]).read_text()
        assert "headless waking" in prime and str(journal) in prime and "Model: model-y" in prime
        assert cmd[cmd.index("--model") + 1] == "model-y"
        assert cmd[cmd.index("--allowedTools") + 1] == "Bash,Read,Edit,Write,Glob,Grep,Agent"
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "acct-a") and cwd == estate.root / "alpha"
        return completed(cmd, 0, result_json("All good."))

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "run", "muse", "--prompt", str(brief), "--repo", "alpha")
    assert rc == 0, err
    assert out.strip() == "All good."
    assert seen["prompt"].startswith(f'Review alpha on {curia.today()}, {{"json": 1}}, just test')
    sd = estate.seat_dir("muse")
    events = curia.session_events(sd)
    assert events[0][0] == "start" and "headless account=a model=model-y" in events[0][2]
    assert events[1][2] == "rc=0 session=sess-1 cost=$0.50 turns=7 minutes=2.0"
    logs = list((estate.dir / "brain" / "muse").iterdir())
    assert len(logs) == 1 and logs[0].read_text().startswith("All good.")
    assert "[rc=0 session=sess-1" in logs[0].read_text()
    # the next waking reads the journal
    prime = curia.build_prime(estate, "muse")
    assert "## Your journal" in prime and "one nit remains" in prime


def test_run_notes_a_missing_journal_and_a_failed_run(curia, cli, estate, monkeypatch, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("Do it.\n")
    monkeypatch.setattr(curia, "invoke_claude",
                        lambda cmd, cwd, env, timeout=None, capture=False, watch=None:
                        completed(cmd, 0, result_json("Forgot the journal.")))
    rc, out, err = cli(*E(estate), "run", "muse", "--prompt", str(brief))
    assert rc == 0 and "wrote no journal entry" in err
    assert "journal=missing" in curia.session_events(estate.seat_dir("muse"))[-1][2]
    monkeypatch.setattr(curia, "invoke_claude",
                        lambda cmd, cwd, env, timeout=None, capture=False, watch=None:
                        completed(cmd, 0, result_json("", is_error=True, subtype="error_during_execution",
                                                      errors=["it broke"])))
    rc, out, err = cli(*E(estate), "run", "muse", "--prompt", str(brief))
    assert rc == 1 and out.strip() == "it broke"
    # plain text from an older claude still comes through
    monkeypatch.setattr(curia, "invoke_claude",
                        lambda cmd, cwd, env, timeout=None, capture=False, watch=None:
                        completed(cmd, 0, "plain answer\n", "some warning"))
    rc, out, _ = cli(*E(estate), "run", "muse", "--prompt", str(brief))
    assert rc == 0 and out.startswith("plain answer") and "[stderr]" in out


def test_run_on_a_limit_marks_the_account_and_retries_down_the_chain(curia, cli, estate, monkeypatch, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("Do it.\n")
    seen = []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        seen.append(Path(env["CLAUDE_CONFIG_DIR"]).name)
        if env["CLAUDE_CONFIG_DIR"].endswith("acct-a"):
            return completed(cmd, 1, "", "You've hit your session limit · resets 4:30pm (Europe/London)")
        return completed(cmd, 0, result_json("Done on b", session_id="s2"))

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "run", "muse", "--prompt", str(brief))
    assert rc == 0, err
    assert out.strip() == "Done on b" and seen == ["acct-a", "acct-b"]
    assert "hit its limit" in err and "again on 'b'" in err
    until = curia.account_limited(estate, "a")
    assert until and until > curia.now()
    local = until.astimezone(ZoneInfo("Europe/London"))
    assert (local.hour, local.minute) == (16, 30)
    events = curia.session_events(estate.seat_dir("muse"))
    assert [e[0] for e in events] == ["start", "end", "start", "end"]
    assert "account=a" in events[0][2] and "rc=1" in events[1][2]
    assert "account=b" in events[2][2] and "session=s2" in events[3][2]


def test_run_with_the_whole_chain_spent_notifies_and_stops(curia, cli, estate, monkeypatch, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("Do it.\n")
    told = tmp_path / "told.txt"
    meta = (estate.dir / "estate.toml").read_text().replace(
        'notify = ""', f'notify = \'printf "%s|%s" "$CURIA_SUBJECT" "$CURIA_REPORT" > {told}\'')
    (estate.dir / "estate.toml").write_text(meta)
    monkeypatch.setattr(curia, "invoke_claude",
                        lambda cmd, cwd, env, timeout=None, capture=False, watch=None:
                        completed(cmd, 1, "", "You've hit your usage limit"))
    rc, out, err = cli(*E(estate), "run", "muse", "--prompt", str(brief))
    assert rc == 1
    assert curia.account_limited(estate, "a") and curia.account_limited(estate, "b")
    assert told.read_text().startswith("Muse: every account limited|")
    assert len([e for e in curia.session_events(estate.seat_dir("muse")) if e[0] == "start"]) == 2


def test_run_set_wants_key_equals_value(cli, estate, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("x {thing}\n")
    rc, _, err = cli(*E(estate), "run", "muse", "--prompt", str(brief), "--set", "nope")
    assert rc == 2 and "--set wants key=value" in err
    rc, out, _ = cli(*E(estate), "run", "muse", "--prompt", str(brief), "--set", "thing=a=b", "--print-cmd")
    assert rc == 0 and "prompt:" in out and "model-y" in out


# ---------------------------------------------------------------- offices

def test_censor_judges_the_last_completed_run(curia, cli, estate, monkeypatch):
    runs = {}
    monkeypatch.setattr(curia, "gh_json", lambda args: runs.get("value"))
    woken = []

    def fake_run(est, name, s, prompt, cwd, timeout, skip, model=None):
        woken.append((name, prompt, cwd))
        return curia.HeadlessResult(text="fixed forward", accounts=["a"])

    monkeypatch.setattr(curia, "run_headless", fake_run)
    running = {"status": "in_progress", "conclusion": None, "url": "u0", "createdAt": "", "headSha": "h0"}
    green = {"status": "completed", "conclusion": "success", "url": "u1", "createdAt": "", "headSha": "h1"}
    red = {"status": "completed", "conclusion": "failure", "url": "u2", "createdAt": "", "headSha": "h2"}

    runs["value"] = [running, green]
    rc, out, _ = cli(*E(estate), "censor")
    assert rc == 0 and not woken and "a newer run is in_progress" in out and "success" in out
    assert (estate.dir / "brain" / "censor" / f"{curia.today()}.md").exists()

    runs["value"] = [running]
    rc, out, _ = cli(*E(estate), "censor")
    assert not woken and "no completed run" in out

    runs["value"] = [running, red]
    rc, out, _ = cli(*E(estate), "censor")
    assert len(woken) == 1 and "-> Censor woke" in out and "fixed forward" in out
    name, prompt, cwd = woken[0]
    assert name == "warden" and cwd == estate.root / "alpha"
    assert "`main` of alpha is failure at u2 (head h2)" in prompt
    assert "Censor woke on 1 repo(s)" in out

    report = estate.dir / "brain" / "censor" / f"{curia.today()}.md"
    before = report.read_text()
    rc, out, _ = cli(*E(estate), "censor", "--dry-run")
    assert len(woken) == 1 and "(dry run)" in out and "written" not in out
    assert report.read_text() == before   # a dry run leaves the day's report alone


def test_lictor_write_notifies(curia, cli, estate, monkeypatch, tmp_path):
    told = tmp_path / "told.txt"
    meta = (estate.dir / "estate.toml").read_text().replace(
        'notify = ""', f'notify = \'printf "%s|%s" "$CURIA_SUBJECT" "$CURIA_REPORT" > {told}\'')
    (estate.dir / "estate.toml").write_text(meta)
    monkeypatch.setattr(curia, "gh_json", lambda args: None)
    old = (curia.now() - dt.timedelta(days=5)).isoformat()
    (estate.root / "alpha" / ".beads" / "issues.jsonl").write_text(
        json.dumps({"id": "al-1", "status": "in_progress", "updated_at": old, "title": "stuck"}) + "\n")
    rc, out, err = cli(*E(estate), "lictor", "--write")
    assert rc == 0, err
    path = Path(out.split("written ", 1)[1].strip())
    assert "STALE in_progress al-1" in path.read_text()
    assert told.read_text() == f"Lictor: 1 nudge(s)|{path}"


def test_notify_failure_is_reported_not_fatal(curia, cli, estate, monkeypatch):
    meta = (estate.dir / "estate.toml").read_text().replace('notify = ""', 'notify = "exit 3"')
    (estate.dir / "estate.toml").write_text(meta)
    monkeypatch.setattr(curia, "gh_json", lambda args: None)
    rc, out, err = cli(*E(estate), "lictor", "--write")
    assert rc == 0 and "notify command failed (rc=3)" in err


# ------------------------------------------------------------ check, status

def test_check_reports_problems_and_notes(curia, cli, estate, monkeypatch):
    monkeypatch.setattr(curia.shutil, "which", lambda name: f"/bin/{name}")
    rc, out, err = cli(*E(estate), "check")
    assert rc == 1 and "skills not linked" in out   # nothing has launched yet
    for acct in ("a", "b"):
        curia.ensure_skills(curia.account_dir(estate, acct))
    rc, out, err = cli(*E(estate), "check")
    assert rc == 0, out + err
    assert "consistent" in out and "  - " not in out
    sd = estate.seat_dir("muse")
    (sd / "RESTART").touch()
    curia.log_session(estate.seat_dir("warden"), "start", "account=a cwd=/x session=1")
    curia.log_session(estate.seat_dir("warden"), "end", "rc=0 session=1")
    curia.log_session(estate.seat_dir("clerk"), "start", "headless account=a model=m cwd=/x")
    curia.log_session(estate.seat_dir("clerk"), "end", "rc=0")
    curia.mark_limited(estate, "b", curia.now() + dt.timedelta(hours=1))
    rc, out, _ = cli(*E(estate), "check")
    assert rc == 0
    assert "- seat muse: stale RESTART marker" in out
    assert "- seat warden: 1 interactive session(s) and no handoff written" in out
    assert "- seat clerk: 1 headless waking(s) and no journal entry" in out
    assert "- account b: limited until" in out
    (estate.seat_dir("worker") / "charter.md").unlink()
    (estate.dir / "prompts" / "lictor-cloud.md").write_text("Fill in for this estate: everything.\n")
    rc, out, _ = cli(*E(estate), "check")
    assert rc == 1
    assert "! seat worker: no charter.md" in out and "! prompts/lictor-cloud.md still carries template text" in out
    assert "- seat muse: stale RESTART marker" in out   # notes still shown under problems


def test_status_shows_who_is_awake(curia, cli, estate):
    curia.log_session(estate.seat_dir("muse"), "start", "headless account=a model=m cwd=/x")
    curia.log_session(estate.seat_dir("warden"), "start", "account=a cwd=/x session=1")
    curia.log_session(estate.seat_dir("warden"), "end", "rc=0 session=1")
    (estate.seat_dir("warden") / "RESTART").touch()
    (estate.seat_dir("warden") / "handoff.md").write_text(FULL_HANDOFF)
    curia.log_session(estate.seat_dir("clerk"), "wait", "every account limited until x")
    (estate.dir / "brain" / "censor").mkdir(parents=True)
    (estate.dir / "brain" / "censor" / "2026-01-01.md").write_text(
        "# Censor report\n- x: hit your session limit\n\nCensor woke on 1 repo(s). Reports...\n")
    rc, out, err = cli(*E(estate), "status")
    assert rc == 0, err
    lines = {line.split()[0]: line for line in out.splitlines() if line.startswith("  ")}
    assert "headless since" in lines["Muse"] and "journal none" in lines["Muse"]
    assert "asleep; last woke" in lines["Warden"] and "rc 0" in lines["Warden"]
    assert "RESTART pending" in lines["Warden"] and "handoff 0h ago" in lines["Warden"]
    assert "waiting for a limit" in lines["Clerk"]
    assert "never woken" in lines["Worker"]
    assert lines["a"].split()[1] == "ok" and "fallback=b" in lines["a"]
    assert "Censor woke on 1 repo(s); mentions a limit" in lines["censor"]
    assert "no report written" in lines["lictor"]


# ------------------------------------------------------------------ rename

def test_rename_keeps_the_seat_memory(curia, cli, estate):
    sd = estate.seat_dir("muse")
    (sd / "handoff.md").write_text(FULL_HANDOFF)
    rc, out, err = cli(*E(estate), "rename", "muse", "erato")
    assert rc == 0, err
    fresh = curia.Estate(estate.dir)
    name, s = fresh.seat("erato")
    assert s["title"] == "Erato" and s["run_model"] == "model-y"
    assert not sd.exists() and (fresh.seat_dir("erato") / "handoff.md").read_text() == FULL_HANDOFF
    assert "Renamed from Muse" in (fresh.seat_dir("erato") / "charter.md").read_text()
    assert curia.session_events(fresh.seat_dir("erato"))[-1][0] == "rename"
    rc, _, err = cli(*E(estate), "rename", "warden", "erato")
    assert rc == 2 and "already exists" in err


# ---------------------------------------------------------------- registry

def other_estate(cli, tmp_path, name, roster="", accounts=""):
    """A second registered estate beside the fixture's, with the roster and
    accounts given (else the template's)."""
    rc, _, err = cli("init", str(tmp_path / name.lower()), "--name", name, "--principal", "X")
    assert rc == 0, err
    cd = tmp_path / name.lower() / "curia"
    if roster:
        (cd / "roster.toml").write_text(roster)
    if accounts:
        (cd / "accounts.toml").write_text(accounts)
    return cd.resolve()


def test_a_seat_name_finds_its_estate_in_the_registry(curia, cli, estate, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CURIA_ESTATE", raising=False)
    other = other_estate(cli, tmp_path, "Other",
                         roster='[seats.oracle]\ntitle = "Oracle"\nkind = "crew"\nmodel = "m"\naccount = "main"\n')
    assert curia.find_estate(None, "muse").dir == estate.dir
    assert curia.find_estate(None, "Oracle").dir == other
    rc, out, err = cli("prime", "muse")
    assert rc == 0, err
    rc, _, err = cli("prime", "nobody")
    assert rc == 2 and "no registered estate" in err
    # an office command from outside any workspace has no seat to go by: stop
    rc, _, err = cli("roster")
    assert rc == 2 and "more than one estate is registered" in err
    # a seat on both estates is ambiguous, not a guess
    (other / "roster.toml").write_text('[seats.muse]\ntitle = "Muse"\nkind = "crew"\nmodel = "m"\naccount = "main"\n')
    rc, _, err = cli("prime", "muse")
    assert rc == 2 and "more than one registered estate" in err
    # inside a workspace the walk up still wins
    monkeypatch.chdir(estate.root / "alpha")
    assert curia.find_estate(None, "muse").dir == estate.dir
    rc, _, err = cli("roster")
    assert rc == 0, err


def test_check_notes_an_account_pooled_across_estates(cli, estate, tmp_path):
    other_estate(cli, tmp_path, "Other", accounts=f'[accounts.pool]\nconfig_dir = "{tmp_path / "acct-b"}"\n')
    rc, out, _ = cli(*E(estate), "check")
    assert "account b: its config dir is also account 'pool' of estate 'other'" in out
    assert "account a: its config dir is also" not in out


# -------------------------------------------------------------------- init

def test_init_refuses_a_registered_name(curia, cli, estate, tmp_path):
    rc, _, err = cli("init", str(tmp_path / "elsewhere"), "--name", "Scratch", "--principal", "X")
    assert rc == 2 and "already registered" in err
    assert not (tmp_path / "elsewhere").exists()
    rc, out, err = cli("init", str(tmp_path / "elsewhere"), "--name", "Second", "--principal", "X")
    assert rc == 0, err
    assert (tmp_path / "elsewhere" / "curia" / "estate.toml").exists()
    assert "[estates.second]" in curia.ESTATES_FILE.read_text()


# -------------------------------------------------------------------- hook

def test_precompact_hook_refuses_manual_compaction_unless_allowed(cli, estate, monkeypatch):
    monkeypatch.setenv("CURIA_SEAT", "muse")
    monkeypatch.setenv("CURIA_ESTATE", str(estate.dir))
    rc, _, err = cli("hook", "precompact", stdin='{"trigger": "manual"}')
    assert rc == 2 and "/handoff" in err and "COMPACT-OK" in err
    ok = estate.seat_dir("muse") / "COMPACT-OK"
    ok.touch()
    rc, _, err = cli("hook", "precompact", stdin='{"trigger": "manual"}')
    assert rc == 0 and not ok.exists()
    rc, _, _ = cli("hook", "precompact", stdin='{"trigger": "auto"}')
    assert rc == 0
    monkeypatch.delenv("CURIA_SEAT")
    rc, _, _ = cli("hook", "precompact", stdin='{"trigger": "manual"}')
    assert rc == 0
    rc, _, err = cli("hook", "nonsense")
    assert rc == 2 and "no hook" in err


# -------------------------------------------------------------------- help

def test_help_covers_every_command(curia, cli):
    rc, _, err = cli("no-such-command")
    names = re.findall(r"'([a-z]+)'", err.split("choose from", 1)[1])
    assert len(names) >= 15
    for name in names:
        assert name in curia.HELP_DETAIL, f"no `curia help {name}` page"
        if name != "help":   # the overview's closing line covers `help` itself
            assert re.search(rf"^  {name}\b", curia.HELP_OVERVIEW, re.M), f"{name} not in the overview"
        rc, out, _ = cli("help", name)
        assert rc == 0 and curia.HELP_DETAIL[name].splitlines()[0][:30] in out
    rc, out, _ = cli("help")
    assert rc == 0 and out.strip() == curia.HELP_OVERVIEW.strip()


def test_prime_reads_the_last_three_journal_entries(curia, estate):
    jd = estate.seat_dir("muse") / "journal"
    jd.mkdir()
    for i in range(1, 5):
        (jd / f"2026-01-0{i}T000000Z-alpha.md").write_text(f"entry {i}\n")
    prime = curia.build_prime(estate, "muse")
    assert "entry 1" not in prime and all(f"entry {i}" in prime for i in (2, 3, 4))
    assert prime.rstrip().endswith("use /handoff, not /exit.")
    assert "the one concern" in prime and "| Warden |" in prime


# -------------------------------------------------------------------- mail

def test_mail_is_read_at_waking_and_archived_by_the_reader(curia, cli, estate, monkeypatch):
    monkeypatch.delenv("CURIA_SEAT", raising=False)
    rc, out, err = cli(*E(estate), "mail", "muse", "the brief is in the bead")
    assert rc == 0, err
    assert "mail left for muse" in out
    mp = estate.seat_dir("muse") / "mail.md"
    assert re.match(r"- \d{4}-\d{2}-\d{2} from Nobody Inparticular: the brief is in the bead\n", mp.read_text())
    prime = curia.build_prime(estate, "muse")
    assert "## Mail (unread)" in prime and "the brief is in the bead" in prime
    assert "curia mail muse --archive" in prime
    # a seat signs with its title, and a broadcast does not come back to it
    monkeypatch.setenv("CURIA_SEAT", "warden")
    rc, out, _ = cli(*E(estate), "mail", "--all", "release is frozen")
    assert rc == 0 and "warden" not in out.split("mail left for")[1]
    assert "from Warden: release is frozen" in mp.read_text()
    assert "release is frozen" in (estate.seat_dir("worker") / "mail.md").read_text()
    assert not (estate.seat_dir("warden") / "mail.md").exists()
    rc, out, _ = cli(*E(estate), "mail", "muse")
    assert "the brief is in the bead" in out and "release is frozen" in out
    rc, out, _ = cli(*E(estate), "mail", "muse", "--archive")
    assert rc == 0 and not mp.exists()
    archived = list((estate.seat_dir("muse") / "history").glob("mail-*.md"))
    assert len(archived) == 1 and "release is frozen" in archived[0].read_text()
    assert "## Mail" not in curia.build_prime(estate, "muse")
    rc, out, _ = cli(*E(estate), "mail", "muse", "--archive")
    assert "no mail" in out
    rc, _, err = cli(*E(estate), "mail", "--all")
    assert rc == 2 and "wants the text" in err


# --------------------------------------------------- envelope, hooks, fences

def test_launch_and_run_carry_the_envelope_and_the_estate_fences(curia, cli, estate, monkeypatch):
    (estate.dir / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "curia hook release-guard"}]}]}}))
    roster = (estate.dir / "roster.toml").read_text().replace(
        'tools = ["Bash", "Read"]\n', 'tools = ["Bash", "Read"]\ndisallowed_tools = ["WebFetch"]\n')
    (estate.dir / "roster.toml").write_text(roster)
    seen = {}

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        seen["cmd"] = cmd
        return completed(cmd, 0, result_json("ok")) if capture else 0

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, _, err = cli(*E(estate), "launch", "warden")
    assert rc == 0, err
    cmd = seen["cmd"]
    settings = json.loads(cmd[cmd.index("--settings") + 1])
    assert "PreCompact" in settings["hooks"] and settings["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
    assert cmd[cmd.index("--allowedTools") + 1] == "Bash,Read"
    assert cmd[cmd.index("--disallowedTools") + 1] == "WebFetch"
    start = curia.session_events(estate.seat_dir("warden"))[0][2]
    assert "model=model-x" in start and f"pid={os.getpid()}" in start
    # a seat that names no tools gets the account's own permissions interactively
    rc, _, _ = cli(*E(estate), "launch", "muse")
    assert "--allowedTools" not in seen["cmd"] and "--disallowedTools" not in seen["cmd"]
    # headless: the roster's list (or the default), plus the fence, plus the hooks
    (estate.dir / "prompts" / "b.md").write_text("do\n")
    rc, _, err = cli(*E(estate), "run", "warden", "--prompt", "b.md")
    assert rc == 0, err
    cmd = seen["cmd"]
    assert cmd[cmd.index("--allowedTools") + 1] == "Bash,Read"
    assert cmd[cmd.index("--disallowedTools") + 1] == "WebFetch"
    assert "PreToolUse" in cmd[cmd.index("--settings") + 1]
    sid = cmd[cmd.index("--session-id") + 1]
    events = curia.session_events(estate.seat_dir("warden"))
    assert events[-2][0] == "start" and f"session={sid}" in events[-2][2] and f"pid={os.getpid()}" in events[-2][2]
    rc, out, _ = cli(*E(estate), "run", "warden", "--prompt", "b.md", "--print-cmd")
    assert "--disallowedTools WebFetch" in out and "1 estate hook(s)" in out
    rc, out, _ = cli(*E(estate), "launch", "warden", "--print-cmd")
    assert "--disallowedTools WebFetch" in out and "1 estate hook(s)" in out
    # a broken hooks.json refuses a launch and fails the check
    (estate.dir / "hooks.json").write_text("{not json")
    rc, _, err = cli(*E(estate), "launch", "warden")
    assert rc == 2 and "not valid JSON" in err
    monkeypatch.setattr(curia.shutil, "which", lambda name: f"/bin/{name}")
    rc, out, _ = cli(*E(estate), "check")
    assert rc == 1 and "hooks.json is not valid JSON" in out


def test_release_guard_refuses_a_push_that_names_a_release_branch(cli, estate, monkeypatch):
    monkeypatch.setenv("CURIA_SEAT", "muse")
    monkeypatch.setenv("CURIA_ESTATE", str(estate.dir))

    def payload(command, tool="Bash"):
        return json.dumps({"tool_name": tool, "tool_input": {"command": command}})

    # alpha releases from main, its integration branch, so nothing is fenced yet
    rc, _, _ = cli("hook", "release-guard", stdin=payload("git push origin main"))
    assert rc == 0
    repos = (estate.dir / "repos.toml").read_text().replace('release_branch = "main"', 'release_branch = "release"')
    (estate.dir / "repos.toml").write_text(repos)
    rc, _, err = cli("hook", "release-guard", stdin=payload("git push origin HEAD:release"))
    assert rc == 2 and "never pushes to `release`" in err and "alpha" in err
    rc, _, _ = cli("hook", "release-guard", stdin=payload("git push --force origin release"))
    assert rc == 2
    for harmless in ("git push origin muse/al-1", "git push origin release-notes", "git log release",
                     "echo release && git status"):
        rc, _, _ = cli("hook", "release-guard", stdin=payload(harmless))
        assert rc == 0, harmless
    rc, _, _ = cli("hook", "release-guard", stdin=payload("git push origin release", tool="Read"))
    assert rc == 0
    monkeypatch.delenv("CURIA_SEAT")
    rc, _, _ = cli("hook", "release-guard", stdin=payload("git push origin release"))
    assert rc == 0


# ----------------------------------------------------------------- rulings

def test_rulings_have_a_lifecycle_and_the_lictor_closes_the_loops(curia, cli, estate, monkeypatch):
    rd = estate.dir / "brain" / "rulings"
    old = (curia.now() - dt.timedelta(days=30)).strftime("%Y-%m-%d")
    (rd / f"{old}-no-force-push.md").write_text("# Ruling\n\nstatus: enacted\nenforced by: nothing yet\n\nCites al-7.\n")
    (rd / f"{old}-tests-first.md").write_text("status: enforced\nenforced by: hooks.json release-guard\n")
    (rd / f"{curia.today()}-fresh.md").write_text("status: enacted\nenforced by: -\n")
    (rd / f"{old}-lost.md").write_text("# no status here\n")
    (rd / f"{old}-dated-header.md").write_text("# Ruling\n\nDate: 2026-01-01. Status: enforced. Ruled by: the principal.\n\nEnforced by: a test\n")
    rc, out, _ = cli(*E(estate), "rulings")
    assert rc == 0
    assert re.search(rf"{old}  enacted   {old}-no-force-push\s+enforced by: -", out)
    assert "enforced  " in out and "hooks.json release-guard" in out and "NO STATUS" in out
    assert re.search(rf"enforced  {old}-dated-header\s+enforced by: a test", out)
    monkeypatch.setattr(curia.shutil, "which", lambda name: f"/bin/{name}")
    for acct in ("a", "b"):
        curia.ensure_skills(curia.account_dir(estate, acct))
    rc, out, _ = cli(*E(estate), "check")
    assert rc == 1 and f"! ruling {old}-lost: no `status:` line" in out
    assert f"- ruling {old}-no-force-push: enacted with nothing enforcing it" in out
    (rd / f"{old}-lost.md").write_text("status: retired\nenforced by: -\nfalsified\n")
    (rd / f"{old}-tests-first.md").write_text("status: enforced\n")
    rc, out, _ = cli(*E(estate), "check")
    assert rc == 1 and f"! ruling {old}-tests-first: status enforced, but no `enforced by:`" in out
    (rd / f"{old}-tests-first.md").write_text("status: bogus\n")
    rc, out, _ = cli(*E(estate), "check")
    assert "status 'bogus' is not one of" in out
    # the lictor: an old enacted ruling nothing enforces, a postmortem no ruling cites
    monkeypatch.setattr(curia, "gh_json", lambda args: None)
    since = (curia.now() - dt.timedelta(days=10)).isoformat()
    (estate.root / "alpha" / ".beads" / "issues.jsonl").write_text("\n".join(json.dumps(x) for x in [
        {"id": "al-7", "status": "open", "labels": ["postmortem"], "created_at": since, "title": "cited"},
        {"id": "al-8", "status": "open", "labels": ["postmortem"], "created_at": since, "title": "uncited"},
        {"id": "al-9", "status": "closed", "labels": ["postmortem"], "created_at": since, "title": "closed"},
        {"id": "al-10", "status": "open", "labels": ["postmortem"], "created_at": curia.now().isoformat(),
         "title": "new"},
    ]) + "\n")
    rc, out, _ = cli(*E(estate), "lictor")
    assert rc == 0
    assert f"- UNENFORCED ruling {old}-no-force-push" in out and f"{curia.today()}-fresh" not in out
    assert "- UNRULED postmortem al-8 (10d): uncited" in out
    alpha = out.split("## alpha")[1]
    assert "al-7" not in alpha and "al-9" not in alpha and "al-10" not in alpha
    rc, out, _ = cli(*E(estate), "lictor", "--postmortem-days", "30", "--ruling-days", "60")
    assert "UNRULED" not in out and "UNENFORCED" not in out


# ------------------------------------------------------------ status, reap

def test_status_totals_spend_and_reap_closes_orphans(curia, cli, estate):
    sd = estate.seat_dir("muse")
    curia.log_session(sd, "start", "headless account=a model=m cwd=/x session=s1 pid=99999999")
    curia.log_session(sd, "end", "rc=0 session=s1 cost=$0.50 turns=7 minutes=2.0")
    curia.log_session(sd, "start", f"headless account=b model=m cwd=/x session=s2 pid={os.getpid()}")
    curia.log_session(sd, "end", "rc=0 session=s2 cost=$1.25 turns=3 minutes=1.0")
    curia.log_session(sd, "start", "headless account=a model=m cwd=/x session=s3 pid=99999999")
    wd = estate.seat_dir("warden")
    curia.log_session(wd, "start", f"account=a cwd=/x session=s4 pid={os.getpid()}")
    rc, out, err = cli(*E(estate), "status")
    assert rc == 0, err
    lines = {line.split()[0]: line for line in out.splitlines() if line.startswith("  ")}
    assert "orphaned; launcher pid 99999999 gone" in lines["Muse"] and "mail 0" in lines["Muse"]
    assert "awake since" in lines["Warden"]
    assert re.search(r"account  a\s+wakings 1\s+\$0\.50\s+turns 7\s+minutes 2", out)
    assert re.search(r"account  b\s+wakings 1\s+\$1\.25", out)
    assert re.search(r"seat     Muse\s+wakings 2\s+\$1\.75\s+turns 10\s+minutes 3", out)
    rc, out, _ = cli(*E(estate), "check")
    assert "- seat muse: a session from" in out and "`curia reap` closes the record" in out
    rc, out, _ = cli(*E(estate), "reap", "--dry-run")
    assert rc == 0 and "would close" in out and "pid 99999999" in out
    assert curia.session_events(sd)[-1][0] == "start"
    rc, out, _ = cli(*E(estate), "reap")
    assert "record closed" in out
    events = curia.session_events(sd)
    assert events[-1][0] == "end" and "reaped: launcher pid 99999999 gone" in events[-1][2]
    assert "session=s3" in events[-1][2]
    assert not curia.open_sessions(sd)
    assert curia.open_sessions(wd)   # a live launcher is left alone
    rc, out, _ = cli(*E(estate), "reap")
    assert "nothing to reap" in out


# ------------------------------------------------------------------- fleet

def git_repo(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    (path / "README").write_text("hello\n")
    git_commit(path, "init")


def git_commit(path, message):
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(path)]
    subprocess.run([*g, "add", "."], check=True)
    subprocess.run([*g, "commit", "-q", "-m", message], check=True)


def branch_of(path):
    return subprocess.run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def test_dispatch_gives_a_worker_a_home_and_reap_takes_it_back_once_landed(curia, cli, estate, monkeypatch):
    src = estate.root / "alpha"
    git_repo(src)
    monkeypatch.setenv("CURIA_SEAT", "muse")   # the office dispatching
    seen = []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        seen.append((cmd, cwd, env))
        (cwd / "work.txt").write_text(f"done {len(seen)}\n")
        git_commit(cwd, "work")
        return completed(cmd, 0, result_json("implemented", session_id=cmd[cmd.index("--session-id") + 1]))

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, _, err = cli(*E(estate), "dispatch", "muse", "--bead", "al-1", "--repo", "alpha")
    assert rc == 2 and "dispatch is for fleet" in err
    wt = estate.root / "worktrees" / "worker" / "alpha"
    rc, out, err = cli(*E(estate), "dispatch", "worker", "--bead", "al-1", "--repo", "alpha", "--print-cmd")
    assert rc == 0, err
    assert f"worktree {wt} on branch worker/al-1 off main" in out and not wt.exists()
    rc, out, err = cli(*E(estate), "dispatch", "worker", "--bead", "al-1", "--repo", "alpha", "--review", "muse")
    assert rc == 0, err
    assert len(seen) == 2
    cmd, cwd, env = seen[0]
    assert cwd == wt and env["CURIA_SEAT"] == "worker"
    prompt = cmd[cmd.index("-p") + 1]
    assert "implement bead al-1 in alpha" in prompt and f"`{wt}`" in prompt
    assert "on branch `worker/al-1` off `main`" in prompt and "just test" in prompt
    rcmd, rcwd, renv = seen[1]
    assert rcwd == wt and renv["CURIA_SEAT"] == "muse"
    rprompt = rcmd[rcmd.index("-p") + 1]
    assert "reviewing bead al-1 as implemented by Worker" in rprompt and "--add-label reviewed" in rprompt
    assert "--- review by Muse ---" in out and "implemented" in out
    assert branch_of(wt) == "worker/al-1"
    log = (estate.seat_dir("worker") / "assignments.log").read_text()
    assert [line.split()[0] for line in log.splitlines()] == ["dispatch", "returned", "reviewed"]
    assert "bead=al-1 repo=alpha branch=worker/al-1" in log and "by=Muse" in log
    # a second job reuses the home on a new branch; a dirty home is refused
    rc, _, err = cli(*E(estate), "dispatch", "worker", "--bead", "al-2", "--repo", "alpha")
    assert rc == 0, err
    assert branch_of(wt) == "worker/al-2"
    (wt / "dirty.txt").write_text("x")
    rc, _, err = cli(*E(estate), "dispatch", "worker", "--bead", "al-3", "--repo", "alpha")
    assert rc == 2 and "uncommitted work" in err
    (wt / "dirty.txt").unlink()
    # reap: not landed, leave it; landed, remove it with its branch
    rc, out, _ = cli(*E(estate), "reap")
    assert "not landed; leaving it" in out and wt.exists()
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(src), "merge", "-q", "worker/al-2"],
                   check=True)
    rc, out, _ = cli(*E(estate), "reap", "--dry-run")
    assert "has landed; would remove it" in out and wt.exists()
    rc, out, _ = cli(*E(estate), "reap")
    assert "; removed" in out and not wt.exists()
    assert (estate.seat_dir("worker") / "assignments.log").read_text().splitlines()[-1].startswith("reap ")
    branches = subprocess.run(["git", "-C", str(src), "branch"], capture_output=True, text=True).stdout
    assert "worker/al-2" not in branches and "worker/al-1" in branches


# -------------------------------------------------------------- portcullis

def test_portcullis_lands_reviewed_green_prs_and_closes_their_beads(curia, cli, estate, monkeypatch, tmp_path):
    told = tmp_path / "told.txt"
    meta = (estate.dir / "estate.toml").read_text().replace(
        'notify = ""', f'notify = \'printf "%s|%s" "$CURIA_SUBJECT" "$CURIA_BODY" > {told}\'')
    (estate.dir / "estate.toml").write_text(meta)
    ok = [{"name": "ci", "conclusion": "SUCCESS", "status": "COMPLETED"}]

    def pr(n, title, head, **kw):
        d = {"number": n, "title": title, "headRefName": head, "isDraft": False, "reviewDecision": "APPROVED",
             "statusCheckRollup": ok, "labels": [], "mergeable": "MERGEABLE", "url": f"u{n}"}
        d.update(kw)
        return d

    prs = [
        pr(1, "al-1: labelled", "worker/al-1", reviewDecision=None, labels=[{"name": "reviewed"}]),
        pr(2, "al-2: approved", "worker/al-2"),
        pr(3, "al-3: unreviewed", "worker/al-3", reviewDecision="REVIEW_REQUIRED"),
        pr(4, "al-4: red", "worker/al-4", statusCheckRollup=[{"name": "ci", "conclusion": "FAILURE", "status": "COMPLETED"}]),
        pr(5, "al-5: pending", "worker/al-5", statusCheckRollup=[{"name": "ci", "conclusion": None, "status": "IN_PROGRESS"}]),
        pr(6, "al-6: draft", "worker/al-6", isDraft=True),
        pr(7, "al-7: conflicts", "worker/al-7", mergeable="CONFLICTING"),
        pr(8, "a human's PR", "feature/x"),
        pr(9, "al-9: no checks", "worker/al-9", statusCheckRollup=[]),
    ]
    monkeypatch.setattr(curia, "gh_json", lambda args: prs if args[:2] == ["pr", "list"] else None)
    merged, closed = [], []

    def fake_gh(args):
        merged.append(args)
        return completed(args, 1 if args[2] == "2" else 0, "", "merge blocked" if args[2] == "2" else "")

    monkeypatch.setattr(curia, "gh_run", fake_gh)
    monkeypatch.setattr(curia, "bd_close", lambda repo, bead: closed.append((repo, bead)) or f"{bead} closed")
    rc, out, _ = cli(*E(estate), "portcullis", "--dry-run")
    assert rc == 0 and not merged and "-> would land" in out and "(dry run)" in out
    assert not (estate.dir / "brain" / "portcullis").exists()
    rc, out, err = cli(*E(estate), "portcullis")
    assert rc == 0, err
    assert [m[2] for m in merged] == ["1", "2"] and merged[0][:2] == ["pr", "merge"]
    assert "--squash" in merged[0] and "--delete-branch" in merged[0]
    assert closed == [(estate.root / "alpha", "al-1")]
    assert "#1 al-1 `worker/al-1`: green, reviewed, mergeable -> landed (squash); al-1 closed" in out
    assert "#2 al-2" in out and "merge FAILED: merge blocked" in out
    assert "#3 al-3 `worker/al-3`: unreviewed" in out
    assert "#4 al-4 `worker/al-4`: checks red (ci)" in out
    assert "#5 al-5 `worker/al-5`: checks pending (ci)" in out
    assert "#6 al-6 `worker/al-6`: draft" in out
    assert "#7 al-7 `worker/al-7`: conflicts" in out
    assert "#9 al-9 `worker/al-9`: no checks reported" in out
    assert "#8" not in out and "## nested" not in out
    assert "Landed 1, held 6, failed 1" in out
    assert len(list((estate.dir / "brain" / "portcullis").glob("*.md"))) == 1
    assert told.read_text().startswith("Portcullis: landed 1, failed 1|")
    rc, out, _ = cli(*E(estate), "status")
    assert "Landed 1, held 6" in out
    # nothing at the gate: nothing recorded, nobody told
    told.unlink()
    monkeypatch.setattr(curia, "gh_json", lambda args: [] if args[:2] == ["pr", "list"] else None)
    rc, out, _ = cli(*E(estate), "portcullis")
    assert rc == 0 and "names a bead" in out and "written" not in out and not told.exists()


def test_init_stamps_the_mechanism_into_the_estate_fences(curia, cli, estate, tmp_path):
    rc, _, err = cli("init", str(tmp_path / "third"), "--name", "Third", "--principal", "X")
    assert rc == 0, err
    cd = tmp_path / "third" / "curia"
    hooks = json.loads((cd / "hooks.json").read_text())
    assert hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == f"{curia.MECHANISM_DIR}/bin/curia hook release-guard"
    assert (cd / "brain" / "rulings").is_dir()
    assert (cd / "prompts" / "dispatch.md").exists() and (cd / "prompts" / "review.md").exists()
    assert "portcullis" in (cd / "launchd" / "portcullis.plist").read_text()


# ---------------------------------------------------------------- rotation

def statusline_payload(sid="sess-1", five=(23.4, 3600), seven=(41.2, 86400), cost=1.25, duration=7200000):
    t = int(time.time())
    return json.dumps({"session_id": sid,
                       "rate_limits": {"five_hour": {"used_percentage": five[0], "resets_at": t + five[1]},
                                       "seven_day": {"used_percentage": seven[0], "resets_at": t + seven[1]}},
                       "cost": {"total_cost_usd": cost, "total_duration_ms": duration}})


def as_seat(monkeypatch, estate, seat, cfg):
    monkeypatch.setenv("CURIA_SEAT", seat)
    monkeypatch.setenv("CURIA_ESTATE", str(estate.dir))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))


def test_usage_hook_records_the_account_reading_and_the_session_cost(curia, cli, estate, monkeypatch, tmp_path):
    as_seat(monkeypatch, estate, "muse", tmp_path / "acct-a")
    rc, out, _ = cli("hook", "usage", stdin=statusline_payload())
    assert rc == 0, out
    assert out.startswith("Muse | a | 5h 23% resets ") and "7d 41%" in out and "$1.25" in out and "2h00m" in out
    reading = curia.usage_reading(tmp_path / "acct-a")
    assert reading["seat"] == "muse" and reading["account"] == "a"
    assert reading["five_hour"]["used_percentage"] == 23.4
    used, resets, window = curia.worst_window(reading)
    assert (used, window) == (41.2, "seven_day") and resets > curia.now()
    sess = curia.session_usage(tmp_path / "acct-a", "sess-1")
    assert sess["cost_usd"] == 1.25 and sess["duration_ms"] == 7200000
    # a window whose reset has passed has emptied; no reading is no window
    gone = {"five_hour": {"used_percentage": 99, "resets_at": int(time.time()) - 5}}
    assert curia.worst_window(gone) == (None, None, "") and curia.worst_window(None) == (None, None, "")
    rc, out, _ = cli("hook", "usage", stdin="not json")
    assert rc == 0 and out.startswith("Muse | a")   # a bare bar, and the reading is still whole


def test_launch_rotates_on_measured_headroom_and_keeps_dedicated_accounts(curia, cli, estate, monkeypatch, tmp_path):
    def reading(acct, used, resets_in=3600):
        curia.write_json(curia.usage_path(tmp_path / f"acct-{acct}"),
                         {"at": curia.now().isoformat(), "seat": "x",
                          "five_hour": {"used_percentage": used, "resets_at": int(time.time()) + resets_in}})

    assert curia.walk_chain(estate, "a", "a") == ("a", [])
    reading("a", 75)                        # past rotate_at: the next account with headroom
    assert curia.walk_chain(estate, "a", "a")[0] == "b"
    reading("b", 80)                        # both past it: the emptiest
    assert curia.walk_chain(estate, "a", "a")[0] == "a"
    reading("a", 96)                        # measured full: limited until the window resets, marker or none
    free, limited = curia.walk_chain(estate, "a", "a")
    assert free == "b" and [n for n, _ in limited] == ["a"] and limited[0][1] > curia.now()
    rc, out, err = cli(*E(estate), "launch", "muse", "--print-cmd")
    assert rc == 0 and "acct-b" in out and "account 'a' limited until" in err
    reading("a", 96, resets_in=-5)          # that window has reset since: empty again
    assert curia.walk_chain(estate, "a", "a")[0] == "a"
    # the thresholds are the estate's
    (estate.dir / "estate.toml").write_text((estate.dir / "estate.toml").read_text().replace("rotate_at = 70", "rotate_at = 10"))
    reading("a", 20)
    reading("b", 5)
    assert curia.walk_chain(curia.Estate(estate.dir), "a", "a")[0] == "b"
    # a dedicated account is only ever its own seats'
    accounts = (estate.dir / "accounts.toml").read_text().replace('fallback = ""\n', 'fallback = ""\nshared = false\n')
    (estate.dir / "accounts.toml").write_text(accounts)
    fresh = curia.Estate(estate.dir)
    assert curia.walk_chain(fresh, "b", "b") == ("b", [])
    assert curia.walk_chain(fresh, "a", "a")[0] == "a"
    curia.mark_limited(fresh, "a", curia.now() + dt.timedelta(hours=1))
    free, limited = curia.walk_chain(fresh, "a", "a")
    assert free is None and [n for n, _ in limited] == ["a"]
    rc, _, err = cli(*E(estate), "launch", "muse")
    assert rc == 2 and "is limited" in err
    monkeypatch.setattr(curia.shutil, "which", lambda name: f"/bin/{name}")
    rc, out, _ = cli(*E(estate), "check")
    assert "- seat muse: dedicated account(s) b in its chain are skipped for it" in out
    rc, out, _ = cli(*E(estate), "status")
    lines = {line.split()[0]: line for line in out.splitlines() if line.startswith("  ")}
    assert "(dedicated)" in lines["b"] and "five-hour 5% resets in 60m" in lines["b"]


def test_loop_survives_a_mid_session_limit_and_relaunches_on_the_fallback(curia, cli, estate, monkeypatch, tmp_path):
    sd = estate.seat_dir("muse")
    told = tmp_path / "told.txt"
    meta = (estate.dir / "estate.toml").read_text().replace(
        'notify = ""', f'notify = \'printf "%s" "$CURIA_SUBJECT" > {told}\'')
    (estate.dir / "estate.toml").write_text(meta)
    calls = []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        calls.append((cmd, env))
        sid = cmd[cmd.index("--session-id") + 1]
        cfg = Path(env["CLAUDE_CONFIG_DIR"])
        if len(calls) == 1:
            # what the session's own hooks do: the status line reads 96%, then a turn dies on the limit
            with monkeypatch.context() as m:
                as_seat(m, estate, "muse", cfg)
                assert cli("hook", "usage", stdin=statusline_payload(sid, five=(96, 1800)))[0] == 0
                transcript = cfg / "projects" / "-ws" / f"{sid}.jsonl"
                transcript.parent.mkdir(parents=True)
                transcript.write_text("{}\n")
                rc, _, _ = cli("hook", "limited", stdin=json.dumps({
                    "session_id": sid, "transcript_path": str(transcript), "error_type": "rate_limit",
                    "error": "You've hit your limit"}))
                assert rc == 0
            assert watch() is True   # the launcher ends the session now
            return 143
        prime = Path(cmd[cmd.index("--append-system-prompt-file") + 1]).read_text()
        assert "ended on a usage limit" in prime and "account `a`" in prime and "/-ws/" in prime
        return 0

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "launch", "muse", "--loop")
    assert rc == 0, err
    assert len(calls) == 2
    assert calls[0][1]["CLAUDE_CONFIG_DIR"].endswith("acct-a") and calls[1][1]["CLAUDE_CONFIG_DIR"].endswith("acct-b")
    until = curia.account_limited(estate, "a")
    assert until and 0 < (until - curia.now()).total_seconds() <= 1800
    assert "ended on a usage limit on 'a'; relaunching on 'b'" in err
    assert told.read_text() == "Muse hit a limit on a"
    events = curia.session_events(sd)
    assert [e[0] for e in events] == ["start", "limit", "end", "start", "end"]
    assert "limited" in events[2][2] and "rc=143" in events[2][2] and "five_hour window at 96%" in events[1][2]
    assert not (sd / "LIMITED").exists() and (sd / "LAST-LIMITED").exists()
    rc, out, _ = cli(*E(estate), "check")
    assert "- seat muse: its last session ended on a usage limit" in out
    # a proper handoff clears the notice
    (sd / "handoff.md").write_text(FULL_HANDOFF)
    cli(*E(estate), "handoff", "muse", "--done")
    assert not (sd / "LAST-LIMITED").exists() and "usage limit" not in curia.build_prime(estate, "muse")


def test_limited_hook_reads_the_reset_from_wherever_it_is_named(curia, cli, estate, monkeypatch, tmp_path):
    as_seat(monkeypatch, estate, "muse", tmp_path / "acct-a")
    cli("hook", "limited", stdin=json.dumps({"error_type": "rate_limit", "retry_after_seconds": 120}))
    until = curia.account_limited(estate, "a")
    assert 100 < (until - curia.now()).total_seconds() <= 120
    cli(*E(estate), "limit", "a", "--clear")
    cli("hook", "limited", stdin=json.dumps({"error_type": "rate_limit", "error": "usage limit reached, resets at 23:59"}))
    assert curia.account_limited(estate, "a").astimezone(UTC).strftime("%H:%M") == "23:59"
    cli(*E(estate), "limit", "a", "--clear")
    cli("hook", "limited", stdin=json.dumps({"error_type": "rate_limit", "error": "429 slow down"}))
    assert 500 < (curia.account_limited(estate, "a") - curia.now()).total_seconds() <= 600
    cli(*E(estate), "limit", "a", "--clear")
    cli("hook", "limited", stdin=json.dumps({"error_type": "overloaded", "error": "overloaded"}))
    assert curia.account_limited(estate, "a") is None   # not a limit: nothing marked


def test_shift_hook_tells_a_seat_once_to_hand_off(curia, cli, estate, monkeypatch, tmp_path):
    sd = estate.seat_dir("muse")
    as_seat(monkeypatch, estate, "muse", tmp_path / "acct-a")
    curia.log_session(sd, "start", f"account=a cwd=/x session=s1 pid={os.getpid()}")
    rc, _, err = cli("hook", "shift", stdin="{}")
    assert rc == 0 and not err                     # nothing measured, shift young
    cli("hook", "usage", stdin=statusline_payload("s1", five=(86, 900)))
    rc, _, err = cli("hook", "shift", stdin="{}")
    assert rc == 2 and "Shift over" in err and "86% of its five-hour window" in err and "/handoff" in err
    assert (sd / "SHIFT-OVER").exists() and curia.session_events(sd)[-1][0] == "shift"
    rc, _, err = cli("hook", "shift", stdin="{}")
    assert rc == 0 and not err                     # said once
    (sd / "SHIFT-OVER").unlink()
    rc, _, _ = cli("hook", "shift", stdin='{"stop_hook_active": true}')
    assert rc == 0                                 # already continuing because of a stop hook
    monkeypatch.setenv("CURIA_HEADLESS", "1")
    rc, _, _ = cli("hook", "shift", stdin="{}")
    assert rc == 0                                 # no /handoff headless
    monkeypatch.delenv("CURIA_HEADLESS")
    # a long shift, with headroom to spare
    cli("hook", "usage", stdin=statusline_payload("s1", five=(10, 900)))
    curia.log_session(sd, "end", "rc=0 session=s1")
    curia.log_session(sd, "start", f"account=a cwd=/x session=s2 pid={os.getpid()}")
    monkeypatch.setattr(curia, "now", lambda: dt.datetime.now(UTC) + dt.timedelta(hours=7))
    rc, _, err = cli("hook", "shift", stdin="{}")
    assert rc == 2 and "awake 7.0h (a shift is 6h)" in err
    (sd / "handoff.md").write_text(FULL_HANDOFF)
    cli(*E(estate), "handoff", "muse", "--done")
    assert not (sd / "SHIFT-OVER").exists()


def test_invoke_claude_ends_a_watched_session_when_told(curia, monkeypatch, tmp_path):
    monkeypatch.setattr(curia, "WATCH_SECONDS", 0.1)
    marker = tmp_path / "LIMITED"
    threading.Timer(0.5, marker.touch).start()
    t0 = time.time()
    rc = curia.invoke_claude(["sleep", "30"], tmp_path, dict(os.environ), watch=marker.exists)
    assert rc != 0 and time.time() - t0 < 10
    assert curia.invoke_claude(["true"], tmp_path, dict(os.environ), watch=lambda: False) == 0


def test_status_shows_the_burn_and_the_launcher_records_interactive_cost(curia, cli, estate, monkeypatch, tmp_path):
    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        sid = cmd[cmd.index("--session-id") + 1]
        settings = json.loads(cmd[cmd.index("--settings") + 1])
        assert settings["statusLine"]["command"].endswith("hook usage")
        assert settings["hooks"]["StopFailure"][0]["matcher"] == "rate_limit" and "Stop" in settings["hooks"]
        with monkeypatch.context() as m:
            as_seat(m, estate, "muse", Path(env["CLAUDE_CONFIG_DIR"]))
            cli("hook", "usage", stdin=statusline_payload(sid, five=(33, 7200), seven=(10, 86400), cost=2.5, duration=1800000))
        return 0

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, _, err = cli(*E(estate), "launch", "muse")
    assert rc == 0, err
    end = curia.session_events(estate.seat_dir("muse"))[-1][2]
    assert "cost=$2.50" in end and "minutes=30.0" in end
    assert not list((tmp_path / "acct-a" / "curia-usage").iterdir())   # recorded, then gone
    rc, out, _ = cli(*E(estate), "status")
    lines = {line.split()[0]: line for line in out.splitlines() if line.startswith("  ")}
    assert "five-hour 33% resets in 2.0h" in lines["a"] and "by muse" in lines["a"]
    assert "no reading yet" in lines["b"]
    assert re.search(r"seat     Muse\s+wakings 1\s+\$2\.50", out)
    rc, out, _ = cli(*E(estate), "accounts")
    assert "five-hour 33%" in out
    # headless runs carry the hooks but no status line, and say so to the shift hook
    seen = {}
    monkeypatch.setattr(curia, "invoke_claude",
                        lambda cmd, cwd, env, timeout=None, capture=False, watch=None:
                        seen.update(cmd=cmd, env=env) or completed(cmd, 0, result_json("ok")))
    (estate.dir / "prompts" / "b.md").write_text("do\n")
    assert cli(*E(estate), "run", "muse", "--prompt", "b.md")[0] == 0
    assert "statusLine" not in json.loads(seen["cmd"][seen["cmd"].index("--settings") + 1])
    assert seen["env"]["CURIA_HEADLESS"] == "1"


def test_carry_resumes_the_cut_session_on_the_next_account_or_wakes_fresh(curia, cli, estate, monkeypatch, tmp_path):
    calls = []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        calls.append(cmd)
        cfg = Path(env["CLAUDE_CONFIG_DIR"])
        if len(calls) == 1:
            sid = cmd[cmd.index("--session-id") + 1]
            transcript = cfg / "projects" / "-ws" / f"{sid}.jsonl"
            transcript.parent.mkdir(parents=True)
            transcript.write_text("{}\n")
            curia.write_json(estate.seat_dir("muse") / "LIMITED",
                             {"at": "t", "account": "a", "until": "u", "session_id": sid,
                              "transcript_path": str(transcript)})
            curia.mark_limited(estate, "a", curia.now() + dt.timedelta(hours=1))
            return 143
        if len(calls) == 2:
            sid = cmd[cmd.index("--resume") + 1]
            assert "--session-id" not in cmd and (cfg / "projects" / "-ws" / f"{sid}.jsonl").exists()
            return 1   # the resume did not take
        assert "--session-id" in cmd and "--resume" not in cmd
        return 0

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "launch", "muse", "--loop", "--carry")
    assert rc == 0, err
    assert len(calls) == 3 and "failed at once" in err and "carrying session" in out
    starts = [e for e in curia.session_events(estate.seat_dir("muse")) if e[0] == "start"]
    assert "carried" in starts[1][2] and "acct-b" not in starts[0][2] and "carried" not in starts[2][2]


# -------------------------------------------------------------- everything

def test_everything_works_the_board_until_it_is_clear_or_stuck(curia, cli, estate, monkeypatch, tmp_path):
    export = estate.root / "alpha" / ".beads" / "issues.jsonl"

    def write(rows):
        export.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def bead(i, status="open", blocks=(), labels=()):
        return {"id": i, "status": status, "title": i, "labels": list(labels),
                "dependencies": [{"type": "blocks", "depends_on_id": b} for b in blocks]}

    told = tmp_path / "told.txt"
    meta = (estate.dir / "estate.toml").read_text().replace(
        'notify = ""', f'notify = \'printf "%s" "$CURIA_SUBJECT" > {told}\'')
    (estate.dir / "estate.toml").write_text(meta)
    rows = {"al-1": bead("al-1"), "al-2": bead("al-2", "blocked", blocks=("al-1",)), "al-3": bead("al-3", "blocked"),
            "al-4": bead("al-4", labels=("needs-principal",)), "al-5": bead("al-5", "in_progress"),
            "al-6": bead("al-6", blocks=("al-4",)), "al-7": bead("al-7", blocks=("zz-9",)), "al-0": bead("al-0", "closed")}
    write(rows.values())
    b = curia.board(estate, "alpha")
    assert [i["id"] for i in b["ready"]] == ["al-1"] and [i["id"] for i in b["working"]] == ["al-5"]
    assert [i["id"] for i in b["blocked"]] == ["al-2"] and b["closed"] == 1
    assert sorted(i["id"] for i in b["human"]) == ["al-3", "al-4", "al-6", "al-7"]
    orders = []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        orders.append(cmd[-1])
        assert env.get("CURIA_LOOP") == "1"   # the shift hook may promise a relaunch: there is one
        for i in ("al-1", "al-5") if len(orders) == 1 else ("al-2",):
            rows[i]["status"] = "closed"
        write(rows.values())
        (estate.seat_dir("warden") / "RESTART").touch()
        return 0

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "launch", "warden", "--repo", "alpha", "--everything", "--say", "gently")
    assert rc == 0, err
    assert len(orders) == 2
    assert "1 ready (al-1)" in orders[0] and "1 in progress (al-5)" in orders[0]
    assert "1 blocked by other beads" in orders[0] and "4 waiting on a human (al-3, al-4, al-6, al-7;" in orders[0]
    assert orders[0].endswith("from the principal: gently")
    assert "1 ready (al-2)" in orders[1] and "0 in progress (none)" in orders[1]
    assert "board in alpha is clear" in out and told.read_text() == "Warden: board clear in alpha"
    assert curia.session_events(estate.seat_dir("warden"))[-1][0] == "clear"
    # a board that does not move stops the loop rather than spinning
    rows["al-8"] = bead("al-8")
    write(rows.values())
    orders.clear()
    monkeypatch.setattr(curia, "invoke_claude",
                        lambda cmd, cwd, env, timeout=None, capture=False, watch=None:
                        orders.append(cmd[-1]) or (estate.seat_dir("warden") / "RESTART").touch() or 0)
    rc, out, err = cli(*E(estate), "launch", "warden", "--repo", "alpha", "--everything")
    assert rc == 0 and len(orders) == 2 and "without the board moving" in err
    assert told.read_text() == "Warden: no progress in alpha"
    assert curia.session_events(estate.seat_dir("warden"))[-1][0] == "stalled"
    # a session that dies at once is not woken again; one that ends quietly is, while the board says so
    monkeypatch.setattr(curia, "invoke_claude",
                        lambda cmd, cwd, env, timeout=None, capture=False, watch=None: 1)
    rc, _, err = cli(*E(estate), "launch", "warden", "--repo", "alpha", "--everything")
    assert rc == 0 and "ended at once" in err
    rc, _, err = cli(*E(estate), "launch", "warden", "--everything")
    assert rc == 2 and "wants a repo" in err


def test_everything_works_several_boards_in_the_order_given(curia, cli, estate, monkeypatch, tmp_path):
    def bead(i, status="open"):
        return {"id": i, "status": status, "title": i, "labels": [], "dependencies": []}

    boards = {"alpha": {"al-1": bead("al-1")}, "nested": {"su-1": bead("su-1")}}
    exports = {k: estate.repo_path(k) / ".beads" / "issues.jsonl" for k in boards}

    def write():
        for k, rows in boards.items():
            exports[k].write_text("".join(json.dumps(r) + "\n" for r in rows.values()))

    write()
    told = tmp_path / "told.txt"
    meta = (estate.dir / "estate.toml").read_text().replace(
        'notify = ""', f'notify = \'printf "%s;" "$CURIA_SUBJECT" >> {told}\'')
    (estate.dir / "estate.toml").write_text(meta)
    wakings = []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        wakings.append((Path(cwd).name, cmd[-1]))
        if Path(cwd) == estate.repo_path("nested"):   # alpha never moves; nested is done in one waking
            boards["nested"]["su-1"]["status"] = "closed"
        write()
        (estate.seat_dir("warden") / "RESTART").touch()
        return 0

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "launch", "warden", "--everything", "--repo", "alpha", "--repo", "nested")
    assert rc == 0, err
    assert [w[0] for w in wakings] == ["alpha", "alpha", "sub"]   # alpha stalls after two wakings, then nested
    assert "work alpha's board" in wakings[0][1] and "work nested's board" in wakings[2][1]
    assert "moving on to the next board" in err and "moves on to nested's board (0 more after it)" in out
    assert told.read_text() == "Warden: no progress in alpha;Warden: board clear in nested;"
    events = [e for e, _, _ in curia.session_events(estate.seat_dir("warden")) if e in ("clear", "stalled", "next")]
    assert events == ["stalled", "next", "clear"]
    # every name is checked before the first board is worked; a plain launch starts in one repo
    wakings.clear()
    rc, _, err = cli(*E(estate), "launch", "warden", "--everything", "--repo", "alpha", "--repo", "zeta")
    assert rc == 2 and "no repo 'zeta'" in err and not wakings
    rc, _, err = cli(*E(estate), "launch", "warden", "--repo", "alpha", "--repo", "nested")
    assert rc == 2 and "only --everything takes several" in err and not wakings


def test_run_falls_back_by_model_before_it_falls_back_by_account(curia, cli, estate, monkeypatch, tmp_path):
    roster = (estate.dir / "roster.toml").read_text().replace(
        'run_model = "model-y"\n', 'run_model = "model-y"\nfallback_model = "model-z"\n')
    (estate.dir / "roster.toml").write_text(roster)
    brief = tmp_path / "brief.md"
    brief.write_text("Do it.\n")
    seen = []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        seen.append((Path(env["CLAUDE_CONFIG_DIR"]).name, cmd[cmd.index("--model") + 1]))
        if seen[-1][1] == "model-y":
            return completed(cmd, 1, "", "You've hit your usage limit")
        return completed(cmd, 0, result_json("done on the fallback model"))

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "run", "muse", "--prompt", str(brief))
    assert rc == 0, err
    assert out.strip() == "done on the fallback model"
    assert seen == [("acct-a", "model-y"), ("acct-a", "model-z")]
    assert curia.account_limited(estate, "a") is None      # a model's limit is not the account's
    assert "trying model-z on the same account" in err
    events = curia.session_events(estate.seat_dir("muse"))
    assert "model=model-y" in events[0][2] and "model=model-z" in events[2][2] and "fallback" in events[2][2]
    assert "fallback_model=model-z" in events[3][2]
    # both models dead on a: the account is limited, and b starts on the primary model again
    seen.clear()

    def fake2(cmd, cwd, env, timeout=None, capture=False, watch=None):
        seen.append((Path(env["CLAUDE_CONFIG_DIR"]).name, cmd[cmd.index("--model") + 1]))
        if seen[-1][0] == "acct-a":
            return completed(cmd, 1, "", "You've hit your usage limit")
        return completed(cmd, 0, result_json("done on b"))

    monkeypatch.setattr(curia, "invoke_claude", fake2)
    rc, out, err = cli(*E(estate), "run", "muse", "--prompt", str(brief))
    assert rc == 0 and out.strip() == "done on b"
    assert seen == [("acct-a", "model-y"), ("acct-a", "model-z"), ("acct-b", "model-y")]
    assert curia.account_limited(estate, "a")
    assert "fallback_model" not in curia.session_events(estate.seat_dir("muse"))[-1][2]
    rc, out, _ = cli(*E(estate), "run", "muse", "--prompt", str(brief), "--print-cmd")
    assert "(fallback model-z on a limit)" in out


# ----------------------------------------------------------------- until and budget

def test_parse_until_handles_hhmm_and_iso_formats(curia, monkeypatch):
    """parse_until: HH:MM later today resolves to today; earlier resolves to tomorrow;
    ISO with tz is kept; ISO naive is local; ISO in the past dies."""
    now = dt.datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(curia, "now", lambda: now)

    # HH:MM much later today (adjusting for system timezone)
    local_now = now.astimezone()
    much_later_hour = (local_now.hour + 5) % 24
    result = curia.parse_until(f"{much_later_hour:02d}:30")
    # result should be today (or tomorrow if hour wrapped) at the specified local time
    result_local = result.astimezone()
    assert result_local.hour == much_later_hour and result_local.minute == 30

    # HH:MM earlier today (should be tomorrow)
    earlier_hour = (local_now.hour - 2) % 24
    result = curia.parse_until(f"{earlier_hour:02d}:00")
    result_local = result.astimezone()
    assert result_local.hour == earlier_hour and result_local.minute == 0
    assert result_local.date() > local_now.date() or (result_local.date() == local_now.date() and result_local < local_now)

    # ISO with timezone
    result = curia.parse_until("2026-01-02T06:00:00Z")
    assert result.year == 2026 and result.month == 1 and result.day == 2

    # ISO naive (assumed local)
    result = curia.parse_until("2026-01-02T06:00:00")
    assert result.year == 2026

    # ISO in the past dies
    with pytest.raises(SystemExit):
        curia.parse_until("2025-12-31T10:00:00Z")


def test_until_and_budget_without_loop_die(cli, estate):
    rc, _, err = cli(*E(estate), "launch", "muse", "--until", "06:30")
    assert rc == 2 and "loop to end" in err
    rc, _, err = cli(*E(estate), "launch", "muse", "--budget", "200")


# ------------------------------------------------ 2026-09-04: the account night

def test_slow_windows_rotate_later_than_the_five_hour_one(curia, estate, tmp_path):
    def reading(acct, **windows):
        curia.write_json(curia.usage_path(tmp_path / f"acct-{acct}"),
                         {"at": curia.now().isoformat(), "seat": "x",
                          **{w: {"used_percentage": used, "resets_at": int(time.time()) + 3600} for w, used in windows.items()}})
    reading("a", seven_day=75)               # a slow window past rotate_at but under rotate_week_at: stay
    assert curia.walk_chain(estate, "a", "a")[0] == "a"
    reading("a", seven_day=92)               # past rotate_week_at: rotate
    assert curia.walk_chain(estate, "a", "a")[0] == "b"
    reading("a", five_hour=75, seven_day=20)  # the five-hour window still rotates at rotate_at
    assert curia.walk_chain(estate, "a", "a")[0] == "b"
    reading("a", five_hour=96)               # and measured full is limited, whatever the window
    free, limited = curia.walk_chain(estate, "a", "a")
    assert free == "b" and [n for n, _ in limited] == ["a"]
    assert curia.rotation_due({"spend_limit": {"used_percentage": 91, "resets_at": int(time.time()) + 60}}, 70, 90)
    assert not curia.rotation_due({"seven_day": {"used_percentage": 99, "resets_at": int(time.time()) - 5}}, 70, 90)


def test_launch_refuses_a_second_live_launcher_for_the_same_seat(curia, cli, estate, monkeypatch):
    sd = estate.seat_dir("muse")
    curia.log_session(sd, "start", f"account=a model=model-x cwd=/ session=older pid={os.getppid()}")
    monkeypatch.setattr(curia, "invoke_claude", lambda cmd, cwd, env, timeout=None, capture=False, watch=None: 0)
    rc, out, err = cli(*E(estate), "launch", "muse")
    assert rc != 0 and "awake already" in err and str(os.getppid()) in err
    assert [e[0] for e in curia.session_events(sd)] == ["start"]   # nothing was woken
    curia.log_session(sd, "end", "rc=0 session=older")
    rc, out, err = cli(*E(estate), "launch", "muse")
    assert rc == 0, err


def test_handoff_done_ends_the_session_when_the_turn_ends(curia, cli, estate, monkeypatch, tmp_path):
    sd = estate.seat_dir("muse")
    as_seat(monkeypatch, estate, "muse", tmp_path / "acct-a")
    # before --done the Stop hook has nothing to say
    rc, out, err = cli("hook", "shift", stdin=json.dumps({"session_id": "s1"}))
    assert rc == 0 and not (sd / "ENDED").exists()
    (sd / "RESTART").touch()   # what handoff --done leaves
    rc, out, err = cli("hook", "shift", stdin=json.dumps({"session_id": "s1", "stop_hook_active": True}))
    assert rc == 0 and (sd / "ENDED").exists()
    (sd / "ENDED").unlink(); (sd / "RESTART").unlink()
    # the launcher's watch ends the session on ENDED, and --loop relaunches on the RESTART it left
    calls = []

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        calls.append(cmd)
        if len(calls) == 1:
            assert not watch()
            (sd / "RESTART").touch()   # --done
            (sd / "ENDED").touch()     # the Stop hook at the end of that turn
            assert watch()
            return 143
        return 0                        # the relaunched session ends by hand, no handoff: the loop stops

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "launch", "muse", "--loop")
    assert rc == 0, err
    assert len(calls) == 2 and "asked to be woken again" in out
    events = curia.session_events(sd)
    assert [e[0] for e in events] == ["start", "end", "start", "end"]
    assert "rc=143" in events[1][2] and "handed-off" in events[1][2]
    assert not (sd / "ENDED").exists() and not (sd / "RESTART").exists()


def test_censor_retries_gh_and_names_an_unread_branch(curia, cli, estate, monkeypatch):
    answers = [None, None, [{"status": "completed", "conclusion": "success", "url": "u1", "createdAt": "", "headSha": "h1"}]]
    monkeypatch.setattr(curia, "gh_json", lambda args: answers.pop(0) if answers else None)
    slept = []
    monkeypatch.setattr(curia.time, "sleep", lambda s: slept.append(s))
    rc, out, _ = cli(*E(estate), "censor")
    assert rc == 0 and slept == [curia.CENSOR_GH_WAIT] * 2 and "success" in out and "NOT judged" not in out
    sd = estate.seat_dir("warden")
    assert curia.session_events(sd)[-1][0] == "check" and "unread=0" in curia.session_events(sd)[-1][2]
    # gh dead for good: three tries, then the branch is named unjudged, never called green
    monkeypatch.setattr(curia, "gh_json", lambda args: None)
    rc, out, _ = cli(*E(estate), "censor")
    assert rc == 0 and "NOT judged" in out and "(3 tries)" in out and "no runs found" not in out
    assert "unread=1" in curia.session_events(sd)[-1][2]
    # a dry run does not wait around
    slept.clear()
    rc, out, _ = cli(*E(estate), "censor", "--dry-run")
    assert rc == 0 and slept == [] and "NOT judged" in out


def test_run_with_a_bead_records_the_assignment_and_its_cost(curia, cli, estate, monkeypatch, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("Review {bead} in {repo}.\n")

    def fake(cmd, cwd, env, timeout=None, capture=False, watch=None):
        journal = Path(re.search(r"journal entry .*? to `([^`]+)`", cmd[cmd.index("-p") + 1], re.S).group(1))
        journal.write_text("# done\n")
        return completed(cmd, 0, result_json("Verdict: MERGE"))

    monkeypatch.setattr(curia, "invoke_claude", fake)
    rc, out, err = cli(*E(estate), "run", "muse", "--prompt", str(brief), "--repo", "alpha", "--bead", "ab-1,ab-2")
    assert rc == 0, err
    log = (estate.seat_dir("muse") / "assignments.log").read_text().splitlines()
    assert len(log) == 2
    assert log[0].startswith("run ") and " bead=ab-1,ab-2 prompt=brief.md by=" in log[0] and " repo=alpha" in log[0]
    assert log[1].startswith("done ") and " bead=ab-1,ab-2 prompt=brief.md rc=0 session=sess-1 cost=$0.50" in log[1]
    # --set bead=<id> is the same record; no bead, no record
    rc, _, err = cli(*E(estate), "run", "muse", "--prompt", str(brief), "--repo", "alpha", "--set", "bead=ab-3")
    assert rc == 0, err
    log = (estate.seat_dir("muse") / "assignments.log").read_text().splitlines()
    assert len(log) == 4 and " bead=ab-3 " in log[2]
    rc, _, err = cli(*E(estate), "run", "muse", "--prompt", str(brief), "--repo", "alpha")
    assert rc == 0, err
    assert len((estate.seat_dir("muse") / "assignments.log").read_text().splitlines()) == 4
    rc, _, err = cli(*E(estate), "run", "muse", "--prompt", str(brief), "--repo", "alpha", "--bead", "not a bead")
    assert rc != 0 and "does not look like a bead id" in err


def test_usage_hook_keeps_a_time_series_of_headroom(curia, cli, estate, monkeypatch, tmp_path):
    as_seat(monkeypatch, estate, "muse", tmp_path / "acct-a")
    monkeypatch.setattr(curia, "memory_headroom", lambda: 61)
    t0 = dt.datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(curia, "now", lambda: t0)
    assert cli("hook", "usage", stdin=statusline_payload())[0] == 0
    assert cli("hook", "usage", stdin=statusline_payload())[0] == 0     # same reading, same minute: no new line
    log = (tmp_path / "acct-a" / "curia-usage.log").read_text().splitlines()
    assert len(log) == 1
    assert log[0].startswith("2026-01-01T10:00:00+00:00 account=a seat=muse session=sess-1 five_hour=23 seven_day=41 ")
    assert log[0].endswith("cost=$1.25 mem=61")
    assert cli("hook", "usage", stdin=statusline_payload(five=(31.0, 3600)))[0] == 0   # the window moved: a line
    monkeypatch.setattr(curia, "now", lambda: t0 + dt.timedelta(minutes=6))
    assert cli("hook", "usage", stdin=statusline_payload(five=(31.0, 3600)))[0] == 0   # five minutes on: a line
    log = (tmp_path / "acct-a" / "curia-usage.log").read_text().splitlines()
    assert len(log) == 3 and " five_hour=31 " in log[1] and log[2].startswith("2026-01-01T10:06:00")
    # another session's lines do not throttle this one
    assert cli("hook", "usage", stdin=statusline_payload(sid="sess-2", five=(31.0, 3600)))[0] == 0
    assert len((tmp_path / "acct-a" / "curia-usage.log").read_text().splitlines()) == 4


# --------------------------------------------------------------- detached

def _wait_for(pred, seconds=40.0):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if pred():
            return True
        time.sleep(0.2)
    return False


def test_headless_runs_are_their_own_processes_and_outlive_the_caller(curia, estate, tmp_path):
    """The binary, not the in-process runner: a run (and a dispatch, same path)
    forks free of the shell that asked for it - its own session, reparented to
    init - so a seat session that hands off and ends mid-job takes nothing with
    it. Three jobs were lost that way in one handoff before this held."""
    import signal
    import sys
    fake = tmp_path / "fakebin" / "claude"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\nsleep 2\n"
                    "printf '%s' '{\"type\":\"result\",\"is_error\":false,\"result\":\"survived\","
                    "\"session_id\":\"s-detached\",\"total_cost_usd\":0.1,\"num_turns\":1,\"duration_ms\":2000}'\n")
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f"{fake.parent}:{os.environ['PATH']}")
    env.pop("CURIA_SEAT", None)
    brief = tmp_path / "brief.md"
    brief.write_text("Do it.\n")
    mech = Path(__file__).resolve().parent.parent / "bin" / "curia"
    cmd = [sys.executable, str(mech), *E(estate), "run", "muse", "--prompt", str(brief), "--repo", "alpha"]
    sd = estate.seat_dir("muse")

    def ends():
        return [e for e in curia.session_events(sd) if e[0] == "end"]

    def starts():
        return [e for e in curia.session_events(sd) if e[0] == "start"]

    # --detach: back at once with the pid and the log; the job writes its own record
    p = subprocess.run([*cmd, "--detach"], capture_output=True, text=True, env=env, timeout=30)
    assert p.returncode == 0, p.stderr
    m = re.search(r"Muse runs detached for brief: pid (\d+), log ([^;]+);", p.stdout)
    assert m, p.stdout
    pid, log = int(m.group(1)), Path(m.group(2))
    assert not ends(), "the fake claude sleeps two seconds; the caller was back before it answered"
    assert _wait_for(lambda: len(ends()) == 1), curia.session_events(sd)
    assert f"pid={pid}" in starts()[0][2] and "session=s-detached" in ends()[0][2] and "rc=0" in ends()[0][2]
    assert log.parent == sd / "runs" and "survived" in log.read_text()
    # the waiting form reads as before: the answer on stdout, the exit status the job's
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    assert p.returncode == 0, p.stderr
    assert "survived" in p.stdout and "waiting for it" in p.stderr and len(ends()) == 2
    # ...and the caller dying, whole process group, does not take the job with it
    caller = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                              start_new_session=True)
    assert _wait_for(lambda: len(starts()) == 3), curia.session_events(sd)
    os.killpg(caller.pid, signal.SIGKILL)
    caller.wait(timeout=10)
    assert _wait_for(lambda: len(ends()) == 3), curia.session_events(sd)
    assert "rc=0" in ends()[2][2] and "session=s-detached" in ends()[2][2]
    assert len(list((estate.dir / "brain" / "muse").iterdir())) == 3


def test_board_reads_the_export_as_pushed_when_the_repo_has_an_origin(curia, estate, tmp_path):
    """The launcher reads the board from origin's integration branch: the
    checkout the estate names may be one nobody pulls, and a stale export read
    twice looks like a board that does not move."""
    def bead(i, status="open"):
        return {"id": i, "status": status, "title": i, "labels": [], "dependencies": []}

    src = estate.root / "alpha"
    git_repo(src)
    export = src / ".beads" / "issues.jsonl"
    export.write_text(json.dumps(bead("al-1")) + "\n")
    git_commit(src, "export")
    b = curia.board(estate, "alpha")
    assert [i["id"] for i in b["ready"]] == ["al-1"] and b["source"] == "the export on disk"   # no origin yet
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    subprocess.run(["git", "-C", str(src), "remote", "add", "origin", str(origin)], check=True)
    subprocess.run(["git", "-C", str(src), "push", "-q", "origin", "main"], check=True)
    # the checkout moves on without pushing: the board is still what origin has
    export.write_text(json.dumps(bead("al-1", "closed")) + "\n" + json.dumps(bead("al-2")) + "\n")
    b = curia.board(estate, "alpha")
    assert [i["id"] for i in b["ready"]] == ["al-1"] and b["closed"] == 0
    assert b["source"].startswith("origin/main at ") and b["source"].endswith(", as pushed")
    git_commit(src, "al-1 closed, al-2 filed")
    subprocess.run(["git", "-C", str(src), "push", "-q", "origin", "main"], check=True)
    b = curia.board(estate, "alpha")
    assert [i["id"] for i in b["ready"]] == ["al-2"] and b["closed"] == 1
    # the orders say where the board came from
    assert "the board read from origin/main at" in curia.everything_orders("alpha", b)


def test_shift_hook_promises_a_relaunch_only_under_a_loop(curia, cli, estate, monkeypatch, tmp_path):
    sd = estate.seat_dir("muse")
    as_seat(monkeypatch, estate, "muse", tmp_path / "acct-a")
    monkeypatch.delenv("CURIA_LOOP", raising=False)
    curia.log_session(sd, "start", f"account=a cwd=/x session=s1 pid={os.getpid()}")
    cli("hook", "usage", stdin=statusline_payload("s1", five=(86, 900)))
    rc, _, err = cli("hook", "shift", stdin="{}")
    assert rc == 2 and "Shift over" in err and "no --loop" in err and "relaunch lands" not in err
    assert "own processes" in err   # dispatched jobs are safe to leave
    (sd / "SHIFT-OVER").unlink()
    monkeypatch.setenv("CURIA_LOOP", "1")
    rc, _, err = cli("hook", "shift", stdin="{}")
    assert rc == 2 and "relaunch lands on an account with headroom" in err and "no --loop" not in err


def test_a_cut_run_takes_its_children_with_it(curia, estate, tmp_path):
    """A run that hits --timeout is ended with its whole process group: the
    seat's dev server started inside it does not go on holding its port."""
    import sys
    pidfile = tmp_path / "child.pid"
    fake = tmp_path / "fakebin" / "claude"
    fake.parent.mkdir()
    fake.write_text(f"#!/bin/sh\nsleep 60 &\necho $! > {pidfile}\nsleep 60\n")
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f"{fake.parent}:{os.environ['PATH']}")
    env.pop("CURIA_SEAT", None)
    brief = tmp_path / "brief.md"
    brief.write_text("Do it.\n")
    mech = Path(__file__).resolve().parent.parent / "bin" / "curia"
    p = subprocess.run([sys.executable, str(mech), *E(estate), "run", "muse", "--prompt", str(brief), "--timeout", "2"],
                       capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 1 and "[timeout after 2s]" in p.stdout, (p.stdout, p.stderr)
    assert _wait_for(lambda: pidfile.exists(), 5)
    child = int(pidfile.read_text().strip())
    assert _wait_for(lambda: not curia.pid_alive(child), 15), "the run's child outlived the cut run"
    events = curia.session_events(estate.seat_dir("muse"))
    assert events[-1][0] == "end" and "rc=124" in events[-1][2]
