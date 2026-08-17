# PROTOCOL — how to work with the user on the NAS

**This file overrides the working style of `PLAN_NAS_FULL_SETUP.md`.**
The plan's content stays. Its pace does not.

## The user's explicit instruction

> "I want you to walk with me step by step BEFORE doing anything. For every
> feature, tell me what it is and ask me whether I want it enabled, what it's
> good for, and when I'd use it. I don't want you doing anything I don't
> understand."

Read that literally. He is not asking for a summary after the fact. He is
asking to understand and approve each thing **before** it happens.

## The unit of work is ONE FEATURE, not one phase

Do not batch. Do not do "the obvious ones" and ask about the rest.
Do not proceed on the assumption that an earlier yes covers this too.

## Before every change, present exactly this card, in Arabic

```
الميزة       : <name>
شنو تسوي     : one or two plain lines, no jargon
وش تستفيد إنت: tied to HIS setup — his photos, his Master AI, his family
متى تستخدمها : a concrete everyday example
لو ما فعّلتها : what he actually loses
التكلفة      : time / disk space / added complexity
تنرجع فيها؟  : reversible, or permanent — say which
مين ينفذ     : him in the DSM UI, or Claude Code over SSH
```

Then ask one question: **نفعّلها الحين؟ نأجلها؟ نتخطاها نهائياً؟**

Then STOP. No action until he answers.

## What you may do without asking

Read-only inspection only: listing packages, reading config, checking disk
health, reading logs. Nothing that writes, installs, enables, deletes,
schedules, or changes a permission.

If a read-only command needs sudo, say so and ask first — he should know when
root is being used on his machine.

## Language and tone rules

- Kuwaiti Arabic. Technical terms in English on their own line, not mixed
  inside an Arabic sentence.
- No unexplained jargon. First time a term appears (snapshot, Btrfs, quota,
  Team Folder, transcoding, DNS-01), define it in one line.
- If he asks "شنو يعني كذا" — answer it fully and do NOT continue to the
  action in the same message.
- Say plainly when something is optional or cosmetic. He should be able to
  skip things without feeling he broke the plan. The certificate work in
  Phase 6 is cosmetic. Backups in Phase 4 are not.
- Never present a recommendation as the only option. Give the alternative and
  what it costs.

## Honesty rules

- If a plan step turns out to be wrong or impossible on Synology, say so
  directly and stop — like the `administrators` group issue in
  `CORRECTION_NAS_PHASE0.md`. Do not quietly work around it.
- Never report something as verified that you did not actually run.
- If a command fails, show the real error. No silent retries with a different
  approach unless you say what you're doing and why.

## Standing safety rules

- SSH on the NAS stays OFF except while a step is actively running. Ask him
  to enable it, work, ask him to turn it off.
- No passwords handled by you, ever. He types those himself.
- Anything irreversible (volume, filesystem, deleting shares or snapshots)
  gets a second explicit confirmation naming what will be lost.

## Ordering

Follow `PLAN_NAS_FULL_SETUP.md` for WHAT to cover and in what order.
Follow THIS file for HOW to move through it.

Current position: Phase 0 complete and verified. Phase 1 (read-only
inventory) is next — that one may run without per-item approval since it
changes nothing, but explain what you're collecting and why before you start.
