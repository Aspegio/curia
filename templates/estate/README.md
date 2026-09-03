# {{ESTATE}} estate

Seats, law and memory for the {{ESTATE}} estate. Mechanism lives in `{{MECHANISM}}`.

- `roster.toml`, `repos.toml`, `accounts.toml` - who, where, whose tokens
- `house-rules.md` - appended to every seat's prime
- `hooks.json` - the estate's fences: hooks carried into every seat session
- `seats/<seat>/` - `charter.md`, `handoff.md`, `laurels.md`, `sessions.log`, `history/`, `journal/` (headless wakings), `mail.md` (unread; the seat archives it), `assignments.log` (fleet); markers `RESTART`, `LIMITED`, `LAST-LIMITED`, `SHIFT-OVER` the launcher and hooks pass between them
- `brain/` - `rulings/` (status, what enforces each); office reports (`censor/`, `lictor/`, `portcullis/`)
- `prompts/` - office prompts (`censor.md`, `lictor-cloud.md`) and the fleet's briefs (`dispatch.md`, `review.md`)
- `launchd/` - scheduled offices on this machine (the Censor at six, the Portcullis on an interval)
- `../worktrees/<seat>/<repo>` - fleet workers' homes, given by `curia dispatch`, removed by `curia reap` once landed
