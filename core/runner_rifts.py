"""Demonic Rifts interrupt only at completed-match/lobby boundaries."""
import time

import cv2

from . import ocr, paths, rifts, vision, settings
from .runner_constants import ENCOUNTER_TELEPORT_SETTLE


class RiftOps:
    def _prepare_rift_lobby(self, hwnd, stop_event):
        # A failed interaction may have opened Play's gamemode menu.
        # Its Back button proves the client is alive but hides lobby Play;
        # unwind it before _ensure_lobby rather than waiting forever.
        if not self._force_focus(hwnd):
            return False
        if vision.find_image(hwnd, 'rift_party_header') is not None:
            self._click_found_image(hwnd, 'rift_party_disband', 3, stop_event)
        if vision.find_image(hwnd, 'nav_back') is not None:
            self._spam_back_until_gone(hwnd, stop_event)
        return not self._checkpoint(stop_event) and self._ensure_lobby(hwnd, stop_event)

    def _rift_blocks_new_match(self):
        return not getattr(self, '_running_rift', False) and rifts.action() != 'normal'

    def _rift_lobby_boundary(self, hwnd, stop_event, default_walk_paths=None, webhook=None):
        if getattr(self, '_running_rift', False):
            return True
        logged = False
        while not self._checkpoint(stop_event):
            action = rifts.action()
            if action == 'normal':
                return True
            if action == 'wait':
                if not logged:
                    self._log('[Rifts] Hourly safeguard: waiting for the next full hour before starting another match.')
                    logged = True
                self._set_status(action='Waiting for hourly Demonic Rift...')
                self._interruptible_sleep(1, stop_event)
                continue
            hour, _ = rifts.window()
            self._running_rift = True
            # A nested rift must not change the paused task's progress or
            # convince its caller that it has already replayed/entered a match.
            fields = ('_current_task', '_active_task_progress', '_soul_task_purchase_failed',
                      '_result_repeated_in_place', '_result_requires_lobby_setup',
                      '_queue_continuation')
            saved = {key: getattr(self, key, None) for key in fields}
            try:
                self._run_hourly_rift(hwnd, stop_event, hour, default_walk_paths or {}, webhook or {})
            except Exception as exc:
                self._log(f'[Rifts] This hour\'s attempt failed: {exc}. Resuming normal tasks.')
                if not stop_event.is_set():
                    self._recover_to_lobby(hwnd, stop_event)
            finally:
                for key, value in saved.items():
                    setattr(self, key, value)
                self._running_rift = False
                task = saved['_current_task'] or {}
                self._set_status(map=task.get('map') or '-', mode=task.get('mode') or '-',
                                 stage=str(task.get('stage') or '-'),
                                 difficulty=task.get('difficulty') or '-',
                                 play_mode=task.get('play_mode') or '-',
                                 macro=task.get('macro') or '-', action='Resuming normal tasks...')
            # Re-read the clock and enable setting, including a slow run that
            # crosses another hour. Missed windows never start a late entry.
        return False

    def _rift_party_text(self, hwnd):
        frame = vision.capture_game_bgr(hwnd)
        if frame is None:
            return ''
        crop = cv2.resize(frame[316:351, 612:1000], None, fx=3, fy=3)
        try:
            return ocr.get_pytesseract().image_to_string(crop, config='--psm 6').lower()
        except Exception:
            return ocr._rapidocr_text(crop).lower()

    def _enter_hourly_rift(self, hwnd, stop_event, hour):
        if not self._prepare_rift_lobby(hwnd, stop_event):
            return False
        data = paths.load_path('Demonic Rift Lobby')
        if not data.get('events'):
            self._log('[Rifts] The bundled lobby walk is missing; cannot enter yet.')
            return False
        paths.replay_events(data['events'], self._keyboard, stop_event, sprint=False)
        for attempt in range(3):
            if self._checkpoint(stop_event):
                return False
            if rifts.window()[0] != hour or rifts.window()[1] >= 15 * 60:
                return False
            self._keyboard.tap(ord('E'))
            panel = vision.wait_for_image(hwnd, 'rift_party_header', timeout=3, stop_event=stop_event)
            if panel is not None:
                break
        else:
            self._log('[Rifts] Entry menu did not appear after three interactions.')
            return False
        # Only click the measured lock control while the supplied Rift party
        # header is visible. Verify PRIVATE explicitly; do not start publicly.
        for attempt in range(3):
            if self._checkpoint(stop_event):
                return False
            text = self._rift_party_text(hwnd)
            if 'private' in text:
                break
            if 'public' not in text:
                self._interruptible_sleep(.5, stop_event)
                continue
            self._click_task_point(hwnd, 1039, 335, 'Making the Rift party private')
            self._interruptible_sleep(.5, stop_event)
        else:
            self._log('[Rifts] Could not verify a private party; leaving without starting.')
            return False
        if (self._checkpoint(stop_event) or rifts.window()[0] != hour
                or rifts.window()[1] >= 15 * 60):
            return False
        return self._click_found_image(hwnd, 'rift_party_start', 5, stop_event) is not None

    def _reset_rift_spawn(self, hwnd, stop_event):
        if not self._prepare_rift_lobby(hwnd, stop_event):
            return False
        if not self._click_found_image(hwnd, 'nav_settings', 3, stop_event):
            return False
        self._interruptible_sleep(.5, stop_event)
        if self._checkpoint(stop_event) or vision.find_image(hwnd, 'nav_settings_on') is None:
            return False
        # Lobby Settings has a different layout from encounter Settings.
        # Match the labeled row; the old encounter point toggles Auto Vote Start.
        teleport = vision.find_image(hwnd, 'lobby_teleport_spawn')
        if teleport is None:
            self._log('[Rifts] Teleport To Spawn row not found -- leaving settings unchanged.')
            self._close_settings_if_open(hwnd, stop_event)
            return False
        self._click_task_point(hwnd, teleport['x'] + teleport['w'] - 25,
                               teleport['cy'], 'Rift retry: teleporting to Spawn')
        self._interruptible_sleep(.5, stop_event)
        for _ in range(3):
            self._close_settings_if_open(hwnd, stop_event)
            if self._checkpoint(stop_event):
                return False
            if vision.find_image(hwnd, 'nav_settings_on') is None:
                self._interruptible_sleep(ENCOUNTER_TELEPORT_SETTLE, stop_event)
                return not stop_event.is_set()
            self._interruptible_sleep(.5, stop_event)
        return False

    def _run_hourly_rift(self, hwnd, stop_event, hour, default_walk_paths, webhook):
        task = {'mode': 'demonic_rift', 'map': 'Fake Hometown - Rift',
                'difficulty': 'Hard', 'play_mode': 'solo', 'macro': rifts.load()['macro']}
        if task['macro'] and not self._macro_is_usable(task['macro']):
            self._log('[Rifts] Assigned macro is unavailable; using Auto Play.')
            task['macro'] = ''
        self._current_task = task
        self._set_status(mode='Demonic Rifts', map=task['map'], action='Entering hourly Rift...')
        state = settings.load().get('demonic_rift_state', {})
        same_hour = state.get('hour') == hour
        clears = int(state.get('clears', 0)) if same_hour else 0
        runs = int(state.get('runs', 0)) if same_hour else 0
        rifts.reserve(hour, runs, clears)
        self._log(f'[Rifts] Prioritizing this hour\'s private Rift until two victories ({clears}/2).')
        entered = False
        reset_spawn = False
        try:
            while clears < 2 and not self._checkpoint(stop_event) and rifts.load()['enabled']:
                if not entered:
                    current_hour, seconds = rifts.window()
                    if current_hour != hour or seconds >= 15 * 60:
                        self._log('[Rifts] Entry window closed; resuming the task queue.')
                        rifts.reserve(hour, runs, clears, finished=True)
                        return
                    if reset_spawn and not self._reset_rift_spawn(hwnd, stop_event):
                        self._interruptible_sleep(2, stop_event)
                        continue
                    if not self._enter_hourly_rift(hwnd, stop_event, hour):
                        self._log('[Rifts] Entry not confirmed; resetting Spawn and retrying while available.')
                        reset_spawn = True
                        self._interruptible_sleep(2, stop_event)
                        continue
                    first_repeat = True
                else:
                    first_repeat = False
                runs += 1
                rifts.reserve(hour, runs, clears)
                if not self._wait_teleport_in(hwnd, stop_event, webhook, task):
                    entered = False
                    reset_spawn = True
                    continue
                self._set_status(current_repeat=f'{clears} / 2 victories', action='Demonic Rift...')
                started = time.time()
                result = self._play_one_match(hwnd, stop_event, task, default_walk_paths,
                                              first_repeat=first_repeat, webhook=webhook)
                if result not in ('win', 'loss'):
                    entered = False
                    reset_spawn = True
                    continue
                if result == 'win':
                    clears += 1
                rifts.reserve(hour, runs, clears, finished=clears >= 2)
                self._log(f'[Rifts] {clears}/2 victories; defeat does not count as a clear.' if result == 'loss'
                          else f'[Rifts] Victory confirmed: {clears}/2 clears.')
                self._result_repeated_in_place = False
                if not self._handle_match_result(hwnd, stop_event, task, result,
                                                 self._format_duration(time.time()-started),
                                                 webhook, repeat=clears < 2 and rifts.load()['enabled']):
                    entered = False
                    reset_spawn = True
                    continue
                entered = self._result_repeated_in_place
                reset_spawn = not entered
            if clears >= 2:
                self._log('[Rifts] Two victories completed; resuming the task queue.')
        finally:
            if not stop_event.is_set():
                if vision.find_image(hwnd, 'rift_party_header') is not None:
                    self._click_found_image(hwnd, 'rift_party_disband', 3, stop_event)
                    self._interruptible_sleep(.5, stop_event)
                self._recover_to_lobby(hwnd, stop_event)
