# {{ESTATE}} estate

Seats, law and memory for the {{ESTATE}} estate. Mechanism lives in
`{{MECHANISM}}`. Laid down on {{DATE}} in the seat shape: one crew seat the
principal talks to, and nothing that runs unattended.

## Layout

- `estate.toml`, `roster.toml`, `repos.toml`, `accounts.toml` - who, where, whose tokens
- `house-rules.md` - appended to every seat's prime
- `hooks.json` - the estate's fences: hooks carried into every seat session
- `seats/<seat>/` - `charter.md`, `handoff.md`, `laurels.md`, `sessions.log`, `history/`, `journal/` (headless wakings), `mail.md` (unread; the seat archives it); markers `RESTART`, `LIMITED`, `LAST-LIMITED`, `SHIFT-OVER` the launcher and hooks pass between them
- `brain/` - `rulings/` (status, what enforces each); office reports land beside it when offices join

## Rhythm

`cd <repo> && curia launch <seat>`: the seat works the board, opens PRs and
hands off with `/handoff`. The principal reviews and merges, or names a gate
in repos.toml and runs `curia portcullis` to land what is reviewed and green.
`curia lictor` prints what is stuck, on demand; `curia status` says how old
the seat's memory is.

## Next

1. `curia rename example_crew <name>` from inside this workspace: a name from
   your naming family (estate.toml `naming_family`), so no seat name is
   ambiguous across estates. Then write `seats/<name>/charter.md`; the
   scaffold says "Fill in for this estate" where it needs you.
2. `repos.toml`: the repo, its branches, and its gate and leaf commands once it has CI.
3. `accounts.toml`: the config dir of each account this estate may use.
4. `curia check` until it is quiet.

## Growing

The crew shape adds a clerk seat, a Censor for red mornings, and the Lictor
and the Portcullis on launchd. Its roster blocks are in
`{{MECHANISM}}/templates/shapes/crew/roster.toml`; the office prompt is
`{{MECHANISM}}/templates/estate/prompts/censor.md` and the units are under
`launchd/` there (stamp in this estate's paths); a charter for each new seat
starts from `{{MECHANISM}}/templates/charters/`. `curia check` says what is
still missing. Seats never roam between estates.
