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
curia launch <seat>              # wake a crew seat, primed with its handoff
curia launch <office> --loop     # wake an office; relaunch after each /handoff
curia ingest <notes...>          # capture beads from meeting notes (wakes the intake office)
curia ingest --paste             # ...from the clipboard; `... ingest -` reads stdin
curia lictor                     # read-only nudge report (crons watch)
curia censor                     # check integration branches; wake the Censor where red (models act)
curia laurel <seat> "a user said the new page finally makes sense"
curia limit <account> --hours 5  # an account hit its limit; launches fall back down the chain
```

The estate is found from `--estate`, `CURIA_ESTATE`, walking up from the
working directory, or the default registered in `~/.config/curia/estates.toml`.

## A new client

```sh
curia init ~/Workspace/NewClient --name "NewClient" --principal "Name"
```

Then fill `roster.toml`, `repos.toml`, `accounts.toml`, write each seat's
`charter.md`, run `curia check`. Give every client its own naming family so a
seat name is never ambiguous, and its own account config dir. Seats never
roam between estates.

## Principles the mechanism encodes

- Seats wake with purpose: prime, charter, last handoff, laurels.
- Hand off, don't exit: `/handoff` is a request the seat consents to.
- Never falsify the record: `sessions.log`, handoff history and brain are append-only.
- Crons watch, models act: `lictor` gathers facts deterministically; `censor` wakes a model only when something is red.
- Read-only offices stay read-only: the Lictor never writes beads.
- Fallback, not failure: an account at its limit hands its seats down the chain.
