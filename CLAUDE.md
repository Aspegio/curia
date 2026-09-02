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
- `tests/` - the fence

## Working here

- Every change: `python3 -m py_compile bin/curia && python3 -m pytest -q tests`.
- Try a command without launching a session: most take `--print-cmd`, which
  shows the resolved account, cwd and prompt instead of running.
- To rehearse something destructive (a rename, a roster edit), copy an estate
  to a scratch directory and run against it with `--estate <path>`; never
  experiment on a live estate.
- Adding a command: a `cmd_*` function plus a subparser in `main()`, and a line
  in the README's daily-use block. Offices are looked up by `role`, not name,
  so a renamed seat keeps working - keep it that way.
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
- Account fallback happens at LAUNCH, walking a chain until it finds one not
  marked limited. A running session cannot change account; that is a fact about
  the harness, not a gap to paper over.
- Read-only offices stay read-only. If a command starts writing to a board,
  that is a new office, not a flag.
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
