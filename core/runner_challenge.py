"""Regular Challenge: readiness/rotation windows, the pre-queue pass, entering and
playing the 3 stage slots.

Split out of core/runner.py mechanically -- a mixin providing part of
MacroRunner's behavior (see core/runner.py, which composes the mixins).
Methods here run with MacroRunner's full self: shared state and helpers
(_log, _coords, _checkpoint, _click_found_image, ...) resolve normally.
"""
import difflib
import os
import re
import threading
import time

import cv2

from . import ocr
from . import vision

# Daily Challenge availability. The two states are one card, so these are
# read as a COMPARISON, never as a single hit -- see
# _enter_daily_challenge_stage.
#   LOOSE      the "is it worth looking at" bar for either state
#   CONFIDENT  what the greyed-out state must score to skip the day ALONE
#   MARGIN     how far ahead it must be when both states match
DAILY_STATE_LOOSE_THRESHOLD = 0.75
DAILY_UNAVAILABLE_CONFIDENT = 0.88
DAILY_STATE_MARGIN = 0.05
from . import ocr_windows
from . import window as wm
from .runner_constants import *  # noqa: F401,F403 -- the shared constants namespace


class ChallengeOps:
    def _detect_current_challenge_map(self, hwnd) -> str:
        """Regular Challenge is Story's own flow with the game picking a
        random one of CHALLENGE_STORY_MAPS for you -- this is the "which one
        did it land on" check, tried against each map's reference image
        (Assets/ui/<map>.png, a different purpose from Assets/maps/<map>.png's
        map-CARD search) in turn. Returns the matched map name, or None if
        none of them were found (not yet on a recognizable Challenge screen,
        or the wrong screen entirely)."""
        try:
            match, map_name = vision.find_image_any(hwnd, CHALLENGE_STORY_MAPS)
        except vision.TemplateNotFound:
            return None
        if match is not None:
            debug_path = self._debug_save(hwnd, map_name, match)
            suffix = f" Debug: {debug_path}" if debug_path else ""
            self._log(f'[Macro] Challenge map detected: "{map_name}" (score {match["score"]:.2f}).{suffix}')
            return map_name
        return self._detect_challenge_map_ocr(hwnd)

    def _report_challenge_map_miss(self, hwnd, label: str) -> None:
        """Say WHY the map search came up empty, and keep the frame.

        "never recognized a map -- stopping" is the least actionable line in
        the log: it cannot distinguish "the art is close but under
        threshold" (a re-cut fixes it) from "nothing on this screen looks
        remotely like a map" (we are not where we think we are) from "OCR is
        missing entirely". All three have happened. So on the way out, run
        ONE more pass at a deliberately generous threshold and print the
        best score each map actually reached, then write the frame to
        debug/ -- unconditionally, not behind the Debug Screenshots toggle,
        because this path already ends the run and one PNG per stopped run
        is not the flood that toggle exists to prevent.
        """
        try:
            best = []
            haystack = vision.capture_game_gray(hwnd)
            if haystack is not None:
                for map_name in CHALLENGE_STORY_MAPS:
                    try:
                        vision.load_template_grays(map_name)
                    except vision.TemplateNotFound:
                        best.append(f"{map_name}: no reference image")
                        continue
                    # The diagnostic matcher, not the polling one: it reports
                    # the strongest candidate across every variant and scale
                    # even when nothing clears threshold, which is the whole
                    # point of asking here.
                    probe = vision.find_in_gray_multiscale_diagnostic(haystack, map_name)
                    top = probe.get("best")
                    best.append(f"{map_name}: {top['score']:.2f}" if top
                                else f"{map_name}: no score")
            if best:
                self._log(f"[Macro] {label}: best map scores this frame -- " + "; ".join(best))
        except Exception as exc:
            self._log(f"[Macro] {label}: couldn't score the map templates ({exc}).")
        try:
            frame = vision.capture_game_bgr(hwnd)
            if frame is not None:
                os.makedirs(vision.DEBUG_DIR, exist_ok=True)
                path = os.path.join(
                    vision.DEBUG_DIR,
                    f"challenge_map_miss_{time.strftime('%Y%m%d_%H%M%S')}.png")
                cv2.imwrite(path, frame)
                self._log(f"[Macro] {label}: saved the unrecognized screen to {path}")
        except Exception as exc:
            self._log(f"[Macro] {label}: couldn't save the map-miss frame ({exc}).")

    def _challenge_map_ocr_crops(self, frame):
        """Daily Challenge map label crops, HUD-anchored first and fixed relative fallback second."""
        crops = []
        try:
            hud_match = vision.find_in_gray_multiscale(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), "daily_challenge_hud")
        except vision.TemplateNotFound:
            hud_match = None
        if hud_match is not None:
            x = max(0, hud_match["x"] + hud_match["w"] - 5)
            y = max(0, hud_match["y"] - 7)
            crop = frame[y:min(frame.shape[0], y + 43), x:frame.shape[1]]
            if crop.size:
                crops.append(crop)

        # MEASURED off a real Regular Challenge frame
        # (debug/challenge_map_miss_20260907_044327.png), not guessed. The
        # label is one right-aligned line -- "<icon> Regular Challenge #1
        # Flower Forest - Act 2" -- sitting at y 322-350, x 860 to the right
        # edge in reference space (1152x756).
        #
        # The old fallback band (x 0.58-0.98, y 0.42-0.52) is 461x76: it
        # contains the label, but also about 100px of grass, tree and rock
        # around it, and Tesseract reads that as noise. Measured on that one
        # frame, side by side: the old band's best read is
        #   "@-= ad -_ | 86 Ss 7 | _ 7 ~ 45 = @ Recnilar Challenae #1 Flower Forest - Ac"
        # while the band below reads "Flower Forest" cleanly on EVERY
        # variant and both PSM modes. Same OCR, same frame -- the crop was
        # the whole problem, and it is why "never recognized a map" happened
        # on a screen where the map name is plainly written.
        #
        # Right edge is the frame's own, not 0.98w: the label is flush to it,
        # and 0.98 clipped "Act 2" off.
        h, w = frame.shape[:2]
        x1 = max(0, int(w * CHALLENGE_MAP_LABEL_BAND[0]))
        y1 = max(0, int(h * CHALLENGE_MAP_LABEL_BAND[1]))
        y2 = min(h, int(h * CHALLENGE_MAP_LABEL_BAND[2]))
        band = frame[y1:y2, x1:w]
        if band.size:
            crops.append(band)
        return crops

    def _detect_challenge_map_ocr(self, hwnd) -> str:
        """Fallback for the tiny Daily Challenge map label shown in-game."""
        frame = vision.capture_game_bgr(hwnd)
        if frame is None:
            return None

        aliases = CHALLENGE_MAP_OCR_ALIASES

        try:
            pytesseract = ocr.get_pytesseract()
        except ocr.TesseractNotAvailable:
            pytesseract = None

        for crop in ChallengeOps._challenge_map_ocr_crops(self, frame):
            # The raw glyphs are only around 10px tall. Color upscaling preserves
            # their white fill and dark outline better than a global threshold.
            candidates = [
                cv2.resize(crop, None, fx=8, fy=8, interpolation=cv2.INTER_CUBIC),
                cv2.resize(crop, None, fx=8, fy=8, interpolation=cv2.INTER_LANCZOS4),
            ]
            candidates.extend(ocr.candidate_masks(crop, upscale=8))
            texts = []
            for candidate in candidates:
                # BOTH psm modes. 7 is "one line", which is what this band is
                # -- but a band that catches a pixel of the row above or
                # below stops being one line to Tesseract, and psm 6 ("a
                # block") reads it where 7 returns noise. Measured on the two
                # saved miss frames: psm 7 alone gets "inrChallende #2 Kins
                # TOBAGO" off the King's Tomb screen while psm 6 on the same
                # image reads "Reguiar, Challenge #2 King's Tomb - Act 4".
                for psm in CHALLENGE_MAP_OCR_PSM_MODES:
                    text = ocr.ocr_mask(pytesseract, candidate, f"--psm {psm}")
                    if text:
                        texts.append(text)
            # Score EVERY read and take the best, rather than returning on
            # the first one that clears the bar. Order was doing real damage:
            # on the King's Tomb frame an early garbage read scores 0.75
            # ("toba" against "tomb") and cleared, while a later read of the
            # actual label scores 1.00. First-past-the-post picked the fluke;
            # best-of picks the one that is obviously right, and a fluke can
            # now only win when nothing better exists.
            ranked = []
            for text in texts:
                tokens = [t for t in re.findall(r"[a-z]+", text.lower())
                          if t not in CHALLENGE_MAP_OCR_STOPWORDS
                          and len(t) >= CHALLENGE_MAP_OCR_MIN_TOKEN]
                if not tokens:
                    continue
                scores = sorted(
                    (
                        max((difflib.SequenceMatcher(None, alias, token).ratio() for token in tokens), default=0),
                        map_name,
                    )
                    for map_name, alias in aliases.items()
                )
                best_score, best_map = scores[-1]
                runner_up = scores[-2][0]
                ranked.append((best_score - runner_up, best_score, best_map, text))
            if not ranked:
                continue
            ranked.sort(reverse=True)
            margin, best_score, best_map, text = ranked[0]
            if best_score >= CHALLENGE_MAP_OCR_MIN_SCORE and margin >= CHALLENGE_MAP_OCR_MARGIN:
                self._log(f'[Macro] Challenge map OCR: "{text.strip()}" -> "{best_map}" '
                          f'(score {best_score:.2f}, margin {margin:.2f}).')
                return best_map
        return None

    def _challenge_has_ready_stage(self) -> bool:
        """Quick side-effect-free check for whether Challenge automation
        has at least one enabled, not-yet-capped stage slot ready to run
        right now -- used by _run_task's repeat loop to decide whether to
        pause a task's repeats and go run Challenge before continuing
        (see challenge_wants_in there), not just once at the very start of
        a Start press. Same enabled/cap/ready checks _run_challenges itself
        makes per slot, just without actually running anything."""
        if self._get_challenge_settings is None:
            return False
        try:
            challenge = self._get_challenge_settings()
        except Exception:
            return False
        daily = challenge.get("daily") or {}
        if daily.get("enabled") and daily.get("ready"):
            return True
        if not challenge.get("enabled"):
            return False
        cap = challenge.get("cap", 0)
        for slot in CHALLENGE_STAGE_SLOTS:
            info = challenge.get("stages", {}).get(slot) or {}
            if not info.get("enabled"):
                continue
            if cap and info.get("count", 0) >= cap:
                continue
            if info.get("ready"):
                return True
        return False

    def _run_challenges(self, hwnd, stop_event: threading.Event, coords: dict,
                          default_walk_paths: dict, webhook: dict) -> None:
        """Runs a ready Daily Challenge first, then every ready Regular
        Challenge stage slot once each in #1/#2/#3 order. Called before
        the Task Queue ever
        starts (see _run), AND again between repeats of an in-progress
        task whenever _challenge_has_ready_stage says a slot's ready (see
        _run_task's repeat loop), not just that one time at the start
        anymore. Challenge is Story's own flow with the
        game picking a random one of CHALLENGE_STORY_MAPS for you instead
        of you picking it, so the actual battle (Pre Start, Start Game,
        Victory/Defeat) reuses _play_one_match/_handle_match_result
        unchanged via a synthetic Story-shaped task -- see
        _run_one_challenge_stage."""
        if self._get_challenge_settings is None:
            return
        try:
            challenge = self._get_challenge_settings()
        except Exception as exc:
            self._log(f"[Macro] Couldn't read Challenge settings: {exc}")
            return
        daily = challenge.get("daily") or {}
        if not challenge.get("enabled") and not daily.get("enabled"):
            return

        self._log("[Macro] Challenge is enabled -- running any ready stage(s) before the Task Queue...")
        if daily.get("enabled") and daily.get("ready"):
            play_mode = challenge.get("play_mode") or "solo"
            result = self._run_one_daily_challenge(
                hwnd, stop_event, play_mode, challenge, coords, default_walk_paths, webhook)
            if self._checkpoint(stop_event):
                return
            if result in ("win", "unavailable"):
                # The gray Unavailable state is the game's source of truth:
                # it means this account cannot claim Daily Challenge again
                # until the shared daily reset, even if local state was lost.
                self._mark_challenge_stage_played("daily")
            elif result == "loss":
                self._log("[Macro] Daily Challenge was a loss -- leaving it ready for another attempt today.")
            else:
                self._log("[Macro] Daily Challenge didn't complete cleanly -- recovering to the lobby.")
                if not self._recover_failed_challenge(hwnd, stop_event):
                    return

        # Daily can be enabled independently of the rotating Regular slots.
        if not challenge.get("enabled"):
            # Every exit from a Challenge pass goes through Leave Stage +
            # Return to Lobby, so the lobby is where the Task Queue starts --
            # even when this pass ran no stage at all. Told to
            # _reach_portal_activated explicitly: on this setup the lobby can
            # still be drawing 13s later, and a Portals task that mistook it
            # for a post-run screen clicked the chooser's calibrated point
            # into empty ground three times and stopped the farm. See
            # 0.31.5's known bug.
            self._portal_expect_lobby = True
            self._log("[Macro] Challenge pass finished -- moving on to the Task Queue.")
            return

        cap = challenge.get("cap", 0)
        # Freeze this pass's ordered work before starting it. All regular
        # slots share one :00/:30 readiness window; repeatedly deciding the
        # work between battles could otherwise let a boundary or settings
        # refresh turn a 1 -> 2 -> 3 interruption into several one-slot
        # interruptions. Once we leave a task for Challenge, finish every
        # slot that was eligible at that point, in numeric order, before
        # returning to the task.
        pending_slots = []
        for slot in CHALLENGE_STAGE_SLOTS:
            info = challenge.get("stages", {}).get(slot) or {}
            if not info.get("enabled"):
                continue
            if cap and info.get("count", 0) >= cap:
                self._log(f'[Macro] Challenge #{slot} is at today\'s cap ({cap}) -- skipping.')
                continue
            if not info.get("ready"):
                self._log(f'[Macro] Challenge #{slot} already played this window -- skipping.')
                continue
            pending_slots.append(slot)

        for slot in pending_slots:
            if self._checkpoint(stop_event):
                return
            # Refresh map/mode configuration, but do not re-decide the slot
            # list: completing 1 must lead to 2 then 3 from this same pass.
            try:
                challenge = self._get_challenge_settings()
            except Exception as exc:
                self._log(f"[Macro] Couldn't read Challenge settings: {exc}")
                return

            play_mode = challenge.get("play_mode") or "solo"
            result = self._run_one_challenge_stage(hwnd, stop_event, slot, play_mode, challenge, coords,
                                                     default_walk_paths, webhook)
            if self._checkpoint(stop_event):
                return
            if result == "win":
                self._mark_challenge_stage_played(slot)
            elif result == "loss":
                # A loss starts the same until-next-window cooldown a win
                # does -- the slot's rotated-in stage won't have changed
                # within this window, so an immediate retry just feeds it
                # the same losing matchup again -- but count_play=False
                # keeps it from eating one of the day's capped plays the
                # way a real completion does. The match already ran its
                # normal Leave Stage + Return to Lobby (see
                # _handle_match_result), so there's nothing left to
                # recover from here.
                self._mark_challenge_stage_played(slot, False)
                self._log(f'[Macro] Challenge #{slot} was a loss -- resting it until the next '
                           f':00/:30 window (daily count not used).')
            else:
                self._log(f'[Macro] Challenge #{slot} didn\'t complete cleanly -- recovering to the lobby.')
                if not self._recover_failed_challenge(hwnd, stop_event):
                    return

        # Every exit from a Challenge pass goes through Leave Stage +
        # Return to Lobby, so the lobby is where the Task Queue starts --
        # even when this pass ran no stage at all. Told to
        # _reach_portal_activated explicitly: on this setup the lobby can
        # still be drawing 13s later, and a Portals task that mistook it
        # for a post-run screen clicked the chooser's calibrated point
        # into empty ground three times and stopped the farm. See
        # 0.31.5's known bug.
        self._portal_expect_lobby = True
        self._log("[Macro] Challenge pass finished -- moving on to the Task Queue.")

    def _recover_failed_challenge(self, hwnd, stop_event: threading.Event) -> bool:
        """Prefer the direct stage exit, then fall back to generic recovery."""
        if not self._click_and_verify_gone(
                hwnd, stop_event, "leave_stage", NAV_CLICK_TIMEOUT, success_name="return"):
            return self._recover_to_lobby(hwnd, stop_event)
        self._click_return_to_lobby_if_found(hwnd, stop_event)
        return not self._checkpoint(stop_event)

    def _run_one_challenge_stage(self, hwnd, stop_event: threading.Event, slot: str, play_mode: str,
                                   challenge: dict, coords: dict, default_walk_paths: dict,
                                   webhook: dict) -> str:
        """Returns "win", "loss", or None -- None covers both a genuine
        technical failure (never got into the stage, map never recognized,
        etc.) AND the run being stopped mid-way, same as _play_one_match's
        own result convention. Callers (_run_challenges) put the slot on
        its until-next-window cooldown for BOTH "win" and "loss" (a loss
        just doesn't consume a daily-cap count -- see
        mark_challenge_stage_played's count_play); only None leaves the
        slot ready, so a technical failure can be retried this window."""
        progress_task = {
            "mode": "challenge", "map": f"Challenge #{slot}",
            "stage": str(slot), "play_mode": play_mode,
        }
        self._send_progress_webhook(
            webhook,
            progress_task,
            f"Challenge #{slot} Started",
            f"Starting Challenge #{slot} ({play_mode}).",
            0x5865F2,
            extra_fields=[{"name": "Play Mode", "value": play_mode, "inline": True}],
            current_action=f"Challenge #{slot} -- entering ({play_mode})",
            next_phase="Identify the assigned map, then start the battle",
        )
        self._log(f"[Macro] Challenge #{slot}: entering ({play_mode})...")
        self._set_status(current_task=f"Challenge #{slot}", map="-", action="Entering Challenge...",
                          mode="challenge", stage="-", difficulty="-", play_mode=play_mode, macro="-")
        result = None
        try:
            if not self._enter_challenge_stage(hwnd, stop_event, slot, play_mode, coords, webhook):
                return None
            if self._checkpoint(stop_event):
                return None
            result = self._run_challenge_battle(
                hwnd, stop_event, f"Challenge #{slot}", play_mode, challenge, default_walk_paths, webhook)
            return result
        finally:
            self._send_challenge_progress_finished(
                webhook, progress_task, f"Challenge #{slot}", play_mode, result, stop_event)

    def _run_one_daily_challenge(self, hwnd, stop_event: threading.Event, play_mode: str,
                                  challenge: dict, coords: dict, default_walk_paths: dict,
                                  webhook: dict) -> str:
        progress_task = {
            "mode": "challenge", "map": "Daily Challenge",
            "stage": "Daily", "play_mode": play_mode,
        }
        self._send_progress_webhook(
            webhook,
            progress_task,
            "Daily Challenge Started",
            f"Starting Daily Challenge ({play_mode}).",
            0x5865F2,
            extra_fields=[{"name": "Play Mode", "value": play_mode, "inline": True}],
            current_action=f"Daily Challenge -- entering ({play_mode})",
            next_phase="Identify the assigned map, then start the battle",
        )
        self._log(f"[Macro] Daily Challenge: entering ({play_mode})...")
        self._set_status(current_task="Daily Challenge", map="-", action="Entering Daily Challenge...",
                          mode="challenge", stage="Daily", difficulty="-", play_mode=play_mode, macro="-")
        result = None
        try:
            entry = self._enter_daily_challenge_stage(hwnd, stop_event, play_mode, coords, webhook)
            if entry != "entered":
                result = entry
                return entry
            if self._checkpoint(stop_event):
                return None
            result = self._run_challenge_battle(
                hwnd, stop_event, "Daily Challenge", play_mode, challenge, default_walk_paths, webhook)
            return result
        finally:
            self._send_challenge_progress_finished(
                webhook, progress_task, "Daily Challenge", play_mode, result, stop_event)

    def _send_challenge_progress_finished(self, webhook: dict, task: dict, label: str,
                                           play_mode: str, result: str,
                                           stop_event: threading.Event) -> None:
        if result == "win":
            status, color = "Victory", 0x3FBF6F
        elif result == "loss":
            status, color = "Defeat", 0xE05A6D
        elif result == "unavailable":
            status, color = "Unavailable", 0xE8935A
        elif stop_event.is_set():
            status, color = "Stopped", 0xE8935A
        else:
            status, color = "Failed", 0xE05A6D
        self._send_progress_webhook(
            webhook,
            task,
            f"{label} Finished",
            f"{label} finished: **{status}**.",
            color,
            extra_fields=[
                {"name": "Status", "value": status, "inline": True},
                {"name": "Play Mode", "value": play_mode, "inline": True},
            ],
            current_action=f"{label} -- {status}",
            next_phase=self._next_challenge_progress(),
        )

    def _run_challenge_battle(self, hwnd, stop_event: threading.Event, label: str, play_mode: str,
                               challenge: dict, default_walk_paths: dict, webhook: dict) -> str:
        """Identify the assigned Story map and run the shared battle flow."""
        self._log(f"[Macro] {label}: identifying the map...")
        self._set_status(action="Identifying Challenge map...")
        deadline = time.time() + CHALLENGE_MAP_DETECT_TIMEOUT
        detected_map = None
        while time.time() < deadline:
            if self._checkpoint(stop_event):
                return None
            detected_map = self._detect_current_challenge_map(hwnd)
            if detected_map:
                break
            time.sleep(MATCH_RESULT_POLL_INTERVAL)
        if not detected_map:
            # NOT fatal any more. Identifying the map only ever decided WHICH
            # Macro Operation to run; it was never a precondition for playing
            # the round, and the round is what the user actually wants. This
            # single `return None` is why Auto Challenge "broke" between the
            # build where it worked flawlessly and this one -- a stage that
            # was entered, loaded and playable got abandoned on the spot,
            # which then dropped the run into the leave/rejoin path and took
            # the rest of the session down with it.
            #
            # Unrecognized now means "no macro assigned", which the line below
            # already knows how to handle: play it on Auto Play. That is the
            # same fallback an unassigned map gets, and it is strictly better
            # than stopping.
            self._log(f"[Macro] {label}: couldn't tell which map this is -- "
                       "playing it on Auto Play instead of stopping.")
            self._report_challenge_map_miss(hwnd, label)
            detected_map = ""
            macro_name = ""
            want_autoplay = True
        else:
            map_cfg = challenge.get("maps", {}).get(detected_map) or {}
            macro_name = map_cfg.get("macro") or ""
            # Auto Play is its OWN per-map setting now, not something inferred
            # from whether a macro is assigned. Those two were entangled, and
            # the entanglement is what forced people to write a template whose
            # only job was to click the Auto Play button in Pre Start -- which
            # then fought _ensure_autoplay on every entry, one turning it off
            # and the other back on. A map can legitimately want its walk path
            # and unit placements AND want the game to play the round.
            #
            # No macro still implies Auto Play: something has to play it.
            want_autoplay = not macro_name
            # A macro NAMED here but missing from disk (renamed, deleted,
            # imported from someone else's build) used to be a setup error
            # that refused to enable Auto Challenge at all. Now it is just
            # another map with nothing to run it, which has an obvious
            # answer: drop the dead name and let Auto Play play it. Silently
            # entering with no blocks and no Auto Play was the one outcome
            # nobody wanted.
            if macro_name and not self._macro_is_usable(macro_name):
                self._log(f'[Macro] {label}: "{detected_map}" is assigned the macro '
                          f'"{macro_name}", which no longer exists (or has no blocks) -- '
                          "running it on Auto Play instead.")
                macro_name = ""
                want_autoplay = True
            if macro_name:
                self._log(f'[Macro] {label} landed on "{detected_map}" -- running "{macro_name}"'
                          + (" with Auto Play on." if want_autoplay else "."))
            else:
                self._log(f'[Macro] {label} landed on "{detected_map}" -- no Macro Operation '
                          "assigned for it, playing it on Auto Play.")

        # mode="story" (not "challenge") deliberately -- this reuses the
        # EXACT SAME Pre Start/Start Game/Victory-Defeat pipeline a real
        # Story task uses (see _play_one_match/_handle_match_result), since
        # that's genuinely what Challenge's own battle is. is_challenge is
        # the marker other code checks when it actually needs to tell the
        # two apart.
        is_daily = label == "Daily Challenge"
        task = {
            "mode": "story", "is_challenge": True, "is_daily_challenge": is_daily,
            "map": detected_map, "difficulty": "Hard" if is_daily else "Normal",
            "macro": macro_name, "play_mode": play_mode, "repeat": 1, "team": "", "equipment": "include",
            # Was never set at all, and _settle_autoplay_for_match reads a
            # missing key as "off" -- so a Challenge map with no macro did not
            # merely run blockless, it got Auto Play switched OFF and nothing
            # played. It now comes from the map's own setting (see
            # want_autoplay above), with "no macro" still implying Auto Play.
            "auto_play": "autoplay" if want_autoplay else "macro",
        }
        self._set_status(map=detected_map or "?", action="Battle...",
                          difficulty=task["difficulty"], macro=macro_name or "-")
        battle_started = time.time()
        result = self._play_one_match(hwnd, stop_event, task, default_walk_paths, first_repeat=True,
                                        webhook=webhook)
        if result is None:
            return None
        duration = self._format_duration(time.time() - battle_started)

        # Challenge always leaves + returns to lobby afterward (repeat=
        # False) -- there's no "Repeat Stage" concept here, the next
        # attempt (if another slot is still ready) goes through the full
        # Challenge -> stage-slot navigation again, not a quick requeue.
        if not self._handle_match_result(hwnd, stop_event, task, result, duration, webhook, repeat=False):
            return None
        return None if self._checkpoint(stop_event) else result

    def _enter_challenge_stage(self, hwnd, stop_event: threading.Event, slot: str, play_mode: str, coords: dict,
                                 webhook: dict) -> bool:
        """Lobby -> Play -> Challenge -> stage slot #1/#2/#3 -> Solo/
        Matchmaking entry (through teleport-in) -- Regular Challenge's
        equivalent of _run_task_setup, except there's no map/difficulty to
        pick (the game assigns both at random), just a fixed-position
        stage row and a screen-load confirmation."""
        if not self._open_challenge_screen(hwnd, stop_event):
            return False

        if slot not in CHALLENGE_STAGE_SLOTS:
            self._log(f'[Macro] Unknown Challenge stage slot "{slot}".')
            return False
        x, y = self._cxy(f"challenge_stage_{slot}")
        self._log(f'[Macro] Challenge screen loaded -- clicking stage slot #{slot} at ({x}, {y}).')
        self._set_status(action=f"Clicking Challenge #{slot}...")
        left, top, _, _ = wm.get_window_rect_screen(hwnd)
        self._mouse.click(left + x, top + y)
        if self._checkpoint(stop_event):
            return False
        return self._enter_selected_challenge(hwnd, stop_event, play_mode, coords, webhook, daily=False)

    def _enter_daily_challenge_stage(self, hwnd, stop_event: threading.Event, play_mode: str,
                                      coords: dict, webhook: dict) -> str:
        """Enter Daily Challenge, or report its gray unavailable state."""
        if not self._open_challenge_screen(hwnd, stop_event):
            return None
        # Available and unavailable are the SAME card in two states, and a
        # loose bar cannot tell them apart on its own -- convention 3b. This
        # used to accept the first `unavailable` hit over 0.75 and skip the
        # whole day's daily on it; a real log shows it doing exactly that at
        # **0.78** on a day the daily was plainly available.
        #
        # So look for both and compare, and lean the tie toward TRYING. The
        # two mistakes are not equal: a wrong "unavailable" silently costs
        # the daily every single day and looks like normal operation, while a
        # wrong "available" costs one failed entry that the recovery path
        # already handles and logs.
        def _score(name):
            try:
                match = vision.find_image(hwnd, name, threshold=DAILY_STATE_LOOSE_THRESHOLD)
            except vision.TemplateNotFound:
                return None
            return match["score"] if match is not None else None

        try:
            unavailable_score = _score("daily_challenge_unavailable")
        except Exception as exc:  # pragma: no cover - defensive, as before
            self._log(f"[Macro] Can't check Daily Challenge availability: {exc}")
            return None
        available_score = _score("daily_challenge_available")

        skip_daily = False
        if unavailable_score is not None:
            if available_score is None:
                # Only the greyed-out state matched. Believe it, but only at
                # a real score -- 0.75 is a "look here" bar, not proof.
                skip_daily = unavailable_score >= DAILY_UNAVAILABLE_CONFIDENT
                if not skip_daily:
                    self._log(
                        f'[Macro] "daily_challenge_unavailable" matched at only '
                        f"{unavailable_score:.2f} and nothing says it IS available -- too weak "
                        "to skip a whole day on, so trying to enter it anyway.")
            else:
                # Both matched. Whichever scores higher wins, and it has to
                # win by a margin; a near-tie means neither template is
                # actually telling us anything.
                margin = unavailable_score - available_score
                skip_daily = margin >= DAILY_STATE_MARGIN
                self._log(
                    f"[Macro] Daily Challenge state: unavailable {unavailable_score:.2f} vs "
                    f"available {available_score:.2f} -- "
                    + ("skipping." if skip_daily else "too close to call, trying to enter it."))
        if skip_daily:
            self._log(
                f'[Macro] Daily Challenge is unavailable for this game day '
                f'(score {unavailable_score:.2f}) -- skipping.')
            # We opened a menu but did not enter a stage; return to the lobby
            # before Regular Challenge or the Task Queue continues.
            return "unavailable" if self._recover_to_lobby(hwnd, stop_event) else None

        self._set_status(action="Clicking Daily Challenge...")
        avail_match = self._click_found_image(
            hwnd, "daily_challenge_available", CHALLENGE_SCREEN_TIMEOUT, stop_event, threshold=0.75)
        if avail_match is None:
            if stop_event is not None and stop_event.is_set():
                return None
            # Fallback: click Daily Challenge tab on left sidebar
            tab_x, tab_y = self._cxy("daily_challenge_tab")
            self._log(f'[Macro] "daily_challenge_available" template missed -- using fallback tab click at ({tab_x}, {tab_y}).')
            left, top, _, _ = wm.get_window_rect_screen(hwnd)
            self._mouse.click(left + tab_x, top + tab_y)
            time.sleep(0.5)

        if self._checkpoint(stop_event):
            return None
        self._set_status(action="Selecting Daily Challenge stage...")
        stage_match = self._click_found_image(
            hwnd, "daily_challenge_stage", CHALLENGE_SCREEN_TIMEOUT, stop_event, threshold=0.75)
        if stage_match is None:
            if stop_event is not None and stop_event.is_set():
                return None
            # Fallback: click the stage card on the right panel.
            #
            # This deliberately reuses "Challenge: Stage Slot 1" rather than a
            # daily-only point. The Daily Challenge's single card sits in the
            # same place as the first card of the Regular Challenge's three, so
            # a separate coordinate was two things to keep calibrated that can
            # never legitimately differ -- and the daily one had no Settings
            # row, no entry in MACRO_COORD_DEFAULTS and no place in
            # MACRO_COORD_KEYS, so it could not be corrected without editing
            # code and rebuilding. Slot 1 is already on the Settings > Debug
            # page with a Pick button, so fixing one fixes both.
            card_x, card_y = self._cxy("challenge_stage_1")
            self._log(f'[Macro] "daily_challenge_stage" template missed -- using the '
                      f'"Challenge: Stage Slot 1" point at ({card_x}, {card_y}) '
                      f'(the daily card sits where slot 1 does).')
            left, top, _, _ = wm.get_window_rect_screen(hwnd)
            self._mouse.click(left + card_x, top + card_y)
            time.sleep(0.5)

        if self._checkpoint(stop_event):
            return None
        if not self._enter_selected_challenge(hwnd, stop_event, play_mode, coords, webhook, daily=True):
            return None
        return "entered"

    def _open_challenge_screen(self, hwnd, stop_event: threading.Event) -> bool:
        """Lobby -> Play -> Challenge and wait for the panel to finish loading."""
        if not self._ensure_lobby(hwnd, stop_event):
            return False
        if self._checkpoint(stop_event):
            return False
        if not self._click_play(hwnd, stop_event):
            return False
        if self._checkpoint(stop_event):
            return False
        if not self._click_gamemode(hwnd, stop_event, "challenge"):
            return False
        if self._checkpoint(stop_event):
            return False

        self._log("[Macro] Waiting for the Challenge screen to load...")
        self._set_status(action="Waiting for Challenge screen...")
        try:
            loaded_match = vision.wait_for_image(
                hwnd, "challenge_loaded", timeout=CHALLENGE_SCREEN_TIMEOUT, stop_event=stop_event)
        except vision.TemplateNotFound as exc:
            self._log(f"[Macro] Can't confirm the Challenge screen loaded: {exc}")
            return False
        if loaded_match is None:
            if not stop_event.is_set():
                self._log(f'[Macro] "challenge_loaded" not found within {CHALLENGE_SCREEN_TIMEOUT:.0f}s -- '
                           f"can't confirm the Challenge screen opened, stopping.")
            return False
        return True

    def _enter_selected_challenge(self, hwnd, stop_event: threading.Event, play_mode: str,
                                   coords: dict, webhook: dict, daily: bool) -> bool:
        """Use the shared Select Stage / matchmaking controls after selection."""
        challenge_task_stub = {
            "mode": "challenge", "is_challenge": True, "is_daily_challenge": daily}
        if play_mode == "matchmaking":
            if not self._click_enter_matchmaking(hwnd, stop_event, coords, "challenge"):
                return False
            if self._checkpoint(stop_event):
                return False
            self._log(f"[Macro] Waiting for the lobby to fill (up to {MATCHMAKING_TELEPORT_TIMEOUT / 60:.0f} "
                       f"min) -- matchmaking has to find real players before it teleports in.")
            if not self._wait_teleport_in(hwnd, stop_event, webhook, challenge_task_stub,
                                            timeout=MATCHMAKING_TELEPORT_TIMEOUT):
                return False
        else:
            self._set_status(action="Clicking Select Stage...")
            if not self._click_and_verify_gone(hwnd, stop_event, "chal_select", CHALLENGE_SCREEN_TIMEOUT):
                self._log('[Macro] "chal_select" never showed up -- stopping.')
                return False
            if self._checkpoint(stop_event):
                return False
            self._log("[Macro] Solo mode -- clicking Start.")
            if not self._click_start_and_wait_teleport(hwnd, stop_event, webhook, challenge_task_stub):
                return False
        return not self._checkpoint(stop_event)
