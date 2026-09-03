# Brain

Rulings that span repos live in `rulings/YYYY-MM-DD-slug.md`; the shape is
`templates/ruling.md` in the mechanism repo. Each states what was ruled, why,
and what enforces it, and carries two lines the mechanism reads:

    status: enacted
    enforced by: hooks.json release-guard

The lifecycle is the fences one, in order: `proposed` (a question put to the
principal), `advisory` (custom; seats are told, nothing refuses), `enacted`
(written law every seat must obey), `enforced` (a program refuses or alerts:
a hook in `hooks.json`, a test, a `curia check` line; `enforced by:` names
it), `retired` (falsified; the status line changes and the reason is added,
the file stays). `curia rulings` lists them, `curia check` faults one with no
status, and the Lictor nudges when an enacted ruling has gone a while with
nothing enforcing it, or an open postmortem bead has gone a while with no
ruling citing it. A ruling is never deleted.

Office reports: `censor/` (morning), `lictor/` (nudges), `portcullis/` (what
landed, what was held and why).
