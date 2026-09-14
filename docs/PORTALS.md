# Portals

Single reference for the Portals feature (Summer Siege / Sky Ruins /
Lightning God / Sovereign portal runs), added in 0.21 and promoted to a
task mode in 0.22.

## What Portals ship as

There are two ways to run one.

**As a task (0.22).** Pick **Portals** in the Task Builder's Mode
dropdown. The task drives the whole cycle -- in, through the run, and
into the next one -- so it needs no portal template; a Macro Operation
on a Portals task is only for placing units in battle.

Set two things on the task:

- **Portals Then Exit** -- how many portals to run. `0` means keep
  going until you stop the task. This replaces Repeat for this mode.
- **Portal in lobby** and **Portal in chooser** -- the two click
  points, both required, each with a Pick button that captures the live
  Roblox window.
  Navigate the game to the matching screen before picking: the Items >
  Portals inventory for the lobby one, a post-run chooser for the other.
  Both are stored on the task, so two queued Portals tasks can farm two
  different portals.

You never choose *which* of those two gets used. The runner looks: if
the post-run chooser is on screen (`portal_offer` / `portal_win`, see
`_portal_chooser_showing`) it picks from the chooser and goes straight
into the next run; otherwise it walks the lobby route -- Items ->
Portals tab -> your lobby slot -> Activate -> Start. The post-run route
is middle of screen (to clear the result panel) -> Select -> your
chooser slot -> Activate -> Start. Both live in
`_reach_portal_activated`.

Activate is not the last click: it opens a **party screen** with its own
green Start button, and nothing teleports until that is pressed. A run that ends anywhere
unexpected therefore re-enters from the lobby on its own.

Portals has no Select Stage screen, no Start button, and no Repeat /
Leave Stage after a run -- Activate teleports you straight in, and the
chooser replaces the result buttons. So it is the one mode that skips
the shared confirm/Solo/Matchmaking tail, and `_handle_portal_result`
stands in for `_handle_match_result`'s repeat/leave branch. There is no
Solo/Matchmaking toggle for the same reason: a portal is always entered
solo from your own inventory.

Teleport-in is confirmed by any of several things that only render once
you are inside a run, checked in this order: the **"Start Game?" prompt**,
the **Start Game button**, the **Auto Play button**, then
**`nav_unitmanager`**. The prompt is the most reliable of them but only
appears when auto-start is off, which is why the HUD buttons back it up.
More than one witness is needed because `nav_unitmanager` is a single crop
of a single HUD button, and when it doesn't match a particular setup the
macro decides a run that loaded fine never started -- then leaves the match
it is already in. The lobby-resync and disconnect checks still take
priority over all of them.

All of this art is cut from a frame the macro itself saved
(`debug/region_teleport_timeout.png`), which is already in the normalised
1152x756 space the matcher works in. Art cropped from a screenshot at some
other scale may never match -- that is what made the first two attempts at
this fix fail.

A Portals task pairs naturally with **Plays The Map: Auto Play** (the
toggle beside Play Mode on every task): the game clears the portal
while the task's Macro Operation is free to do something else with its
Battle and Loop blocks. The Macro Operation picker stays available --
choosing Auto Play does not replace the template, it just changes who
is fighting. See `_ensure_autoplay`, which reads the button's state
before touching it and switches it back off for a Macro task.

Auto Play is only checked on a **lobby** entry. It survives from one
portal into the next through the chooser and is reset only by returning
to the lobby, so clicking it on a chooser entry would toggle it off
mid-chain. The runner records which route it took in
`_portal_entered_from`.

Pointing a Portals task at one of the bundled portal templates is safe:
those templates' "wait for Activate" and post-run Select blocks carry
`"skip_modes": ["portals"]` and are skipped (taking their ELSE branch)
when a Portals task is running, so they can't race the task for the
same buttons. `skip_modes` is generic -- any Pre Start, Battle or Loop
block in any template can list task modes it should sit out.

**As a template (0.21).** At the runner level, Portals are template-driven -- three bundled
examples under `Templates/examples/` (`Portals - single portal (exit to
lobby)`, `Portals - N portals then exit`, `Portals - continuous`) drive
the entire run using generic Detect + Click blocks. Every anchor image
lives under `Assets/ui/portal_*/` and every click point comes from
`MACRO_COORD_DEFAULTS` in `main.py` (Settings > Debug > Macro
Coordinates), so a user picks each point once and every template
respects it -- the same "override story" the rest of the runner uses
for `matchmaking_region_*`, `story_click_x/y`, etc.

## Detect names (`Assets/ui/<name>/`)

Every entry is a folder; the macro's Detect block matches by folder
name, and every `*.png` inside is tried as an interchangeable variant.
Naming follows the pristine short-prefix convention (`portal_*`, same
shape as `exp_*`, `chal_*`, `craft_*`, `fuel_*`, `shop_*`).

### Navigation into the event

The art below still ships, but **nothing in the Portals route uses it any
more** -- since 0.22 a portal is opened straight out of the inventory. It
is kept for templates that navigate the event menu themselves, and as
reference for anyone building one.

- `portal_event_bar` -- bottom bar in the event lobby (Shop / Gamemode / Quests).
- `portal_event_open` -- the Tidal Siege event card that opens the mode picker.
- `portal_mode_tile` -- the Portal Mode tile inside the picker.
- `event_mode_tile` -- the Event Mode tile alongside Portal Mode.

### Portal inventory flow (from lobby)

- `portal_tab_selected` -- the Portals tab in its SELECTED (blue) state, used to
  verify the tab click landed. Distinct from `portal_tab`, which is the
  unselected state -- the two never match at once, which is what makes it a
  reliable proof.

- `nav_items` -- Items button on the main lobby HUD.
- `portal_tab` -- Portals sub-tab inside the Items panel.
- `portal_inventory` -- Portal Inventory screen (idle + post-win alt).
- `portal_selected` -- highlighted state when a portal is currently selected.
- `portal_activate` -- confirmation screen after clicking a portal.
- `portal_party` -- the party screen Activate opens. Cropped to the "Public
  Party" band, NOT the header: the header carries the portal's name and tier
  and would only ever match one portal. Detection only, never clicked.
- `portal_start` -- the green Start button on that party screen.

### In-inventory tier icons

- `portal_tier_1` .. `portal_tier_5` -- Summer Portal tier icons (icon + name-label alt).
- `sky_ruins_portal_tier_5` -- Sky Ruins T5 icon (T1--T4 not shot yet).

### The in-round three-card offer

These appear DURING the live round, before Victory/Defeat -- not on the
result screen. See `_find_portal_offer_cards` and
`_pick_portal_offer_card` in `core/runner.py`.

- `portal_offer_card` -- ONE card of the three, matched three times and
  sorted by x. Deliberately not a band crop across all three: a band is
  mostly live gameplay between the cards and scored 0.19-0.41 against a
  0.60 bar, while a single card's lantern scores 0.88-1.00 across every
  tier. Threshold 0.60, and all three must be found -- two hits could be
  cards 1+2 or 2+3, and guessing would click the wrong portal.

- `portal_modifier_traitless` -- the green "Traitless" pill as it appears
  in the detail sidebar of the card the cursor is HOVERING. Detection
  only, never clicked. Matched at 0.82 rather than the 0.90 default: a
  miss lets a Traitless card through, a false positive only skips a card,
  so the bar leans toward the recoverable mistake. Adding another
  modifier means art under `Assets/ui/<name>/`, an entry in
  `runner.PORTAL_MODIFIER_IMAGES` and one in `app.js`'s
  `PORTAL_MODIFIERS` -- all three, or the name is unfilterable and the
  runner logs that it is.

The card the macro takes is the first one whose sidebar carries none of
the task's blacklisted modifiers (Task Builder > "Traitless Portal
Cards", stored as `portal_blacklist`; unset means Traitless is skipped).
Every path that cannot decide -- empty blacklist, missing art, all three
rejected -- takes the MIDDLE card, which is what this did
unconditionally before 0.24.24. An offer left open blocks the round, so
an unfiltered pick always beats no pick.

### Post-run portal chooser + exit

- `portal_win` -- victory screen with the 3-portal offer.
- `portal_offer` -- the "choose your next portal" screen (T1..T5 variants as alts).
- `portal_select` -- the blue **Select Portal** button on the post-run result
  panel, which opens the Portal Selection list.
- `portal_chooser_confirm` -- the green **Select** button in that list's right
  pane, which starts the chosen portal.
- `portal_exit` -- Exit to Lobby button (idle + selected).

**Both of those buttons ship `*_docked*` variants as of 0.25.1, and those are
the ones that match.** The older crops were cut from an undocked window:
`portal_chooser_confirm.png` is 266x46 where the docked button is 236x36
(1.13x / 1.28x), and `portal_select_live.png` is 300x74 against 211x40
(1.42x / 1.85x). `SCALE_FACTORS` only reaches 0.90x, so both missed silently
on every cycle and the route fell back to a stored coordinate every time --
which meant two of its steps were blind clicks with no verification at all.
Convention 3c-ter, and the reason it is worth re-reading before cutting any
new art: measure the crop against a docked 1152x756 capture (Settings >
General > Image Manager) before shipping it.

## Picking a portal by NAME (the Portal Scanner, 0.26.0)

Set **Portal Priority** on a Portals task and the saved squares stop being
used. The scanner clicks its way across the grid, reads each card's
detail pane, and confirms only the card whose name matches and whose
modifiers the task accepts. A square holding the wrong portal is skipped,
not spent -- which is the only thing that survives the grid re-flowing
(convention 3f).

- It is an ordered LIST. The scanner takes the highest-ranked portal it
  can find, so "Summer Portal, then Sovereign's" is one task. One pass over
  the grid: every slot read once, best rank remembered, a #1 match ends the
  pass. The winner is re-selected and re-read before anything is confirmed,
  because the pass moved the selection on.
- Leave the tier off the name. The card shows the tier on its own line,
  so `Summer Portal` matches every tier; `Summer Portal Tier 5` works too
  (tier is stripped from both sides before comparing). Alternatives can
  be separated with `|`.
- Matching is fuzzy on purpose: letters and digits only, lowercase, and a
  sliding-window `SequenceMatcher` at **0.78** over the words in the
  pane, so the rarity and stat text around the name don't count against
  it. `Sumrner Portal` matches; `Sky Ruins Portal` does not.
- **A scan that finds nothing clicks nothing.** It does not fall back to
  the saved square -- "I couldn't find it, so I'll click this anyway" is
  exactly how the wrong portal gets spent.
- Runs on both screens: the lobby inventory and the post-run Portal
  Selection list.

Geometry lives in Settings > Debug > Portal Scanner: the squares to click
per screen, and the two detail-pane regions to read. **The shipped
regions were measured on a different build's window** -- same 1152x756
space, so they should be close, but expect one calibration pass. Select a
portal by hand and press **Test Read**: it prints what it read and writes
the exact crops to `debug/portal_scan_name_region.png` and
`debug/portal_scan_modifier_region.png`.

Reading is held off until two consecutive captures of the pane differ by
less than 1% (`_wait_for_detail_pane`). OCR-ing mid-repaint reads the
PREVIOUS portal, which would hand the scanner a confident wrong answer --
worse than no scanner at all.

## Which of the three offered cards to take

`Card Select` on the task: **Default** takes the middle card (what this did
before 0.24.24), **Advanced** hovers each card, reads its sidebar and skips
the task's blacklisted modifiers. Advanced is the default. Every path that
cannot decide -- Default, empty blacklist, missing art, all three rejected --
takes the middle card, because an offer left open blocks the round.

## Picking a portal out of a grid (the ghost-click check)

Both portal slots -- the lobby inventory square and the post-run chooser
square -- are coordinate clicks into a grid whose squares carry no art
of their own. Nothing on screen proves which one is selected, so a click
that never registered is indistinguishable from one that did, and the
NEXT step (Select) then confirms whatever was already highlighted: a
different portal, spent for real, with a log that reads clean.

`_click_portal_slot` closes that. It captures a 150x90 reference-space
box around the click point, clicks (through `_hover_click`, so focus is
asserted and the cursor hovers in -- convention 5, which this one click
had been skipping), settles, captures again, and requires at least
**2.5%** of the pixels to have changed by more than 18 gray levels.
Selecting a portal draws a border/glow and repaints the pane beside it,
so a real click clears that bar comfortably while compression noise on a
static screen does not.

Unchanged means the click did not take, and it re-clicks -- up to 3
attempts. Still unchanged means the route **stops** rather than pressing
Select. That is the whole point: refusing to confirm is how the wrong
portal stops being spent. A capture that fails outright (window covered
mid-step) is the one path that trusts the click, and says so in the log.

## Click coord keys (`MACRO_COORD_DEFAULTS`)

Every Click block in the bundled templates passes a `coord_key` param
instead of a hardcoded x/y. The runner's `_run_click_block` (see
`core/runner_blocks.py`, extended in 0.21) reads `<key>_x` and
`<key>_y` from the runner's coords map -- populated from
`MACRO_COORD_DEFAULTS` in `main.py` and overridable per user in
Settings > Debug > Macro Coordinates. An unset coord logs
`coord_key '<key>' not set in Settings > Debug > Macro Coordinates
-- skipping` and no click happens (identical to the old "no position
set -- skipping" behavior for a forgotten Set picker).

The six configurable points the route uses, in route order:

- `nav_items` -- Items button on the lobby HUD.
- `portal_tab` -- Portals sub-tab inside the Items panel.
- `portal_activate` -- Activate button on the portal confirmation screen.
- `portal_start` -- Start button on the party screen Activate opens (fallback only).
- `portal_select` -- Select button on the post-run screen, which opens the chooser.
- `portal_exit` -- Exit to Lobby button, used after the last portal.

Portal names use fixed search and first-result points in the same 1152x756
reference space as the configurable coordinates. In the lobby the route
searches at `(460, 180)` and selects the first result at `(387, 247)`. After a
run it searches at `(506, 187)` and selects the first result at `(294, 254)`.
The first-result click always happens before Activate or the green Select.

Every step of both routes is image-first with its coordinate as the
fallback, so stale reference art degrades to coordinate clicking rather
than stopping the task.

Each step also **verifies itself** (`_portal_step`). It names the art
that proves its click worked -- Items expects the Portals tab or the
inventory, the Portals tab expects the inventory, a portal slot expects
the Activate screen -- and re-clicks up to three times if that art
doesn't appear. This exists because a Roblox click can land on the
right pixel and still not register; without the check, the route
marched on and every later step failed against a screen that had never
changed. A step also skips its click when it is *already* where it was
trying to get to, so a retry that starts with the panel still open
can't toggle it shut.

Pick verification anchors that change **because of the click**: the
Portals tab is proven by the tab turning blue (`portal_tab_selected`),
not by the inventory art, which drifts as the game is updated. A stale
anchor turns a working step into a failing one, which is worse than no
check at all. Portal clicks therefore also assert window focus and hover in
before clicking (`_hover_click` / `click_match(shuffle=True)`), the same
treatment the lobby Event button and the Start Game click already
needed.

One rule when adding art to any of these folders: **every variant must
be safe to click.** `template_variant_paths` tries `<name>.png` first
and then the rest alphabetically, the first variant over threshold
wins, and what gets clicked is the *centre of that match*. A crop of a
whole panel will therefore click the middle of the panel rather than
the button inside it -- which is exactly why 0.22 moved the old
231x378 `portal_activate.png` out to `Assets/ui/_unused/`. Crop to the
button, not to the screen it lives on.

Nothing from the Event menu is here any more. Through 0.21 the route
entered via the event card and the Portal Mode tile; opening a portal
straight out of the inventory works from the lobby regardless of what
else is on screen, so `nav_event`, `portal_event_open` and
`portal_mode_tile` were dropped along with those two screens.

There is deliberately **no "which portal" point here, not even a
fallback**. Which portal to run is per-player *and* per-task -- two
queued tasks can farm two different portals out of one inventory -- so a
shared default could only ever be right for one of them, and a task
quietly opening someone else's portal is worse than a task that says
what it needs. A Portals task carries both points and will not run
without them.

## Bundled example templates

**Removed at 0.25.0.** Three portal templates used to ship here
(`Portals - single portal`, `Portals - N portals then exit`,
`Portals - continuous`). They were written for the pre-0.22 workflow, where
a TEMPLATE drove the portal cycle: navigate in, start a portal, and watch
Loop A for the exit screen. Since 0.22 the TASK drives the cycle -- it enters
the portal, plays it, chains into the next one and exits after its
"Portals Then Exit" count -- so the templates were doing a second, competing
version of the same job. Their Loop A clicked Select on the post-run chooser,
which is the exact click the task makes and counts, so running one alongside
a Portals task raced for the same button and made the count wrong. The
`skip_modes` machinery in `core/runner_blocks.py` exists only because of
that collision.

A Macro Operation on a Portals task is for placing units (or anything else)
DURING the run. It does not need to know about portals at all.

## First-run defaults

0.21.0 shipped every entry above as `None`; 0.21.2 replaced them with
real values picked from a live 1152x756 window, and 0.22 added the two
`*_pick` points the same way. Per-user overrides in `settings.json`
always win, so a game update that shifts a point is a picker click in
Settings > Debug > Macro Coordinates rather than a release. The
`*_pick` points are the two most worth re-picking on a fresh install
-- everything else is a fixed piece of UI, those two are your own
inventory.

## What still needs a shot

`Assets/ui/` folders that would round out the pack but aren't
strictly required to run:

- `portal_activate_button` -- tight crop of just the Activate / Start button on the portal-activate screen.
- `sky_ruins_portal_tier_1` .. `sky_ruins_portal_tier_4` -- Sky Ruins tier icons (T5 shipped).
- `portal_insufficient_fuel` -- the "not enough fuel" popup, if it has its own art.

Drop any of those into an `Assets/ui/<name>/` folder and the runner
picks them up automatically.

## Where the full "Portals as a UI tab" mode is

0.22 delivered the task-queue half of this: Portals is a mode in the
Task Builder, with its own portal-type dropdown and run counter (see
"As a task" above). What is still outstanding is the *settings tab*
alongside Auto Challenge / Auto Bounty -- tier picker, per-tier macro
binding, health check, `setup_ready` gate -- it needs a
new panel in `ui/index.html` + `ui/app.js` mirrored from the Auto
Challenge panel, and a `core/runner_portals.py` mixin styled after
`core/runner_challenge.py` -- 500+ lines across three files, which is
why it stayed out of 0.22 as well. The task path added in 0.22 covers
the "just run portals from the queue" case that panel would mostly
serve; the panel is what a per-tier setup would need.
