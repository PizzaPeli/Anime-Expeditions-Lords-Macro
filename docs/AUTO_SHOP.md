# Auto Shop recognition

Auto Shop has independent Gold Shop and Expedition Shop tabs. Both run only
at the existing lobby-safe boundaries, with separate enable switches, item
selections, quantities, retry state, and daily progress. Expedition Shop uses
the same remote menu route, locating its own card title and verifying its own
header before scanning the four-column list. Futuristic Payload is excluded
because it uses Gold rather than Expedition Coins. Gem and Gold quantities
refer to the game's 50x purchase bundles.

List / Squares changes presentation for both tabs and is saved with the
settings. Squares adapt their columns to the available panel width. New shop
items start disabled, and existing Gold Shop choices survive migration.

The November 1 captures live in `Assets/reference/auto_shop/expedition_20261101`;
`scripts/dev/extract_expedition_shop_captures.py` regenerates their templates.
Trait Crystal was sold out, so its full stock limit is unknown; the UI labels
that explicitly rather than borrowing Gold Shop's limit. Its numeric input
has a generic 9999 ceiling, while Max uses the game's available quantity.

Expedition Pre Start remains once per run. Initial Start Game starts the
normal Battle phase; each later Start Game popup can replay Battle once.
Repeated frames of the same popup do not rewind Battle again. The game owns
phantom units and affordability; no extra placed-unit checks are added.
Extraction behavior is unchanged.

Gold Shop opens remotely using the top-bar three-dot menu, All Shops, then
Restocking. Navigation identifies the Gold Shop card by its title and clicks
Open Shop relative to that card, so its grid row is not assumed. It verifies
the Gold Shop header before purchasing. Normal navigation does not teleport,
tilt the camera, press E, or use Buy All. Existing lobby-safe scheduling,
selected items, quantity settings, and restock rules are preserved.

The October 31 remote-navigation captures are archived in
`Assets/reference/auto_shop/remote_20261031`. To reproduce their navigation
templates, run `python scripts/dev/extract_remote_shop_captures.py`.

Auto Shop searches the visible list for each selected item's icon and verifies
the icon/name area before using its controls. It scrolls in overlapping steps,
so changes to item order do not require new row or column coordinates. The
scan uses whole-notch scroll steps, waits two seconds for the list to
settle, and checks up to three frames before moving on. Each recognition check
uses one frame for the icon, card identity, and terminal controls. The scrollbar
must remain unchanged across two scroll attempts to confirm the list end;
animated card artwork does not control that decision.

The
shop header confirms that the list opened without assuming a particular first
item. Missing items remain pending; a sold-out label in an old slot is never
assigned to an unidentified item.

The Update 3 captures from 4 October 2026 are stored in
`Assets/reference/auto_shop/update_20261004`. They include Survival Rations and
Rice, 100-unit food stocks, the disabled Trait Crystal card, and both quantity
toggle states. Trait Crystal is already out of stock in these captures.
Survival Rations and Rice appear in the Auto Shop purchase selection menu,
including when loading settings saved before those items were added. New items
start disabled and can be enabled with either a numeric quantity or Max.

Buy is located below the matched icon within the same card's control band.
A verified sold-out card can be recognized even when its Buy button is gray.
The purchase popup uses Cancel as the anchor for the input and Max/Min toggle,
and locates the green confirmation button beside it. "Min" means the maximum
quantity is selected; "Max" means it can be selected.

New positions alone do not require new pictures. Changed artwork, typography,
or card/control spacing may require refreshed references or detection changes.
Icon variants live in `Assets/ui/shop_<item>/`. Card identity crops live in
`Assets/reference/auto_shop/identities/<item>/`; each crop is 140 by 110 pixels
and excludes the stock badge and price. Preserve full docked captures for
regression checks, including sold-out cards and both quantity states.

Run the shop regression checks with:

```text
python -m pytest tests/test_expedition_shop.py tests/test_remote_gold_shop.py tests/test_shop_update_captures.py tests/test_runner_shop_no_ocr.py tests/test_runner_shop.py tests/test_auto_shop.py tests/test_auto_shop_settings.py tests/test_runner_shop_scheduler.py tests/test_ui_js.py
```

These checks exercise screenshot recognition and simulated runner behavior.
A live game run is still needed to verify scrolling, input timing, and purchases.
Source changes require a rebuilt executable, with the updated Assets supplied
to the installed build.
