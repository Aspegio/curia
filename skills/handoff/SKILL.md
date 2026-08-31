---
name: handoff
description: Close out a Curia seat session properly - write the handoff note the next session wakes up to, then request a restart. Use when the user says "hand off", "take a beat then hand off", "wrap up", "close out", or when context is deep and the seat should end cleanly instead of being compacted or exited. Only for sessions launched as a Curia seat (CURIA_SEAT is set, or the system prompt names your seat).
---

# /handoff

A handoff is a request, not a SIGTERM. You consent to it, finish what is safe
to finish, write your own notes, and ask to be woken again. The next session
is you, reading your diary.

1. Identify your seat: `echo $CURIA_SEAT`, or the seat named in your prime.
   If there is neither, say so and stop; this skill is for seats.
2. Finish or park. Anything mid-flight is committed to a branch or left with a
   clear note. Never leave a bead claimed that nobody is working.
3. Run `curia handoff <seat> --begin`. It archives the previous handoff to
   `history/` and prints the path to write.
4. Write the handoff at that path following the template it names
   (`templates/handoff.md` in the mechanism repo): where things stand, beads
   touched, decisions and why, loose ends and what next, for the principal,
   notes to self. Under about 150 lines. No secrets. Never falsify: if
   something went wrong, that goes in plainly.
5. Run `curia handoff <seat> --done`. It records the session and sets the
   restart marker so a `--loop` launcher wakes you again with the new note.
6. If this handoff is because of a usage limit, also run
   `curia limit current --until "<reset time from the error, ISO>"` so the
   relaunch lands on the fallback account instead of the limited one.
7. Tell the principal in one line that the handoff is written and the session
   may end. Do not exit yourself.
