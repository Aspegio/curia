# curia

The mechanism for a seat-based agent estate. Mechanism, not law.

An **estate** is one client's workspace. Its `curia/` directory holds the
roster (who the seats are), the manifest (which repos), the accounts (whose
tokens), the seats' memory (charter, handoff, laurels) and the brain (rulings
that span repos). That is the law, and it is bespoke: it names products,
people and numbers. This repo holds only what every estate shares:

- `bin/curia` - launch seats with their memory primed, run offices headless,
  the read-only Lictor report, the Censor sweep, account fallback, handoffs.
- `skills/handoff/` - the `/handoff` skill (install at user level, see below).
- `templates/estate/` - what `curia init` copies for a new client.
- `tests/` - the fence: nothing in this repo may name an estate, its
  products or its principal. The denylist is read from the estates
  registered in `~/.config/curia/estates.toml`, so the mechanism never has to
  know the names it is forbidden to know.

## Vocabulary

| Word | Meaning |
|---|---|
| seat | a named, persistent role with memory; survives sessions and model upgrades |
| session | one waking of a seat |
| office | a standing seat with a function; scheduled or on demand |
| crew | a seat with a jurisdiction (concerns, not repos); the principal talks to it |
| fleet | seats an office dispatches; never launched directly; each has its own worktree |
| prime | the system prompt a seat wakes up with: identity, colleagues, charter, last handoff, laurels, house rules |
| handoff | the note a seat writes on its way to sleep; the next session reads it first |
| laurel | spontaneous praise for a seat's work, recorded so the seat sees it on waking; carries no work |
| mail | a note one seat leaves another; read in the prime at waking, archived by the reader |
| gate | a mechanical yes or no; the Portcullis lands work that passes it, and no model wakes for it |
| fence | a program that refuses what the law forbids; the estate declares them in `hooks.json` |
| ruling | law that spans repos, with a status and what enforces it; `brain/rulings/` |

## Install

```sh
ln -s "$PWD/bin/curia" ~/.local/bin/curia
ln -s "$PWD/skills/handoff" ~/.claude/skills/handoff     # user-level skill
```

## Daily use

```sh
curia help                       # the vocabulary and the rhythm; `curia help <command>` for one in full
curia roster                     # who is on the estate
curia check                      # is the estate consistent
curia status                     # who is awake, whose memory is how old, what the offices last said
curia launch <seat>              # wake a crew seat, primed with its handoff
cd <repo> && curia launch <seat>  # ...in the repo you are in; --repo <repo> names one from anywhere
curia launch <office> --loop     # wake an office; relaunch after each /handoff, and after a mid-session limit
curia launch <seat> --loop --carry   # ...carrying a cut session's transcript to the next account (experimental)
curia launch <office> --repo <repo> --everything   # work the board in a loop until nothing remains but what waits on a human
curia launch <office> --everything --repo <repo> --repo <repo2>   # ...several boards, in that order, one night
curia launch <office> --repo <repo> --everything --until 06:30   # ...the board, until 06:30 local time
curia launch <office> --repo <repo> --everything --budget 200    # ...the board, until $200 of recorded spend
curia ingest <notes...>          # capture beads from meeting notes (wakes the intake office)
curia ingest --paste             # ...from the clipboard; `... ingest -` reads stdin
curia ingest --paste --repo <repo>   # ...when the notes concern one repo: start and file there
curia lictor                     # read-only nudge report (crons watch)
curia censor                     # check integration branches; wake the Censor where red (models act)
curia laurel <seat> "a user said the new page finally makes sense"
curia mail <seat> "the brief is in the bead; start there"   # read at the seat's next waking; --all broadcasts
curia dispatch <fleet> --bead <id> --repo <repo> --review <seat>   # a worker gets a worktree and a job; a reviewer judges it
curia dispatch <fleet> --bead <id> --repo <repo> --detach   # ...back at once; the job is its own process either way and outlives your shell
curia portcullis                 # land the seats' reviewed, green PRs and close their beads (a cron runs this)
curia reap                       # close the record of dead sessions; remove worktrees whose branch landed
curia rulings                    # the brain's rulings, with status and what enforces each
curia limit <account> --hours 5  # an account hit its limit; launches fall back down the chain
curia launch <seat> --account <acct>   # start on a named account, e.g. one with headroom
```

The estate is found from `--estate`, `CURIA_ESTATE`, walking up from the
working directory, or the registry in `~/.config/curia/estates.toml`: the
estate whose roster has the seat you named, or the only one registered. Two
estates and no seat to tell them apart, and a command stops rather than guess.

## A new client

```sh
curia init ~/Workspace/NewClient --name "NewClient" --principal "Name"
```

Then fill `roster.toml`, `repos.toml`, `accounts.toml`, write each seat's
`charter.md`, look at `hooks.json` (the estate's fences; the release-guard is
wired in as the example), run `curia check`. Give every client its own naming family so a
seat name is never ambiguous: the registry finds a seat's estate by its name.
A client with a dedicated account gets its own config dir, listed in that
estate alone; a client without one lists the principal's own accounts, the
pool, which such estates share. Seats never roam between estates.

## Principles the mechanism encodes

- Seats wake with purpose: prime, charter, last handoff, laurels.
- Hand off, don't exit: `/handoff` is a request the seat consents to.
- A headless waking keeps a journal: `run` ends with orders to write one entry, the prime reads the last few.
- Never falsify the record: `sessions.log`, handoff history and brain are append-only.
- Crons watch, models act: `lictor` gathers facts deterministically; `censor` wakes a model only when something is red.
- Read-only offices stay read-only: the Lictor never writes beads.
- Design out the drudgery: no seat idle-waits on a PR. The Portcullis, a gate with no model behind it, lands what is reviewed and green and closes the bead.
- A home of one's own: `dispatch` gives a fleet worker its own worktree and a job; `reap` takes the worktree back only once the branch has landed and nothing is uncommitted.
- Seats talk to each other: `mail` is read at waking and archived by the reader, so the principal is not the relay.
- Law grows teeth: a ruling carries a status (proposed, advisory, enacted, enforced, retired) and names what enforces it; `hooks.json` turns a rule into a refusal in every seat session; `check` faults a ruling with no status and `lictor` nudges when an enacted ruling has nothing enforcing it, or a postmortem has no ruling.
- The envelope is the roster's: `disallowed_tools` are refused in every session, `tools` are allowed without asking.
- A headless run falls back by model before it falls back by account: a roster `fallback_model` is tried on the same account when the primary dies on a limit, and the record says which model answered.
- Rotation is measured: each seat's status line records what Claude Code measures of its account's rate-limit windows; a launch takes the first account in the chain with headroom, a dedicated account (`shared = false`) is only ever its own seats'.
- A night has a goal: `--everything` reads the board each waking, names what is ready and what waits on a human, and stops when the board is clear or has not moved in two wakings. Given several repos, it works their boards in that order. It can also have an end: `--until` (HH:MM local, or ISO datetime) and `--budget` (USD of recorded spend) cap the night; the seat is told to wrap up `wrap_minutes` before the deadline and at budget percent, the way a shift ends.
- The night does not die on a limit: a seat's Stop hook says "hand off now" past a threshold or a shift length, while it still has tokens to write the note; its StopFailure hook marks the account when a turn dies on the limit, and the looping launcher ends that session and relaunches on the fallback, telling the seat what happened and where the transcript is.
- Fallback, not failure: an account at its limit hands its seats down the chain; a headless run marks the limit itself and retries, a looped seat waits it out.
- The record is dated when it happens: the clock is read per event, never cached at start.
