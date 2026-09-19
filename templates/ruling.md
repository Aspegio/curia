# Ruling - <slug>, <date>

status: proposed
enforced by: nothing yet

## What was ruled
One paragraph. What every seat must now do, or never do.

## Why
The incident, postmortem bead or question that led here. Cite bead ids; the
Lictor stops nudging a postmortem once a ruling names it.

## What enforces it
The program that refuses or alerts: a hook in `hooks.json`, a test, a `curia
check` line. Until there is one, the status stays `enacted` and the ruling is
law by obedience; when there is one, name it on the `enforced by:` line and
set the status to `enforced`. A fence that refuses should append a line to
`brain/fences.log` (the mechanism's do); the Lictor reads it to say whether
this fence is idle or busy, and a fence nobody can account for is retired.

## History
- <date>: proposed by <seat>, ruled by the principal
