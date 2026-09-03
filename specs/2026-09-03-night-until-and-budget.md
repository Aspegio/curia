# Spec: a night with an end - `launch --until` and `launch --budget`

Written 2026-09-03 by the estate's clerk seat, at the principal's request, for
an implementing agent working in this repo. Read `CLAUDE.md` and `README.md`
first; the fence test applies to this file too, so it names no estate.

## The ask

The principal likes `launch --everything` but is nervous about starting one:
a night's size is not visible before launch, and once running it ends only
when the board is clear or has stalled. He wants to say "work everything, but
stop no later than a given time" and, for the same reason, "stop when the
night has spent a given amount". The seat wraps up at that point the way it
already does at the end of a shift: finish or park what is in hand, make the
board on disk true, hand off. Nothing here needs judgment from the mechanism;
the seat keeps its judgment in its handoff.

## Why this shape

The shift hook (`hook_shift`) already ends a session well: at the end of every
turn it checks two conditions (account past `handoff_at`, session awake past
`shift_hours`) and, when one is true, tells the seat ONCE to hand off (exit 2,
`SHIFT-OVER` marker). The `--loop` launcher then relaunches. A deadline and a
budget are two more reasons in that hook, plus a check in the launcher so it
does not wake the seat again once the night is over. No new office, no board
writes, no new marker file: the launcher passes the night's terms to the
session in its environment, exactly as it passes `CURIA_SEAT` today.

## Behaviour

### Flags

Two new options on `curia launch`, valid only with `--loop` (and so with
`--everything`, which implies it). Given without either: `die("a deadline
needs a loop to end; add --loop or --everything")`.

- `--until <time>`: when the night ends. `HH:MM` is local wall clock, the
  next occurrence (if already past today, tomorrow). A full ISO datetime is
  accepted too; naive means local. Stored and logged as UTC. An ISO time
  already past: `die`. Every message prints both forms, e.g. `06:30 local
  (01:00Z)`, because the principal types local and the record is UTC.
- `--budget <usd>`: the most the night may spend, in US dollars, as the
  status line measures it. Not a number, or not above zero: `die`.

Both may be given together; whichever is reached first ends the night.

### Thresholds

Two new entries in `THRESHOLDS`, overridable by name in `estate.toml` like
the existing four, with the same comment block in
`templates/estate/estate.toml`:

- `wrap_minutes = 45`: how long before `--until` the seat is told to wrap
  up. The margin exists because the Stop hook fires only at the end of a
  turn, and a turn can sit inside a long gate or a headless review; the
  deadline is "start wrapping up by", not "stopped by". The default is a
  guess that fits an integration gate plus a handoff; an estate whose gates
  are slower sets it higher. 0 means no margin.
- `budget_wrap_at = 90`: percent of `--budget` at which the seat is told to
  wrap up. A handoff costs tokens, so the hook speaks before the money is
  gone.

### The launcher (`launch_seat`)

At the top of each iteration of the relaunch loop, before the board is read
and before `walk_chain`:

1. If `--until` is set and `now() >= until - wrap_minutes`: the night is
   over. Print `curia: <title>'s night ends at <local> (<Z>); not waking it
   again` and, with `--everything`, `; <n> ready, <m> in progress remain in
   <repo>` from a fresh `board()` read. `log_session(sd, "deadline",
   f"until=<iso> remaining=<n>")`. `notify(est, f"{title}: night ended at
   the deadline", <the same message>)`. Break.
2. If `--budget` is set and `spent >= budget`: the same shape with event
   `budget` and detail `spent=<usd> budget=<usd>`.

`spent` is a local that starts at 0 and, after every session, adds
`usage["cost_usd"]` when the launcher reads the session's usage for the end
line (it already does). A session that wrote no usage (died at once, or the
machine died) adds nothing; the record says "recorded spend" for that reason
and the help says so.

The deadline and the budget end the WHOLE night. With several `--repo`
boards they do not move on to the next board the way a stall does; they
break out of the loop. Say so in the help.

A waking that starts just before the wrap-up point will be told to hand off
at the end of its first turn. That is one short session and a true record,
not a fault; do not add a second margin to avoid it.

The launcher logs the night's terms once, before the first waking:
`log_session(sd, "night", "until=<iso> budget=<usd> wrap=<minutes>")`, with
only the fields given. `status` may read the last `night` line of an awake
looped seat and show `night ends HH:MMZ` in its row; that display is
optional, the log line is not.

### The environment

The `env` dict the launcher builds gains, when set:

- `CURIA_UNTIL`: the deadline as an ISO UTC string.
- `CURIA_BUDGET`: the budget in USD, as a plain number.
- `CURIA_SPENT`: recorded spend of the earlier wakings this night, in USD,
  as a plain number (0 on the first waking).

Hooks run as children of the session and inherit it, which is how
`CURIA_SEAT`, `CURIA_ESTATE` and `CLAUDE_CONFIG_DIR` reach them today.

### The orders

A new helper, `night_orders(until, budget, wrap, budget_wrap) -> str`,
returns one or two sentences, e.g.:

> The night ends at 06:30 local (01:00Z); the shift hook tells you when to
> wrap up, 45 minutes before. Inside that margin start nothing new: no
> dispatch, no review, no gate you cannot wait out. Finish or park what is in
> hand, make the board on disk true, and hand off. Whatever your charter says
> closes a night (a push, a promotion) must start early enough to finish
> before the deadline, not before the margin.

and, for a budget:

> The night's budget is $200 of recorded spend; the shift hook tells you to
> wrap up at 90%.

With `--everything`, `everything_orders` appends it to its own text, BEFORE
any `Also, from the principal:` line, so the existing test's `endswith`
still holds. With plain `--loop`, it is prepended to `--say` or stands alone
as the opening message. Mechanism voice: what is forbidden and what to do,
no estate facts, no named rituals beyond "what your charter says".

### The shift hook (`hook_shift`)

Two more reasons, gathered alongside the existing two, same exit 2, same
`SHIFT-OVER` marker, same once-only behaviour, same silence when headless or
when `stop_hook_active`:

- `CURIA_UNTIL` set and `now() >= until - wrap_minutes`: reason
  `the night ends at <HH:MM>Z (<n> minutes remain)`. Past the deadline the
  minutes are 0, never negative.
- `CURIA_BUDGET` set: live session cost is `session_usage(cfg, sid)`'s
  `cost_usd`, where `sid` is `payload["session_id"]`, else the account
  reading's `session_id`, else nothing (then this reason is skipped). When
  `CURIA_SPENT + live >= budget * budget_wrap_at / 100`: reason
  `recorded spend $<x> of the night's $<y> budget`.

The message the seat reads stays the existing one ("Shift over: <reasons>.
Hand off now: finish or park what is in hand ..."). The seat already knows
what to do with it.

### What this does NOT do

- It is not a hard stop. A turn in flight finishes; the seat is told, not
  killed. The margin is what makes the deadline hold in practice.
- It does not read spend from the API. "Recorded spend" is what the status
  line hands the usage hook, summed over the wakings that wrote it.
- It does not reach headless runs (`curia run`): no shift hook speaks
  headless, and a headless Muse wake is one prompt, not a night.
- It does not filter the board. A subset (`--only`, `--limit`) is a separate
  spec, if wanted; this one caps time and money, which is what the
  principal asked for first.

## Changes, file by file

`bin/curia`:

- `THRESHOLDS`: add `wrap_minutes` and `budget_wrap_at` with the comment
  lines the others have.
- `cmd_launch` / `launch_seat`: parse `--until` (a small `parse_until(s)
  -> dt.datetime` helper, UTC-aware, tested on its own) and `--budget`;
  refuse without a loop; the loop checks above; `spent`; the `night` log
  line; the env vars; the `deadline` and `budget` endings with notify.
- `everything_orders`: takes the night's terms (or the composed sentence)
  and appends it before the principal's line. `night_orders` helper.
- `hook_shift`: the two reasons.
- Help, all four places (`CLAUDE.md`, "Working here", says why and warns
  that argparse reflows; read it back with `curia help launch`):
  - `HELP_OVERVIEW`: the `launch` parenthetical gains `--until, --budget`.
  - `HELP_DETAIL["launch"]`: a paragraph after the `--everything` one saying
    what the two flags do, that the margin is `wrap_minutes`, that the
    night ends across all boards, that spend is recorded spend, that one
    short last waking is possible, and that a hard stop is not what this is.
  - `HELP_DETAIL["hook"]`: the `shift` paragraph names the two new reasons
    and the env vars they read.
  - `HELP_DETAIL["init"]`: the thresholds list gains the two new names.
  - `HELP_EXAMPLES["launch"]`: two lines, aligned to column 40, using
    `<office>`, `<repo>` placeholders:
    `curia launch <office> --repo <repo> --everything --until 06:30` and
    `... --everything --budget 200`.
  - `add_argument` help strings for both flags.

`README.md`:

- The daily-use block: the two example lines above, after the existing
  `--everything` ones.
- Principles: the "A night has a goal" bullet gains a sentence: it can also
  have an end, `--until` and `--budget`, and the seat is told to wrap up
  `wrap_minutes` before, the way a shift ends.

`CLAUDE.md`:

- The `--everything` design commitment currently says the loop ends on
  "exactly two conditions". Amend it: the loop ends on mechanical conditions
  only - the board clear, the board unmoved for two wakings, the deadline
  reached, the budget reached - and none of them needs judgment; do not add
  one that does.

`templates/estate/estate.toml`: the two thresholds with comments, after
`shift_hours`.

The vademecum artifact: update the artifact
"https://claude.ai/code/artifact/79b47d63-1d85-4905-9cb5-0ec3383700d3?via=banner_open"
so it describes the two flags and the wrap-up margin wherever it describes
`--everything` and the shift hook.

## Tests (`tests/test_cli.py`, same idioms as the everything and shift tests)

- `parse_until`: `HH:MM` later today resolves to today; `HH:MM` earlier
  than a monkeypatched `now` resolves to tomorrow; ISO with tz is kept; ISO
  naive is local; ISO in the past dies.
- `--until` and `--budget` without `--loop`/`--everything`: rc 2 and the
  message.
- Deadline ends the night: a board with ready beads; a fake `invoke_claude`
  that touches `RESTART` and, on its first call, moves a monkeypatched
  `now` to inside the margin. Exactly one waking; `out` says the night
  ended; the board still has ready beads (so it was the deadline, not
  clearance); `sessions.log` ends with `deadline` and carries a `night`
  line; the notify command was called with the deadline subject. The
  fake also asserts `env["CURIA_UNTIL"]` is present and ISO.
- Deadline ends the whole night across boards: two `--repo`s, the deadline
  hits during the first; no `next` line is logged for the second.
- Budget ends the night: the fake reads the session id from `cmd`
  (`--session-id <sid>`), writes `<cfg>/curia-usage/<sid>.json` with
  `cost_usd` equal to the budget, touches `RESTART`. One waking; event
  `budget`; the end line still carries `cost=$...`. With a cost of half the
  budget, a second waking starts and its `env["CURIA_SPENT"]` equals the
  first session's cost.
- `hook shift`: with `CURIA_UNTIL` outside the margin, rc 0; inside, rc 2
  and `the night ends at` in stderr; past the deadline, `0 minutes remain`.
  With `CURIA_BUDGET=100`, `CURIA_SPENT=50` and a usage file for the
  session at 40, rc 2 and `recorded spend $90.00 of the night's $100.00
  budget`; at 30, rc 0. Headless still silent.
- The existing everything test still passes unchanged (the night sentence
  goes before the principal's line).
- `python3 -m pytest -q tests` green, including the fence.

## Acceptance

- `curia launch <office> --repo <repo> --everything --until 06:30` prints
  the terms it understood (local and Z), wakes the seat with orders that
  name the deadline and the margin, and, once `now()` is inside the margin,
  does not wake it again; the seat's last session got "Shift over: the
  night ends at ..." at the end of a turn and handed off.
- `--budget` behaves the same on recorded spend.
- `curia help launch`, `curia help hook` and `curia help init` read back
  correctly; README and CLAUDE.md say the same thing; the artifact above is
  updated.
- Nothing in the change names an estate, a product, a person or a repo; the
  fence test passes.
