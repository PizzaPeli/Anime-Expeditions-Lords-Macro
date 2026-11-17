"""Local hourly Demonic Rift schedule and per-account entry ledger."""
from datetime import datetime

from . import settings


def load():
    data = settings.load().get('demonic_rifts', {})
    return {'enabled': bool(data.get('enabled', False)),
            'macro': str(data.get('macro') or '')}


def window(now=None):
    now = now or datetime.now().astimezone()
    # Include the offset so the repeated hour at the DST change is distinct.
    return now.strftime('%Y-%m-%dT%H%z'), now.minute * 60 + now.second


def action(now=None, config=None, state=None):
    config = load() if config is None else config
    if not config.get('enabled'):
        return 'normal'
    hour, seconds = window(now)
    state = settings.load().get('demonic_rift_state', {}) if state is None else state
    if seconds >= 57 * 60:
        return 'wait'
    if seconds < 15 * 60 and (state.get('hour') != hour or
            (not state.get('finished', True) and state.get('clears', 0) < 2)):
        return 'enter'
    return 'normal'


def reserve(hour, runs=0, clears=0, finished=False):
    # Kept apart from the user's options so editing a macro/toggle cannot
    # reset the ledger. Defeats are attempts, never successful clears.
    settings.update({'demonic_rift_state': {'hour': hour, 'runs': runs,
                     'clears': clears, 'finished': finished}})
