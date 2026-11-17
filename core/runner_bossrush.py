"""Bossrush gate navigation without resetting a custom macro between fights."""
import time

from . import bossrush, paths, vision
from .runner_constants import MAP_SELECT_RETRY_ATTEMPTS, STAGE_SCREEN_TIMEOUT


class BossrushOps:
    def _reach_bossrush(self, hwnd, stop_event, task):
        if task.get('map') != 'District 7':
            self._log('[Bossrush] Unknown map; District 7 is the only supported stage.')
            return False
        for attempt in range(MAP_SELECT_RETRY_ATTEMPTS):
            if self._checkpoint(stop_event):
                return False
            if (self._ensure_lobby(hwnd, stop_event)
                    and self._click_play(hwnd, stop_event)
                    and self._click_gamemode(hwnd, stop_event, 'bossrush')):
                found = vision.wait_for_image(hwnd, 'bossrush_district',
                                              timeout=STAGE_SCREEN_TIMEOUT, stop_event=stop_event)
                if found is not None:
                    return True  # District 7 is selected when this screen opens.
            self._log(f'[Bossrush] Entry attempt {attempt+1} failed; backing out before retrying.')
            self._spam_back_until_gone(hwnd, stop_event)
        return False

    def _bossrush_reset(self, task):
        target, preference = bossrush.options(task)
        self._bossrush_state = {
            'target': target, 'preference': preference, 'completed': 0,
            'phase': 'travel', 'card_visible': False, 'choice': None,
            'next_action': 0.0, 'changed_at': time.monotonic(),
            'enter_attempts': 0, 'start_attempts': 0,
        }
        self._log(f'[Bossrush] Fight boss after {target} gates; cards: {preference}.')

    def _bossrush_click(self, hwnd, stop_event, x, y, label):
        self._release_quick_place_shift()
        if self._checkpoint(stop_event) or not self._force_focus(hwnd):
            return False
        self._keyboard.tap(ord('Z'))
        self._click_task_point(hwnd, x, y, label)
        return True

    def _bossrush_combat_ready(self, hwnd):
        if self._current_task_mode() != 'bossrush':
            return True
        ui = bossrush.observe(vision.capture_game_bgr(hwnd))
        return (getattr(self, '_bossrush_state', {}).get('phase') in ('gate', 'boss')
                and not any(ui.get(key) for key in ('card', 'decision', 'start', 'gates', 'victory', 'defeat')))

    def _bossrush_pause_blocks(self):
        # A Wait block measures combat time, excluding the walk/card/vote gap.
        self._battle_block_state.pop('bossrush_wait_tick', None)
        for runtime in (getattr(self, '_loop_runtime', None) or {}).values():
            runtime.get('state', {}).pop('bossrush_wait_tick', None)

    def _bossrush_wait_tick(self, block):
        state = self._battle_block_state
        now = time.monotonic()
        if 'bossrush_wait_left' not in state:
            try:
                state['bossrush_wait_left'] = max(0, float(block.get('params', {}).get('ms') or 0)) / 1000
            except (TypeError, ValueError):
                state['bossrush_wait_left'] = 0
        previous = state.get('bossrush_wait_tick', now)
        state['bossrush_wait_left'] -= max(0, now - previous)
        state['bossrush_wait_tick'] = now
        return state['bossrush_wait_left'] <= 0

    def _bossrush_tick(self, hwnd, stop_event):
        """Return (result, busy). Busy suspends Battle and both Loop phases.

        Gate cards confirm completion, not a disappeared Start prompt or a
        timer. Only a fresh card after an entered gate advances the count.
        No Battle/Loop indices, remaining upgrade budgets or Once flags are reset.
        """
        state = self._bossrush_state
        ui = bossrush.observe(vision.capture_game_bgr(hwnd))
        now = time.monotonic()
        if ui.get('victory'):
            return 'win', True
        if ui.get('defeat'):
            return 'loss', True
        if self._checkpoint(stop_event):
            return None, True
        if ui.get('card'):
            if not state['card_visible']:
                state['card_visible'] = True
                if state['phase'] in ('gate', 'starting_gate') or state['choice'] is None:
                    state['choice'] = bossrush.card_choice(state['preference'])
                if state['phase'] in ('gate', 'starting_gate'):
                    state['completed'] += 1
                    self._log(f'[Bossrush] Gate {state["completed"]} cleared.')
                state['phase'] = 'after_gate'
                state['changed_at'] = now
            if now >= state['next_action']:
                choice = state['choice']
                self._bossrush_click(hwnd, stop_event, *bossrush.CARD_POINTS[choice],
                                     f'Bossrush: choosing {choice.title()} card')
                state['next_action'] = now + 0.75
            return None, True
        if state['card_visible']:
            state['card_visible'] = False
            state['changed_at'] = now

        if ui.get('decision'):
            if now >= state['next_action']:
                fight = state['completed'] >= state['target']
                clicked = self._bossrush_click(hwnd, stop_event, 635 if fight else 516, 220,
                                              'Bossrush: fighting boss' if fight else 'Bossrush: continuing to next gate')
                if not clicked:
                    return None, True
                state['phase'] = 'starting_boss' if fight else 'after_gate'
                state['next_action'] = now + 0.75
                state['changed_at'] = now
            return None, True

        if ui.get('start'):
            # Repeated clicks belong to the SAME fight. Never replay blocks.
            if now >= state['next_action']:
                if state['start_attempts'] >= 3:
                    return self._bossrush_failed(hwnd, 'start_stuck')
                if state['phase'] not in ('starting_boss', 'boss'):
                    state['phase'] = 'starting_gate'
                point = ui['start']
                if self._bossrush_click(hwnd, stop_event, point['cx'], point['cy'], 'Bossrush: Start Game'):
                    state['start_attempts'] += 1
                state['next_action'] = now + 1.0
                state['changed_at'] = now
            return None, True

        if state['phase'] in ('starting_gate', 'starting_boss'):
            # Gate labels can still be drawing behind the Start transition.
            if now < state['next_action']:
                return None, True
            state['phase'] = 'boss' if state['phase'] == 'starting_boss' else 'gate'
            state['start_attempts'] = 0
            state['enter_attempts'] = 0
            state['changed_at'] = now
            return None, False

        if state['phase'] == 'entering' and ui.get('boss_health') and not ui.get('gates') and not ui.get('enter'):
            # Auto Vote Start / a matchmaking leader can clear Start before
            # our next poll. Confirm the entered map in two frames instead
            # of requiring this client to have clicked its own Start button.
            state['combat_reads'] = state.get('combat_reads', 0) + 1
            if state['combat_reads'] >= 2:
                state['phase'] = 'gate'
                state['start_attempts'] = state['enter_attempts'] = 0
                return None, False
            return None, True
        state['combat_reads'] = 0

        if state['phase'] in ('gate', 'boss'):
            return None, False

        # A cleared gate returns us to spawn. Allow the card/boss vote and
        # teleport to settle before replaying the next spawn-based path.
        if state['phase'] == 'after_gate':
            if now - state['changed_at'] < 1.5:
                return None, True
            if state['completed'] >= state['target']:
                # Wait for the explicit Fight Boss choice, including after 6.
                if now - state['changed_at'] > 45:
                    return self._bossrush_failed(hwnd, 'boss_vote_missing')
                return None, True
            state['phase'] = 'travel'

        if state['phase'] == 'travel' and ui.get('gates'):
            gate = state['completed'] + 1
            data = paths.load_path(f'Boss Rush Gate {gate}')
            if not data.get('events'):
                return self._bossrush_failed(hwnd, f'gate_{gate}_path_missing')
            if not self._force_focus(hwnd):
                return None, True
            self._release_quick_place_shift()
            self._keyboard.tap(ord('Z'))
            self._set_status(action=f'Bossrush: walking to gate {gate}...')
            self._log(f'[Bossrush] Walking spawn path to gate {gate}.')
            paths.replay_events(data['events'], self._keyboard, stop_event, sprint=False)
            state['phase'] = 'entering'
            state['changed_at'] = time.monotonic()
            state['next_action'] = state['changed_at'] + 0.5
            return None, True

        if state['phase'] == 'entering' and ui.get('enter') and now >= state['next_action']:
            if state['enter_attempts'] >= 3:
                return self._bossrush_failed(hwnd, 'gate_entry_stuck')
            if self._force_focus(hwnd):
                self._keyboard.tap(ord('E'))
                state['enter_attempts'] += 1
                state['next_action'] = now + 2.0
            return None, True

        if now - state['changed_at'] > 45:
            # Do not replay a spawn path from an unknown position or count a
            # failed walk as a cleared gate. Shared recovery re-enters safely.
            return self._bossrush_failed(hwnd, 'gate_transition_stuck')
        return None, True

    def _bossrush_failed(self, hwnd, reason):
        self._log(f'[Bossrush] {reason.replace("_", " ")} -- recovering this task from lobby.')
        self._save_debug_screenshot_unconditional(hwnd, 'bossrush_' + reason)
        return 'failed', True
