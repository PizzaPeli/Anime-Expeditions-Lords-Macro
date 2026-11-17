# Demonic Rifts

Enable **Resources > Demonic Rifts** to visit the hourly lobby rift. Choose
Auto Play or assign a Macro Operation using **Plays the Rift**. The party is
made private and verified before Start is clicked.

The schedule uses the Windows account's local clock. With rifts enabled, no
new match or replay starts from minute 57 until the next full hour. A match
already running finishes normally. The rift takes priority at the next safe
lobby boundary, while its 15-minute entry window is still open. If that
window was missed, the normal queue continues until the next hour.

Each hourly visit keeps priority until **two victories**. Defeats do not count
as clears. Use the detected **Repeat Stage** while more victories are needed;
never select Next Stage. If replay fails, re-enter while the 15-minute lobby
entry window is open. Failed walk-ins use Settings > Teleport To Spawn before
retrying the recorded route. Normal tasks and maintenance wait until the two
victories finish or entry is no longer available. An ongoing match finishes
normally; an available in-place repeat can continue after lobby entry closes.
Attempts and confirmed clears are saved per account so a restart preserves
progress. Stop and disabling Rifts remain supported.

The bundled **Demonic Rift Lobby** walk is the later two-event recording:
hold W for 3.455 seconds from the normal lobby spawn/default camera. This
walk is separate from normal map walk assignments.

A camera-ready Rift map image is captured automatically on its first entry
while the placement preview is missing. The supplied result/party screenshots
are navigation references, not placement backgrounds.

Use `TEST_BUILD.bat` to test the rebuilt canonical executable with the current
Windows account's saved test setup. Source tests and screenshot matching do
not replace live validation of walking, private-party OCR, teleport, replay,
and returning to the paused task.
