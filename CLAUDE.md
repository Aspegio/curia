# curia - the mechanism

This repo is the **mechanism** for a seat-based agent estate: the launcher, the
seat/session model, account fallback, the `/handoff` skill, the read-only
nudge report, the morning branch sweep, and the template a new estate is made
from. Read `README.md` for the vocabulary before changing anything.

## The one hard rule

**Mechanism is reusable; law is not.** Nothing in this repo may name a client,
a product, a person, a repository, or a number belonging to one. Those live in
an estate (`<workspace>/curia/`), never here. This is enforced:

```sh
python3 -m pytest -q tests    # fails if any file here names a registered estate
```

The denylist is read at test time from the estates registered in
`~/.config/curia/estates.toml`, so this repo never has to contain the words it
is forbidden to contain. If a prompt string needs to talk about an estate's
notes, its vault, or its people, say "per your charter" and let the estate's
charter carry the specifics. That test failing is the fence working; do not
weaken it to get green.

## Layout

- `bin/curia` - the whole CLI, one stdlib-only Python file (3.11+ for tomllib)
- `skills/` - skills every seat gets; `launch` links them into the RESOLVED
  account's `$CLAUDE_CONFIG_DIR/skills`, not just `~/.claude/skills`
- `templates/estate/` - what `curia init` copies for a new client
- `templates/handoff.md` - the note shape a seat writes at sleep
- `templates/ruling.md` - the shape of a ruling: `status:` and `enforced by:` lines the
  mechanism reads, then what, why, what enforces it
- `tests/` - the fence, plus `conftest.py`, which builds a scratch estate from
  the template with a fake `claude`, and `test_cli.py` on top of it

## Working here

- Every change: `python3 -m py_compile bin/curia && python3 -m pytest -q tests`.
  A behaviour change gets a test. The `estate` fixture is a scratch estate in
  a temp dir and `invoke_claude` is the one place claude starts, so replace
  that and nothing needs a live estate or a real session.
- Try a command without launching a session: most take `--print-cmd`, which
  shows the resolved account, cwd and prompt instead of running.
- To rehearse something destructive (a rename, a roster edit), copy an estate
  to a scratch directory and run against it with `--estate <path>`; never
  experiment on a live estate.
- Adding a command: a `cmd_*` function plus a subparser in `main()`, and a line
  in the README's daily-use block. Offices are looked up by `role`, not name,
  so a renamed seat keeps working - keep it that way.
- Anything that runs git or gh does so through `git()`, `gh_json()`, `gh_run()`
  and `bd_close()`, so tests replace those and never reach a forge. A dispatch
  test builds a real git repo in the scratch estate; that is cheap, keep it.
- **`curia help` is part of the change, not documentation of it.** Any new
  command, new flag, or changed behaviour updates the help in the same commit.
  There are four places and they are easy to half-do:
  - `HELP_OVERVIEW` - the command list; a flag worth knowing goes in the
    parenthetical after its command
  - `HELP_DETAIL[<cmd>]` - the prose page behind `curia help <cmd>`; say what
    the command does and what it will NOT do
  - `HELP_EXAMPLES[<cmd>]` - the epilog; real invocations, aligned to column 40
  - the `add_argument` help string, which is what `-h` shows
  Read it back (`curia help <cmd>`) rather than trusting the diff - argparse
  reflows prose and swallows misalignment. Help that lies is worse than absent:
  a seat reads it as law. The fence applies here too - no client, person or
  repo names, so examples use `<seat>`, `<repo>`, `<acct>` placeholders.
- Prompts the CLI composes are read by a model with the seat's prime already in
  context. Say what is forbidden and what to do, not how to phrase it.

## Design commitments (do not casually reverse)

- A seat's memory is files it writes itself. The launcher reads them in; the
  seat writes them back at `/handoff`. Nothing else consolidates them silently.
  Headless, that memory is the journal: `run` orders one entry per waking into
  `seats/<seat>/journal/`, the prime reads the last few, and the mechanism
  only ever notes that an entry is missing, never writes one.
- Time is read when asked (`now()`, `stamp()`, `today()`), never cached at
  import. A looping launcher and an hour-long headless run outlive their start;
  a cached clock stamped every end with its start and primed a seat relaunched
  after midnight with yesterday.
- Account rotation happens at LAUNCH, walking a chain for the first account
  with headroom: not marked limited, not measured past `limited_at`, under
  `rotate_at` on its fullest window as the seat's status line last read it.
  A running session cannot change account; that is a fact about the harness,
  not a gap to paper over. So the hooks make the session END well: the Stop
  hook says "hand off now" past `handoff_at` or `shift_hours`, the StopFailure
  hook marks the account when a turn dies on the limit and leaves LIMITED for
  the launcher, which ends the session and relaunches. A headless run is a
  launch, so it marks its own limit and retries down the chain; a `--loop`
  launch waits out a spent chain rather than dying overnight. Measurement is
  what Claude Code hands the status line, never an API call of our own; with
  no reading on file the walk is markers only. A headless run tries a roster
  `fallback_model` on the same account before it marks the account: a limit
  may be the model's. `shared = false` accounts are
  nobody's fallback. `--carry` (copy the transcript, `--resume` on the next
  account) is experimental and opt-in; it leans on Claude Code's transcript
  layout, which is not ours.
- How the principal is told is the estate's to say: `notify` in estate.toml is
  a command, and the mechanism only ever calls it with a subject, a body and a
  report path. Nothing here knows a channel.
- Read-only offices stay read-only. If a command starts writing to a board,
  that is a new office, not a flag. The Portcullis is the one that writes
  (merges, closes beads), and it is a gate, not an office: its yes or no is
  gh's facts and no model wakes for it. Keep it that way; judgment belongs
  to a reviewer seat, before the gate.
- `--everything` reads the board and never writes it. Each waking's orders come
  from the repo's beads export, the seat is told to export before handing off,
  and the loop ends on exactly two conditions: nothing remains that is not
  waiting on a human, or two wakings in a row left the board untouched. Do not
  add a third that needs judgment; that is the seat's, in its handoff.
- Mail is a file the reader archives. `seats/<seat>/mail.md` is read into the
  prime at every waking until the seat runs `curia mail <seat> --archive`;
  nothing archives it silently, and a seat mails a seat, never the outside.
- A fleet worker's home is given at `dispatch` and taken back by `reap`, and
  reap only ever removes a worktree whose branch has landed and which holds
  nothing uncommitted. Reap closes a session record only when the launcher
  pid on the start line is provably gone; a live pid is left alone.
- Fences are the estate's law with the mechanism as transport. `hooks.json`
  rides into every seat session through `--settings`; the mechanism ships
  `hook release-guard` as the worked example and nothing in it names a
  branch. A ruling's `enforced by:` line names its program; `check` and
  `lictor` say which rulings are still only custom. Do not add a fence that
  needs an estate's facts to the mechanism; put the facts in repos.toml and
  read them.
- Skills are linked per ACCOUNT, at launch. Claude Code reads user skills from
  `$CLAUDE_CONFIG_DIR/skills`, and a seat runs under whichever account it
  resolved to - so linking into one config dir by hand leaves every seat on
  every other account without them (which is how `/handoff` went missing for a
  whole account's seats). Launch is the moment the account is known; link there.
- The estate is discovered (`--estate`, `CURIA_ESTATE`, a walk up from the
  working directory, then the registered default), so no command needs a
  particular working directory.
- The working directory chooses the repo. `launch`, `run` and `ingest`
  default `--repo` to the registered repo containing the cwd (the most
  specific where repos nest); the roster home applies only from outside any
  repo, and `ingest` treats the estate root as plain home, not a repo hint.
  Discovery still needs no particular directory; this is about where a seat
  starts, not whether it can.

## State that lives outside this repo

`~/.config/curia/estates.toml` (which estates exist on this machine), each
account's `$CLAUDE_CONFIG_DIR/skills/*` and `~/.local/bin/curia` (symlinks into
here), each estate's own directory, and any launchd units an estate installs.
Changing a path here can break those; check before you move something.
