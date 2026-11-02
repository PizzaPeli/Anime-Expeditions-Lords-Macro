"""Soul Furnace entry, per-round purchase schedules, and safe lobby boundaries."""
import re
from pathlib import Path
from functools import lru_cache
import time

import cv2
import numpy as np

from . import vision, wave, ocr
from .runner_constants import WAVE_REGION, NAV_CLICK_TIMEOUT


SOUL_ITEMS = {'dmg_boost': {'id': 'dmg_boost', 'label': 'DMG Boost', 'image': 'soul_item_dmg_boost', 'buy_dy': 85},
 'rng_boost': {'id': 'rng_boost', 'label': 'RNG Boost', 'image': 'soul_item_rng_boost', 'buy_dy': 85},
 'spa_boost': {'id': 'spa_boost', 'label': 'SPA Boost', 'image': 'soul_item_spa_boost', 'buy_dy': 85},
 'random_unit': {'id': 'random_unit', 'label': 'Random Unit', 'image': 'soul_item_random_unit', 'buy_dy': 85},
 'pumpkin_armor': {'id': 'pumpkin_armor',
                   'label': 'Pumpkin Armor',
                   'image': 'soul_item_pumpkin_armor',
                   'buy_dy': 86},
 'final_boss': {'id': 'final_boss', 'label': 'Final Boss', 'image': 'soul_item_final_boss', 'buy_dy': 85},
 'unlock_path': {'id': 'unlock_path', 'label': 'Unlock Path', 'image': 'soul_item_unlock_path', 'buy_dy': 85},
 'close_path': {'id': 'close_path', 'label': 'Close Path', 'image': 'soul_item_close_path', 'buy_dy': 85},
 'concert': {'id': 'concert', 'label': 'Concert', 'image': 'soul_item_concert', 'buy_dy': 85},
 'monster_mash': {'id': 'monster_mash',
                  'label': 'Monster Mash',
                  'image': 'soul_item_monster_mash',
                  'buy_dy': 86},
 'evening_umbrella': {'id': 'evening_umbrella',
                      'label': 'Evening Umbrella',
                      'image': 'soul_item_evening_umbrella',
                      'buy_dy': 85},
 'kings_guitar': {'id': 'kings_guitar',
                  'label': 'King’s Guitar',
                  'image': 'soul_item_kings_guitar',
                  'buy_dy': 85},
 'life_eater': {'id': 'life_eater', 'label': 'Life Eater', 'image': 'soul_item_life_eater', 'buy_dy': 85},
 'morphing_sword': {'id': 'morphing_sword',
                    'label': 'Morphing Sword',
                    'image': 'soul_item_morphing_sword',
                    'buy_dy': 85},
 'piety_obliteration': {'id': 'piety_obliteration',
                        'label': 'Piety & Obliteration',
                        'image': 'soul_item_piety_obliteration',
                        'buy_dy': 85},
 'draconic_tome': {'id': 'draconic_tome',
                   'label': 'Draconic Tome',
                   'image': 'soul_item_draconic_tome',
                   'buy_dy': 85},
 'forsaken_tome': {'id': 'forsaken_tome',
                   'label': 'Forsaken Tome',
                   'image': 'soul_item_forsaken_tome',
                   'buy_dy': 85},
 'primordial_tome': {'id': 'primordial_tome',
                     'label': 'Primordial Tome',
                     'image': 'soul_item_primordial_tome',
                     'buy_dy': 85},
 'unbound_tome': {'id': 'unbound_tome',
                  'label': 'Unbound Tome',
                  'image': 'soul_item_unbound_tome',
                  'buy_dy': 85}}

DEFAULT_PURCHASES = [{"item": "final_boss", "trigger": "heat", "target": 3}]
EVENT_SCREEN_TIMEOUT = 10.0
MAX_PURCHASE_ATTEMPTS = 5
PURCHASE_RETRY_SECONDS = 3.0
SOUL_POLL_INTERVAL = 0.2
SHOP_SCROLL_SETTLE = 0.1
SHOP_CONFIRM_INTERVAL = 0.1
HEAT_DIGIT_REGION = (405, 78, 18, 20)
SHOP_REGION = (235, 215, 665, 365)


def normalize_purchases(task):
    """Absent lists get the shared default; an explicitly empty list stays empty."""
    rows = task.get("soul_purchases", DEFAULT_PURCHASES)
    if not isinstance(rows, list):
        rows = DEFAULT_PURCHASES
    out = []
    for row in rows:
        if not isinstance(row, dict) or row.get("item") not in SOUL_ITEMS:
            continue
        try:
            target = max(0, int(row.get("target", 1)))
        except (ValueError, TypeError):
            continue
        out.append({"item": row["item"], "trigger": "heat" if row.get("trigger") == "heat" else "wave",
                    "target": target})
    return out


@lru_cache(maxsize=1)
def _heat_references():
    references = []
    for level in range(10):
        name = f"soul_heat_{level}"
        path = Path(vision.UI_ASSETS_DIR) / name / (name+".png")
        if path.is_file():
            gray = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            references.append((level, cv2.inRange(gray, 205, 255)))
    return references


def read_heat(frame):
    """Read only the completed Heat Bars digit, never the fill's souls fraction."""
    x, y, w, h = HEAT_DIGIT_REGION
    digit = frame[y:y+h, x:x+w]
    if digit.size == 0:
        return None
    gray = cv2.cvtColor(digit, cv2.COLOR_BGR2GRAY)
    mask = cv2.inRange(gray, 205, 255)
    scores = sorted(((float(cv2.matchTemplate(mask, reference, cv2.TM_CCOEFF_NORMED)[0, 0]), level)
                     for level, reference in _heat_references()), reverse=True)
    if scores and scores[0][0] >= 0.88 and (len(scores) == 1 or scores[0][0]-scores[1][0] >= 0.06):
        return scores[0][1]
    # OCR works for levels without a supplied reference too (including level 2).
    big = cv2.resize(255-mask, None, fx=12, fy=12, interpolation=cv2.INTER_NEAREST)
    big = cv2.copyMakeBorder(big, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    text = ocr.ocr_mask(ocr.get_pytesseract(), big,
                        "--psm 10 -c tessedit_char_whitelist=0123456789", whitelist="0123456789")
    return int(text) if re.fullmatch(r"\d{1,2}", text.strip()) else None


def runs_before_lobby(task):
    try:
        return max(0, int(task.get("runs_before_lobby", 0)))
    except (ValueError, TypeError):
        return 0


def lobby_batch_due(task, completed_in_visit):
    count = runs_before_lobby(task)
    return count > 0 and completed_in_visit >= count


class SoulFurnaceOps:
    def _soul_find(self, hwnd, name, region=None, frame=None):
        try:
            if frame is None:
                return vision.find_image(hwnd, name, region=region, threshold=0.86)
            crop = frame
            if region is not None:
                x, y, w, h = region
                crop = frame[y:y+h, x:x+w]
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            match = vision.find_in_gray_multiscale(
                gray, name, threshold=vision._effective_threshold(name, 0.86))
            if match is not None and region is not None:
                match = dict(match)
                for key in ("x", "cx"):
                    match[key] += region[0]
                for key in ("y", "cy"):
                    match[key] += region[1]
            return match
        except vision.TemplateNotFound:
            return None

    def _soul_click(self, hwnd, x, y):
        self._hover_click(*vision.ref_to_screen(hwnd, x, y), hwnd)

    def _reach_soul_furnace(self, hwnd, stop_event):
        if not self._ensure_lobby(hwnd, stop_event):
            return False
        for name, label in (("nav_event", "Events"),
                            ("soul_halloween_event", "Halloween Event"),
                            ("soul_event_gamemode", "Event Gamemode")):
            self._set_status(action=f"Soul Furnace -- opening {label}...")
            if self._click_found_image(hwnd, name, EVENT_SCREEN_TIMEOUT, stop_event) is None:
                return False
            self._interruptible_sleep(0.5, stop_event)
            if self._checkpoint(stop_event):
                return False
        # The shared entry tail verifies Select Stage, clicks Start, and waits
        # for Unit Manager in the actual match before any battle work runs.
        return True

    def _soul_result(self, hwnd, frame=None):
        if frame is None:
            frame = vision.capture_game_bgr(hwnd)
        if frame is None:
            return None
        for name, result in (("soul_victory", "win"), ("victory", "win"), ("defeat", "loss")):
            if self._soul_find(hwnd, name, frame=frame):
                return result
        return None

    def _soul_close_shop(self, hwnd, stop_event=None):
        """Confirm the shop disappeared; retry a dropped close click, never reopen it."""
        for _ in range(3):
            if stop_event is not None and self._checkpoint(stop_event):
                return False
            if not self._soul_find(hwnd, "soul_forge", region=(190, 150, 740, 70)):
                return True
            self._soul_click(hwnd, 907, 186)
            if stop_event is None:
                time.sleep(0.3)
            else:
                self._interruptible_sleep(0.3, stop_event)
        if stop_event is not None and self._checkpoint(stop_event):
            return False
        return not self._soul_find(hwnd, "soul_forge", region=(190, 150, 740, 70))

    def _soul_read_souls(self, hwnd, frame=None):
        crop = (frame[183:203, 815:849] if frame is not None else
                vision.capture_window_region_bgr(hwnd, (815, 183, 34, 20)))
        if crop is None:
            return None
        big = cv2.resize(crop, None, fx=8, fy=8, interpolation=cv2.INTER_LANCZOS4)
        text = ocr.ocr_mask(ocr.get_pytesseract(), big,
                            "--psm 7 -c tessedit_char_whitelist=0123456789", whitelist="0123456789")
        return int(text) if re.fullmatch(r"\d+", text.strip()) else None

    def _soul_purchase_attempt(self, hwnd, stop_event, item_id):
        """One bounded attempt. Never treat a click alone as a completed purchase."""
        if self._checkpoint(stop_event) or self._soul_result(hwnd):
            return False
        self._release_quick_place_shift()
        if not self._soul_find(hwnd, "soul_forge", region=(190, 150, 740, 70)):
            self._soul_click(hwnd, 576, 606)  # Forge button from the supplied 1152x756 capture
            for _ in range(8):
                self._interruptible_sleep(0.1, stop_event)
                if self._checkpoint(stop_event):
                    return False
                if self._soul_find(hwnd, "soul_forge", region=(190, 150, 740, 70)):
                    break
        if not self._soul_find(hwnd, "soul_forge", region=(190, 150, 740, 70)):
            return False
        # Every supplied catalog entry belongs to Tier I. Reset the list so
        # a preceding purchase's scroll position cannot select another item.
        self._soul_click(hwnd, 681, 193)
        self._mouse.move_to(*vision.ref_to_screen(hwnd, 870, 400))
        self._mouse.nudge()
        self._interruptible_sleep(0.05, stop_event)
        self._mouse.scroll(120 * 60)
        self._interruptible_sleep(SHOP_SCROLL_SETTLE, stop_event)
        item = SOUL_ITEMS[item_id]
        for _ in range(18):
            if self._checkpoint(stop_event):
                return False
            frame = vision.capture_game_bgr(hwnd)
            if frame is None:
                return False
            # Searching every Victory/Defeat variant over the full frame on
            # each scroll consumed seconds per step. The visible Forge header
            # proves we are still shopping; only check results if it disappears.
            if not self._soul_find(hwnd, "soul_forge", (190, 150, 740, 70), frame=frame):
                return False
            found = self._soul_find(hwnd, item["image"], region=SHOP_REGION, frame=frame)
            if found:
                buy_x = found["cx"]
                buy_y = found["y"] + item["buy_dy"]
                # A clipped card's buy button must be scrolled fully into view.
                if buy_y > 558:
                    self._mouse.scroll(-120)
                    self._interruptible_sleep(SHOP_SCROLL_SETTLE, stop_event)
                    continue
                # A shorter scroll settle must not turn a moving card into
                # a click on its neighbor. Confirm the target stopped moving.
                self._interruptible_sleep(0.05, stop_event)
                if self._checkpoint(stop_event):
                    return False
                stable_frame = vision.capture_game_bgr(hwnd)
                if stable_frame is None:
                    continue
                stable = self._soul_find(hwnd, item["image"], region=SHOP_REGION, frame=stable_frame)
                if (stable is None or abs(stable["cx"]-found["cx"]) > 2
                        or abs(stable["y"]-found["y"]) > 2):
                    continue
                found, frame = stable, stable_frame
                buy_x, buy_y = found["cx"], found["y"]+item["buy_dy"]
                if item_id == "final_boss" and (
                        self._soul_find(hwnd, "soul_final_boss_forging", SHOP_REGION, frame=frame)
                        or self._soul_find(hwnd, "soul_final_boss_timer", (630, 582, 150, 45), frame=frame)):
                    return False
                button = frame[max(0, int(buy_y)-9):int(buy_y)+9,
                               max(0, int(buy_x)-50):int(buy_x)+50]
                if button.size == 0:
                    return False
                hsv = cv2.cvtColor(button, cv2.COLOR_BGR2HSV)
                green = cv2.inRange(hsv, np.array([30, 90, 70]), np.array([95, 255, 255]))
                if np.mean(green > 0) < 0.12:
                    return False  # locked, unavailable, or not enough souls
                before = None if item_id == "final_boss" else self._soul_read_souls(hwnd, frame=frame)
                self._soul_click(hwnd, buy_x, buy_y)
                for _ in range(20):
                    self._interruptible_sleep(SHOP_CONFIRM_INTERVAL, stop_event)
                    if self._checkpoint(stop_event):
                        return False
                    frame = vision.capture_game_bgr(hwnd)
                    if frame is None:
                        continue
                    if not self._soul_find(hwnd, "soul_forge", (190, 150, 740, 70), frame=frame):
                        return bool(self._soul_result(hwnd, frame=frame))
                    if item_id == "final_boss":
                        if (self._soul_find(hwnd, "soul_final_boss_forging", SHOP_REGION, frame=frame)
                                or self._soul_find(hwnd, "soul_final_boss_timer", (630, 582, 150, 45), frame=frame)):
                            return True
                    elif before is not None:
                        after = self._soul_read_souls(hwnd, frame=frame)
                        if after is not None and after < before:
                            return True
                return False
            self._mouse.move_to(*vision.ref_to_screen(hwnd, 870, 400))
            self._mouse.nudge()
            if _ == 0:
                self._log("[Soul Forge] Scrolling down to the requested item.")
            self._mouse.scroll(-120 * 2)
            self._interruptible_sleep(SHOP_SCROLL_SETTLE, stop_event)
        return False

    def _soul_tick(self, hwnd, stop_event, task, state):
        """Poll confirmed thresholds; each configured row runs at most once per match."""
        frame = vision.capture_game_bgr(hwnd)
        if frame is None:
            return None
        result = self._soul_result(hwnd, frame=frame)
        if result:
            return result
        if state.get("shop_close_pending"):
            if not self._soul_close_shop(hwnd, stop_event):
                return "shop_open"
            state.pop("shop_close_pending", None)
        now = time.monotonic()
        if now < state.get("next_check", 0):
            return None
        x, y, w, h = WAVE_REGION
        heat = read_heat(frame)
        current, maximum = wave.read_wave(frame[y:y+h, x:x+w])
        if self._checkpoint(stop_event):
            return None
        state["next_check"] = time.monotonic() + SOUL_POLL_INTERVAL
        for key, value in (("wave", current if maximum is None else None), ("heat", heat)):
            if value is None:
                state[key+"_confirmations"] = 0
                continue
            state[key+"_confirmations"] = (state.get(key+"_confirmations", 0) + 1
                                            if state.get(key) == value else 1)
            state[key] = value
        self._set_status(action=f"Soul Furnace -- wave {current if current is not None else '?'} | Heat Bars {heat if heat is not None else '?'}")
        if current == 30:
            state["wave30_seen"] = True
        # Wait for wave 31: leaving on the first wave-30 frame would abandon it.
        if (current is not None and maximum is None and current >= 31
                and (current == 31 or state.get("wave30_seen"))
                and state.get("wave_confirmations", 0) >= 2):
            if not self._soul_close_shop(hwnd, stop_event):
                state["shop_close_pending"] = True
                return "shop_open"
            self._log("[Soul Furnace] Wave 30 completed -- using the top-bar lobby button.")
            if self._click_and_verify_gone(hwnd, stop_event, "soul_to_lobby", NAV_CLICK_TIMEOUT,
                                           success_name="return"):
                self._click_return_to_lobby_if_found(hwnd, stop_event)
                return "wave_limit" if not self._checkpoint(stop_event) else None
            return None  # retry the exit on the next tick, rather than restarting the task
        if state.get("skip_remaining"):
            return None
        completed = state.setdefault("completed", set())
        for index, row in enumerate(normalize_purchases(task)):
            trigger = row["trigger"]
            if (index in completed or state.get(trigger) is None
                    or state.get(trigger+"_confirmations", 0) < 2
                    or state[trigger] < row["target"]):
                continue
            self._log(f'[Soul Forge] {SOUL_ITEMS[row["item"]]["label"]} due at {trigger} {row["target"]}.')
            try:
                for attempt in range(1, MAX_PURCHASE_ATTEMPTS+1):
                    if self._checkpoint(stop_event):
                        return None
                    self._log(f"[Soul Forge] Purchase attempt {attempt}/{MAX_PURCHASE_ATTEMPTS}.")
                    if self._soul_purchase_attempt(hwnd, stop_event, row["item"]):
                        completed.add(index)
                        self._log("[Soul Forge] Purchase confirmed.")
                        break
                    if self._soul_result(hwnd):
                        return self._soul_result(hwnd)
                    if attempt < MAX_PURCHASE_ATTEMPTS:
                        self._interruptible_sleep(PURCHASE_RETRY_SECONDS, stop_event)
                else:
                    state["skip_remaining"] = True
                    self._soul_task_purchase_failed = True
                    self._log("[Soul Forge] Five attempts failed -- no more purchases or task repeats; waiting for this match to end (or wave 30 to complete), then continuing the queue.")
            finally:
                if not stop_event.is_set():
                    if not self._soul_close_shop(hwnd, stop_event):
                        state["shop_close_pending"] = True
                        self._log("[Soul Forge] Shop is still open -- retrying closure before continuing battle actions.")
            if state.get("shop_close_pending"):
                return "shop_open"
            # Return to normal battle/loop processing between purchases.
            return None
        return None
