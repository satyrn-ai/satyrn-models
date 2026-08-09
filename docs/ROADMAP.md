# Roadmap

Current state only. This file is rewritten in place, not appended to —
history lives in git, not in a superseded-banner trail.

## t-strings corpus and Mellum2 fine-tuning (`spikes/tstrings/`)

**Established:** training a 12B model (Mellum2-12B-A2.5B-Instruct) on a
language feature it has never seen works standalone — bare model 5/100 on an
independently-authored benchmark, adapter alone 55.8/100, zero regressions,
from 443 training rows.

**Withdrawn:** the corpus does not beat documentation-in-prompt. Adapter +
docs vs. docs alone is not significant (p = 0.185, three seeds) — an earlier
p = 0.011 result was a stdout-parsing bug in the verification oracle that
deflated only the untrained control arm. See `spikes/tstrings/README.md`.

**Next actionable step:** grow the corpus per `spikes/tstrings/SP5_SCALE_BRIEF.md`
— roughly 30 additional seeds weighted to regex, logging, SQL, and HTML, the
patterns currently thinnest in the 5035-row candidate pool.

## PEP 750 original spike (`spikes/pep750/`)

Historical. Superseded by `spikes/tstrings/`; kept for its original
dataset-generation and evaluation scripts.
