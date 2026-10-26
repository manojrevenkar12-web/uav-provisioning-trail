# 4. "Systemic" means one place stands out beyond chance

Status: accepted

Counting failures by code finds what fails, not why. A lead acts on where: a slot to service, a lot to
quarantine, a release to stop, an operator to coach. The analysis tests each place with Fisher's exact test,
Bonferroni-corrected per code, and prefers the narrowest place that explains the same failures. A first version
compared a place against the rest of the line's rate taken as exact. It called noise systemic on one of 40 noise
shifts, so it was replaced by the exact test. The false-alarm rate on noise is now a test.
