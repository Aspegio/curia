# {{ESTATE}} estate

Seats, law and memory for the {{ESTATE}} estate. Mechanism lives in
`{{MECHANISM}}`. Laid down on {{DATE}} in the factory shape: an office that
works the board at night and dispatches a fleet; crew who design and review
by jurisdiction, a record seat and a clerk; an intake office; the Censor;
a Lictor seat for a cloud routine; the Portcullis on launchd.

## Layout

- `estate.toml`, `roster.toml`, `repos.toml`, `accounts.toml` - who, where, whose tokens
- `house-rules.md` - appended to every seat's prime
- `hooks.json` - the estate's fences: hooks carried into every seat session
- `seats/<seat>/` - `charter.md`, `handoff.md`, `laurels.md`, `sessions.log`, `history/`, `journal/` (headless wakings), `mail.md` (unread; the seat archives it), `assignments.log` (fleet); markers `RESTART`, `LIMITED`, `LAST-LIMITED`, `SHIFT-OVER` the launcher and hooks pass between them
- `brain/` - `rulings/` (status, what enforces each); office reports (`censor/`, `lictor/`, `portcullis/`)
- `prompts/` - office prompts (`censor.md`, `lictor-cloud.md`) and the fleet's briefs (`dispatch.md`, `review.md`)
- `launchd/` - the Censor at six, the Lictor hourly, the Portcullis on an interval; copy into `~/Library/LaunchAgents` and `launchctl load` them when the offices should run
- `inbox/` - where `curia ingest --paste` lands a transcript; disposable, the intake office archives it
- `../worktrees/<seat>/<repo>` - fleet workers' homes, given by `curia dispatch`, removed by `curia reap` once landed

## Rhythm

Evening: `curia launch <office> --loop`, tell the office what to land.
Overnight: design first - the office has the crew seat whose jurisdiction
it is design every bead that needs it, and the design goes on the bead -
then `curia dispatch <worker> --bead <id> --repo <repo> --review <seat>`,
one home per worker under `worktrees/`; the reviewer marks the PR; the
Portcullis lands what is reviewed and green and closes the bead.
Mornings: `curia censor` (launchd) reads every integration branch and wakes
the Censor where one is red; `brain/censor/<date>.md` is the report.
Hourly: the Lictor nudges, on this machine (`curia lictor --write`,
launchd) or in the cloud (`prompts/lictor-cloud.md`); one or the other.
Day: `curia launch <seat>` for design and review work that should not wait
for the night; `curia launch <clerk>` for documents and questions;
`curia ingest <notes>` after every meeting. Crew hand off with `/handoff`,
never `/exit`. `curia status` says who is awake and what was spent;
`curia reap` closes dead records and takes landed worktrees back.

## Next

1. `curia rename <example_seat> <name>` from inside this workspace, for each
   `example_*` seat, names from your naming family (estate.toml
   `naming_family`); add a crew block per concern and a fleet block per
   worker this machine can gate at once. The offices are keyed by role and
   may keep their names while this is the only such estate on the
   machine; a second estate with the same office names needs `--estate`
   from outside a workspace. Then write each `seats/<name>/charter.md`; the
   scaffolds say "Fill in for this estate" where they need you.
2. `repos.toml`: each repo, its branches, its gate and leaf commands, and
   `merge` if the Portcullis should not squash. Offices skip a repo with no
   gate.
3. `accounts.toml`: a dedicated account for the client is `shared = false`
   and listed here alone; the principal's own accounts are the pool.
4. `prompts/`: `censor.md`, `dispatch.md` and `review.md` read right as they
   are; `lictor-cloud.md` needs this estate's repos and thresholds if a
   cloud routine will run it (delete the lictor seat if not). `estate.toml`
   `notify` says how the offices reach you; `human_labels` names the labels
   that say a bead waits on a person.
5. `curia check` until it is quiet; then load the launchd units.

## Add a product

One block in `repos.toml`; a `CLAUDE.md` and `.beads` in the product. Crew
jurisdictions are concerns, so they extend on their own. Run `curia check`.
