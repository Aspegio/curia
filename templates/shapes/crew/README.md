# {{ESTATE}} estate

Seats, law and memory for the {{ESTATE}} estate. Mechanism lives in
`{{MECHANISM}}`. Laid down on {{DATE}} in the crew shape: crew seats by
jurisdiction and a clerk, which the principal launches; a Censor that rolls
a red integration branch forward; the Lictor and the Portcullis on launchd,
which wake no model. No fleet.

## Layout

- `estate.toml`, `roster.toml`, `repos.toml`, `accounts.toml` - who, where, whose tokens
- `house-rules.md` - appended to every seat's prime
- `hooks.json` - the estate's fences: hooks carried into every seat session
- `seats/<seat>/` - `charter.md`, `handoff.md`, `laurels.md`, `sessions.log`, `history/`, `journal/` (headless wakings), `mail.md` (unread; the seat archives it); markers `RESTART`, `LIMITED`, `LAST-LIMITED`, `SHIFT-OVER` the launcher and hooks pass between them
- `brain/` - `rulings/` (status, what enforces each); office reports (`censor/`, `lictor/`, `portcullis/`)
- `prompts/` - `censor.md`, the Censor's brief
- `launchd/` - the Censor at six, the Lictor hourly, the Portcullis on an interval; copy into `~/Library/LaunchAgents` and `launchctl load` them when the offices should run

## Rhythm

Day: `cd <repo> && curia launch <seat>` for the seat whose jurisdiction the
work is in; `curia launch <clerk>` for documents and questions. A seat
opens a PR; another seat or the principal reviews it and marks it (the
`land_label` in estate.toml, or an approving review); the Portcullis lands
it and closes the bead. Seats hand off with `/handoff`, never `/exit`.
Night, when the board is worth it: `curia launch <seat> --everything --repo
<repo>` works a board until nothing remains but what waits on a person.
Mornings: `curia censor` reads every integration branch and wakes the Censor
where one is red. Hourly: `curia lictor --write` nudges; `curia status`
shows the offices' latest reports.

## Next

1. `curia rename example_crew <name>` and `curia rename example_clerk
   <name>` from inside this workspace, names from your naming family
   (estate.toml `naming_family`); add a crew block per concern. The offices
   are keyed by role and may keep their names while this is the only
   such estate on the machine; a second estate with the same office names
   needs `--estate` from outside a workspace. Then write each
   `seats/<name>/charter.md`; the scaffolds say "Fill in for this estate"
   where they need you.
2. `repos.toml`: each repo, its branches, its gate and leaf commands. The
   Censor and the Portcullis skip a repo with no gate.
3. `accounts.toml`: the config dir of each account this estate may use.
4. `prompts/censor.md` reads right as it is; `estate.toml` `notify` says how
   the offices reach you.
5. `curia check` until it is quiet; then load the launchd units.

## Growing

The factory shape adds an office that works the board at night and
dispatches a fleet into worktrees of their own, a record seat, an intake
office and a Lictor seat for a cloud routine. Its roster blocks are in
`{{MECHANISM}}/templates/shapes/factory/roster.toml`; the fleet's briefs
are `{{MECHANISM}}/templates/estate/prompts/dispatch.md` and `review.md`,
the cloud Lictor's `lictor-cloud.md`; a charter for each new seat starts
from `{{MECHANISM}}/templates/charters/`. `curia check` says what is still
missing. Seats never roam between estates.
