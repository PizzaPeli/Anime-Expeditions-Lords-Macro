# Bossrush

Add a task with **Mode > Bossrush > District 7**. The task uses Auto Play
unless a Macro Operation is selected. Solo and Matchmaking use the normal
stage entry, result, repeat and lobby interval handling.

- **Gates before boss:** 2 by default, selectable from 2 through 6.
- **Buff cards:** Random by default. Dark always picks the right card,
  Light the middle, and Flame the left. Random chooses anew for each gate.
- The six bundled gate paths are the creator's latest recordings from the
  automatic spawn position using the normal Settings camera test setup.
  Gates are visited in order. The shared camera setup runs on map entry.
- Each gate's card screen confirms a clear. Repeated captures/click retries
  of that same screen do not increment the count. The explicit boss vote
  uses Continue until the selected number is reached, then Fight Boss.
- Pre Start runs once per complete run. Units, Battle and Loop indices,
  upgrade budgets and pending Wait time carry through gate transitions.
  Combat actions pause for gate walks, Start Game, cards and boss votes.
- A failed gate interaction is tried three times. A stuck transition saves
  a diagnostic capture and uses the normal task recovery from the lobby;
  it never replays a spawn path from an unknown position.

Creation's placement picker includes **Bossrush > District 7**, taken from
the creator's camera-ready screenshot. Source captures are retained in
`Assets/reference/bossrush`; their crop import script is
`scripts/dev/import_bossrush_captures.py`.

Use `TEST_BUILD.bat` after syncing the project to each Windows account.
Bossrush Shop and Raid Shop are separate follow-up work.
