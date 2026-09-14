# v0.0.1 beta

First combined beta based on the creator's 0.31.6 update and the custom macro branch.

- Portal queue tasks now use one portal-name field and the first result from the
  built-in search bar. The fixed search points are `(460, 180)` in the lobby and
  `(506, 187)` after a run; portal priority, trait avoidance, and per-task slot
  coordinates are removed.
- Portal chains can either pick the middle offered portal or let Roblox choose;
  the latter simply waits for the result screen.
- `No Macro` now always means in-game Auto Play. Camera setup and a known map's
  default walking path still run; unknown maps safely skip missing path setup.
- Auto Shop now discovers item cards progressively while scrolling, validates
  card identity before buying, derives purchase controls from the visible card,
  and leaves unseen items pending for a later visit without runtime OCR.
- The default interface now uses true-black surfaces with balanced red accents;
  success and warning states retain green and amber for quick recognition.
- Includes the creator's 0.31.6 Challenge, Bounty, Shop, UI, capture, recovery,
  and reliability changes while retaining custom macro blocks such as Drag.

# v0.31.6

## Fixed -- the macro could spend 30 minutes reading a screenshot of another app

Root cause of every portal failure in the 0.31.5 session, and it is not in the
portal code.

`debug/region_match_result_timeout.png` (00:32:35) and
`debug/region_rejoin_timeout.png` (00:35:11) are **byte-identical** -- md5
`8a4261d8...`, 340,670 bytes both. Between them Roblox was closed, relaunched
and re-docked (00:33:40 - 00:33:51). Two frames of a live game cannot be
identical across a client restart. And they are not of the game: both show the
user's chat client, which was sitting over the Roblox rectangle.

The default capture path is a screen-region grab of the window's rectangle, so
it returns whatever is in that rectangle -- including a window in FRONT of the
game. `capture_game_gray` states the assumption that made that acceptable ("the
runner only ever calls this while Roblox is the actually-visible, foreground
game"), and it is false the moment anything covers it.

Everything else in that session is downstream of the same stuck frame:

- `Neither "victory" nor "defeat" matched within 30 min` -- watching a picture,
  then blaming the reference art and sending the user to the Image Manager.
- `"nav_play" not found within 15s -- likely a silent disconnect` -- force-closed
  and relaunched a perfectly healthy client.
- `leave_stage` matched **1.00** on six clicks that never cleared it.
- `nav_closeui` found and clicked **eight times in a row**.
- Four consecutive `Couldn't open a portal after 2 attempts`, across a
  14-minute wedge in which every layer said "continuing anyway" and handed the
  wedged client to the next one.

**Nothing noticed.** That is the defect fixed here -- the capture path already
has a documented answer (Settings > General > "Hardware Capture Fix", the WGC
backend, which reads the game's own composed frames and cannot be covered), but
a macro that reads the screen has to be able to tell "the screen is not
changing" from "the screen keeps telling me the same thing", and it could not.

### The detector

`vision.capture_game_gray` now records a 64x64 signature of every FULL-WINDOW
capture; `capture_unchanged_seconds()` reports how long it has been identical.
Sub-region captures are not tracked -- a HUD corner or a button box is
legitimately identical for long stretches, while a live full frame effectively
never repeats (this game animates its lobby, its world and its timers).
`FROZEN_FRAME_SECONDS` is 300s: far past any legitimate pause, six times sooner
than `MATCH_RESULT_TIMEOUT`.

`_frame_is_frozen` says so once per stretch, names the likely cause and the
setting that fixes it, saves `debug/region_frozen_frame.png`, and resets the
clock. Wired into:

- **`_wait_for_match_result`**, checked next to the Victory/Defeat search. Ends
  the wait in 5 minutes instead of 30, and returns the ordinary failure result
  so the caller recovers to the lobby and re-enters.
- **`_ensure_lobby`**, ahead of both "not a disconnect" vetoes. Sitting on a
  portal screen for a moment is still not a disconnect; sitting on a screen
  that has not changed a pixel in five minutes is, and the rejoin now happens.
  The freshness check runs FIRST so a frozen frame cannot use its own stale
  contents as the alibi.
- **`_attempt_rejoin_locked`** resets the clock when it launches a fresh
  client, so a loading window does not inherit the old window's freeze.

## Fixed -- backing out clicked a dead corner X eight times

`_spam_back_until_gone` closes a corner X when there is no Back button, then
looks again -- a loop when the click does not take, ended only by
`BACK_SPAM_MAX_CLICKS`. The 0.31.5 log ran all eight, ~3s apart, on one
unchanging screen. It now stops after `CLOSE_X_MAX_CONSECUTIVE` (3) identical
closes with no Back button ever appearing, and says why.

## Fixed -- pressing Stop was reported as an empty inventory slot

`_portal_step` returns False on a Stop, so stopping mid-activate printed
`Couldn't get to the party screen after picking a portal from the inventory --
either the slot is empty or Activate never registered.` That accuses an
inventory that was never the problem. All three portal-step diagnostics
(`Select`, `Activate`, `Start`) now check `stop_event` first and stay quiet.

# v0.31.5

## Fixed -- the chooser route, run against a lobby that had not drawn yet

Seven "Couldn't start a portal from the chooser" stops in one session. **Six of
them were the macro clicking the Portal Selection point into the lobby floor.**

`region_portal_chooser_stuck.png`, the screenshot the runner saves on giving
up, is the **lobby** -- Play button plainly visible at (113, 484). And the
shape is identical every time:

```
23:47:34 Challenge pass finished -- resuming "Chooser Portal".
23:47:47 Not on the lobby and the post-run anchors didn't match -- assuming
         the result screen is up and trying the chooser route anyway.
23:47:57 "portal_select" not on screen; falling back to the calibrated point (292, 581).
         (x3, ~10s apart, none registering)
23:48:40 Couldn't start a portal from the chooser.
```

Thirteen seconds after Return to Lobby, every time. `_reach_portal_activated`
decided its route from a **single instantaneous** `find_image("nav_play")`, and
this machine's lobby routinely needs 20-35s to redraw -- the same session logs
"the lobby turned up on the second look -- it was just slow, not gone" five
separate times from `_ensure_lobby`, which does wait. So a lobby mid-render read
as "not the lobby", the code fell through to its documented "assume the result
screen" guess, and three blind clicks went into empty ground.

Two fixes, and the route logic itself is unchanged -- only how confidently the
question gets answered:

- **`_portal_lobby_visible`** replaces the instantaneous check. Fast path
  first, then a bounded wait (`PORTAL_LOBBY_CONFIRM_WAIT`, 8s). This costs a
  genuine post-run entry nothing: the chooser matches on the fast path above it
  (0.92 every time it worked), and the Portal Selection screen never renders
  `nav_play` anyway.
- **`_portal_expect_lobby`** is the strong signal. The Challenge, Crafting and
  Act 4 diversions all leave via Leave Stage + Return to Lobby, so they *know*
  where the next entry starts. They now say so, and that entry gets
  `_ensure_lobby`'s full 35s patience (`PORTAL_LOBBY_EXPECTED_WAIT`) instead of
  a guess. Set at both Challenge exits -- the in-task resume and the pre-queue
  "moving on to the Task Queue" pass, which accounts for the other two stops.

The seventh stop (22:51:35) is unrelated -- a Portal Scanner detail-pane
re-read mismatch on a real chooser screen, which is known bug #1's territory.

Not changed: the refusal to fall back to the lobby inventory after a failed
chooser route. That refusal is correct and is what kept this bug from spending
portals; it is just no longer reached for this reason.

# v0.31.4

## Fixed -- a Defeat screen the macro could not see

`defeat` never matched. Measured against two real Defeat frames saved on the
user's own machine (`debug/debug_screenshot_1.png` and
`debug/screen_manual_20260908_000520.png`), all three shipped crops peak at the
**top** of the scale sweep and still miss the 0.90 bar:

| crop | best score | at scale |
| --- | --- | --- |
| `defeat.png` | 0.858 | 1.10 |
| `defeat_alt2.png` | 0.888 | 1.10 |
| `defeat_alt3.png` | 0.829 | 1.10 |

Same failure as `nav_area` (0.28.1) and `challenge_loaded`: art cut smaller
than this UI renders it, peaking at 1.10x, silently under the bar. All three
find the banner in the right place -- (167, 144) -- they just never clear the
threshold, so `_wait_for_match_result` polled a result screen that could no
longer change and the run would only have escaped at `MATCH_RESULT_TIMEOUT`,
30 minutes later.

- **`Assets/ui/defeat/defeat_current.png`** ships beside them: a 75x25 crop cut
  1:1 from that frame, the same way `victory_current*.png` were. It scores
  **1.00 at 1.0x** on both Defeat frames.
- **`"defeat": 0.85`** added to `_BUILTIN_NAME_THRESHOLDS` as the brace under
  it. Safe margin: the new crop scores at most **0.56** on non-Defeat frames (a
  Victory result screen, the portal chooser).

## Fixed -- Auto Play verified on, then off again by the first wave

The same run lost a Challenge stage it had already set up correctly:

```
00:02:16 Auto Play button reads "o Auto Play, k" -> off
00:02:16 Auto Play is off, this task wants it on -- clicking it (attempt 1/3).
00:02:20 Auto Play button reads "(c) AutoPlaying" -> on
00:02:20 Auto Play is now on.
00:02:22 Found Start Game (nav_start_game, score 1.00) -- clicking it (attempt 1/3).
00:02:24 Found Start Game (nav_start_game, score 1.00) -- clicking it (attempt 2/3).
00:02:31 Moving into Battle.
```

The result frame 2m8s later shows the button back on **"Auto Play"**, with
**Total Kills 0** and **Total Damage 0**. It was read as on, and it was off by
the time the waves started -- and nothing ever looked again, because Auto Play
was only ever set once per entry, before Start Game.

`_reassert_autoplay_after_start` now reads the button one more time immediately
after the Start Game sequence and re-sets it if it reads the wrong way. It is a
read-then-act check, never a blind click, so it cannot turn off a run that is
already auto-playing -- which is also why it is safe on a portal entered from
the chooser (convention 9 forbids touching that button blind, not reading it).
Expedition is skipped; it has no such button.

The stale comment in `_play_one_match` that claimed Auto Play was handled
"after the round has actually started" has been corrected -- it was set before
Start Game and nothing confirmed it afterwards. Now both halves are true.

# v0.31.3

## Verified -- the Portal Priority controls, without the game

Roblox was down, so 0.31.2's fix was checked headlessly instead. The six
functions were pulled out of `ui/app.js` and driven under node with a stub
`findTask` / `setTaskProp` / `renderTaskBuilder`. **24 assertions, all
passing:**

- Add a portal to a task that already has one -- the case that was broken.
- Type into the new row (trimmed on the way in).
- Reorder, including the no-ops at the first and last row.
- Clear a row's text -- the row survives now, blank, instead of vanishing.
- Remove past the last row -- never leaves the box with nothing to type into.
- A brand-new portals task, a legacy `portal_name` task, duplicate names, and
  `portal_priority` stored as a bare string.

The 0.31.1 code was run against the same script and reproduces both failures
exactly: `+ Add Portal` leaves the drawn rows byte-identical, and clearing a
row's text empties the list. So the fix is demonstrated, not assumed.

`runner._portal_targets` was checked against the same seven stored shapes and
agrees with the UI on all of them -- including the blank rows the editor can
now hold, which it drops as before. No settings migration needed.

## Context

`AI_CONTEXT.md` brought current:

- The header claimed the working tree "is at 0.24.8". It now points at
  `VERSION` and says not to quote a number there.
- The **Releases** entry still described shipping
  `lords-macro-portals-<version>.zip` overlays. Those stopped at 0.26.2;
  it now records that work goes straight into the working tree, and why.
- Known bug #13 records how the fix was verified, and the general form: this
  kind of UI logic does not need the game -- pull the functions out and drive
  them.

# v0.31.2

## Fixed -- every control in Portal Priority did nothing

`+ Add Portal`, the arrows, the remove button, even clearing a row's text --
all of them ran, and the box redrew looking identical.

One function was doing two jobs. `portalTargets()` drops empty entries, which
is right for the RUNNER: a blank row is not a portal to go looking for. But
the editor was reading its rows from it too, so:

- **`+ Add Portal`** appended a blank row, and the very next render filtered
  that blank row straight back out. Nothing to see.
- **Clearing a row's text** deleted the row instead of leaving it there to be
  retyped.
- **The arrows** looked dead because with one row there is nothing to reorder
  -- correct, but indistinguishable from broken.

Split in two:

- `portalPriorityRows(t)` -- what is stored and edited, blanks kept.
- `portalTargets(t)` -- what the runner is told, derived from the rows,
  trimmed, blanks dropped, de-duplicated.

`runner._portal_targets` already filters on its side, so a stored blank row is
harmless there and no settings migration is needed.

Also: the up arrow on the first row and the down arrow on the last are now
greyed out, so "nothing to reorder" reads as unavailable rather than broken.
Removing the last row leaves one blank row rather than an empty box with
nothing to type into.

# v0.31.1

## Fixed -- Auto Shop couldn't find Cancel on an open purchase modal

```
[Shop] The purchase modal IS open ("shop_purchase_modal" matched) but "shop_cancel"
       was not found on it -- and every part of the purchase (amount toggle, final
       Buy) is positioned from Cancel, so this pass cannot continue.
```

The Screen Snapshot added in 0.29.0 caught the frame, and it settles it: the
Buy Amount modal was fully open with Cancel plainly visible. The art was cut
too small -- convention 3c-ter again.

Scored against that real docked frame, the whole modal set peaks at the TOP of
the scale sweep, which is the signature:

| template | size | best score | at scale |
|---|---|---|---|
| `shop_cancel` | 181x28 | **0.807** | 1.05 |
| `shop_amount_max` | 43x22 | **0.900** | 1.10 |
| `shop_amount_min` | 48x28 | 0.642 | 1.10 |
| `shop_buy` | 32x28 | 0.835 | 1.10 |

`shop_cancel` never cleared the 0.90 bar, so no purchase could proceed.
`shop_amount_max` scrapes it at exactly 0.900 *at the very edge of the sweep*
-- one slightly different frame from failing the same way.

Shipped beside the originals (never replacing them):

- `shop_cancel/shop_cancel_modal.png` -- 201x37, the whole button including
  its borders. Scores **1.000** on that frame, at scale 1.0, at exactly one
  location.
- `shop_amount_max/shop_amount_max_modal.png` -- 51x32, same: **1.000**, one
  location.

The offsets that position everything else (`AMOUNT_INPUT_FROM_CANCEL`,
`AMOUNT_TOGGLE_FROM_CANCEL`, `FINAL_BUY_FROM_CANCEL`) scale by
`width / CANCEL_ANCHOR_BASE_WIDTH`, so they need no change -- and they land
CLOSER with the new anchor. Checked against the measured positions on that
frame:

| region | measured | from new art | from old art |
|---|---|---|---|
| amount input | (374, 374, 56, 32) | (376, 370, 53, 32) | (389, 376, 50, 30) |
| Max toggle | (726, 373, 51, 32) | (726, 370, 53, 32) | (721, 376, 50, 30) |
| final Buy | (369, 420, 203, 37) | (370, 418, 205, 40) | (384, 421, 194, 38) |

The old anchor put the amount input 15px off in x; the new one is within 4px
everywhere.

## Note

`shop_amount_min` (0.642) and `shop_buy` (0.835) are both under the bar on that
frame too, and `shop_buy` matched the GRID's Buy button rather than the modal's
"Buy1x". Neither blocked this pass -- the modal's Buy is found by region, not by
template -- so they are left alone rather than guessed at. If a later pass fails
on one of them, the fix is the same: press Screen Snapshot on the open modal and
recut from that frame.

# v0.31.0

## Removed -- "assign a macro to every Story map first"

```
[Macro] Auto Challenge was not enabled. Assign a saved Macro Operation to every
Story map first (missing or old macros: School Grounds ("Autoplay"), ...)
```

That gate is gone, for Auto Challenge, Daily Challenge and Auto Bounty alike.
It was refusing to enable a whole feature over a condition that has a perfectly
good answer: **a map with no usable macro runs on Auto Play.**

- `_story_macro_setup` is advisory now. `setup_ready` is always true;
  `missing_maps` / `invalid_maps` stay in the payload because "which maps will
  fall back to Auto Play" is worth showing, but nothing reads them as a veto.
- Clearing a map's macro no longer switches Auto Challenge or Auto Bounty off.
  It logs *"<map>" has no Macro Operation -- it will run on Auto Play.*
- The three refusal branches and their UI warnings are deleted rather than
  left dead.

## Fixed -- a macro that no longer exists

The message above was not lying: the "Autoplay" template was assigned to all
six maps and had stopped resolving. That case is now handled where it happens
instead of before the run: `_macro_is_usable` is checked at the moment the map
is identified, and a name that no longer resolves (renamed, deleted, imported
from another build) is dropped with a line saying so, and the map plays on Auto
Play. Entering a stage with no blocks *and* no Auto Play was the one outcome
that helped nobody, and it was what the old gate existed to prevent -- badly.

## Changed -- Auto Bounty gets the per-map Auto Play field too

`bounty.maps.<map>.auto_play`, same meaning as Challenge's, and `auto_play` is
now always set on the Bounty task dict. It was missing entirely, which
`_settle_autoplay_for_match` reads as "off" -- so a Bounty map with no macro
was having Auto Play switched off with nothing else to play it. (No toggle in
the Bounty UI yet; it defaults to off, and "no macro" still forces it on.)

## Changed -- Expedition never looks for an Auto Play button

There isn't one. `_settle_autoplay_for_match` returns immediately for
`mode == "expedition"` instead of spending `AUTOPLAY_BUTTON_TIMEOUT` on every
entry to conclude what was known before it started.

# v0.30.0

## Added -- Auto Play is a per-map Challenge setting

Each Story map in **Challenge > Maps** now has its own Auto Play toggle,
beside its Macro Operation rather than instead of it.

- **Both together.** Pre Start still walks the path and places the units, then
  Auto Play plays the round. That combination had no way to be expressed
  before.
- **No macro assigned = always on**, shown as such and not togglable. Something
  has to play the map.
- Stored per map (`challenge.maps.<map>.auto_play`), read by
  `_run_challenge_battle`, and named in the log: *landed on "King's Tomb" --
  running "Autoplay" with Auto Play on.*

This replaces a workaround, and removes the bug it caused. The only way to get
Auto Play on a Challenge map with a macro was a template whose Pre Start
clicked the Auto Play button itself -- and that fought `_ensure_autoplay` every
single entry, one turning it off and the other back on, which is what three
releases of "the Auto Play bug" were really about. The runner inferred the
setting from whether a macro was assigned; now it just reads the setting.

Existing templates that click the button still work (0.29.1 fixed that click),
but they are no longer needed: assign the macro, turn the toggle on, and drop
the Detect/Click pair from Pre Start.

# v0.29.1

## Fixed -- the Click block's click wasn't registering

The Auto Play read is now correct and the double-click is gone:

```
Auto Play button reads "o Auto Play" -> off (autoplay_off 0.96, autoplay_on 0.69)
```

What is still not happening is the *click* that was supposed to switch it on --
and that click does not come from `_ensure_autoplay` at all. It comes from the
"Autoplay" template's own blocks:

```
Pre Start block #2 (Detect): image "autoplay_off" -- FOUND at (1093, 474) score 0.96. Running Then branch.
Pre Start block #3 (Click): clicking (1093, 474).
```

Right point, right button, and Auto Play stayed off. The Click block was using
a bare `mouse.click()` -- a cursor that teleports onto the target and presses.
It skips both things this codebase has already learned the game needs: the
window has to actually hold focus, and a number of Roblox buttons only
register after genuine hover-IN movement (the same reason `vision.click_match`
shuffles, added for the lobby Event button). The corroboration is three lines
further down in the same log, where Start Game needs `attempt 2/3` -- the same
swallowed-first-click signature.

It now goes through `_hover_click`, which asserts focus and shuffles in. Still
no image search and no verification afterwards: the block clicks where it is
told, whatever is or isn't there, which is what makes it the escape hatch.

## Note

Nothing else in this release. The 0.29.0 label OCR is working exactly as
intended on both maps -- `autoplay_off 0.96` against `autoplay_on 0.69` and
`0.80` -- so the state read is no longer guessing, and the run made it through
two Challenge stages with no toggling.

# v0.29.0

## Fixed -- the Auto Play double-click

```
Auto Play is on, this task wants it off -- clicking it (attempt 1/3).
Found "autoplay_on" (score 0.81) -- clicking it.
Auto Play is on, this task wants it off -- clicking it (attempt 2/3).
Found "autoplay_on" (score 0.89) -- clicking it.
Auto Play is now off.
```

The first click worked. The second undid it -- and the Detect block right
after proves it, sitting through all 20 of its searches without finding
`autoplay_off`.

Two causes, both fixed:

**0.28.9's label OCR never ran.** The tell is that "Auto Play button reads
..." appears nowhere in a 700-line log. `portal_scan.ocr_variants` upscales 4x
and then hands the result to `ocr_best`, whose `candidate_masks` upscales
**six times again** -- 24x on a 150x42 button is a 3600x1008 image through a
bilateral filter, and it came back empty every time. `_autoplay_read_label`
now does its own OCR with the recipe that was actually measured against the
saved frames (4x cubic, then plain / CLAHE / Otsu / inverted, psm 6), which
read `'o Auto Play'` and `'oS" Auto Play |'` -- correctly off, on both.

**A blind retry on a toggle undoes itself.** Every state read fell back to
template scores, and an OFF button matches `autoplay_on` at up to 0.89, so the
verification kept saying "still wrong" after a click that had worked. On a
toggle an unreliable verification is *worse* than none -- one click at least
lands on the right side of the coin. The runner now tracks where the state
came from (`label` or `template`) and, when it could not actually read the
button, clicks once and stops rather than retrying. It says so in the log the
first time it happens.

## Added -- Screen Snapshot (Settings > Debug > Screenshot)

A basic tool for "it's stuck and I don't know what it's looking at":

- Brings Roblox forward, saves one picture of its own window to `debug/`,
  returns focus here. Nothing is clicked, nothing changes -- safe mid-run.
- Separate from the Portal Scanner's **Test Read**, which reads four
  portal-specific regions and judges them; that output is meaningless on any
  other screen.
- Also separate from **Debug Screenshot**, which grabs the screen *rect* --
  so whatever is in front of Roblox is what lands in the file.
- **The runner now takes it itself** when a route gives up:
  `portal_reselect_mismatch` when a re-selected slot comes back as a
  different portal, and `portal_chooser_stuck` when the Portal Selection
  screen never opens. Both of those failed three times in the last run with
  nothing kept to look at.

## Fixed -- Debug actions no longer leave Roblox in front

Test Read (and the new Snapshot) have to steal focus to capture the game. They
were leaving it there, so the panel sat behind the game afterwards -- the
first click on anything went to raising the window instead, which reads as the
UI having broken. Both now hand focus back to the panel when they are done,
and the JS drops to the dashboard before starting. `_focus_game_for_debug` /
`_return_focus_to_panel` in `main.py` are the shared pair, so the next Debug
action that touches the live game gets it right by default.

# v0.28.9

## Fixed -- "Auto Play is already on" over a button that was off

The Auto Play fallback never activated anything, and the run had to be
switched on by hand. `_autoplay_state` checked `autoplay_on` first at a
relaxed 0.80 bar and returned on the first hit. Measured on the two saved
Challenge frames, with Auto Play verifiably **off** both times:

```
autoplay_off_label  0.956   0.956
autoplay_on_label   0.776   0.810
```

0.810 cleared the 0.80 bar. The run reported "already on -- nothing to do"
and played the match with Auto Play off.

The old code's comment claimed an OFF button cannot match the ON art. It can:
"Auto Play" is a literal prefix of "Auto Playing", so the templates overlap in
**both** directions and no threshold or margin rule can separate them --
that is why the previous fix went the other way and produced this one.

So the templates now only LOCATE the button, and **OCR reads what it says.**
"Auto Playing" is on, "Auto Play" without the "ing" is off. Unambiguous at 4x
on both frames (`'o Auto Play'`, `'oS" Auto Play |'` -> off, correctly). The
crop is padded outward past the matched box on purpose: the OFF template's box
ends exactly where "Auto Play" ends, so the "ing" that proves ON lies just
past it. Template scores stay as the fallback for a machine with no OCR, and
the decision is logged with both scores.

## Fixed -- the map label reads, on the second frame too

0.28.8's band worked on the Flower Forest frame and still missed King's Tomb.
Three things, each measured on the two saved frames:

- **The band was 4px too tall.** Text occupies y 325-341; the band ran
  317-354 and caught scenery rows top and bottom. Tightened to y 0.4259-0.4577.
- **psm 7 only.** psm 7 is "one line", which the band is -- until it catches a
  pixel of the row above, at which point psm 6 is the one that reads it. psm 7
  alone gets `"inrChallende #2 Kins TOBAGO"`; psm 6 on the same image reads
  `"Reguiar, Challenge #2 King's Tomb - Act 4"`. Both modes now run.
- **First-past-the-post scoring.** An early garbage read scored 0.75 ("toba"
  against "tomb") and cleared the bar before the clean 1.00 read was even
  tried. Every read is scored now and the best margin wins, so a fluke can
  only win when nothing better exists.

End to end on both saved frames: **1.00** for the right map, runner-up 0.36
and 0.73.

# v0.28.8

## Fixed -- the map WAS on screen the whole time; the crop was wrong

The frame 0.28.7's diagnostic saved settles it. Top right, in plain text:

> **Regular Challenge #1 Flower Forest - Act 2**

Nothing was broken about detection in principle. `_challenge_map_ocr_crops`'
fallback band (x 0.58-0.98, y 0.42-0.52) is 461x76 -- it contains that label
and also about a hundred pixels of grass, tree and rock around it, and
Tesseract reads that as noise. Measured on that exact frame, same OCR, same
engine, only the crop changed:

```
old band  ->  "@-= ad -_ | 86 Ss 7 | _ 7 ~ 45 = @ Recnilar Challenae #1 Flower Forest - Ac"
new band  ->  "Reaular Challende #1 Flower Forest - Act 2"
```

The new band is measured, not guessed: the label is one right-aligned line at
y 322-350, x 860 to the frame's right edge in reference space
(`CHALLENGE_MAP_LABEL_BAND`). It reads "Flower Forest" on every contrast
variant and both PSM modes. Scored end to end against the real reads it comes
out at **1.00** with the runner-up at 0.36, while the 0.28.6 noise read that
produced the bogus "East Town" is now rejected outright.

Right edge is the frame's own, not 0.98w -- the label is flush to it and 0.98
clipped "Act 2" off.

`CHALLENGE_MAP_OCR_STOPWORDS` gains `regular`, `hard`, `mode` (the Regular
Challenge label's own boilerplate, plus the "Hard Mode" tag sitting inside the
band) and `forest`, which is shared by Fairy King Forest and Flower Forest and
so identifies neither.

## Note on the Beta zip

The Beta (0.24.21) was unpacked and its `core` modules read out of the
PyInstaller archive. There is nothing to revert to: `_run_challenge_battle`
there carries the identical `": never recognized a map -- stopping."`,
`_detect_current_challenge_map` and `_challenge_map_ocr_crops` are the same
functions, `vision`'s `SCALE_FACTORS`, `DEFAULT_THRESHOLD` and
`_effective_threshold` are unchanged, and all six maps' `Assets/ui/<map>/`
folders are byte-for-byte identical (verified by md5). The Beta worked because
its runs happened to land on maps whose scenery art matched; the crop bug was
always there waiting.

The image-template path is still the weak one -- best scores on that real
frame were 0.50 / 0.51 / 0.56 / 0.46 / 0.75 / 0.57, i.e. scenery matching from
a camera angle that no longer lines up. It is left in place as the first try,
with the OCR band now doing the real work behind it.

# v0.28.7

## Fixed -- the map check no longer ends the run

This is the answer to "the old build's Auto Challenge worked flawlessly".
Identifying the map only ever decided **which Macro Operation to run**. It was
never a precondition for playing the round -- but `_run_challenge_battle`
returned `None` when it failed, so a stage that had been entered, loaded and
was sitting there playable got abandoned, which dropped the run into the
leave/rejoin path and took the rest of the session with it.

Unrecognized now means "no macro assigned", which that code already knew how
to handle: play it on Auto Play. Same fallback an unassigned map gets, and
strictly better than stopping.

`auto_play` is now set on the Challenge task dict too (`"macro"` with a macro,
`"autoplay"` without). It was never set at all, and `_settle_autoplay_for_match`
reads a missing key as OFF -- so a Challenge map with no macro did not merely
run blockless, it got Auto Play switched **off** and nothing played. With the
fallback above that would have become the common case.

## Fixed -- the map OCR named a map out of pure noise

```
Challenge map OCR: "a 5 -. . . . 7 : " ye 7 es a es" -> "East Town" (score 0.67).
```

The fragment `es` scores 0.67 against `east` (two matched characters out of
six), nothing else in that noise came close, so it cleared both the 0.65 floor
and the runner-up margin -- and the Daily Challenge then ran East Town's macro
with full confidence. A wrongly-named map is worse than an unnamed one, now
that an unnamed one just plays on Auto Play.

Tokens shorter than `CHALLENGE_MAP_OCR_MIN_TOKEN` (4) no longer score at all
-- every alias is at least four characters, so a two-letter fragment cannot be
evidence of one. Floor raised to 0.72.

## Fixed -- the Portal Scanner clicked its own winner off the board

```
taking "Summer Portal" from slot 3 (priority #1, read "Tier }Fus | Summer Portal")
re-selecting slot 3 -- confirmed (the slot changed, 74.7% of it)
slot 3 reads "'oe 1.8)x >" -- not a portal this task wants
re-selecting that slot did not bring back the same portal -- NOT confirming
```

A priority #1 hit `break`s the scan loop the moment it is found -- which
leaves the winner as the **currently selected** slot. The re-select then
clicked it again, and clicking an already-selected slot toggles it OFF. The
74.7% "change" was the detail pane emptying; the unreadable text was a pane
with nothing in it. The click did exactly what it was told.

The scan now tracks which slot the selection is on and re-reads instead of
re-clicking when the winner is already it.

## Fixed -- "nav_play vanished" is no longer a verdict

Gone is not the same as failed. That line is only ever reached on a retry --
after a Play click whose `nav_back` wait timed out -- and the commonest reason
Play is now missing is that the click **did** work and the menu is already up,
having taken longer than `STORY_SCREEN_TIMEOUT` to draw. Routine on a client
relaunched moments earlier; the 0.28.6 log turns it into "stopping" twice,
both within a second of a rejoin. `_click_play` now looks for `nav_back`
before concluding anything.

## Fixed -- the focus check was crying wolf

0.28.6's `LOBBY_WAIT_ALIVE` veto did not fire, because on a black loading
screen there is nothing recognizable to see -- so the rejoin still went ahead
and still force-closed a healthy client. `_ensure_lobby` now waits a second
full `LOBBY_CHECK_SECOND_CHANCE` (20s) before doing something irreversible.
Twenty seconds of patience only ever costs a run that was about to be
destroyed anyway.

And the focus warnings themselves were mostly false. The 0.28.6 log reports
"couldn't confirm focus" on `nav_area`, `nav_shop` and `area_gold_shop` in a
row -- and every one of those clicks landed, because the next screen appeared
each time. `GetForegroundWindow() == hwnd` is too strict: after a rejoin the
dock hands the runner one hwnd while the foreground is held by another
top-level window of the same Roblox process, and SendInput does not care which
one is in front. New `_focus_confirmed` accepts same-process (new
`wm.get_foreground_window`), which turns a stream of meaningless warnings back
into a signal worth reading.

`_shop_enter_gold_shop`'s own `activate_window` bail is advisory now too --
the same fix 0.28.6 made one function earlier, missed here.

# v0.28.6

## Fixed -- the macro was force-closing a healthy Roblox client

Three separate runs in the 0.28.5 log end the same way, and every one of them
starts with the same line:

```
[Macro] Checking you're on the lobby...
[Macro] "nav_play" not found within 15s -- not on the lobby (likely a silent
        disconnect), attempting a rejoin via deep link.
[Macro] Closed the disconnected Roblox client -- launching a fresh one.
```

The client was not disconnected. The macro had just clicked "Return to Lobby"
seconds earlier, and the lobby simply had not finished redrawing inside
`LOBBY_CHECK_TIMEOUT`. Roblox got killed and relaunched for it -- and
**everything that fails afterwards in that log is downstream of that
relaunch**: the failed focus before Play, the "nav_play vanished", the Shop
stopping.

`_ensure_lobby` already had a veto of exactly this shape for the portal
screens. It is now general: after the full wait fails, one look for anything
proving the game is still up (`nav_unitmanager`, `leave_stage`, `victory`,
`defeat`, `result_modal_close`, `nav_back`, `challenge_loaded`) skips the
rejoin and reports what is actually on screen. The Roblox reconnect prompt is
deliberately not on that list -- that one is a real disconnect and
`_handle_disconnect` still owns it.

## Fixed -- `_force_focus` gave up after half a second

Two attempts 250ms apart, and only `activate_window` on each. On the one path
that keeps failing, that is not enough and never was: a freshly relaunched
Roblox refuses the foreground for several seconds, and every "Couldn't confirm
focus before clicking Play" in the log lands within a second of "Roblox
docked".

It now waits the client out (up to `FOCUS_WAIT_TIMEOUT`, 4s), calls
`wm.show_window` before *every* attempt -- which `_run` and the Debug test
path have always done and `_force_focus` was the one place that skipped, and
which matters most against a brand-new window the dock watchdog has only just
re-parented -- and confirms with `wm.is_foreground` rather than trusting
`SetForegroundWindow`'s return value, since the change can land a frame after
it reports failure.

## Fixed -- one refused activation killed the whole Auto Shop run

```
[Shop] Starting Auto Shop for 1 item(s).
[Shop] Couldn't confirm Roblox took focus.
[Macro] Stopped. (was: Preparing Gold Shop...)
```

`_run_auto_shop` was the only place in the app that treats a refused
`SetForegroundWindow` as fatal -- it `return`ed on the spot. Nothing else
does; the runner's own start-up path logs it and carries on. All three
occurrences are within ~15s of a rejoin, i.e. exactly the window in which the
fix above says the client legitimately refuses focus. It now uses
`_force_focus`, and if that still cannot confirm, it says so and keeps going.

## Added -- "never recognized a map" now says why

`Challenge #1: never recognized a map -- stopping.` is the least actionable
line in the log: it cannot tell "the art is close but under threshold" (re-cut
it) from "nothing here looks like a map at all" (we are not where we think we
are) from "OCR is missing". On the way out, `_report_challenge_map_miss` now
runs one pass with `find_in_gray_multiscale_diagnostic` and prints the best
score each of the six Story maps actually reached, then writes the frame to
`debug/challenge_map_miss_<timestamp>.png`.

Unconditional, not behind Debug Match Screenshots: this path already ends the
run, so one PNG per stopped run is not the flood that toggle exists to
prevent.

**This is instrumentation, not the fix.** The map-detection failure itself is
still unexplained -- the art is byte-identical to the build where it worked,
and the log proves the macro really was in the match (it found `leave_stage`
at 1.00 immediately afterwards). The next run's score line should settle it.

## Withdrawn

The 0.28.5 note blamed `nav_unitmanager_alt5.png` / `alt6.png` for firing
early on a loading screen. Measured: they are 143x43 and 94x24, and the stock
`nav_unitmanager.png` is **91x21** -- alt6 is not the outlier that note
claimed. The 0.28.5 log also shows the teleport wait taking a full 18s before
matching, which is not the signature of a premature hit. Leave them in place.

# v0.28.5

## Fixed -- the Victory screen was mistaken for the Portal Selection screen

```
Opening the Portal Selection screen -- already done (that screen is showing), skipping the click.
Portal Selection screen did not appear after Select Portal.
```

Those two lines are one bug. The "already there, don't click" shortcut
(convention 4) accepted ANY of the step's verification witnesses, and one of
them is `portal_chooser_header` -- the swirl banner around the words "Portal
Selection". **The Victory screen wears the identical banner with different
text, and grayscale matching does not read text.** So on the result screen
the header matched, the route decided the list was already open, skipped the
click that would have opened it, and then failed its own verify.

Verifying and skipping now use different evidence. Verifying still accepts
either witness -- any proof the screen opened will do. Skipping requires the
**green Select button**, which exists only once the list is genuinely open.
`_portal_step` takes a `skip_if` for this.

## Changed

- The post-result log line said "Portal selection was handled during the live
  round", which reads as though something else did it. It now says the macro
  made that choice itself, during the round.

## Found, not shipped -- what broke Auto Challenge

You asked me to compare against the Beta build where Challenge and Auto Shop
work. The map art is **byte-identical** between that build and your tree --
same five `East Town` crops, same bytes -- so the maps are not the problem.

The difference is in `nav_unitmanager`. The working build ships **eight**
crops. Your tree has those eight plus two you saved yesterday:
`nav_unitmanager_alt5` (143x43) and `alt6` (**94x24**). That 94x24 crop is
small and generic, and `nav_unitmanager` is what "Teleported in-game" waits
for -- so a crop that matches too early declares the teleport finished before
the map has drawn, and the very next step is `Challenge #1: identifying the
map... never recognized a map`.

The timeline fits exactly: map detection worked for weeks, you added those
two crops, and it broke in the same session.

**Try deleting `nav_unitmanager_alt5.png` and `nav_unitmanager_alt6.png`**
(Assets/ui/nav_unitmanager/). I have not deleted them myself -- they were
added deliberately to fix a teleport that was not being detected, and if
removing them brings that back, the answer is a bigger crop rather than
neither.

# v0.28.4

Your Victory-screen Test Read gave the first capture of the result panel.
Three things came out of it.

## Fixed -- `portal_exit` was not a crop of that button at all

`portal_exit_live.png` is 64x74 and peaks at **0.665 at every scale** against
your real result screen -- it never had a chance, which is why every single
exit falls back to a coordinate. The actual Exit button is a **58x46** red
icon tile at (672, 560); its centre is (701, 583), which is exactly the
fallback point the log has been clicking. `portal_exit_result.png` is cut
from your frame and self-matches at 1.00.

## Better `autoplay_on` art

The shipped crop scores **0.912 at scale 1.0** on a genuine "Auto Playing"
button, so it is not badly scaled -- but the log's live reads were 0.80 and
0.89, i.e. right on the 0.90 line. A tighter 139x32 crop of the button is
added (`autoplay_on_result.png`), unique on the frame at 0.483.

**And a correction to yesterday's Auto Play theory.** I said the toggle was
being double-clicked. Re-reading it with the art measured, the likelier story
is simpler and matches everything else this week: the FIRST click was
swallowed and the second one worked. The scores rising 0.80 -> 0.89 across
the two attempts is consistent with the button still being ON both times,
which a real double-toggle would not produce. Which leads to:

## Fixed -- most of the macro's clicks never asserted focus

`_click_found_image` is what clicks nearly every nav button in this project,
and it clicked without ever taking focus first. Play does reassert focus, and
the portal route does (convention 5) -- but everything else went through this
helper. Your logs are full of

```
Found "X" (score 1.00) -- clicking it.
... the next step then times out on a screen that never changed
```

which is exactly what a click the game never received looks like. It now goes
through `_force_focus` (two attempts, 250ms apart) like the paths that were
already doing it right. This is one change with a wide blast radius: the
Challenge nav, the shop route, the Auto Play toggle and the teleport buttons
all click through it.

## Note

The log you sent is still v0.28.2 -- restart to pick up 0.28.3's Daily
Challenge fix, which is why the daily still says "unavailable (score 0.78)"
there.

# v0.28.3

## Fixed -- the Daily Challenge was skipped on a 0.78 guess

```
[Macro] Daily Challenge is unavailable for this game day (score 0.78) -- skipping.
```

Available and unavailable are the SAME card in two states, and both were
searched at a **0.75** bar with the negative one checked first and winning
outright. 0.78 is a "worth looking at" score, not proof of anything -- and on
that reading the macro threw away the whole day's daily, three times in your
log, on a day it was plainly available. Convention 3b: two states of one
thing cannot be told apart by a loose match; they have to be COMPARED.

Both are now scored and weighed:

| unavailable | available | result |
|---|---|---|
| 0.78 | — | **enter** (too weak to skip a day on) |
| 0.78 | 0.80 | **enter** (too close to call) |
| 0.80 | 0.79 | **enter** (no margin) |
| 0.92 | — | skip |
| 0.95 | 0.80 | skip |

The tie deliberately leans toward TRYING, because the two mistakes are not
equal: a wrong "unavailable" silently costs the daily every day and looks
like normal operation, while a wrong "available" costs one failed entry that
the recovery path already handles and logs.

## Fixed -- the Play click after a rejoin

Every `Couldn't confirm focus before clicking Play` in your log is followed
by `"nav_play" vanished before it could be clicked` -- a click the game
ignored. It fires right after a rejoin has re-docked the window, which is
exactly when Windows is most likely to refuse the first foreground request.
That call was still a single `activate_window`; it now goes through
`_force_focus`, which asks again 250ms later (0.25.0).

## Understood, not yet fixed -- Auto Play

Your log finally shows the mechanism:

```
Auto Play is on, this task wants it off -- clicking it (attempt 1/3).
Found "autoplay_on" (score 0.80) -- clicking it.
Auto Play is on, this task wants it off -- clicking it (attempt 2/3).
Found "autoplay_on" (score 0.89) -- clicking it.
Auto Play is now off.
```

Two clicks on a toggle is one click too many: the first almost certainly
turned it off, the state was then re-read as still on, and the second click
turned it back on -- with the third read finally calling it off while it may
well have been on. Both reads scored **below the 0.90 bar** (0.80, 0.89),
which is the same marginal-art pattern as everything else this week, and
convention 3h already records the specific trap here: "Auto Play" is a prefix
of "Auto Playing", so the OFF template scores HIGHER on an ON button.

I am not fixing this blind. What settles it: an Image Manager capture taken
in-match with Auto Play **ON**, and a second with it **OFF**. Both crops can
then be measured and re-cut the way `nav_area` was, and the state rule
checked against real scores instead of assumed.

# v0.28.2

## Fixed -- `shop_purchase_modal` was never looked at

You cut the amount/purchase window and it changed nothing, because **nothing
in the code ever searched for that name**. "Did the modal open?" was answered
by looking for the Cancel BUTTON (`shop_cancel`) and nothing else, so a
Cancel crop that misses is indistinguishable from a Buy that never worked —
and the log confidently blamed insufficient Gold for what is a template
problem.

- `shop_purchase_modal` is now a real template name
  (`AUTO_SHOP_UI_TEMPLATES["purchase_modal"]`), **detection only** — never
  clicked, so its crop may be the whole modal. Your 429x179 capture works as
  it is.
- The open-check waits for **either** Cancel or the modal.
- "Did it close?" now requires **both** to be gone, so a modal that lingers
  is not read as closed.

One thing this does not do, and it matters: **Cancel is still required.**
Every later step is positioned FROM it — the amount toggle, the final Buy and
the cancel click all derive their regions from `cancel_match` — so the modal
art proves the window is up but cannot replace it. When the modal matches and
Cancel does not, the log now says exactly that and names the crop to recut,
instead of blaming Gold.

## Fixed -- a fallback path that could never have run

`_shop_open_purchase_modal_fallback` asked for
`AUTO_SHOP_UI_TEMPLATES["modal_cancel"]` — a key that has never existed in
that dict. It raised `KeyError` every time, and a bare `except Exception`
swallowed it, so the fallback silently did nothing for as long as it has been
there. Now uses `"cancel"`, and catches only `TemplateNotFound`, which is the
one failure that is actually expected.

## From your log

`nav_area` matched at 0.97–0.99 on every pass — 0.28.1's recut works, and
Auto Shop now gets four screens deeper than it could before. Your recuts of
`nav_shop`, `area_gold_shop` and `shop_gold_tab` each unblocked the next step
in turn, which is the same wrong-scale art class again.

Still ahead of it: `Trait Crystal was not found at its calibrated scroll
position (-720)` on one pass and found on the next — the pre-existing Auto
Shop open item, most likely the out-of-stock card rendering differently
rather than the scroll being wrong.

# v0.28.1

## Fixed -- `nav_area` was ~35% too SMALL, so Auto Shop could never start

Your lobby Test Read gave the first lobby capture, and it settles bug #2.
The shipped `nav_area.png` is **41x40**; the real Areas button on your docked
1152x756 screen is **58x64**. Matched against your own frame across the whole
scale sweep:

```
scale 0.90 -> 0.483      scale 1.05 -> 0.799
scale 0.95 -> 0.485      scale 1.10 -> 0.895   <- top of the sweep, still under 0.90
scale 1.00 -> 0.533
```

`SCALE_FACTORS` stops at 1.10 and the default bar is 0.90, so it peaked at
**0.895 at the very edge of the sweep** and missed -- which is why Auto Shop
died on entry every single time with `"nav_area" not found within 10s`, on a
lobby the very next check confirmed we were standing on.

This is convention 3c-ter in mirror image: every previous case was art cut
too BIG from an undocked window, so it is worth stating the rule without a
direction. **Art cut at the wrong scale in either direction misses silently,
and a fallback coordinate hides it.**

A correctly-scaled `nav_area_live.png` (58x64, the tile plus its full "Areas"
label) is added beside the old crop -- nothing removed, since every `*.png`
in a folder is tried. It self-matches at 1.00 on your frame and its
next-best match anywhere else on that frame is 0.583, so it is unambiguous.

## Still open

- **`portal_exit`** cannot be recut yet. Both of your portal-screen Test
  Reads were on the Portal Selection list; Exit to Lobby lives on the result
  panel one screen earlier, and no capture of that exists. Press Test Read on
  the Victory/result screen -- BEFORE clicking Select Portal -- and it can be
  cut the same way.
- **Auto Play** still needs a run with the task set to Macro rather than Auto
  Play. Everything in these logs is the task's own `auto_play: autoplay`
  behaving as designed, which neither confirms nor rules out what you are
  seeing.

# v0.28.0

Your Test Read on the post-run screen is the first capture of the Portal
Selection list this project has had, and it answered two of the open bugs
outright.

## Fixed -- the chooser is a DIFFERENT screen, and was being read as if it weren't

Not the inventory in another frame: five columns instead of four, pitch ~89
rather than ~92.7, and the whole panel sits left and up of the inventory's.
The detail pane moves with it, about 25px left.

- **Chooser lattice measured**: 5 x 4 = 20 slots at x 263/352/441/530/619,
  y 243/332/421/511. Verified by drawing all twenty points back onto your
  frame -- every one lands dead centre on a card. It had been a copy of the
  inventory lattice, which would have clicked between cards.
- **The detail regions are now per screen.** This is the one worth stating
  plainly, because the shared pair looked perfectly reasonable until both
  were OCR-ed against real captures of each screen: the inventory pair reads
  its own screen **4/4** and the chooser **0/4**, where it slices "Summer"
  into "mmer" and cuts the Traitless icon off its pill. Chooser name is
  `(690, 196, 210, 42)` and modifier `(694, 400, 265, 72)`; both read 4/4 on
  your frame, `Summer Portal` matches and `Traitless` is caught.
- **Test Read now reads BOTH pairs every press** and draws all four boxes on
  the frame. It cannot know which screen is up, and reading one pair is
  exactly how a good calibration looks like a failure on the other screen.

## Fixed -- the pane was read before it finished changing

The slot-1/2/4 noise from your last run (`"TT ~~ So are an | V0 7]"`) while
slots 3 and 5 read perfectly. Same regions, same run, so it was timing.

- `_wait_for_detail_pane` accepted ONE comparison under 1% as settled. A pane
  that fades in moves less than that between two frames while still half
  drawn. It now needs **two consecutive** stable comparisons, and never reads
  before a 0.25s minimum settle -- the dangerous version of this bug is not
  noise but reading the PREVIOUS portal's name, which the pane still shows
  mid-transition.
- **A slot that matches nothing is now read a second time**, after parking
  the cursor again, because the park does not always clear the hover card on
  the first go (as you reported). One extra OCR pass, and the log says when
  the second look is what saved it.

## Added / changed

- **A fresh `portal_chooser_confirm` crop cut from your own frame** (264x42,
  the green Select button) -- correct scale by construction, unlike the
  inherited art that never matched.
- `_spam_back_until_gone` no longer claims "failed map search" when it is
  Auto Shop or a portal route backing out.

Still open, unchanged: `nav_area` and `portal_exit` both need recutting (no
capture of either screen yet), and Auto Play needs a run with the task set to
Macro rather than Auto Play before anything is guessed about it.

# v0.27.1

## Calibrated -- the scanner's geometry now comes from YOUR screen

Your Test Read frame is the first real capture of Items > Portals this
project has had, and it settles three things that were previously inherited
from the other build's window.

- **The slot lattice was wrong by ~70px in x.** The 0.26.0 defaults put
  column one at x=287; the real cards are centred at **359, 452, 544, 637**,
  with rows at **240, 332, 424, 517** (pitch ~92.7 across, ~92.3 down).
  Column one at 287 would have clicked the left nav, not a card. Measured off
  the frame by edge-detecting the card borders, then checked by drawing the
  sixteen points back onto it -- every one lands dead centre on a card.
- **Four rows, not five.** A fifth row is half-drawn at the panel's bottom
  edge, and the grid scrolls (your panel reads 20/100), so anything past the
  first sixteen needs scrolling the scanner does not do yet.
- **Both detail regions are tighter and measured.** Name is now
  `(715, 190, 200, 44)` and modifier `(718, 408, 235, 72)`. Checked by
  actually OCR-ing your frame: the name reads "Summer Portal" on every
  preparation variant, and the modifier region finds Traitless on **8 of 8**
  where the old wider region managed 2 of 8 -- most of what it covered was
  portal art.

End to end against your frame: `Summer Portal` matches, `Summer Portal Tier
5` matches (tier stripped), `Sky Ruins Portal` and `Sovereign's Portal`
correctly do not, and the blacklist catches Traitless.

**The Portal Selection lattice is still unverified** -- that screen has never
been captured, so it starts as a copy of the inventory one. If a chooser scan
reports "not one slot reacted", Test Read on that screen is the fix.

## Fixed -- the OCR fallback was overriding its own psm

`ocr_variants` asked `ocr_best` for `--psm 6`, but `ocr_best` substitutes its
own sweep INTO the config string, and its default sweep is (7, 8) -- single
line and single word. So the one preparation that works on a two-line detail
pane was never actually used. Measured on your pane: psm 6 reads "Summer
Portal", psm 7 reads "Sacnner Partal". Now passed explicitly as the sweep.

If you pressed Save on the Portal Scanner panel before this, your saved
values are still the old ones -- press **Reset to defaults** to pick these up.

# v0.27.0

Both of these come from sxlt's Task Builder, which is worth copying where it
is better than ours.

## New -- Card Select: Default or Advanced

The three-card portal offer has been hover-and-filtered since 0.24.24 with no
way to turn it off. Per task now, same as his:

- **Default** takes the middle card and moves on -- the pre-0.24.24 behaviour.
- **Advanced** hovers each card, reads its detail sidebar and skips the
  modifiers the task rejects (falling back to the middle card if all three
  are rejected).

Advanced stays the default, so nothing changes for an existing task. It is a
real switch rather than a legacy path: the hover costs about three seconds
against the offer's ~20s auto-select timer, and on a machine where the
modifier art does not match it buys nothing. The blacklist rows are hidden
under Default, since nothing reads them there.

## New -- Portal Priority, an ordered list

The single "Portal Name" box is now a list, best first: **"Summer Portal,
then Sovereign's if there is no Summer left"** is one task instead of two.

- The scanner takes the highest-ranked portal it can find in the grid.
- **One pass, not one pass per portal.** Every slot is clicked and read once,
  the best rank seen is remembered, and a slot matching #1 ends the pass
  immediately since nothing can beat it. Priority-outer would have meant up
  to (portals x slots) clicks for the same answer.
- The winner is **re-selected and re-read** before anything is confirmed: the
  pass moves the selection on to later slots, and "I clicked the slot I
  meant" is exactly the assumption that spends the wrong portal. If the
  re-read doesn't bring back the same portal, it stops rather than confirm.
- Rows reorder with the arrows; `|` still separates spellings inside one row.
- `portal_name` from 0.26 is still read as a one-entry list, so existing
  tasks keep working. The JS and Python halves of that rule were tested
  against the same five cases and agree.

# v0.26.4

## Fixed -- Test Read was photographing the macro, not the game

`debug/portal_scan_frame_regions.png` from the 0.26.1 run settles it: the
captured frame is **the macro's own Settings window**, with the two regions
drawn neatly over an empty panel. Pressing the button left our window in
front, and on a setup where captures go through a screen grab rather than
PrintWindow, a screen grab returns whatever is actually on top. The regions
were never the problem, and neither was OCR -- it was reading our own UI.

Test Read now does the same focus dance every other Settings > Debug action
that touches the live game already does (`show_window` + `activate_window`,
then a short settle before capturing) -- the pattern `read_rewards`,
`debug_test_path`, the Camera Setup buttons and path recording all follow.
`FOCUS_SETTLE` is the settle: the window is still being raised and repainted
for a moment after the call returns, and a capture taken inside that moment
can still hold what was covering it.

## Fixed -- two more places where the new code did not match the old

Both found by re-reading this session's additions against the originals
rather than by hitting them:

- **`find_tesseract_binary` re-probed on every call.** Each probe spawns a
  real `tesseract --version` subprocess, and `get_ocr_status` (which the
  Settings screen polls) called it -- reintroducing exactly the repeated
  subprocess cost `_resolved_tesseract_cmd` was written to kill, complete
  with the console-window flashes that memoization was added to stop. It now
  goes through the same memo, and `reset_tesseract_cache()` still forces a
  fresh look for the installer.

- **The Portal Scanner retried every empty inventory square three times.**
  `_click_portal_slot` exists to catch ghost clicks, where a retry is right.
  A scan walking a grid is a different job: a square that does not react is
  an EMPTY square, which is a normal thing to find. Probing now clicks once
  and stays quiet, so a 15-slot scan is one pass instead of up to 45 clicks
  and forty log lines. Its summary distinguishes "no slot reacted at all"
  (empty inventory, or wrong slot positions) from "slots reacted but nothing
  was readable" (OCR or region problem).

# v0.26.3

## Removed -- the last two blind clicks in the portal route

Both were clicks into a screen the code had just admitted it could not
identify. Neither had anything to verify against, so neither could tell you
whether it had helped or made things worse.

- **"Dismissing anything covering the post-run screen"** (middle of the
  screen, on entry) is gone. It fired whenever the post-run anchors missed --
  in the 0.24.21 log, two seconds before the chooser route failed. In its
  place the cursor is parked and the anchors are checked once more, which is
  the safe half of what that click was reaching for: a hover card really can
  cover them, and moving the mouse away costs nothing and risks nothing.

- **"Dismissing the post-run screen"** (middle of the screen, before Exit to
  Lobby on the last portal) now only runs if Exit to Lobby was NOT found. A
  reward overlay covering it is real, but that is a reason to dismiss
  something *when the button is missing*, not to click blind on every last
  portal whether anything is covering it or not. Convention 3c: a recovery
  click needs a precondition.

The `screen_middle` click that remains is the one in
`_dismiss_reward_card_if_found`, which fires only after the reward-card art
has actually been matched -- it clicks a card it can see, which is the
opposite case.

# v0.26.2

## Fixed -- "Installed successfully" while Tesseract was not usable

Both halves of your log were true at once:

```
[Tesseract] Installed successfully.
[Health] FAIL Text reading (OCR) -- Tesseract failed: Tesseract OCR engine not found.
```

**winget without admin installs into `%LOCALAPPDATA%\Programs\Tesseract-OCR`
and puts nothing on PATH.** `core/ocr.py` only ever looked in `C:\Program
Files\Tesseract-OCR` and the (x86) twin, so the engine was genuinely on disk
and genuinely unfindable. The installer then reported winget's exit code as
if it were the outcome, which is how a failed setup announced itself as a
success.

- The search now covers `%LOCALAPPDATA%\Programs\Tesseract-OCR`,
  `%LOCALAPPDATA%\Tesseract-OCR`, both Program Files locations (read from the
  environment, not hardcoded), and `shutil.which`.
- **The installer verifies its own work.** It returns the path of a Tesseract
  it has actually RUN, or nothing. winget exiting 0 is no longer treated as
  success, and when the binary can't be found afterwards the log says exactly
  where it looked.
- The resolved path is **remembered** (`tesseract_cmd` in settings) and
  re-applied at every launch, so an engine that isn't on PATH only has to be
  sorted out once. If it later moves or is uninstalled, the stale path is
  dropped rather than pinning every read to something that no longer runs.
- `get_ocr_status` now reports the path it found and why Windows OCR is
  unavailable, so "installed" can be checked rather than believed.

**Separately, Windows OCR is unavailable on your machine for its own reason:**
`No module named 'winsdk'`. That is a pip dependency from `requirements.txt`
missing from this build, not something the Tesseract button can fix -- but
with Tesseract now actually wired up, the scanner has an engine either way.

## Removed -- the corner click that never closed anything

`_close_open_panels` clicked the window's top-left corner on the theory that
it was the lobby's close button and would shut whatever panel a failed
attempt had left open. It never did that. The logs agree: "Closing any open
panel before retrying" is followed by exactly the same failure as before,
every time.

What that corner is genuinely good for is somewhere harmless to **park the
cursor**. So the click is gone and the move stays -- and the move now also
happens where it was actually needed:

- **The Portal Scanner parks before every read.** The cursor sits on the slot
  it just clicked, which is the most reliable way there is to raise a hover
  card over the detail pane it is about to OCR. That was a real chance of the
  scanner reading nothing on a slot that was perfectly fine.
- `_portal_anchor`'s existing park is now the same helper (`_park_cursor`)
  rather than a second copy of it.
- The `portal_panel_close` coordinate stays in Settings -- removing a wired
  coord row has caused its own bugs before (convention 3j) -- but nothing
  clicks it any more.

## Fixed -- backing out of the Challenge screen

The Challenge screen has **no Back button** -- it closes with an X, and the
Back button belongs to the gamemode menu underneath it. `_spam_back_until_gone`
only looked for Back, so a run that failed there logged
`Back button gone after 0 click(s) -- done` and left the game parked on the
Challenge screen, with everything after it working against the wrong screen.

It now closes the X first (`nav_x`, then the long-shipped `nav_closeui`) and
looks for Back again, only stopping when neither is on screen. `_recover_to_lobby`
goes through the same path, so Auto Challenge's recovery gets this too.

# v0.26.1

## Fixed -- Test Read could not tell you what was actually wrong

"Nothing readable" had three completely different causes behind it and no way
to tell them apart, so the first calibration attempt had nothing to act on.
It now answers all three with one press:

- **The window wasn't captured at all** (Roblox minimised or unrenderable) --
  previously indistinguishable from a bad region, and it wrote no crops, which
  is why `debug/` stayed empty.
- **No OCR engine on this machine** -- then no region is right, because
  nothing can be read anywhere. It now names what it found and what Windows
  OCR said when it refused.
- **OCR works but both regions read nothing** -- only now is "the regions are
  wrong" the honest conclusion.

It also always writes **`debug/portal_scan_frame.png`** (the full frame) and
**`debug/portal_scan_frame_regions.png`** (the same frame with the two regions
drawn on it). Those are what new regions get measured from, and seeing the
boxes on the real screen makes a mis-aimed region obvious instead of inferred.

## Changed

- **The scanner now falls back to the project's full OCR chain.**
  `ocr_variants` tried Windows OCR alone over its 4x-upscaled variants; if
  that came back empty it now runs `ocr.ocr_best`, which is RapidOCR ->
  Windows OCR -> Tesseract over its own prepared masks. A machine without
  Windows OCR could not have scanned a single slot before this.

# v0.26.0

## New -- the Portal Scanner: a portal is chosen by NAME, not by square

This is the answer to convention 3f, and to "sometimes it selects the wrong
portal". Every portal bug this project has had comes back to one thing: a
coordinate is not a portal identity. Both grids re-flow as portals are spent,
so the square that held your Summer T5 yesterday holds something else today,
and the route spends it with a log that reads clean. No coordinate fixes
that. Only reading the card does.

**Type the portal's name into the task and the squares stop mattering.**

- **Task Builder > Portal Name.** Leave the tier off -- the card shows the
  tier on its own line, so "Summer Portal" matches every tier. Alternatives
  can be separated with `|`.
- The scanner clicks its way across the grid, reads each card's detail pane,
  and confirms only when the name matches and no blacklisted modifier is on
  it. A square holding the wrong portal is **skipped, not spent**.
- **A scan that finds nothing clicks nothing.** It does not fall back to the
  saved square: "I couldn't find your portal, so I'll click this one anyway"
  is precisely how the wrong portal gets spent.
- Works on **both** screens -- the lobby inventory and the post-run Portal
  Selection list. (The build this was reimplemented from only ever handled
  the post-run one; its Portal mode needs the first portal opened by hand.)
- With no name, nothing changes: the saved-coordinate path runs exactly as
  before, guarded by 0.25.0's click check. The queue row now says
  "name the portal, or pick both slots".

Matching is deliberately forgiving, because OCR of stylised game text is:
tier stripped from both sides, letters and digits only, and a sliding-window
fuzzy compare at 0.78 so the words around the name in the pane don't count
against it. "Sumrner Portal" matches "Summer Portal"; "Sky Ruins Portal"
does not.

## New -- Settings > Debug > Portal Scanner

The geometry the scanner uses: the squares it clicks on each screen, and the
two parts of the detail pane it reads. **Test Read** selects nothing and
changes nothing -- it reads the two regions right now, prints what came back,
and writes the exact crops to `debug/`, so a wrong region is obvious in one
look instead of being inferred from a failed run.

Be honest about this part: the shipped regions are measured from the other
build's window, not from yours. They are the same 1152x756 reference space,
so they should be close, but **expect one calibration pass** -- open a portal
screen, select a portal by hand, press Test Read. If it reads the name, the
scanner will too.

## Changed

- `_wait_for_detail_pane` holds off the read until two consecutive captures
  of the pane differ by less than 1%. Reading mid-repaint reads the PREVIOUS
  portal, which would hand the scanner the wrong answer with full
  confidence -- worse than having no scanner.

# v0.25.1

## Fixed -- the last two blind clicks in the portal route

Your 0.24.21 log falls back to a calibrated point on **every single cycle**
for both of these, which means neither button has been found by image in a
long time:

```
Opening the Portal Selection screen -- "portal_select" not on screen; falling back...
Confirming the portal (Select) -- "portal_chooser_confirm" not on screen; falling back...
```

The art is the reason, and it is convention 3c-ter again: our crops were cut
from an UNDOCKED window, so they are too big for the 1152x756 matching space
by more than the 0.90-1.10 scale sweep can reach.

- `portal_chooser_confirm.png` is **266x46**; the same button cut in docked
  space is **236x36** -- 1.13x too wide and 1.28x too tall.
- `portal_select_live.png` is **300x74** against **211x40** -- 1.42x and
  1.85x. That one was never going to match at any point in the sweep.

Four correctly-scaled variants are added beside them (nothing is removed --
every `*.png` in a folder is tried, so the old crops stay as alternates):

- `portal_chooser_confirm/portal_chooser_confirm_docked.png` (236x36) and
  `_docked2.png` (234x37) -- the green **Select** button.
- `portal_select/portal_select_docked.png` (211x40) and `_docked_tight.png`
  (142x41) -- the blue **Select Portal** button.

Both buttons should now be FOUND rather than clicked at a stored coordinate,
which means both steps get a real verification instead of a blind click that
"probably" landed -- the same class of problem as 0.25.0's slot clicks.

Art comes from the other build ("Macro summer update V5"), which normalizes
to the same 1152x756 space we do (its `core/config.py` is byte-identical on
these values), so its crops are in our matching space by construction.

**Not shipped:** their third confirm crop, a tight 62x23 cut of just the word
"Select". "Select" is a substring of "Select Portal", and a tight text crop of
one is a plausible match inside the other -- the two buttons live on different
screens, but that is precisely the kind of near-miss that spends a portal. The
two full-button crops make it unnecessary.

# v0.25.0

All five of these came out of your 0.24.21 log.

## Fixed -- the wrong portal, spent for real

- **Portal slot clicks now prove they landed.** Both portal squares -- the
  lobby inventory one and the post-run chooser one -- were coordinate clicks
  into a grid with no art of its own, so a click that never registered looked
  exactly like one that did. The route walked on to Select, and Select
  confirms whatever is *already* highlighted: a different portal, a real item
  spent, and a log that reads clean. `_click_portal_slot` captures a 150x90
  box around the point, clicks, captures again and requires 2.5% of it to have
  changed. Unchanged means re-click (3 attempts); still unchanged means STOP
  rather than press Select.

- **That click was also the one portal click not going through
  `_hover_click`.** It was a bare `mouse.click()` -- no focus assertion, no
  hover-in -- while every other portal click has asserted both since 0.22
  (convention 5). Your log has ~90 "Couldn't confirm focus before the click"
  lines in one session, and each one is a click Roblox was free to ignore.

- **Focus is now asked for twice.** Windows refuses a foreground change while
  another window is mid-activation; asking again 250ms later usually gets it
  (`_force_focus`). This is the ghost click at its source.

## Fixed -- multi-place never exited

- **A Z tap now leaves placing mode whatever put us in it.** 0.24.23 added Z
  to the quick-place *chain* release, which does nothing for a single Place
  Unit block: the hotkey still put the game in placing mode, and nothing takes
  it back out -- not a failed white-tile search, not the placement cap, not a
  Pre Start list that simply ended. The game then swallows everything that
  follows (Start Game included) as clicks aimed at the unit still in hand,
  which is the "it can't continue after multi-place" you hit.
  `_exit_placement_mode` is tracked (`_placement_mode_active`), so the tap
  fires exactly once and never on a run with no Place Unit blocks.

## New -- per-map camera profiles

- **Settings > Debug > Camera Profiles.** Pre Start framed every map
  identically -- tilt down, hold O for 2s -- with one hardcoded exception for
  Expedition. A profile is that same sequence made editable per map: tilt on
  or off, an arrow-key rotate for N ms, an O zoom for N ms. Pick a map, Test
  it against the live game, Save.
- Stored per MAP name, with a MODE name as a catch-all, resolved map ->
  mode -> built-in (`_camera_profile_for`). Expedition's sequence is now a
  built-in row rather than an `if`, and still honours the existing
  "Expedition Camera Zoom" calibration.
- A map with no profile behaves exactly as before. Malformed rows fall back
  to the built-in and values are clamped, so a hand-edited settings.json
  degrades to stock rather than hanging Pre Start for a quarter of an hour.

## Changed -- Portals behaves like the other modes on failure

- **A portal step that fails now asks whether the game is disconnected**
  before blaming the route. Story/Raid/Event reach failure through
  `_ensure_lobby`, which checks for Roblox's Reconnect/Retry prompt and
  deep-link rejoins; Portals reached failure a different way and had no such
  check, so a chain that dropped mid-run reported "couldn't start a portal
  from the chooser", told you to re-pick a coordinate that was fine, and
  stopped the task (`_portal_recover_disconnect`).

## Removed

- **The three bundled portal example templates.** Written for the pre-0.22
  workflow where a template drove the portal cycle; since 0.22 the task does,
  and the templates' Loop A clicked the same Select the task clicks and
  counts. A Macro Operation on a Portals task is for placing units during the
  run, nothing more.

# v0.24.24

## Changed -- the round's three portal cards are read, not guessed

Portals has always taken the MIDDLE card of the three the round offers,
because nothing told it what the other two were. It now hovers each card and
reads the detail sidebar that hover raises, taking the first one that carries
none of the modifiers the task rejects.

- **Traitless is skipped by default.** Per task, in the Task Builder
  ("Traitless Portal Cards" -- Skip or Take), stored as `portal_blacklist`.
  A task with nothing saved gets the default rather than "filter nothing"; an
  explicitly empty list means take whatever is offered.

- **The hover IS the mechanism.** The sidebar describes the card the cursor is
  ON, so the cursor moves to a neutral point and settles between cards --
  reading before moving would describe the previous card. This is the one
  place that deliberately raises a tooltip rather than parking the cursor to
  avoid one (convention 3g).

- **Every undecidable path still takes the middle card**: empty blacklist,
  missing reference art, or all three cards rejected. An offer left open
  blocks the round, so an unfiltered pick beats no pick. The offer's own
  auto-select timer is around 20s and three hovers cost about 3s.

- **New art: `portal_modifier_traitless`** -- the green "Traitless" pill from
  the sidebar, detection only, matched at **0.82** rather than the 0.90
  default. The two failures are not symmetrical: a miss takes a Traitless
  portal, a false positive only skips a card, so the bar leans toward the
  recoverable one.

- `_find_middle_portal_card` is now `_find_portal_offer_cards` and returns all
  three sorted by x with a `_slot` number for the log; choosing between them
  is `_pick_portal_offer_card`'s job.

Design and reference art come from reading another build of this macro
("Macro summer update V5"), which solves the same problem with the same hover
mechanism. Its constants are in the same 1152x756 reference space as ours.

# v0.24.23

## Fixed

- **Quick-place chains never exited placement mode.** 0.23.5's ending was
  written but the working tree's `core/runner_blocks.py` was six lines behind
  the 0.24.6 base and never got it, so every overlay since then shipped
  without it -- `_release_quick_place_shift` released Shift and stopped there.
  The game stays in placing mode with the unit still in hand, so the next
  Place Unit block's own Z/hotkey pair can collide with that leftover state
  and drop the wrong unit on the wrong tile. It now releases Shift and then
  taps **Z**, in that order, exactly as 0.23.5 described.

## Removed

- **The duplicate root-level `app.js` and `index.html`.** Leftovers from a
  pre-0.22 layout, ~1.5k lines behind the real files in `ui/`. Nothing has
  loaded them for a long time: `main.py` builds `UI_INDEX` from
  `constants.UI_DIR`, and the PyInstaller spec bundles the `ui` folder only.
  They survived because the release zip kept picking them up off the root,
  so every diff of the UI showed a second, older copy of itself. `CLEANUP.bat`
  now deletes them, and they are dropped from the release zip.

# v0.24.22

## Fixed

- **Portals never clicked "Return to Lobby".** Exit to Lobby brings up the same
  confirmation Leave Stage does; Challenge has always clicked it
  (`_click_return_to_lobby_if_found`), Portals never did. So the red button was
  pressed and the run then sat on the confirmation -- and everything after that
  looked like "not on the lobby", which is what sent the next check down the
  silent-disconnect path. Portals now clicks it too, the same way.

- **A stuck "rejoin pending" latch was burning ~105s per check, forever.** Once
  set it was only cleared by a rejoin that actually reached the lobby, so one
  bad diagnosis left it ON for the rest of the session: every later lobby check
  spent 15s failing to find `nav_play` plus 90s "waiting on the existing
  launch" and achieved nothing. Your log shows that loop repeating for hundreds
  of lines. It now expires after 5 minutes (`REJOIN_PENDING_TTL`).

- **A portal screen is no longer mistaken for a disconnect.** The post-run panel
  and the Portal Selection list are normal places to be, and `nav_play` is
  legitimately absent on both -- calling that a silent disconnect fired a
  pointless rejoin and set the latch above. The lobby check now recognises a
  portal screen and says so instead. This is the direct cause of your
  "sometimes it is in lobby after a challenge and says not in lobby".

# v0.24.21

## Changed -- fewer wasted clicks in the portal chain

All four came straight out of the logs, not from guesswork.

- **No more double corner click.** The chooser route's failure path calls
  `_close_open_panels`, and the retry loop called it again immediately after --
  two clicks at (3, 3) back to back, every retry ("Closing any open panel
  before retrying" twice in a row). A second click within 3s now collapses into
  the first; it could never have closed anything the first one didn't.

- **No back-out from the post-run screen.** On a failed chooser attempt the
  route used to spam Back and click the corner -- throwing away the exact
  screen it needs, so every later attempt started from a worse position than
  the first. It now stays put.

- **The retry loop only closes panels when the retry starts from the lobby.**
  On the post-run screen there is no stray panel to close.

- **Portal route attempts 3 -> 2.** Each attempt already re-clicks every step
  up to 3 times, so three full passes meant up to nine clicks per button on a
  route that works on the first click when it works at all. Map/Event/Tower
  keep their own count; this only changes Portals.

- **The cursor park no longer runs on the fast path.** 0.24.13 parks the mouse
  top-left before an anchor check; that also fired on the zero-timeout
  "are we already there?" probe before every step -- a move plus a 0.15s settle
  each time, on the path where nothing is wrong. It now runs only when the
  check is actually going to wait.

# v0.24.20

## Fixed

- **APPLY.bat was silently dropping most of the pack.** It copied `main.py`
  and four named files from `core\`, and nothing else -- so
  `core\runner_constants.py`, `core\runner_challenge.py` and the **entire
  `ui\` folder** were never applied. That is why the daily coordinate did not
  change in 0.24.17 or 0.24.19, and why 0.24.17's new Settings row, renamed
  labels and mouse-position read-out never appeared: the overlay was applied
  and those files stayed on the old version. It now copies `core\*.py` and
  `ui\` by wildcard, so nothing can be left behind by omission again.

## Changed

- **The Daily Challenge stage fallback now reuses "Challenge: Stage Slot 1".**
  The daily's single card sits exactly where the Regular Challenge's first card
  does, so a separate `daily_challenge_stage` point was two things to keep
  calibrated that can never legitimately differ.

  It was also the worse of the two: it had **no Settings row, no entry in
  `MACRO_COORD_DEFAULTS` and no place in `MACRO_COORD_KEYS`**, so it could only
  be changed by editing code and rebuilding -- which is why nudging it in
  0.24.17 and again in 0.24.19 changed nothing on a machine running an older
  build. Slot 1 already has a row and a Pick button, so one calibration now
  fixes both, on any machine, without a rebuild.

  `daily_challenge_stage_x/y` is removed from `DEFAULT_COORDS`; the
  `daily_challenge_stage` IMAGE is untouched and still tried first.

# v0.24.19

## Changed

- **Daily Challenge stage fallback is now (650, 260).** 0.24.17 moved it from
  360 to 315; 260 is the value confirmed against the real screen.

# v0.24.18

## Fixed

- **The shipped `autoplay_off.png` was contaminated.** Something translucent
  was sitting over the left two-thirds of the button when that crop was taken,
  dimming the gear tile and half the word "Auto". It matched on the PC where
  the same overlay happened to be present and failed everywhere it wasn't --
  which is exactly the "worked here, not there" pattern. Diagnosed by the user
  from the image itself.

  A clean capture is now the primary art, rescaled to docked space: the gear in
  the supplied crop matched a docked frame at **1.09x**, so it ships at
  1/1.09 (117x33) with the raw crop kept as a variant. The contaminated file is
  kept too, as `autoplay_off_overlaid.png` -- it is what matches when that
  overlay IS present, and extra variants never hurt.

- **The Auto Play state rule, corrected before it shipped wrong.** 0.24.17
  replaced the 0.93 bar with "score both states, take the winner by margin".
  Testing that against a real docked frame showed it was unsafe: on a button
  reading "Auto Playing", `autoplay_off` scores **0.86** against
  `autoplay_on`'s **0.81**, because "Auto Play" is a literal prefix of "Auto
  Playing" and the off template matches the left part of an ON button. The
  margin rule would have read ON as OFF and clicked auto-play **off**
  mid-match -- the precise failure it was meant to prevent.

  The rule is now: relaxed **0.80** locate bar (which is what finds the button
  on a machine scoring 0.81 where 0.93 saw nothing), but **ON is checked first
  and wins outright**. The asymmetry holds in both directions and both were
  measured: an ON button matches the off art, but an OFF button does not match
  the on art -- there is no "ing" to match. Verified end to end: a real docked
  "Auto Playing" frame reads `on`, a clean "Auto Play" frame reads `off`.

# v0.24.17

## Fixed

- **Auto Play was never found on a second machine.** `_autoplay_state` used a
  single 0.93 bar, and on that PC every image scored lower (portal_activate
  0.85 where it is 1.00 here) -- so the button was never seen and an Auto Play
  task ran without auto-play on, every round. Simply lowering the bar is the
  dangerous fix: the two states are the same button differing mostly in its
  label, and a loose match can call an ON button "off" and click auto-play OFF
  mid-match. Now both states are scored at a relaxed 0.80 locate bar and the
  winner must beat the other by `AUTOPLAY_STATE_MARGIN` (0.03); ambiguous still
  means "leave it alone", but that is now reached only when the frame really is
  ambiguous rather than whenever scores dip. The click uses the same relaxed
  bar -- identifying the button at 0.80 then refusing to click it at 0.93 would
  have found it and done nothing.

- **Daily Challenge stage fallback raised 45px** -- `daily_challenge_stage_y`
  360 -> 315. It was landing just below the card: close enough to look right in
  the log and never register.

- **`portal_chooser_confirm` now has a fallback coordinate**, default
  **(792, 564)**, wired through all three lists (`MACRO_COORD_KEYS`,
  `MACRO_COORD_DEFAULTS`, and its Settings row) so it can actually save. The
  log showed the green Select missing its image and then having no point to
  fall back to.

## Changed

- **The 3-card scan no longer floods the log.** It holds off **2 minutes** from
  the start of the battle, then checks every **5s** instead of every 3s from
  the first second -- ~50 identical lines per run became one. The offer's own
  auto-select timer runs ~20s, so a 5s poll still catches it several times.

- **A Portals task with a set count is now a batch.** With "Portals Then Exit"
  above 0, Challenge / Crafting / Fuel / Auto Shop / memory-refresh all wait
  until the requested portals are done -- each diversion costs a trip back to
  the lobby, which is the one thing the chooser route exists to avoid. Count 0
  (run until stopped) keeps the old behaviour, since it never finishes on its
  own and diversions would otherwise never run.

- **Clearer names for the two portal slots.** "Portal in lobby" / "Portal in
  chooser" are now **"Portal to run -- from the lobby"** and **"Portal to run
  -- after a run ends"**, with descriptions saying which screen each is picked
  on and why they are separate. The queue warning reads "pick both portals".
  In Settings, "Portal: Select Next Portal" is now **"Portal: Open Portal List
  (after a run)"** and its description names the grey Select Portal button on
  the Victory screen.

## New

- **Settings > Debug > "Show mouse position".** A live read-out of the cursor
  in the same 1152x756 space every Macro Coordinate uses -- hover anything in
  Roblox to read its x/y instead of going through a Pick picker. Read-only: it
  never moves the cursor, clicks, or touches focus. Says so when the cursor
  leaves the window, and reports the real window size if it is not docked.

# v0.24.16

## New

- **`BUILD_EXE.bat`** -- one double-click to produce the exe. Finds a Python
  (prefers 3.12, which `build_pyinstaller.py` is written against, and warns
  rather than refusing on anything else), installs `requirements.txt` +
  PyInstaller, runs the build, then assembles `dist\Lords-Macro-Beta\` with
  the exe, `Assets\`, `Templates\`, `docs\` and the version/readme files.

  **`Assets\` must sit beside the exe** -- it is deliberately not bundled
  inside it, because `core/constants.py` points `ASSETS_DIR` at the exe's own
  folder so reference images can be replaced and added through the Image
  Manager without a rebuild. Sending only the .exe gives you a macro that
  cannot match anything. The script assembles the whole folder and says so.

- **`CLEANUP.bat`** -- removes the overlay leftovers (`APPLY.bat`,
  `REMOVE_THESE.txt`, `README-FIX-PACK.md`), the retired `undocked_*` art,
  `__pycache__` trees, and truncates `debug.log`. The docked Image Manager
  captures are **moved**, not deleted, into `Assets\reference\captures\` --
  they are the only ground-truth frames for cutting art that matches, and
  sitting in `Assets\ui\` made them searchable template names for no reason.

# v0.24.15

## Fixed

- **Select worked, and the macro called it a failure.** The log is unambiguous:
  *"Confirming the portal (Select) -- found portal_chooser_confirm (score 1.00),
  clicking it"* followed by *"the click doesn't seem to have registered
  (portal_start / portal_party never appeared)"*. The click landed; the check
  was watching for the wrong screen.

  From the LOBBY, Activate opens a party screen and Start teleports. From the
  CHOOSER you are already in a session, so Select launches straight into the
  run and the game's own **"Start Game?" prompt** appears at the top -- no party
  screen ever renders. The confirm step now also accepts
  `PORTAL_IN_MATCH_IMAGES` (the Start Game prompt, the Start Game button, and
  either Auto Play state) -- the same set `_wait_teleport_in` already trusts.
  The failure log now names everything it watched for.

## Working as of 0.24.14

- `Opening the Portal Selection screen -- confirmed ("portal_chooser_header" is
  on screen)` -- the docked art fixed that screen.
- `Picking the portal from the chooser -- clicking (436, 242)` -- the chooser
  slot is used, not the lobby one.
- The 3-card pick continues to fire every run.

# v0.24.14

## Fixed

- **Portal Selection is finally recognised.** A docked Image Manager capture of
  that screen settles it: every anchor shipped for it needed **0.71-0.72x** to
  fit -- outside the 0.90-1.10 sweep, so all of them missed silently. The
  content was right (0.87-0.92 at that scale); the size was 1.4x off, the exact
  undocked-vs-docked factor. All of it was cut from undocked screenshots.

  Re-cut 1:1 from the docked capture: `portal_chooser_header_docked` (320x56,
  banner + medallion), `portal_chooser_header_docked_pill` (200x34) and
  `portal_chooser_confirm` (266x46). Both names now match that screen at
  **1.00** through the real matcher.

  This should also stop the failing click. The Portal Selection screen was
  already open when the route tried to click Select Portal to open it -- with
  working anchors, `_portal_step`'s already-at-destination check skips that
  click instead of firing it into the grid.

- **Every other undocked-derived crop retired** to `Assets/ui/_unused/` with an
  `undocked_` prefix: the older chooser-header variants and the
  `portal_select` / `portal_exit` "_live" art from the same batch. They are all
  ~1.4x oversized for the docked frame and can only ever add noise.

# v0.24.13

## Changed

- **No camera setup on an Auto Play task.** The top-down pinned view exists so
  the MACRO can place units at known positions; Auto Play plays from its own
  camera and gains nothing from it. On a task whose "Plays The Map" is Auto
  Play, the right-click drag and O zoom-hold are skipped entirely -- it was
  moving the player's view for no benefit and adding a drag that can leave the
  cursor in a bad state. The settle that step provided is kept, since that is
  what lets the map finish rendering before any Pre Start block runs.

## Fixed

- **The cursor is parked in the top-left corner before any portal anchor
  check.** Wherever the last click landed, the cursor stayed there -- and on
  these panels resting over a card or button pops a hover tooltip that can sit
  on top of the very art being searched for. `_portal_anchor` now moves to the
  window's top-left corner and settles before looking. Costs nothing, and
  removes a whole class of "it was clearly on screen but never matched".

# v0.24.12

## Fixed

- **A failed chooser route no longer burns the wrong portal.** It used to back
  out to the lobby and open whatever sat in the task's saved lobby square. That
  square is a fixed coordinate into a grid that **re-flows every time a portal
  is consumed**, so a few portals into a chain it holds something else
  entirely -- the macro then spent a real item on the wrong portal and the log
  looked completely normal. The route now stops and names both things worth
  checking. Stopping costs one interrupted farm; guessing costs inventory every
  time.

  Verified while investigating: the code is NOT mixing the two saved points up.
  `_portal_task_point(task, "lobby")` and `..., "chooser"` read
  `portal_lobby_x/y` and `portal_chooser_x/y` respectively, and the log's
  (551, 235) is the lobby point on both entries. The wrong portal came from the
  grid moving under a fixed coordinate, not from the wrong coordinate.

## Known, unfixed

- `portal_select` still never matches on the post-run screen, so the route
  falls to its calibrated point (292, 581), and that click does not open Portal
  Selection. Both the art and that coordinate need to come from a DOCKED frame
  (Settings > General > Image Manager) -- see AI_CONTEXT convention 3c-ter.

# v0.24.11

## Fixed

- **"portal_chooser_header never appeared" on a screen that had visibly
  opened.** The Select Portal click worked, the Portal Selection screen came
  up, and the step still failed three times and stopped the task. Measured
  against a capture of that screen, the header crops score **0.83-0.88** while
  the green Select button scores **0.94** -- so the screen is now confirmed by
  either one. `portal_chooser_confirm` joins `portal_chooser_header` as a
  witness in the Select Portal step, in the follow-up check, and in
  `_portal_chooser_showing`. One marginal anchor should never be the only
  thing standing between a working click and a dead task (convention 8).

## Working as of this build

- The in-round three-card pick now fires for real: *"3-portal selection
  detected DURING the round (3 cards, best score 0.89) -- clicking the middle
  one."* Per-card matching was the right call.
- The chain reaches the post-run screen and takes the chooser route instead of
  bailing to the lobby.

# v0.24.10

## Fixed

- **The post-run Portal Selection screen is now recognised.** New
  `portal_chooser_header` variants cut at live scale: the full banner with its
  compass medallion (405x126) and the "Portal Selection" pill on its own
  (223x52). The shipped art needed ~1.63x to fit the real window, so the screen
  was never seen. Both new crops match that screen at **1.00**.

## New

- **The chooser route now presses the green SELECT button.** After clicking the
  task's saved chooser slot it clicks `portal_chooser_confirm` (384x67, the
  Portal Selection screen's own confirm in the right-hand detail pane), verified
  by the party screen appearing. This is NOT the lobby route's "Activate
  Portal" -- different screen, different button, different art -- and without it
  the route picked a portal in the grid and then went looking for a party
  screen that nothing had opened. `_activate_portal`'s Activate step skips its
  own click when the party screen is already up, so Select landing straight
  there costs nothing.

## Note on the art

  The reference crops supplied for these were at **0.714x** of live scale
  (measured: all three wanted ~1.40x to fit a live-space frame). Rather than
  upscale them and lose detail, the same regions were cut directly from a
  live-space capture of that screen -- crisper, and correct by construction.

# v0.24.9

## Fixed

- **Every anchor for the post-run portal screen was cut at the wrong scale and
  could never match.** Measured against the user's own screenshots of those
  exact screens:
  - `portal_chooser_header` needs **1.63x** to fit the real Portal Selection window
  - `portal_select` and `portal_exit` were cut **1:1 from a 1347x802 screenshot**,
    while captures normalise to 1152x756 (~0.855x)

  The scale sweep only reaches 0.90x, and an out-of-range template misses
  silently. So `_portal_chooser_showing` answered "not the chooser" every time,
  and a finished run was sent to the lobby route from a screen that is not the
  lobby -- reported as "wants to go back to lobby instead of picking a portal
  again". Correctly-scaled art now ships for all four: `portal_chooser_header_live`,
  `portal_select_live`, `portal_select_inventory_live`, `portal_exit_live`, each
  cut from a full-window screenshot resized to the capture space.

- **Route choice no longer depends on that art being right.** The decision is
  inverted to key off `nav_play` -- which renders only on the lobby and matches
  reliably here -- instead of off the post-run anchors. Seeing the chooser is a
  fast path; *not* seeing it is no longer taken as evidence of the lobby. When
  neither is visible the chooser route gets the attempt anyway, since that is
  overwhelmingly where a finished run leaves us; it verifies every step and
  falls back to the lobby route, so a wrong guess costs one recoverable retry
  instead of a dead task.

- **The 3-portal offer was never detected -- and scale was never the reason.**
  A real Image Manager capture of that screen (already 1152x756, so no
  calibration needed) settles it: EVERY band template misses badly --
  0.19-0.41 against a 0.60 bar, the shipped `*_runtime` crops included. A band
  spanning all three cards is mostly **live gameplay** between and behind them,
  and that background is different every run, so most of the template's pixels
  are noise. The card pitch in that capture is 306px against 493px in the
  source screenshots -- a 0.621 factor, which means 0.24.7's 0.615 rebuild was
  right about scale all along and still could not work.

  Replaced with per-card matching: new `portal_offer_card` (a 115x105 crop of
  one card's lantern, almost entirely fixed art) found with `find_image_all`,
  hits sorted by x, middle one clicked. Grayscale matching discards the
  per-tier colour so one shape covers every tier; with three variants shipped,
  all five tiers score **0.88-1.00**. All three cards are required before
  clicking -- two hits could be cards 1+2 or 2+3, and guessing clicks the wrong
  portal.

- **The post-run route no longer waits for cards that cannot be there.**
  `_open_portal_from_chooser` polled for the three-card offer for 30s and
  failed the whole route when it never appeared -- but the cards are shown
  during the live round and are long gone once a result screen exists. It now
  picks the task's saved chooser slot directly, which is the coordinate
  strategy already in use.

# v0.24.8

## Fixed

- **Auto Shop: Meat added as the 6th food.** The Gold Shop is a two-column list
  navigated by scroll position and column, two items per row, so a new item
  shifts every item below it -- which is why Auto Shop died right after the
  fifth food. Meat sits in row 2 beside Mana Flask (200/day, 300 gold). The
  catalog entry and all four layout tables in `core/runner_shop.py` are updated
  together, and the full order is now verified against overlapping screenshots
  of the live shop so every pair is confirmed twice:

  ```
  row 0  scroll     0   Cursed Boba       Red Flower
  row 1  scroll  -120   Frown Fruit       Delicious Pie
  row 2  scroll  -480   Mana Flask        Meat            <- new
  row 3  scroll  -720   Trait Crystal     Sprite (Grey)
  row 4  scroll  -960   Equipment Reroll  Equipment Lock
  row 5  bottom         Stat Reroll       Stat Lock
  ```

  12 items still fit 6 rows, so no scroll amount changed -- only which items sit
  at each one. New `shop_meat` art, cut from the live shop and rescaled to the
  size the other shop icons use (57x61, identical to `shop_mana_flask`). Meat
  appears in settings automatically, disabled with a target of 1; nothing needs
  migrating, just enable it.

- **The Portals tab was read as already selected when it wasn't.** Selected and
  unselected are the same shape and differ by COLOUR, and matching is
  grayscale -- so the one thing that separates them is discarded before
  scoring. Both names also sit at a lowered 0.80 threshold because each misses
  its own art at 0.90. Measured on the shipped art, `portal_tab_selected`
  scores **0.892** against the *unselected* tab. So the runner reported
  "confirmed (portal_tab_selected is on screen)", then "already done (that
  screen is showing), skipping the click" -- never selected the tab -- and then
  clicked the saved inventory slot on whatever tab was really open, reported as
  "No Activate screen after picking the portal ... or that inventory square is
  empty".

  Fixed the way `find_upgrade_state` already handles the same problem: locate by
  template, decide the state by colour. New `vision.portal_tab_is_selected()`
  measures blue fill at the match -- 0.70 on both selected variants, 0.00 on all
  four unselected ones, so the 0.25 bar sits nowhere near either. `_portal_anchor`
  now routes that one name through it, which covers every call site at once.

- **The post-run dismiss click no longer fires on the lobby.** 0.24.7 added a
  "clear anything covering the result panel" click to `_reach_portal_activated`,
  and a task starting cold has no run behind it -- so it clicked the middle of
  the lobby as the first act of every fresh task ("Dismissing anything covering
  the post-run screen" as the opening log line). It is now skipped when
  `nav_play` is on screen, which renders only on the lobby.

- **Auto Challenge could never confirm the Challenge screen.** `challenge_loaded`
  peaked at 0.87 against a real Challenges screen, and only at the 1.10 end of
  the scale sweep -- under the 0.90 bar, so every run stopped at
  "challenge_loaded not found within 10s". Two changes: a new
  `challenge_loaded_modal` variant cut from that screen (shipped at both the
  screenshot's scale and the reference scale), which includes the modal's compass
  medallion so it identifies the *modal* rather than the gamemode menu's
  Challenge button; and a 0.85 builtin floor for the name, the same shipped-fix
  approach already used for the portal names.

  Note the old variants are left in place and are state-dependent -- `alt3` is
  "Regular Challenge / Rewards Available!", `alt4` is "Daily Challenge /
  Unavailable", `_current` is "Daily Challenge / Rewards Available!". Each only
  matches one daily state (convention 7), which is why the state-independent
  banner is now the one to rely on.

# v0.24.7

## Fixed

- **Portals now actually chain.** A repeating Portals task stopped dead after
  its first run: it sat on the Victory screen until the teleport wait timed
  out, then recovered to the lobby and failed the task. Two bugs stacked.

  `_handle_portal_result`'s continuing branch had been reduced to a log line
  and `return True` -- it enters nothing -- but `_run_task`'s repeat loop still
  assumed it had entered the next portal and went straight to
  `_wait_teleport_in`, waiting for a teleport that nothing had started.
  `mode == "portals"` now takes the `_run_task_setup` re-entry path alongside
  matchmaking and `left_live_match`, which re-runs `_reach_portal_activated`
  (chooser route first, lobby route as its fallback) and does its own teleport
  wait with `PORTAL_IN_MATCH_IMAGES`.

  Underneath that, `_portal_chooser_showing` -- the gate that decides chooser
  route vs lobby route -- only looked for `portal_chooser_header`, the "Portal
  Selection" banner. That banner does not exist until *after* the first click
  of the route the gate guards. Straight off a finished run the screen is the
  Victory panel, so the gate always answered "no chooser" and sent the task to
  the lobby route from a screen that is not the lobby. It now also accepts
  `portal_exit` ("Exit to Lobby"), which exists only on the post-run result
  panel and so identifies it without the false positives that got
  `portal_offer` / `portal_win` / `portal_selected` banned from this check.

- **A covered post-run panel no longer costs the chooser route.** A reward or
  level-up overlay can land on the result panel and hide both buttons. The exit
  path already had to clear it; `_reach_portal_activated` now does the same --
  but only after looking first, and it looks *again* afterwards rather than
  assuming the click worked (convention 1). Still falls through to the lobby
  route if the panel really isn't there.

- **Nine reference images could never match.** The matcher works in a fixed
  1152x756 space and every search path treats "template bigger than the frame"
  as a clean miss, with no error and no log line; the scale sweep only reaches
  0.90x. Nine shipped images were over that line and had never matched once.
  - `portal_offer_t1..t5` were the raw screenshots at capture size (1266-1361px
    wide), so the in-round three-card detector only ever worked on the two
    `*_runtime` crops -- i.e. only Summer and Sky Ruins. Rebuilt: scale fixed at
    0.615x (0.625x for t3) by matching the known-good runtime crop's card into
    each, then cropped to the three-card band symmetrically about the middle
    card, so the match centre `click_match` uses IS the middle card (0px offset,
    all five).
  - `portal_win.png` was a 1347x802 whole screenshot -- and
    `Templates/examples/Portals - single portal (exit to lobby).json` calls
    `find('portal_win')`, so that check never fired. Now a 440x90 crop of the
    Victory ribbon and the portal panel's frame.
  - `portal_tier_2_icon.png` was 267x255, roughly 2x its siblings. Rescaled to
    139x133.
  - `portal_inventory_alt2.png`, `event_mode_tile.png`, `portal_mode_tile.png`
    and `portal_selected.png` moved to `Assets/ui/_unused/`. The two tile images
    were the *primary* variant of their name, so every lookup burned its first
    slot on a template that could not match before falling through to the
    `_name` crop that works.

- **`portal_chooser_picker.png` moved out of the template tree.** An 819x511
  whole-panel image sitting in `Assets/ui/portal_select/` -- a folder whose name
  gets clicked, where every `*.png` is an interchangeable variant and the click
  lands on the match centre. Had it won a match, Select Portal would have
  clicked dead centre of the panel. It is only ever loaded by explicit path for
  the coordinate picker's static reference, so it now lives in
  `Assets/reference/` and `main.py` points there.

## New

- **Oversized reference art is no longer silent.** `core/vision.py` records any
  template larger than the capture space as it loads, writes one line naming the
  file and its size, and exposes `oversized_template_report()`. Empty is the
  healthy state. This is the guard that would have caught all nine above the day
  they were added.

## Removed

- **Dead code in `_handle_portal_result`.** A trailing
  `self._set_status(... 'Victory' if result == 'win' ...)` referencing `result`,
  which is not a parameter of that method and is never assigned in it -- a live
  `NameError` that survived only because both branches above it returned first.
  Removed, with the redundant `if repeat:` that followed an `if not repeat:`
  which had already returned, and the docstring that still claimed the next run
  was entered there.

# v0.23.6

- Portal post-run detection now recognizes the new Portal Selection header images supplied by the user.
- Keeps the existing portal chooser/offer images as fallback detectors.

# v0.23.5

- Quick-place chains now explicitly press **Z** after the final placement to exit quick-placement mode.
- Shift is released before Z so the next unit/block starts cleanly.

# Changelog

All notable changes to Anime Expeditions (Lord's Macro) are documented here.

## [0.22.6] - 2026-09-04

### Fixed
- **Teleport detection, properly this time.** 0.22.3 added the Auto Play button as a second witness and it still failed -- the debug frame the macro saved at the moment it gave up shows the player plainly in the match, with the HUD, the Auto Play button *and* the Start Game prompt all on screen, so every witness was missing its target. The cause was the art: all of it had been cut from chat screenshots at whatever scale they happened to be, while the matcher works in a normalised 1152x756 space. The anchors are now cut from that debug frame itself, which is already in exactly that space -- `nav_unitmanager` (added as a variant beside the shipped art) and `autoplay_off` (replaced as the primary).
- **The "Start Game?" prompt is now the first witness checked**, ahead of Unit Manager: it is large, high-contrast and unmistakable. It only appears when auto-start is off, so the HUD buttons stay as the fallback for anyone who has auto-start on. New `start_game_prompt` (detection only -- the modal is never clicked, since clicking a modal crop would land in the middle of it) and three new `nav_start_game` button variants, which also help the ordinary Start Game click outside Portals.
- The teleport wait's log line now names every image it is actually watching, instead of only `nav_unitmanager`.

## [0.22.5] - 2026-09-04

### Removed
- **The dead "Event Gamemode Card" coordinate row.** It had a row and a Pick button in Settings > Debug but no entry in `MACRO_COORD_DEFAULTS`, so `set_macro_coord` rejected the key and anything picked or typed there was silently discarded -- and nothing read the value in the first place. Predates 0.22 (absent in 0.21.2 too). It was left for a since-retired event. Removing it is a no-op for behaviour: every Macro Coordinates row can now actually save, which is the point.
- Unaffected: the `event_gamemode` **image**, which is a different thing and is still what the Event route clicks (`_reach_event_act_selected`). Event mode itself is untouched.

## [0.22.4] - 2026-09-04

### Changed
- **The two portal slots are now required, not defaulted.** `portal_lobby_pick` / `portal_chooser_pick` are removed from Settings > Debug entirely -- rows, keys and defaults. Which portal to run is per-player *and* per-task (two queued Portals tasks can farm two different portals out of one inventory), so a shared default could only ever be right for one of them, and a task quietly opening someone else's portal is worse than a task that says what it needs. A Portals task carries both points, shows `⚠ pick portal slots` on its queue row until it has them, and refuses to run without them.
- **Auto Play is set before the run starts, not partway through it.** The check moved to immediately after teleport-in -- the earliest the in-match button can exist -- ahead of Pre Start and the Start Game sequence, so a run auto-plays from its first wave (`_settle_autoplay_for_match`). The chooser-entry skip is unchanged.

### New
- **Shipped defaults for the remaining coordinates**, from a live 1152x756 window: `portal_start` (681, 519) and `portal_panel_close` (3, 3). Every point the portal route uses now has a working default.

## [0.22.3] - 2026-09-04

### Fixed
- **A loaded portal was abandoned as "never teleported".** Teleport-in was confirmed by one image, `nav_unitmanager`, whose shipped crop doesn't match every setup -- so a run that loaded correctly sat out the full 30s wait and was then Left Stage out of a match it was already in. The wait now accepts a second witness: the in-match Auto Play button (either state), which only renders once you are actually inside a run. Everything else about the wait is unchanged -- the lobby-resync and disconnect paths still take priority, and a genuine failure to load still times out.
- **Auto Play is no longer toggled off between portals.** It survives a chooser-to-chooser chain and only resets via the lobby, so clicking it on a chooser entry turned it *off* mid-chain. `_ensure_autoplay` now runs only when the portal was entered from the lobby; the runner records which route it took (`_portal_entered_from`).

### New
- **Auto Play coordinate fallback**, defaulting to (1123, 485) -- Settings > Debug > Macro Coordinates, "Auto Play Button". Used when neither `autoplay_on` nor `autoplay_off` matches. Unlike the route's buttons this one doesn't move within a match, so a fixed point is safe.

## [0.22.2] - 2026-09-04

### Fixed
- **The portal never actually started.** Activate opens a **party screen** (portal name, rewards, party slots) with its own green Start button, and nothing teleports until that is pressed -- so a run picked its portal, looked entirely successful in the log, and then sat on that screen until the teleport wait timed out. The route now clicks Start after Activate. New `portal_start` art from the live game, plus a `portal_start` coordinate in Settings > Debug ("Portal: Start Run") as the fallback.
- **Activate is now verified too.** It was the one step with nothing to check against; it is now proven by the party screen appearing -- its Start button and the "Public Party" band both exist only there. New `portal_party` art, cropped to that band rather than the header, since the header carries the portal's name and tier and would only ever match one portal.

### New
- **`AI_CONTEXT.md`** in the project root: a living handoff of what the Portals work is, the conventions behind it (each learned from a real failure), a map of the code, and what is still open. Written to be picked up cold by a new session or a different assistant, so the context isn't lost when a chat ends. It ships in the release zip and should be updated in the same change as the behaviour it describes.

## [0.22.1] - 2026-09-04

### Fixed
- **A working Portals-tab click was reported as a failed one.** The step was verified against `portal_inventory`, whose shipped art no longer resembles the panel -- so the click opened the inventory, the check missed it, and the step re-clicked three times and gave up on a route that had actually worked. The Portals tab is now verified by the tab turning **blue** (new `portal_tab_selected`, art from the live game) or by **Activate Portal** appearing beside the grid; `portal_inventory` is kept as a third option but nothing depends on it. A fresh `portal_inventory` crop is added too -- the left tab column and panel chrome, which stay put, rather than the grid, whose contents change as portals are spent.
- **A retry no longer undoes itself.** With the panel left open by a failed attempt, the next attempt clicked "Items" again and toggled it shut -- visible in the reported log as attempt 2 failing where attempt 1 had succeeded. Each step now checks whether it is *already* where it was trying to get to and skips the click entirely if so. This also means an unset `portal_panel_close` costs much less: the route recovers from a dirty start on its own.

## [0.22.0] - 2026-09-04

### New
- **Portals is a task mode.** Pick **Portals** in the Task Builder's Mode dropdown and the queue runs portals the way it runs Story or Event. The task drives the whole cycle itself -- into a portal, through the run, and straight into the next one -- so no portal template is needed; a Macro Operation on a Portals task is only for placing units in battle.
- **The runner works out which portal panel it's looking at.** There is no portal-type setting: a run that ends on the post-run chooser continues from the chooser, and anything else goes back to the lobby and re-opens one from the inventory. `_portal_chooser_showing` decides by matching `portal_offer` / `portal_win`, so the two cases don't have to be predicted in advance -- they alternate constantly in practice.
- **The two click points live on the task**, picked from the Task Builder (*Portal in lobby* / *Portal in chooser*, each with a Pick button that opens the same live-capture modal the Macro Coordinates rows use). Per task rather than in settings because two queued Portals tasks can farm two different portals out of one inventory. A task missing either point says so on its queue row and logs which one to pick instead of clicking blind.
- **Continuous running.** *Portals Then Exit* is the run count and `0` means keep going until you stop the task; it replaces Repeat for this mode (Repeat is hidden, since two controls fighting over one number is how they end up disagreeing). After each run `_handle_portal_result` takes the place of Repeat/Leave Stage -- Portals has neither button -- picking the next portal from the chooser, falling back to a full lobby re-entry when the chooser isn't there, and exiting to the lobby on the last one.
- **Runner entry path** (`core/runner.py::_reach_portal_activated`, from a new `elif mode == "portals"` in `_run_task_setup`): lobby -> event card -> Portal tile -> Items -> Portals tab -> your portal -> Activate. The four navigation steps click by reference image first and fall back to their calibrated coordinate if the template doesn't match, so a game re-skin degrades instead of failing. Retried from the lobby `MAP_SELECT_RETRY_ATTEMPTS` times like every other mode. Portals does not rejoin the shared Select Stage + Solo/Matchmaking tail -- Activate *is* the teleport.
- **`limit_from_task` on counter Detect blocks** (`core/detect.py::_counter_limit`): a counter block can name a field on the running task to take its limit from instead of the number baked into the template. Used by `Portals - N portals then exit` for template-driven runs; falls back to the block's own `limit` (and logs why) outside a task or on an unparseable value.
- **"Plays The Map" on every task** (Task Builder, a Solo/Matchmaking-style toggle): **Macro** -- the template's blocks fight the round, as always -- or **Auto Play**, which hands combat to the game's own Auto Play button. Both settings act: Macro switches Auto Play *off* if a previous task left it on, so the choice works in both directions rather than being one-way. The Macro Operation picker stays visible and the template still runs either way, which is the point -- an Auto Play task can use its Battle/Loop blocks for something else entirely while the game fights (walking to the water and fishing through a portal run, say). Saved tasks from before 0.22 default to Macro.
- **The Auto Play state is read, not assumed** (`core/runner.py::_ensure_autoplay`, run once per match right after the round starts, since the button only exists on the in-match HUD). The button is matched first and clicked only when it is in the wrong state -- a blind click would toggle Auto Play *off* on any task that already had it on -- then re-read to confirm, and retried up to 3 times. New reference art in `Assets/ui/autoplay_on/` and `Assets/ui/autoplay_off/`: full-button and label-only crops of each state. Because the two states are the same button differing only in the word on it ("Auto Play" / "Auto Playing"), matching runs at a raised threshold (0.93) and tests ON first, so a near-tie resolves to "already on" -- worst case a missed toggle, never a click that turns Auto Play back off. A screen with no Auto Play button is logged and left alone, not treated as a failure.
- **`skip_modes` on a block** (Pre Start and Battle/Loop A/B): a template can declare a block as not applicable to given task modes. All three bundled portal templates now carry `"skip_modes": ["portals"]` on their "wait for Activate" Pre Start block and their post-run Loop A block, so pointing a Portals task at one is safe -- without it the template's Loop A would race the task for the same Select button and throw the count off. Standalone behaviour from the Macro Manager is unchanged.

### Changed
- **The portal route goes through the inventory, not the Event menu.** Opening a portal is now: **Items -> Portals tab -> your portal -> Activate**, which works from the lobby whatever else is or isn't on screen. The 0.21 route entered through the Event menu and its Portal Mode tile -- two extra screens that had to be navigated correctly before the portal was even in reach, and the source of the "portal_event_open not found, clicking (142, 285)" failure. `nav_event`, `portal_event_open` and `portal_mode_tile` are gone from the route and from Settings > Debug > Macro Coordinates along with it.
- **The post-run route is explicit**: middle of screen (dismisses the result panel covering the buttons, reusing the shared `screen_middle` point) -> **Select** -> your chooser portal -> Activate.
- **The two portal slots now have Settings fallbacks.** A Portals task's own pair, picked in the Task Builder, still wins. `portal_lobby_pick` / `portal_chooser_pick` are back in Settings > Debug as the pair a task with none set uses, so a single-portal setup can be configured once globally instead of per task. A task using them shows `default portal slots` on its queue row and `Settings default` in its pickers.
- Macro Coordinates now carries exactly the seven points the route uses, in route order: `nav_items`, `portal_tab`, `portal_lobby_pick`, `portal_activate`, `portal_select`, `portal_chooser_pick`, `portal_exit`.

### Fixed
- **Portal clicks now actually register.** `nav_items` was matching at score 1.00 and being clicked, and the Items panel still didn't open -- the click landed on the right pixel without the game accepting it. Two things a bare `mouse.click()` skipped, both already solved elsewhere in this codebase: window focus (the Start Game click reasserts it on every attempt) and genuine hover-in movement (`vision.click_match`'s `shuffle`, added for the lobby Event button, which failed exactly this way). Every portal click -- image match, calibrated point and task-stored portal slot alike -- now asserts focus and hovers in.
- **Every portal step verifies itself and retries.** A step names the art that proves its click worked -- Items expects the Portals tab or the inventory, the Portals tab expects the inventory, a portal slot expects the Activate screen -- and re-clicks (up to 3 times) when that art doesn't appear. Previously an unregistered click was invisible: the route marched on and every later step failed against a screen that had never changed, which is what the reported log shows. Failures are now reported at the step that actually failed.
- **Search always comes before the fallback point.** Within each attempt the image is searched for first and the calibrated coordinate is used only after that search misses -- the image is what confirms which screen is up; the coordinate is only a guess about where a button sits on it. Step timeouts dropped to 6s (search) and 5s (verify) since a step is retried now rather than waited out.
- **Portal reference art re-grabbed from the live game.** `nav_items`, `portal_tab` and `portal_activate` all failed to match on a real 100%-scale window while non-portal images (the lobby Play button) matched fine -- so the art, not the vision path, was stale. Each folder now leads with a fresh capture, with a label-only crop as the second variant and the previously shipped crops kept behind them.
- **`portal_activate.png` was a crop of the whole confirmation panel (231x378), not the button.** `template_variant_paths` tries `X.png` first and the first variant over threshold wins -- and a match's *centre* is what gets clicked, so any frame where that panel matched would have clicked dead centre of the panel, nowhere near Activate. Moved out of the folder to `Assets/ui/_unused/portal_activate_panel.png` (named so the subfolder lookup rule can't pull it back in). The folder now holds only crops it is safe to click.
- **A missing Activate image no longer stops the task.** `_activate_portal` treated "portal_activate not found" as proof the picked slot was empty and failed the whole attempt -- so stale reference art looked like a bad portal pick. It now falls back to the `portal_activate` coordinate like every other step; the teleport wait that follows is the real confirmation, and a click that didn't take just retries.
- **The post-run path has fallbacks too.** Exit to Lobby is now image-then-coord, and it gets the same middle-of-screen dismiss the continuing path uses -- the result panel covers Exit just as it covers Select.
- **Retries start from a clean lobby.** A failed attempt tends to leave the Items/Portals panel open, and the next attempt then clicks "Items" at a point that is now something else -- one missed image cascading into a run of wrong clicks, which is exactly what the reported log shows. `_close_open_panels` clicks the lobby's top-left close button before every retry and on every back-out. New `portal_panel_close` coord in Settings > Debug (shipped unset; an unset value is logged and skipped, never a failure -- it is cleanup, not a step of the route).

- **The Portals route never opened the Event menu.** `_reach_portal_activated` started at the Tidal Siege event *card* (`portal_event_open`), which only exists once the Event menu is already open -- so from a real lobby that search timed out, fell back to its calibrated point, and clicked empty lobby, after which every following step was working on the wrong screen. Fixed by dropping the Event menu from the route entirely (see Changed above): the inventory route needs neither screen.
- **Clearer portal-route logs.** Each navigation step now says up front that a missed image falls back to its calibrated point. `_click_found_image`'s own miss line reads "-- stopping.", which is true for its other callers but not this one, so the log read as a stop followed by an unexplained click.
- **`run.bat` no longer keeps a console window open, and closing that window no longer kills the macro.** It ran `python main.py` inline, making the console the parent process. It now launches detached via `start` and prefers `pythonw.exe`, so the window closes immediately and the app keeps running. `run_console.bat` is added for troubleshooting a startup crash -- it keeps the old attached behaviour and prints the traceback.
- **The block editor no longer strips counter Detects.** `serializeBlock` / `blockFromSaved` in `ui/app.js` are whitelists, and `counter` wasn't in the list of valid modes -- so opening any template with a `mode: "counter"` block in Macro Manager and saving it silently turned that block into an image Detect with no image (permanently false), losing `limit`, `counter_id` and `label` with it. Present since counter mode landed in 0.20.9. Those fields, plus `limit_from_task` and `skip_modes`, are now carried through verbatim. They still have no editor controls -- this is preservation, not UI.

### Notes
- No portal click point ships in `MACRO_COORD_DEFAULTS` any more; `portal_pick` (removed in 0.21.2) is not coming back as a global setting. The navigation points (`portal_event_open`, `portal_mode_tile`, `nav_items`, `portal_tab`, `portal_activate`, `portal_select`, `portal_exit`) are unchanged in Settings > Debug -- those are fixed pieces of game UI. Only the "which portal" points moved onto the task.
- Still deferred: Portals as its own **settings tab** (tier picker, per-tier macro binding, health check, `setup_ready` gate) and the `core/runner_portals.py` mixin. The task path covers running portals from the queue; the panel is what a per-tier setup would need.

## [0.21.2] - 2026-09-04

### Improved
- **Portal coord defaults shipped** in `MACRO_COORD_DEFAULTS` (`main.py`), picked from a live 1152x756 window: `portal_event_open` (142, 285), `portal_mode_tile` (930, 381), `nav_items` (114, 335), `portal_tab` (227, 246), `portal_activate` (834, 591), `portal_select` (292, 581), `portal_exit` (701, 581). Per-user overrides in `settings.json` still win, so a game update that shifts one is a picker click away in Settings > Debug > Macro Coordinates.
- **Simplified portal templates** to match the actual usable workflow (all three: single, N-run, continuous). Prestart now waits for the Activate screen and clicks Activate. That's it. The lobby-fallback branch that used `portal_pick` is gone, because which portal to run is user-specific (inventory layout differs per player and shifts as portals are gained/lost, and the pre-run inventory has a different layout from the post-run 3-portal chooser). Workflow: user opens the portal they want to run manually, then presses Play; the macro takes over from the Activate screen forward and the post-run chooser is handled by `portal_select` (whichever of the 3 offered portals -- the Select button is the same regardless).

### Removed
- **`portal_pick` coord** removed from the Settings panel (`ui/index.html` row deleted, `MACRO_COORD_KEYS` entry in `ui/app.js` dropped, `portal_pick_x/y` no longer in `MACRO_COORD_DEFAULTS`). It never had a coherent single value -- see above.

## [0.21.1] - 2026-09-04

### Fixed
- **Portal coord rows now appear in Settings > Debug > Macro Coordinates.** 0.21.0 added the 8 `portal_*` / `nav_items` entries to `MACRO_COORD_DEFAULTS` in `main.py`, and the coord API surfaced them, but the frontend panel's list is hardcoded in `ui/app.js`'s `MACRO_COORD_KEYS` and its rows are hardcoded in `ui/index.html`, so the new keys never got a UI row to attach to. Added both: 8 new `.setting-row` entries in `index.html` immediately after "Enter Matchmaking Region", each wired to its own `openCoordPicker` + numeric x/y inputs following the exact shape of the pristine "Story Card" / "Event Gamemode Card" rows, and the 16 new x/y keys registered in `MACRO_COORD_KEYS` so `loadMacroCoords` populates them from `settings.json` on load.

## [0.21.0] - 2026-09-04

### New
- **Portal-mode reference layout renamed to match pristine conventions**: every `Assets/ui/summer_*/`, `tidal_siege_*/`, and `summer_siege_*/` folder from 0.20.7–0.20.9 is now `portal_*` (or `event_mode_tile`, `nav_items`), matching the short prefix style used by `exp_*`, `chal_*`, `craft_*`, `fuel_*`, `shop_*`. Bundled template detect references are updated in lockstep. The compat-only `summer_lobby_event_button` folder was dropped since pristine's `nav_event/` already covers the lobby Event button.
- **Portal click coordinates are proper settings**: 8 new entries in `MACRO_COORD_DEFAULTS` (`main.py`) -- `portal_event_open_{x,y}`, `portal_mode_tile_{x,y}`, `nav_items_{x,y}`, `portal_tab_{x,y}`, `portal_pick_{x,y}`, `portal_activate_{x,y}`, `portal_select_{x,y}`, `portal_exit_{x,y}` -- exposed via Settings > Debug > Macro Coordinates the same way `matchmaking_region_*` and `story_click_x/y` are. Shipped as `None` so an unpicked coord is skipped with a log line; drop in real values from a live Roblox window and they become the shipped defaults for future installs.
- **`click` block gained a `coord_key` param** (`core/runner_blocks.py::_run_click_block`): passing `"coord_key": "portal_activate"` reads `portal_activate_x` / `portal_activate_y` from the runner's coords map instead of the block's hardcoded `x`/`y`, so a bundled template stays valid across users without every user re-picking the same points. Backward-compatible -- blocks with hardcoded x/y still work exactly as before.
- **Three renamed portal templates**: `Portals - single portal (exit to lobby)`, `Portals - N portals then exit`, `Portals - continuous` (all under `Templates/examples/`). Every Click block resolves via `coord_key`; the N-run template uses the 0.20.9 counter mode.
- **`docs/PORTALS.md`** replaces the earlier `SUMMER_SIEGE.md` as the single Portals reference (detect-name map, coord-key list, template summaries, first-run-defaults protocol).

### Deferred to v0.22
- Portals as a first-class settings tab alongside Auto Challenge / Auto Bounty -- portal-type dropdown, tier picker, per-tier macro binding, health check, `setup_ready` gate, task-queue registration. Needs a UI panel mirrored from Auto Challenge in `ui/index.html` (171 KB) + `ui/app.js` (347 KB) and a `core/runner_portals.py` mixin styled after `core/runner_challenge.py`. Splitting it into its own release keeps 0.21 focused on the runner-side plumbing (naming, `coord_key`, counter mode) that 0.22 builds on.

## [0.20.9] - 2026-09-04

### New
- **Counter mode on Detect blocks** (`core/detect.py`): a Detect block set to `mode: "counter"` branches on a persistent hit-count instead of an image match. `limit: N` means the THEN branch fires on hits 1..N and the ELSE branch on hit N+1 onward; `limit: ""` (empty), `0`, or missing means infinite (branch stays TRUE forever). The counter map lives on `runner._detect_counters` and is naturally reset when the macro (re-)starts; sharing a `counter_id` between blocks (e.g. one in `loop_a`, one in `loop_b`) lets them count into the same tally. This is the real per-portal counter mirrored on Auto Bounty / Auto Challenge's `cap`, using no new block type and no runner-loop-engine change -- just a new evaluation path in `detect._evaluate_context`.
- **`Templates/examples/Summer Siege - N portals then exit.json`** replaces v0.20.8's time-based workaround. Loop A wraps the Select-portal step in a `mode: "counter"` Detect (default `limit: 3`) so the THEN branch clicks Select while count <= limit and the ELSE branch clicks Exit to Lobby once the counter passes it. Change the `limit` value to any positive integer for that many portals, or set it to `""` for infinite.

### Removed
- `Templates/examples/Summer Siege - N portals then exit (time-based).json` — superseded by the real counter above. The other two v0.20.8 example templates (single-portal and continuous) are unchanged.

### Not in this release
- Portals as a first-class UI game mode alongside Expedition / Bounty / Challenge (Settings > Play > Portals with portal-type dropdown, tier picker, and run-count field). This needs a new runner-ops mixin (~30–60 KB Python, cf. `core/runner_challenge.py` / `core/runner_bounty.py`), a new web-UI panel under `ui/`, a settings-schema entry, and task-queue integration. It's proper v0.21 work.

## [0.20.8] - 2026-09-04

### New
- **Full Summer Siege detect coverage**: all 33 labeled screenshots from `Images you requested/` placed into their `Assets/ui/<name>/` folders. Tier icons 1–5 (both the portal icon and the name-text overlay as alt variants), post-run selection screens for every tier, the Portal-Mode and Event-Mode picker tiles, the Sky Ruins T5 icon, the Exit-to-Lobby button (idle + selected states), and the victory anchor are all real in-game shots -- no more placeholder folders.
- **Three portal-run templates** under `Templates/examples/` covering the workflow the compiled build never had:
  - `Summer Siege - single portal (exit to lobby).json` — one portal, then exit. Ideal for gold-mine / drill refill loops.
  - `Summer Siege - N portals then exit (time-based).json` — continuous portals with a `leave_at_minute` scheduled stop, so a N-portal run is a matter of setting the minute value to `N × average-portal-time`.
  - `Summer Siege - continuous portals.json` — infinite loop, stops when fuel runs out or you press Stop.
- **Auto Challenge troubleshooting doc**: `docs/TROUBLESHOOTING_AUTO_CHALLENGE.md` explains why the compiled 0.19.1 build refuses to start Auto Challenge on your setup — every entry in `challenge.maps[*].macro` is empty, so `setup_ready: false`, so the runner logs `Backing out after failed map search...` (matching your `debug.log`). Fix is to bind at least one story map to a saved macro template in `Settings > Play > Auto Challenge > Maps` and enable the toggle. The secondary OCR health-check failure (`winsdk`/`winrt` missing, Tesseract not installed) doesn't block Challenge — it only affects OCR-dependent code paths.

### Notes
- The "run N portals then exit" mode is time-based rather than count-based because the block runner has no per-iteration counter block. Adding one (mirroring `challenge.cap`) is a proper Python change to `core/runner_blocks.py` that belongs in a bigger release; the time-based template is the honest built-in workaround.
- All pristine detect names and Assets/ui folders remain intact — the 0.20.7 restoration of `event_gamemode` is preserved, and every new folder added in 0.20.8 uses a distinct Summer-Siege-scoped name so nothing collides with existing modes.

## [0.20.7] - 2026-09-03

### New
- **Summer Siege / Tidal Siege portal references**: added detect-name folders under `Assets/ui/` for the Summer Siege portal flow (event bar, event-gamemode button, Tidal Siege button, lobby Items entry, Portals sub-tab, portal inventory, portal-activate screen, portal-select screen and its Select button). All PNGs are real in-game screenshots taken from a 0.20.x client; see `docs/SUMMER_SIEGE.md` for the full name map and the state each anchor represents.
- **Bundled example template**: `Templates/examples/Summer Siege - portal auto-select.json` demonstrates the full navigation with Detect blocks over the new reference names, so users can copy it in from Load Example, tweak the click points to their layout, and run.
- **Map backdrops**: `Assets/map/Portal/Coral Kingdom - Tidal Siege.png` and `Assets/map/Portal/Sky Ruins Portal.png` for the Path Editor.

### Fixed
- **Default window size regression**: the fork's 0.20.6 build launched at the full GUI size on machines whose scaled resolution could only fit the compact one, placing the window partly off-screen. Reverted to the compact default (the screen-width check upgrades to full when it actually fits, same behavior as 0.19.1).
- **`event_gamemode` reference restored**: 0.20.6 overwrote `Assets/ui/event_gamemode/event_gamemode.png` with a Tidal-Siege-specific crop, which broke Villain Invasion event navigation for anyone updating from 0.19.1. The pristine crop is back; the Tidal Siege variants moved to their own `tidal_siege_event_button/` folder so they no longer collide.

### Notes
- Every pristine detect name and Assets/ui folder from 0.19.1 is preserved: no removals, no renames, and no overwrites of files that shipped with the last release. All Summer Siege additions are new folders under distinct names.
- Detect-name folders that still need real screenshots (tier icons 1–5, Activate button crop, insufficient-fuel popup, claim-rewards button, event banner) are documented in `docs/SUMMER_SIEGE.md`. The macro treats a missing folder as "not found" (see `core/detect.py`) so downstream templates keep running until those are populated.

## [0.19.1] - 2026-08-13

### Improved
- **Auto Fuel interval control**: the minutes/hours fields now remain available while Auto is selected, so a custom refill wait can be entered instead of being locked to the automatic 8-hour Max interval.
- **Expedition encounters**: added native encounter handling, routes, and screen references for East Town, Flower Forest, Rose Kingdom, and School Grounds.
- **Expedition reliability**: improved checkpoint, wave counter, Repeat Stage, Start Game, upgrade-card, and unit re-placement handling.
- **Navigation recovery**: widened card searches, added lobby re-sync, and exits the AFK Chamber when it blocks progress.
- **macOS**: stabilized code-signing identity across updates and fixed the Macro Manager panel rendering blank while the macro runs.

### Fixed
- Villian Invasion navigation now opens the event card before selecting the game mode.
- East Town is now available in the Challenge and Bounty Story map list.

## [0.19.0] - 2026-08-11

### New
- **East Town map**: added to the expedition and story map lists.
- **Tower game mode**: Play -> Tower -> Select Stage -> Start (solo). Wins advance floors with `Next_Floor`; defeats retry with `Repeat_Floor`. Supports Normal and Traitless Tower. No map dropdown in the builder; Rose Kingdom is the internal default.
- **Auto Fuel custom interval**: set any refill interval in minutes or hours (e.g. 30 minutes, 1 hour), or leave it on Auto to keep the per-amount default behavior.

### Improved
- **Event mode**: waits for the Event gamemode screen, clicks a user-configurable card coordinate, then image-clicks the Event Gamemode button.
- **Disconnect recovery**: kills a stuck Roblox client before deep-link relaunch, still respecting the multi-window guard.
- **File dialogs**: cancelled or failed native file dialogs now return clean results instead of rejected JS promises.
- **Auto Upgrade Unit**: bounded wait for the unit info panel before searching `priority_upgrade`, so slow-rendering panels are no longer skipped. New `quote_on` / `quote_off` reference images for user-built Detect conditions.
- **OCR overhaul**:
  - Auto Bounty wave OCR: wave-anchored parsing with card-local crops and contrast voting. Clipped wave numbers (`6`, `6C`) now resolve to `60` instead of ending the run at wave 6.
  - Optional RapidOCR engine layer (separate `requirements-rapidocr.txt`, Python 3.13-safe) with a RapidOCR -> Windows OCR -> Tesseract fallback chain.
  - Windows OCR output is always filtered by the config whitelist, preserving stats/wave/shop reads.
  - Daily Challenge map OCR keeps the HUD-anchored crop primary and adds a fixed relative top-right crop as fallback.
- **Packaging**: PyInstaller keeps `winsdk`/`winrt` collection and adds RapidOCR data only when installed.

### Fixed
- Auto Bounty no longer exits early on wave-60 bounties when OCR clips the trailing zero.
- Challenge map OCR recovers when the Daily Challenge HUD label is not found.
