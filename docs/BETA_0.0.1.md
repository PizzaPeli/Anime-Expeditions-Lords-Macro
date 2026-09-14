# 0.0.1 beta — validation status

This working branch combines the supplied 0.31.6 source with the requested
custom behavior. The requested merge scope is implemented as version 0.0.1.
It is a beta and has not been pushed.

Implemented: portal search text at fixed lobby (460,180) and chooser
(506,187) positions; per-task middle-card or Roblox-auto-selection choice;
No Macro implies Auto Play; default walking path and camera setup; restored
drag blocks; progressive Auto Shop search, pending-not-located state, and
card identity checks before purchases.

Validation: 145 focused portal/shop/camera/drag/settings/UI tests passed.
JavaScript syntax, Python compilation, and lint checks passed. The complete
legacy suite reported 879 passed, 34 failed, and 5 skipped. Most failures are
tests for the deliberately replaced portal implementation or stale contracts
from the two source histories; several attempt real screen capture without a
live Roblox window. They are not counted as merge-flow validation.

Before promoting this beta to a stable release:
- Validate the portal search points, first-result selection, both card-choice
  modes, camera/path behavior, and an empty portal search in Roblox.
- Validate one cheap numeric and one Max Auto Shop purchase in Roblox. Existing items use
  bundled screenshot-derived references; Meat lacks a card identity reference
  and remains pending. New folders currently need icon.png and identity.png.
- Improve end-of-list detection against animation and capture failures;
  check modal uncertainty cannot allow another purchase in the same visit.
- Reconcile or retire the remaining legacy tests before declaring the whole
  historical test suite clean.

Personal settings.json was not intentionally imported or edited.
