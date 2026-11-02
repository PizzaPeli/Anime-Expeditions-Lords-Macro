"""Shop automation executed only from lobby-safe runner boundaries."""

import hashlib
import threading
import time
import cv2

from . import auto_shop
from . import auto_shop_vision
from . import keys
from . import vision
from . import window as wm


SHOP_KEY = "gold_shop"
SHOP_NAV_TIMEOUT = 10.0
SHOP_LOAD_TIMEOUT = 60.0
SHOP_OPEN_TIMEOUT = 10.0
SHOP_MODAL_TIMEOUT = 4.0
SHOP_BUY_TIMEOUT = 2.0
SHOP_TERMINAL_TIMEOUT = 2.0
SHOP_MODAL_CLOSE_TIMEOUT = 5.0
SHOP_SCROLL_AMOUNT = -480
SHOP_SCROLL_REFINEMENT_AMOUNT = -120
SHOP_SCROLL_RESET_AMOUNT = 2400
SHOP_ITEM_SEARCH_TIMEOUT = 3.0
SHOP_BOTTOM_SCROLL_AMOUNT = -4800
SHOP_LIST_CENTER = (545, 410)
SHOP_LIST_SLOT_VIEWPORTS = {
    "left": (398, 218, 154, 362),
    "right": (552, 218, 154, 362),
}
SHOP_OUT_OF_STOCK_BANDS = {
    0: (218, 90),
    -120: (300, 110),
}
SHOP_OUT_OF_STOCK_DEFAULT_BAND = (218, 110)
SHOP_LIST_ACTION_VIEWPORT = (390, 218, 316, 362)
SHOP_DISCOVERY_VIEWPORT = (390, 180, 316, 440)
SHOP_SCROLLBAR_VIEWPORT = (707, 218, 7, 358)
SHOP_DISCOVERY_SCROLL_AMOUNT = -120
SHOP_DISCOVERY_MAX_SCROLLS = 48
SHOP_DISCOVERY_CAPTURE_ATTEMPTS = 3
SHOP_DISCOVERY_RECHECK_DELAY = 0.35
SHOP_SETTLE_DELAY = 1.2
SHOP_LIST_SETTLE_DELAY = 2.0
SHOP_MODAL_POST_CLOSE_DELAY = 0.8
SHOP_MODAL_CLEAR_CHECKS = 3
SHOP_MODAL_CLEAR_INTERVAL = 0.25
SHOP_CAPTURE_INTERVAL = 0.12
SHOP_CATALOG_VIEWPORT = (350, 198, 570, 396)
# Relative to the Gold Shop title, not a fixed grid slot. Both the All Shops
# and Restocking layouts put Open Shop here; Buy All is to its right.
SHOP_REMOTE_OPEN_FROM_TITLE = (37, 165)
# Historical layout retained for legacy helpers only. The active Auto Shop
# sweep discovers item cards visually and never uses these slot tables.
SHOP_ITEM_SCROLL_STEPS = {
    "cursed_boba": 0,
    "red_flower": 0,
    "frown_fruit": 1,
    "delicious_pie": 1,
    "mana_flask": 1,
    "meat": 1,
    "trait_crystal": 2,
    "sprite_grey": 2,
    "equipment_reroll": 3,
    "equipment_lock": 3,
    "stat_reroll": 4,
    "stat_lock": 4,
}
SHOP_ITEM_SCROLL_AMOUNTS = {
    "cursed_boba": 0,
    "red_flower": 0,
    "frown_fruit": -120,
    "delicious_pie": -120,
    "mana_flask": -480,
    "meat": -480,
    "trait_crystal": -720,
    "sprite_grey": -720,
    "equipment_reroll": -960,
    "equipment_lock": -960,
    "stat_reroll": SHOP_BOTTOM_SCROLL_AMOUNT,
    "stat_lock": SHOP_BOTTOM_SCROLL_AMOUNT,
}
SHOP_ITEM_COLUMNS = {
    "cursed_boba": "left",
    "red_flower": "right",
    "frown_fruit": "left",
    "delicious_pie": "right",
    "mana_flask": "left",
    "meat": "right",
    "trait_crystal": "left",
    "sprite_grey": "right",
    "equipment_reroll": "left",
    "equipment_lock": "right",
    "stat_reroll": "left",
    "stat_lock": "right",
}
SHOP_SWEEP_POSITIONS = (
    (0, ("cursed_boba", "red_flower")),
    (-120, ("frown_fruit", "delicious_pie")),
    (-480, ("mana_flask", "meat")),
    (-720, ("trait_crystal", "sprite_grey")),
    (-960, ("equipment_reroll", "equipment_lock")),
    (SHOP_BOTTOM_SCROLL_AMOUNT, ("stat_reroll", "stat_lock")),
)

_TERMINAL_ITEM_STATUSES = {
    auto_shop.STATUS_COMPLETED,
    auto_shop.STATUS_OUT_OF_STOCK,
    auto_shop.STATUS_MAX_INVENTORY,
    auto_shop.STATUS_FAILED_TODAY,
}


class ShopOps:
    def _auto_shop_settings(self) -> dict:
        if self._get_auto_shop_settings is None:
            return {}
        try:
            return self._get_auto_shop_settings() or {}
        except Exception as exc:
            self._log(f"[Shop] Couldn't read Auto Shop settings: {exc}")
            return {}

    def _auto_shop_due_items(self, settings=None, shop_key=SHOP_KEY) -> list:
        settings = settings or self._auto_shop_settings()
        if not settings.get("enabled"):
            return []
        shop = (settings.get("shops") or {}).get(shop_key) or {}
        if not shop.get("enabled"):
            return []
        if (shop.get("state") or {}).get("status") == auto_shop.STATUS_FAILED_TODAY:
            return []
        return [
            item
            for item in (shop.get("items") or [])
            if item.get("enabled")
            and (item.get("state") or {}).get("status") not in _TERMINAL_ITEM_STATUSES
        ]

    def _auto_shop_wants_in(self) -> bool:
        """Return whether either shop has an actionable configured item."""
        return any(self._auto_shop_due_items(shop_key=key) for key in auto_shop.SHOP_CATALOGS)

    def _shop_save_item_state(self, shop_key: str, item_key: str, state: dict) -> None:
        if self._save_auto_shop_item_state is None:
            return
        try:
            self._save_auto_shop_item_state(shop_key, item_key, state)
        except Exception as exc:
            self._log(f"[Shop] Couldn't save {item_key} state: {exc}")

    def _shop_save_shop_state(self, shop_key: str, state: dict) -> None:
        if self._save_auto_shop_shop_state is None:
            return
        try:
            self._save_auto_shop_shop_state(shop_key, state)
        except Exception as exc:
            self._log(f"[Shop] Couldn't save {shop_key} state: {exc}")

    @staticmethod
    def _shop_state_period(state: dict) -> str:
        return str((state or {}).get("period") or auto_shop.current_auto_shop_period())

    @staticmethod
    def _shop_region_is_visible(
            region: tuple, allow_top_clip: bool = False, shop_key=SHOP_KEY) -> bool:
        x, y, width, height = region
        view_x, view_y, view_width, view_height = (
            (275, 250, 590, 326) if shop_key == "expedition_shop" else SHOP_LIST_ACTION_VIEWPORT)
        min_y = 180 if allow_top_clip else view_y
        return (
            x >= view_x
            and y >= min_y
            and x + width <= view_x + view_width
            and y + height <= view_y + view_height
        )

    def _shop_find_item(
            self, hwnd, item: dict, stop_event: threading.Event):
        template = auto_shop.item_definition(item["key"])["template"]
        target_step = SHOP_ITEM_SCROLL_STEPS[item["key"]]
        self._log(
            f'[Shop] Locating "{item["name"]}" at scroll step '
            f"{target_step}..."
        )
        x, y = vision.ref_to_screen(hwnd, *SHOP_LIST_CENTER)
        self._mouse.move_to(x, y)
        self._mouse.nudge()
        self._mouse.scroll(SHOP_SCROLL_RESET_AMOUNT)
        time.sleep(SHOP_SETTLE_DELAY)
        scroll_amount = SHOP_ITEM_SCROLL_AMOUNTS[item["key"]]
        if scroll_amount:
            if self._checkpoint(stop_event):
                return None
            self._mouse.scroll(scroll_amount)
            time.sleep(SHOP_SETTLE_DELAY)
        if self._checkpoint(stop_event):
            return None
        try:
            match = vision.wait_for_image(
                hwnd,
                template,
                timeout=SHOP_ITEM_SEARCH_TIMEOUT,
                stop_event=stop_event,
            )
        except vision.TemplateNotFound as exc:
            self._log(f"[Shop] {exc}")
            return None
        allow_top = (scroll_amount == 0)
        if match is not None:
            stock_region = auto_shop_vision.stock_status_region_from_item_match(match)
            buy_region = auto_shop_vision.initial_buy_region_from_item_match(match)
            if (
                    self._shop_region_is_visible(stock_region, allow_top_clip=allow_top)
                    and self._shop_region_is_visible(buy_region)):
                return match

            self._log(
                f'[Shop] "{item["name"]}" is visible but its controls are '
                "clipped; scrolling one more step..."
            )
            self._mouse.scroll(SHOP_SCROLL_REFINEMENT_AMOUNT)
            time.sleep(SHOP_SETTLE_DELAY)
            try:
                match = vision.wait_for_image(
                    hwnd,
                    template,
                    timeout=SHOP_ITEM_SEARCH_TIMEOUT,
                    stop_event=stop_event,
                )
            except vision.TemplateNotFound as exc:
                self._log(f"[Shop] {exc}")
                return None
            if match is not None:
                stock_region = auto_shop_vision.stock_status_region_from_item_match(match)
                buy_region = auto_shop_vision.initial_buy_region_from_item_match(match)
                if (
                        self._shop_region_is_visible(stock_region, allow_top_clip=allow_top)
                        and self._shop_region_is_visible(buy_region)):
                    return match
        self._log(
            f'[Shop] "{item["name"]}" was not found at its expected '
            f"scroll step ({target_step})."
        )
        return None

    def _shop_find_visible_item(
            self, hwnd, item: dict, stop_event: threading.Event):
        """Find a card by its own icon, never by a calibrated row or column."""
        if self._checkpoint(stop_event):
            return None
        definition = auto_shop.item_definition(item["key"])
        template = definition["template"]
        shop_key = getattr(self, "_active_shop_key", SHOP_KEY)
        bounds = (275, 250, 590, 326) if shop_key == "expedition_shop" else SHOP_DISCOVERY_VIEWPORT
        reason = None
        for attempt in range(SHOP_DISCOVERY_CAPTURE_ATTEMPTS):
            if self._checkpoint(stop_event):
                return None
            # Match the icon, identity and controls in one frame. Animated
            # cards can otherwise change between the separate captures.
            frame = vision.capture_game_bgr(hwnd)
            if frame is None or not frame.size:
                reason = "screen capture was unavailable"
                continue
            viewport = auto_shop_vision.crop_region(frame, bounds)
            try:
                match = vision.find_in_gray_multiscale(
                    cv2.cvtColor(viewport, cv2.COLOR_BGR2GRAY), template,
                    template_dir=definition.get("template_dir", vision.UI_ASSETS_DIR))
            except vision.TemplateNotFound as exc:
                self._log(f"[Shop] {exc}")
                return None
            if match is None:
                if attempt + 1 < SHOP_DISCOVERY_CAPTURE_ATTEMPTS:
                    time.sleep(SHOP_DISCOVERY_RECHECK_DELAY)
                continue
            for field in ("x", "cx"):
                match[field] += bounds[0]
            for field in ("y", "cy"):
                match[field] += bounds[1]
            buy_region = auto_shop_vision.find_card_buy_button(frame, match)
            if auto_shop_vision.verify_card_identity(frame, item["key"], match):
                if (buy_region is not None
                        and self._shop_region_is_visible(buy_region, shop_key=shop_key)):
                    return match
                # Sold-out cards have a disabled Buy. Identify the card first,
                # then read its own terminal label, regardless of its row.
                if self._shop_find_terminal_label(hwnd, match, stop_event, frame=frame):
                    return match
                reason = "its controls were clipped or disabled"
            else:
                reason = "its card identity did not match"
            if attempt + 1 < SHOP_DISCOVERY_CAPTURE_ATTEMPTS:
                time.sleep(SHOP_DISCOVERY_RECHECK_DELAY)
        if reason:
            self._log(f'[Shop] Saw "{item["name"]}", but {reason}; continuing the scan.')
        return None

    def _shop_find_slot_out_of_stock(
            self, hwnd, item: dict, scroll_amount: int,
            stop_event: threading.Event) -> bool:
        """Check the sold-out label inside one calibrated row and column."""
        if self._checkpoint(stop_event):
            return False
        column = SHOP_ITEM_COLUMNS[item["key"]]
        x, _y, width, _height = SHOP_LIST_SLOT_VIEWPORTS[column]
        y, height = SHOP_OUT_OF_STOCK_BANDS.get(
            scroll_amount,
            SHOP_OUT_OF_STOCK_DEFAULT_BAND,
        )
        try:
            match = vision.find_image(
                hwnd,
                auto_shop.AUTO_SHOP_UI_TEMPLATES["out_of_stock"],
                region=(x, y, width, height),
            )
        except vision.TemplateNotFound as exc:
            self._log(f"[Shop] {exc}")
            return False
        return match is not None

    def _shop_retry_item_state(self, item: dict) -> dict:
        state = item.get("state") or {}
        period = self._shop_state_period(state)
        retry = auto_shop.normalize_item_state(state, period)
        if retry["status"] != auto_shop.STATUS_PENDING_VERIFICATION:
            retry["attempts"] = 0
            retry["status"] = auto_shop.STATUS_RETRY_PENDING
            retry["verification"] = None
        return retry

    def _shop_out_of_stock_state(self, item: dict) -> dict:
        state = item.get("state") or {}
        period = self._shop_state_period(state)
        completed = auto_shop.normalize_item_state(state, period)
        completed["status"] = auto_shop.STATUS_OUT_OF_STOCK
        completed["attempts"] = 0
        completed["verification"] = None
        return completed

    def _shop_move_to_scroll_position(
            self, hwnd, scroll_amount: int,
            stop_event: threading.Event) -> bool:
        """Reset to Top, then apply one calibrated absolute scroll delta."""
        if self._checkpoint(stop_event):
            return False
        x, y = vision.ref_to_screen(hwnd, *SHOP_LIST_CENTER)
        self._mouse.move_to(x, y)
        self._mouse.nudge()
        self._mouse.scroll(SHOP_SCROLL_RESET_AMOUNT)
        time.sleep(SHOP_LIST_SETTLE_DELAY)
        if scroll_amount:
            if self._checkpoint(stop_event):
                return False
            self._mouse.scroll(scroll_amount)
            time.sleep(SHOP_LIST_SETTLE_DELAY)
        return not self._checkpoint(stop_event)

    def _shop_run_no_ocr_sweep(
            self, hwnd, shop_key: str, items: list,
            stop_event: threading.Event) -> None:
        """Sweep the live list once, discovering cards by icon at each scroll.

        No row, column, synthetic match, stock OCR, or saved scroll offset is
        trusted here.  A card can only own a Buy click in the same viewport in
        which its item image was freshly found.
        """
        pending = {item["key"]: item for item in items}
        seen = set()
        unchanged_scrolls = 0
        self._log("[Shop] Scanning slowly: small scrolls, 2s settling, and three checks per item.")
        x, y = vision.ref_to_screen(hwnd, *SHOP_LIST_CENTER)
        self._mouse.move_to(x, y)
        self._mouse.nudge()
        self._mouse.scroll(SHOP_SCROLL_RESET_AMOUNT)
        time.sleep(SHOP_LIST_SETTLE_DELAY)

        for _step in range(SHOP_DISCOVERY_MAX_SCROLLS + 1):
            if self._checkpoint(stop_event):
                return
            self._log(f"[Shop] Checking list position {_step + 1}...")
            for item_key, item in tuple(pending.items()):
                if item_key in seen or self._checkpoint(stop_event):
                    continue
                self._set_status(action=f'Looking for {item["name"]}...')
                match = self._shop_find_visible_item(hwnd, item, stop_event)
                if match is None:
                    continue
                seen.add(item_key)
                self._shop_process_visible_item(
                    hwnd, shop_key, item, match, stop_event,
                )

            if len(seen) == len(pending) or self._checkpoint(stop_event):
                break
            # Keep item tooltips out of the list capture after a purchase.
            self._mouse.move_to(x, y)
            before = self._shop_discovery_signature(hwnd)
            self._mouse.scroll(SHOP_DISCOVERY_SCROLL_AMOUNT)
            time.sleep(SHOP_LIST_SETTLE_DELAY)
            after = self._shop_discovery_signature(hwnd)
            unchanged_scrolls = unchanged_scrolls + 1 if before is not None and before == after else 0
            if unchanged_scrolls >= 2:
                self._log("[Shop] Reached the end of the shop list.")
                break

        for item_key, item in pending.items():
            if item_key in seen or self._checkpoint(stop_event):
                continue
            # A label at an old slot cannot identify an item after a reorder.
            # Only a freshly identified card may supply its terminal state.
            period = self._shop_state_period(item.get("state") or {})
            self._shop_save_item_state(
                shop_key,
                item_key,
                auto_shop.mark_item_not_located(item.get("state"), period),
            )
            self._log(
                f'[Shop] "{item["name"]}" was not found in the full list; '
                "it remains pending for a later Auto Shop pass."
            )

    def _shop_discovery_signature(self, hwnd):
        """Return a compact viewport fingerprint for physical-end detection."""
        bounds = (903, 250, 7, 326) if getattr(self, "_active_shop_key", SHOP_KEY) == "expedition_shop" else SHOP_SCROLLBAR_VIEWPORT
        frame = vision.capture_game_bgr(hwnd, bounds)
        if frame is None or not frame.size:
            return None
        # Animated item backgrounds never stop changing at the bottom. The
        # scrollbar position does; coarse brightness removes capture noise.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return hashlib.sha256((gray > 35).tobytes()).digest()

    def _shop_synthetic_item_match(self, item: dict, scroll_amount: int) -> dict:
        """Construct synthetic item match coordinates from calibrated slot position."""
        column = SHOP_ITEM_COLUMNS[item["key"]]
        center_x = 475 if column == "left" else 629
        center_y = 295 if scroll_amount == 0 else 430
        return {
            "x": center_x - 30,
            "y": center_y - 27,
            "w": 61,
            "h": 55,
            "cx": center_x,
            "cy": center_y,
        }

    def _shop_try_fallback_modal(
            self, hwnd, item: dict, synthetic_match: dict,
            stop_event: threading.Event):
        """Attempt clicking calibrated buy button if template match failed, returning cancel_match if modal opens."""
        if self._checkpoint(stop_event):
            return None
        region = auto_shop_vision.initial_buy_region_from_item_match(synthetic_match)
        try:
            buy_crop = vision.capture_game_bgr(hwnd, region)
        except Exception:
            buy_crop = None
        if buy_crop is None or not buy_crop.size or not auto_shop_vision.buy_button_is_enabled(buy_crop):
            return None
        x, y, width, height = region
        buy_match = {
            "x": x,
            "y": y,
            "w": width,
            "h": height,
            "cx": x + width // 2,
            "cy": y + height // 2,
        }
        vision.click_match(self._mouse, hwnd, buy_match)
        try:
            cancel_match = vision.wait_for_image(
                hwnd,
                # Was "modal_cancel", a key that has never existed in
                # AUTO_SHOP_UI_TEMPLATES -- so this raised KeyError, the bare
                # except below swallowed it, and this whole fallback path
                # could never once have succeeded.
                auto_shop.AUTO_SHOP_UI_TEMPLATES["cancel"],
                timeout=SHOP_MODAL_TIMEOUT,
                stop_event=stop_event,
            )
        except vision.TemplateNotFound:
            # A missing crop is the only expected failure here. Catching
            # everything is what hid the KeyError above for as long as it
            # existed.
            cancel_match = None
        if cancel_match is not None:
            self._log(f'[Shop] Fallback modal opened for "{item["name"]}"!')
            return cancel_match
        return None

    def _shop_read_observation(
            self, hwnd, item: dict, item_match: dict,
            stop_event: threading.Event) -> dict:
        status_region = auto_shop_vision.stock_status_region_from_item_match(item_match)
        try:
            out_of_stock = vision.find_image(
                hwnd,
                auto_shop.AUTO_SHOP_UI_TEMPLATES["out_of_stock"],
                region=status_region,
            ) is not None
        except vision.TemplateNotFound:
            out_of_stock = False

        stock_region = auto_shop_vision.stock_region_from_item_match(item_match)
        crops = []
        for index in range(3):
            if self._checkpoint(stop_event):
                break
            crop = vision.capture_game_bgr(hwnd, stock_region)
            if crop is not None and crop.size:
                crops.append(crop)
            if index < 2:
                time.sleep(SHOP_CAPTURE_INTERVAL)

        signature = (
            auto_shop.build_stock_signature(crops[-1])
            if crops else ""
        )
        if out_of_stock:
            return {
                "left": 0,
                "signature": signature,
                "out_of_stock": True,
            }
        daily_maximum = int(item["daily_maximum"])
        left = (
            auto_shop_vision.read_left_consensus(crops, daily_maximum)
            if len(crops) == 3 else None
        )
        return {
            "left": left,
            "signature": signature,
            "out_of_stock": False,
        }

    def _shop_find_terminal_label(
            self, hwnd, item_match: dict, stop_event: threading.Event,
            wait: bool = False, frame=None):
        region = auto_shop_vision.card_terminal_region_from_item_match(
            item_match
        )
        names = (
            auto_shop.AUTO_SHOP_UI_TEMPLATES["out_of_stock"],
            auto_shop.AUTO_SHOP_UI_TEMPLATES["max_inventory"],
        )
        if frame is not None:
            try:
                crop = auto_shop_vision.crop_region(frame, region)
            except ValueError:
                return None
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            for name in names:
                try:
                    if vision.find_in_gray_multiscale(gray, name) is not None:
                        return name
                except vision.TemplateNotFound:
                    continue
            return None
        try:
            if wait:
                match, name = vision.wait_for_image_any(
                    hwnd,
                    names,
                    region=region,
                    timeout=SHOP_TERMINAL_TIMEOUT,
                    stop_event=stop_event,
                )
            else:
                match, name = vision.find_image_any(
                    hwnd,
                    names,
                    region=region,
                )
        except vision.TemplateNotFound as exc:
            self._log(f"[Shop] {exc}")
            return None
        return name if match is not None else None

    def _shop_max_inventory_state(
            self, state: dict, period: str) -> dict:
        completed = auto_shop.normalize_item_state(state, period)
        completed["status"] = auto_shop.STATUS_MAX_INVENTORY
        completed["verification"] = None
        return completed

    def _shop_open_purchase_modal(
            self, hwnd, item_match: dict, stop_event: threading.Event,
            item_key: str = None):
        frame = vision.capture_game_bgr(hwnd)
        if item_key and not auto_shop_vision.verify_card_identity(frame, item_key, item_match):
            self._log(f'[Shop] "{item_key}" card identity changed before Buy; skipping it.')
            return None
        region = auto_shop_vision.find_card_buy_button(frame, item_match)
        if region is None:
            if stop_event.is_set():
                return None
            self._log(
                "[Shop] The visible Buy region is not enabled; "
                "no purchase was attempted."
            )
            return None
        x, y, width, height = region
        buy_match = {
            "x": x,
            "y": y,
            "w": width,
            "h": height,
            "cx": x + width // 2,
            "cy": y + height // 2,
        }
        vision.click_match(self._mouse, hwnd, buy_match)
        # "Did the modal open?" and "where is its Cancel button?" are two
        # different questions, and answering the first with the second is
        # what made this report insufficient Gold for a missing template.
        # The modal's own art answers the first; Cancel is still needed for
        # the second, because every other part of this flow is measured FROM
        # it (amount controls and the cancel click derive their regions from
        # cancel_match; final Buy is located by color beside Cancel).
        cancel_name = auto_shop.AUTO_SHOP_UI_TEMPLATES["cancel"]
        modal_name = auto_shop.AUTO_SHOP_UI_TEMPLATES["purchase_modal"]
        try:
            opened, opened_by = vision.wait_for_image_any(
                hwnd,
                (cancel_name, modal_name),
                timeout=SHOP_MODAL_TIMEOUT,
                stop_event=stop_event,
            )
        except vision.TemplateNotFound as exc:
            self._log(f"[Shop] {exc}")
            return None
        if opened is None:
            if not self._checkpoint(stop_event):
                self._log(
                    "[Shop] Buy was clicked, but the purchase modal did not open "
                    f'(watched for "{cancel_name}" and "{modal_name}"). The button may be '
                    "disabled by insufficient Gold -- or neither crop matches your screen; "
                    "add one through Settings > General > Image Manager."
                )
            return None
        if opened_by == cancel_name:
            return opened
        # The modal is definitely up. Cancel just has not been found yet --
        # give it its own look now rather than treating a slow or slightly
        # off Cancel crop as "the purchase failed".
        try:
            cancel_match = vision.wait_for_image(
                hwnd, cancel_name, timeout=SHOP_MODAL_TIMEOUT, stop_event=stop_event)
        except vision.TemplateNotFound:
            cancel_match = None
        if cancel_match is None:
            if not self._checkpoint(stop_event):
                self._log(
                    f'[Shop] The purchase modal IS open ("{modal_name}" matched) but '
                    f'"{cancel_name}" was not found on it -- and every part of the purchase '
                    "(amount controls and final Buy) requires Cancel, so this pass "
                    f'cannot continue. Recut "{cancel_name}" from a docked capture.'
                )
            return None
        return cancel_match

    def _shop_configure_amount(
            self, hwnd, cancel_match: dict, target, amount: int,
            stop_event: threading.Event) -> bool:
        if str(target).lower() == "max":
            region = auto_shop_vision.amount_toggle_region_from_cancel(cancel_match)
            # Check if Max is already selected before clicking the toggle.
            # The game displays "Min" when Max is active and vice versa.
            try:
                max_match = vision.find_image(
                    hwnd,
                    auto_shop.AUTO_SHOP_UI_TEMPLATES["amount_max"],
                    region=region,
                )
            except vision.TemplateNotFound:
                max_match = None
            try:
                min_match = vision.find_image(
                    hwnd,
                    auto_shop.AUTO_SHOP_UI_TEMPLATES["amount_min"],
                    region=region,
                )
            except vision.TemplateNotFound:
                min_match = None
            action = auto_shop.max_toggle_action(
                max_visible=max_match is not None,
                min_visible=min_match is not None,
            )
            if action == auto_shop.MAX_TOGGLE_ALREADY_SELECTED:
                return not self._checkpoint(stop_event)
            x, y, width, height = region
            screen_x, screen_y = vision.ref_to_screen(
                hwnd,
                x + width // 2,
                y + height // 2,
            )
            self._mouse.click(screen_x, screen_y)
            return not self._checkpoint(stop_event)

        region = auto_shop_vision.amount_input_region_from_cancel(cancel_match)
        x, y, width, height = region
        screen_x, screen_y = vision.ref_to_screen(
            hwnd,
            x + width // 2,
            y + height // 2,
        )
        self._mouse.double_click(screen_x, screen_y)
        time.sleep(0.15)
        self._keyboard.combo(keys.VK_CONTROL, ord("A"))
        self._keyboard.tap(keys.VK_DELETE)
        self._keyboard.type_text(str(int(amount)))
        time.sleep(SHOP_SETTLE_DELAY)
        return not self._checkpoint(stop_event)

    def _shop_cancel_modal(self, hwnd, cancel_match: dict) -> None:
        x, y = auto_shop_vision.cancel_click_point(cancel_match)
        screen_x, screen_y = vision.ref_to_screen(hwnd, x, y)
        self._mouse.click(screen_x, screen_y)

    def _shop_wait_for_modal_closed(
            self, hwnd, stop_event: threading.Event) -> bool:
        """Require sustained modal disappearance before claiming a purchase.

        Template matching can miss a single frame while Roblox redraws the
        modal.  Treating that one miss as a closed modal caused false
        "purchase executed" reports, so require several consecutive clear
        observations instead.
        """
        names = (
            auto_shop.AUTO_SHOP_UI_TEMPLATES["cancel"],
            auto_shop.AUTO_SHOP_UI_TEMPLATES["purchase_modal"],
        )
        deadline = time.time() + SHOP_MODAL_CLOSE_TIMEOUT
        clear_checks = 0
        missing_templates = set()
        while time.time() < deadline:
            if self._checkpoint(stop_event):
                return False
            still_showing = False
            checked_template = False
            for name in names:
                try:
                    match = vision.find_image(hwnd, name)
                except vision.TemplateNotFound as exc:
                    if name not in missing_templates:
                        self._log(f"[Shop] {exc}")
                        missing_templates.add(name)
                    continue
                checked_template = True
                if match is not None:
                    still_showing = True
                    break
            if checked_template and not still_showing:
                clear_checks += 1
                if clear_checks >= SHOP_MODAL_CLEAR_CHECKS:
                    return True
            else:
                clear_checks = 0
            time.sleep(SHOP_MODAL_CLEAR_INTERVAL)
        return False

    def _shop_confirm_purchase(
            self, hwnd, cancel_match: dict, stop_event: threading.Event) -> bool:
        region = auto_shop_vision.find_modal_buy_button(
            vision.capture_game_bgr(hwnd), cancel_match)
        if region is None:
            self._log("[Shop] Green confirmation Buy button was not found beside Cancel; purchase was not clicked.")
            self._shop_cancel_modal(hwnd, cancel_match)
            return False
        x, y, width, height = region
        screen_x, screen_y = vision.ref_to_screen(
            hwnd,
            x + width // 2,
            y + height // 2,
        )
        self._mouse.click(screen_x, screen_y)
        self._log(
            f"[Shop] Final Buy clicked at ({screen_x}, {screen_y}); "
            "waiting for sustained modal closure."
        )
        if self._checkpoint(stop_event):
            return False
        if self._shop_wait_for_modal_closed(hwnd, stop_event):
            time.sleep(SHOP_MODAL_POST_CLOSE_DELAY)
            self._log(
                f"[Shop] Purchase modal stayed closed for "
                f"{SHOP_MODAL_CLEAR_CHECKS} consecutive checks."
            )
            return True
        self._log(
            f"[Shop] Purchase modal closure was not stable within "
            f"{SHOP_MODAL_CLOSE_TIMEOUT:.0f}s; the purchase is unconfirmed."
        )
        self._shop_cancel_modal(hwnd, cancel_match)
        return False

    @staticmethod
    def _shop_observation_changed(before: dict, after: dict):
        before_signature = str(before.get("signature") or "")
        after_signature = str(after.get("signature") or "")
        if not before_signature or not after_signature:
            return None
        try:
            return auto_shop_vision.stock_visual_changed(
                before_signature,
                after_signature,
            )
        except ValueError:
            return None

    def _shop_state_from_observation(
            self, item: dict, state: dict, observation: dict) -> dict:
        current = auto_shop.normalize_item_state(
            state,
            self._shop_state_period(state),
        )
        current["last_known_left"] = observation.get("left")
        current["stock_signature"] = str(observation.get("signature") or "")
        current["verification"] = None
        if observation.get("out_of_stock"):
            current["status"] = auto_shop.STATUS_OUT_OF_STOCK
        else:
            plan = auto_shop.calculate_purchase_plan(
                item["key"],
                item["target"],
                int(observation["left"]),
            )
            current["status"] = plan["status"]
        return current

    def _shop_verify_pending(
            self, item: dict, state: dict, observation: dict):
        verification = state.get("verification") or {}
        if observation.get("out_of_stock"):
            return self._shop_state_from_observation(item, state, observation), True
        if observation.get("left") is None:
            return state, False
        before = {
            "left": verification.get("before_left"),
            "signature": verification.get("before_signature"),
        }
        result = auto_shop.classify_stock_verification(
            before.get("left"),
            observation.get("left"),
            self._shop_observation_changed(before, observation),
        )
        if result == auto_shop.VERIFICATION_PROGRESS:
            return self._shop_state_from_observation(item, state, observation), True
        if result == auto_shop.VERIFICATION_UNCHANGED:
            ready = auto_shop.normalize_item_state(
                state,
                self._shop_state_period(state),
            )
            ready["status"] = auto_shop.STATUS_PENDING
            ready["verification"] = None
            ready["last_known_left"] = observation["left"]
            ready["stock_signature"] = observation.get("signature") or ""
            return ready, True
        return state, False

    def _shop_process_visible_item(
            self, hwnd, shop_key: str, item: dict, item_match: dict,
            stop_event: threading.Event, cancel_match: dict = None) -> None:
        """Buy one already-visible card without reading its remaining stock."""
        item_key = item["key"]
        period = self._shop_state_period(item.get("state") or {})
        state = auto_shop.normalize_item_state(item.get("state"), period)

        if state["status"] == auto_shop.STATUS_PENDING_VERIFICATION:
            self._log(
                f'[Shop] "{item["name"]}" has an uncertain earlier purchase; '
                "skipping it safely."
            )
            self._shop_save_item_state(shop_key, item_key, state)
            return

        terminal_label = self._shop_find_terminal_label(
            hwnd,
            item_match,
            stop_event,
        )
        if terminal_label == auto_shop.AUTO_SHOP_UI_TEMPLATES["max_inventory"]:
            self._log(f'[Shop] "{item["name"]}" has Max Inventory.')
            self._shop_save_item_state(
                shop_key,
                item_key,
                self._shop_max_inventory_state(state, period),
            )
            return
        if terminal_label == auto_shop.AUTO_SHOP_UI_TEMPLATES["out_of_stock"]:
            completed = auto_shop.normalize_item_state(state, period)
            completed["status"] = auto_shop.STATUS_OUT_OF_STOCK
            completed["verification"] = None
            self._log(f'[Shop] "{item["name"]}" is out of stock.')
            self._shop_save_item_state(shop_key, item_key, completed)
            return

        target = item["target"]
        amount = int(item["daily_maximum"])
        if str(target).lower() != "max":
            amount = int(target)
        self._set_status(action=f'Opening {item["name"]} purchase...')
        self._log(
            f'[Shop] Opening purchase for "{item["name"]}": '
            f"{amount} requested."
        )
        if cancel_match is None:
            cancel_match = self._shop_open_purchase_modal(
                hwnd,
                item_match,
                stop_event,
                item_key,
            )
        if cancel_match is None:
            if not stop_event.is_set():
                self._shop_save_item_state(
                    shop_key,
                    item_key,
                    self._shop_retry_item_state(item),
                )
                self._log(
                    f'[Shop] "{item["name"]}" Buy is unavailable; '
                    "leaving it for a later pass."
                )
            return
        if not self._shop_configure_amount(
                hwnd,
                cancel_match,
                target,
                amount,
                stop_event,
        ):
            self._shop_cancel_modal(hwnd, cancel_match)
            return
        if not self._shop_confirm_purchase(hwnd, cancel_match, stop_event):
            if stop_event.is_set():
                return
            uncertain = auto_shop.normalize_item_state(state, period)
            uncertain["status"] = auto_shop.STATUS_FAILED_TODAY
            uncertain["verification"] = {"reason": "modal_did_not_close"}
            self._shop_save_item_state(shop_key, item_key, uncertain)
            self._log(
                f'[Shop] "{item["name"]}" purchase could not be confirmed; '
                "use Reset Today before retrying it."
            )
            return

        updated = auto_shop.normalize_item_state(state, period)
        updated["attempts"] = 0
        updated["verification"] = None
        if str(target).lower() == "max":
            updated["status"] = auto_shop.STATUS_COMPLETED
            message = f'[Shop] "{item["name"]}" purchase executed today.'
        else:
            updated["status"] = auto_shop.STATUS_RETRY_PENDING
            message = (
                f'[Shop] "{item["name"]}" purchase executed; it remains '
                "scheduled until stock is exhausted."
            )
        self._shop_save_item_state(shop_key, item_key, updated)
        self._log(message)

    def _shop_process_item(
            self, hwnd, shop_key: str, item: dict,
            stop_event: threading.Event) -> None:
        item_key = item["key"]
        period = self._shop_state_period(item.get("state") or {})
        state = auto_shop.normalize_item_state(item.get("state"), period)
        match = self._shop_find_item(hwnd, item, stop_event)
        if match is None:
            self._shop_save_item_state(
                shop_key,
                item_key,
                auto_shop.record_item_failure(state, period),
            )
            return

        terminal_label = self._shop_find_terminal_label(
            hwnd,
            match,
            stop_event,
        )
        if terminal_label == auto_shop.AUTO_SHOP_UI_TEMPLATES["max_inventory"]:
            self._log(
                f'[Shop] "{item["name"]}" has Max Inventory; '
                "skipping stock OCR."
            )
            self._shop_save_item_state(
                shop_key,
                item_key,
                self._shop_max_inventory_state(state, period),
            )
            return
        if terminal_label == auto_shop.AUTO_SHOP_UI_TEMPLATES["out_of_stock"]:
            observation = {
                "left": 0,
                "signature": "",
                "out_of_stock": True,
            }
        else:
            self._set_status(action=f'Reading {item["name"]} stock...')
            self._log(f'[Shop] Reading stock for "{item["name"]}"...')
            observation = self._shop_read_observation(
                hwnd,
                item,
                match,
                stop_event,
            )
        if observation.get("out_of_stock"):
            self._log(f'[Shop] "{item["name"]}" is out of stock.')
        elif observation.get("left") is not None:
            self._log(
                f'[Shop] "{item["name"]}" stock confirmed: '
                f'{observation["left"]} left.'
            )
        else:
            self._log(
                f'[Shop] OCR could not confirm "{item["name"]}" stock.'
            )
        if state["status"] == auto_shop.STATUS_PENDING_VERIFICATION:
            self._set_status(action=f'Verifying {item["name"]}...')
            self._log(
                f'[Shop] Verifying the previous "{item["name"]}" purchase...'
            )
            state, resolved = self._shop_verify_pending(item, state, observation)
            self._shop_save_item_state(shop_key, item_key, state)
            if not resolved or state["status"] != auto_shop.STATUS_PENDING:
                return

        if observation.get("out_of_stock"):
            self._shop_save_item_state(
                shop_key,
                item_key,
                self._shop_state_from_observation(item, state, observation),
            )
            return
        if observation.get("left") is None:
            self._shop_save_item_state(
                shop_key,
                item_key,
                auto_shop.record_item_failure(state, period),
            )
            return

        plan = auto_shop.calculate_purchase_plan(
            item_key,
            item["target"],
            int(observation["left"]),
        )
        if plan["status"] != auto_shop.STATUS_PENDING:
            self._shop_save_item_state(
                shop_key,
                item_key,
                self._shop_state_from_observation(item, state, observation),
            )
            return

        self._set_status(action=f'Opening {item["name"]} purchase...')
        self._log(
            f'[Shop] Opening purchase for "{item["name"]}": '
            f'{plan["pending_amount"]} requested.'
        )
        cancel_match = self._shop_open_purchase_modal(
            hwnd,
            match,
            stop_event,
        )
        if cancel_match is None:
            if stop_event.is_set():
                return
            self._log(
                f'[Shop] "{item["name"]}" purchase was not started safely.'
            )
            self._shop_save_item_state(
                shop_key,
                item_key,
                auto_shop.record_item_failure(state, period),
            )
            return
        if not self._shop_configure_amount(
                hwnd,
                cancel_match,
                item["target"],
                plan["pending_amount"],
                stop_event,
        ):
            self._shop_cancel_modal(hwnd, cancel_match)
            if stop_event.is_set():
                return
            self._shop_save_item_state(
                shop_key,
                item_key,
                auto_shop.record_item_failure(state, period),
            )
            return

        pending = auto_shop.normalize_item_state(state, period)
        pending["status"] = auto_shop.STATUS_PENDING_VERIFICATION
        pending["last_known_left"] = observation["left"]
        pending["stock_signature"] = observation.get("signature") or ""
        pending["verification"] = {
            "before_left": observation["left"],
            "before_signature": observation.get("signature") or "",
        }
        self._shop_save_item_state(shop_key, item_key, pending)

        if not self._shop_confirm_purchase(hwnd, cancel_match, stop_event):
            if not stop_event.is_set():
                self._shop_save_item_state(
                    shop_key,
                    item_key,
                    auto_shop.record_item_failure(pending, period),
                )
            return

        self._set_status(action=f'Verifying {item["name"]} purchase...')
        self._log(
            f'[Shop] Purchase submitted for "{item["name"]}"; '
            "re-reading stock..."
        )
        terminal_label = self._shop_find_terminal_label(
            hwnd,
            match,
            stop_event,
            wait=True,
        )
        if terminal_label == auto_shop.AUTO_SHOP_UI_TEMPLATES["max_inventory"]:
            self._log(
                f'[Shop] "{item["name"]}" reached Max Inventory '
                "after purchase."
            )
            self._shop_save_item_state(
                shop_key,
                item_key,
                self._shop_max_inventory_state(pending, period),
            )
            return
        if terminal_label == auto_shop.AUTO_SHOP_UI_TEMPLATES["out_of_stock"]:
            after = {
                "left": 0,
                "signature": "",
                "out_of_stock": True,
            }
        else:
            after = self._shop_read_observation(
                hwnd,
                item,
                match,
                stop_event,
            )
        if after.get("out_of_stock"):
            self._log(
                f'[Shop] "{item["name"]}" is out of stock after purchase.'
            )
        elif after.get("left") is not None:
            self._log(
                f'[Shop] "{item["name"]}" stock after purchase: '
                f'{after["left"]} left.'
            )
        else:
            self._log(
                f'[Shop] "{item["name"]}" stock could not be confirmed '
                "after purchase; verification remains pending."
            )
        result = auto_shop.classify_stock_verification(
            observation["left"],
            after.get("left"),
            self._shop_observation_changed(observation, after),
            out_of_stock=bool(after.get("out_of_stock")),
        )
        if result in (
                auto_shop.VERIFICATION_PROGRESS,
                auto_shop.VERIFICATION_OUT_OF_STOCK):
            final_state = self._shop_state_from_observation(item, pending, after)
            self._shop_save_item_state(shop_key, item_key, final_state)
        elif result == auto_shop.VERIFICATION_UNCHANGED:
            self._shop_save_item_state(
                shop_key,
                item_key,
                auto_shop.record_item_failure(pending, period),
            )

    def _shop_enter_gold_shop(self, hwnd, stop_event: threading.Event) -> bool:
        return self._shop_enter_remote_shop(hwnd, stop_event, SHOP_KEY)

    def _shop_enter_remote_shop(
            self, hwnd, stop_event: threading.Event, shop_key=SHOP_KEY) -> bool:
        """Open the requested shop remotely without moving the player."""
        if self._checkpoint(stop_event):
            return False
        templates = dict(auto_shop.AUTO_SHOP_UI_TEMPLATES)
        if shop_key == "expedition_shop":
            templates.update(remote_header="shop_remote_expedition_header", remote_gold_card="shop_remote_expedition_card")
        shop_name = auto_shop.SHOP_NAMES[shop_key]
        try:
            if vision.find_image(hwnd, templates["remote_header"]) is not None:
                return True
            catalog_open = vision.find_image(hwnd, templates["remote_restocking"]) is not None
            if not catalog_open:
                menu_open = vision.find_image(hwnd, templates["remote_all_shops"]) is not None
                if not menu_open:
                    self._set_status(action="Opening the global menu...")
                    if self._click_found_image(
                            hwnd, templates["remote_menu"], SHOP_NAV_TIMEOUT, stop_event,
                            region=(210, 5, 55, 55)) is None:
                        return False
                self._set_status(action="Opening All Shops...")
                if self._click_found_image(
                        hwnd, templates["remote_all_shops"], SHOP_NAV_TIMEOUT, stop_event,
                        region=(220, 155, 240, 85)) is None:
                    return False
            if self._checkpoint(stop_event):
                return False
            self._set_status(action=f"Finding {shop_name}...")
            if self._click_found_image(
                    hwnd, templates["remote_restocking"], SHOP_NAV_TIMEOUT, stop_event,
                    region=(215, 330, 130, 50)) is None:
                return False
            # Let the filter finish rearranging the cards before locating the
            # title. An immediate match can otherwise refer to the old row.
            time.sleep(SHOP_SETTLE_DELAY)
            card = vision.wait_for_image(
                hwnd, templates["remote_gold_card"], region=SHOP_CATALOG_VIEWPORT,
                timeout=SHOP_NAV_TIMEOUT, stop_event=stop_event)
            if card is None or self._checkpoint(stop_event):
                return False
            dx, dy = SHOP_REMOTE_OPEN_FROM_TITLE
            x, y = card["x"] + dx, card["y"] + dy
            vx, vy, width, height = SHOP_CATALOG_VIEWPORT
            if not (vx <= x < vx + width and vy <= y < vy + height):
                self._log(f"[Shop] {shop_name}'s Open Shop button is clipped -- not clicking.")
                return False
            self._set_status(action=f"Opening {shop_name} remotely...")
            self._mouse.click(*vision.ref_to_screen(hwnd, x, y))
            opened = vision.wait_for_image(
                hwnd, templates["remote_header"], region=(225, 165, 200, 45),
                timeout=SHOP_OPEN_TIMEOUT, stop_event=stop_event)
        except vision.TemplateNotFound as exc:
            self._log(f"[Shop] Remote {shop_name} reference missing: {exc}")
            return False
        if opened is None or self._checkpoint(stop_event):
            return False
        self._log(f"[Shop] {shop_name} opened remotely.")
        time.sleep(SHOP_SETTLE_DELAY)
        return not self._checkpoint(stop_event)

    def _run_auto_shop(self, hwnd, stop_event: threading.Event) -> None:
        try:
            for shop_key in auto_shop.SHOP_CATALOGS:
                if stop_event.is_set():
                    break
                self._active_shop_key = shop_key
                self._run_auto_shop_for_shop(hwnd, stop_event, shop_key)
        finally:
            self._active_shop_key = SHOP_KEY

    def _run_auto_shop_for_shop(
            self, hwnd, stop_event: threading.Event, shop_key=SHOP_KEY) -> None:
        settings = self._auto_shop_settings()
        due_items = self._auto_shop_due_items(settings, shop_key)
        if not due_items:
            return
        shop = settings["shops"][shop_key]
        shop_name = auto_shop.SHOP_NAMES[shop_key]
        period = self._shop_state_period(shop.get("state") or {})
        self._log(f"[Shop] Starting Auto Shop for {len(due_items)} item(s).")
        self._set_status(
            current_task="Auto Shop",
            action=f"Preparing {shop_name}...",
            mode="shop",
            map="-",
            stage="-",
            difficulty="-",
            macro="-",
            play_mode="-",
        )
        # Advisory, NOT fatal. This used to `return` on a single refused
        # SetForegroundWindow, which is how "Stopped. (was: Preparing Gold
        # Shop...)" ends three separate runs in the 0.28.5 log -- every one
        # of them within ~15s of a rejoin, i.e. while a freshly relaunched
        # Roblox was still refusing the foreground. Nothing else in the app
        # treats a refused activation as a reason to abandon the task: the
        # runner's own start-up path logs it and carries on. _force_focus
        # now waits the client out; if it still cannot be confirmed, say so
        # and keep going rather than killing the whole shop run.
        if not self._force_focus(hwnd):
            self._log("[Shop] Couldn't confirm Roblox took focus -- continuing anyway; "
                       "clicks may not register until it does.")
        time.sleep(0.5)
        if not self._ensure_lobby(hwnd, stop_event):
            return
        entered = (self._shop_enter_gold_shop(hwnd, stop_event) if shop_key == SHOP_KEY
                   else self._shop_enter_remote_shop(hwnd, stop_event, shop_key))
        if not entered:
            failed = auto_shop.record_navigation_failure(
                shop.get("state"),
                period,
            )
            self._shop_save_shop_state(shop_key, failed)
            if not stop_event.is_set():
                self._recover_to_lobby(hwnd, stop_event)
            return

        self._shop_save_shop_state(
            shop_key,
            auto_shop.fresh_shop_state(period),
        )
        self._shop_run_no_ocr_sweep(
            hwnd,
            shop_key,
            due_items,
            stop_event,
        )

        if not stop_event.is_set():
            try:
                close_match = vision.find_image(
                    hwnd, auto_shop.AUTO_SHOP_UI_TEMPLATES["remote_close"],
                    region=(880, 160, 50, 50))
            except vision.TemplateNotFound:
                close_match = None
            if close_match is not None:
                vision.click_match(self._mouse, hwnd, close_match)
                time.sleep(SHOP_SETTLE_DELAY)
                self._log(f"[Shop] Auto Shop pass finished. {shop_name} closed.")
            else:
                self._log(f"[Shop] Couldn't close {shop_name} -- recovering the lobby.")
                self._recover_to_lobby(hwnd, stop_event)

    def _run_auto_shop_if_due(
            self, hwnd, stop_event: threading.Event) -> None:
        if self._auto_shop_wants_in():
            self._run_auto_shop(hwnd, stop_event)
