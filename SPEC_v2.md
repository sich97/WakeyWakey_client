# WakeyWakey v2 — Protocol & Design Contract

This document is the binding contract for the server and client rewrites.
Both repos MUST implement exactly this. If an implementation detail seems
wrong or missing, implement it anyway and note the concern in the commit
message — do NOT unilaterally change the contract.

## Hard requirements (non-negotiable, from the owner)

1. **Nothing on the network or in the client may stop the alarm.** There is
   NO `set_alarm_state` command. The ONLY path that clears `alarm_state`
   is a `submit_answer` that the SERVER validates itself.
2. **The client is a dumb terminal.** It fetches the test, renders it,
   captures the user's input, forwards it, and displays the server's
   verdict. The client NEVER validates the test locally. (v1 flaw: the
   client's word killed the alarm — flaky render = couldn't stop it even
   when awake; a script = could stop it while asleep.)
3. **Every test is fresh, server-generated, and one-shot.** A solved
   answer cannot be replayed; an answer must reference a currently
   active, server-issued test.
4. **A second "are you still awake" alarm** fires after a configurable
   delay once the first test is solved, with its OWN fresh test. Until
   that test is also solved, the alarm state after the second alarm
   behaves exactly like the first (rings until solved).
5. **No snooze, no off-switch, no cap on ring duration** in software.
   (The physical failsafe is a key in the garage — outside software.)

## Transport

- Same as v1: TCP socket, one command per line, ASCII.
- Client → server: `command arg1 arg2 ...`
- Server → client: single-line responses, mostly a bare token or a JSON
  object (one line, no internal newlines).
- All multi-field payloads in this contract are JSON, base64-encoded as a
  single argument where the command takes exactly one payload argument.

## Commands (v2 protocol)

### Kept from v1 (unchanged semantics)
- `get_alarm_state` → `0` or `1`
- `set_active_state 0|1` → `ok`
- `set_wakeup_hour <h>` / `set_wakeup_minute <m>` / `set_wakeup_window <s>` → `ok`
- `set_utc_offset <minutes>` → `ok`
- `get_timezone_time` → `<iso-local-time>`
- `get_user_preferences` → JSON line (all persisted settings)
- `get_grace_period` / `set_grace_period <s>` → `ok`
- `get_test_params` / `set_test_params <json>` → `ok`
  `test_params` = `{"cols": int, "rows": int, "min_path_points": int}`
  (difficulty knobs; stored server-side like v1's line_thickness did)
- `get_second_alarm` / `set_second_alarm <seconds>` → `ok`
  `0` disables the second alarm (default 600).

### Removed (must be gone from server dispatch AND client)
- `set_alarm_state` — **gone.** No replacement.
- `set_line_thickness` / `get_line_thickness` /
  `set_precision_mouse_threshold` / `get_precision_mouse_threshold` —
  replaced by `test_params`.

### New
- `get_test` → JSON line describing the CURRENT active test, or `none`
  if no alarm is ringing:
  ```
  {"test_id": "<64 hex>", "kind": "maze", "cols": C, "rows": R,
   "start": [c0, r0], "exit": [c1, r1],
   "walls": [[c, r, side], ...],   // side in "N","S","E","W" = wall on that side of cell
   "min_path_points": N,
   "sig": "<64 hex>"}
  ```
- `submit_answer <test_id> <base64-json>` → `accepted` or
  `rejected <reason>` where reason ∈
  `bad_sig | unknown_test | consumed | bad_start | bad_exit |
   teleport | out_of_bounds | crossed_wall | too_few_points`
  The base64-json payload is:
  ```
  {"sig": "<sig echoed from get_test>",
   "path": [[c, r], [c, r], ...]}   // floats, cell units, 0-indexed
  ```

## Cryptography

- Server holds a 32-byte secret key `k`: persisted in the existing
  `server_settings` sqlite table as row key `crypto_key` (generated
  random on first startup, never sent to any client).
- `sig = HMAC-SHA256(k, test_id + "|" + canonical_json(test_without_sig))`
  where `canonical_json` = sorted keys, no whitespace (use
  `json.dumps(..., sort_keys=True, separators=(",", ":"))`).
- The client echoes `sig` back in `submit_answer`; the server recomputes
  and rejects with `bad_sig` on mismatch. (Binds the answer to a
  server-issued test instance.)
- **One-shot:** every issued `test_id` is recorded in a new sqlite table
  `issued_tests(test_id TEXT PRIMARY KEY, issued_at REAL, consumed INTEGER DEFAULT 0)`.
  A successful answer sets `consumed=1` for that test_id. Any answer
  referencing a consumed test → `rejected consumed`; a test_id not in the
  table → `rejected unknown_test`.
- A NEW test is generated and becomes the active one:
  (a) when the alarm starts (first or second),
  (b) after ANY `submit_answer` (accepted or rejected) so the next
      attempt always gets a fresh test.
  `get_test` always returns the current active test while
  `alarm_state == 1`, else `none`.

## Alarm lifecycle (server-side)

1. Grace period (v1 behavior, kept): grace sound, then at wakeup time
   `alarm_state = 1` + generate test (a).
2. While `alarm_state == 1`: ring (buzzer loop as in v1) and wait.
3. `submit_answer` accepted:
   - mark test consumed;
   - if `second_alarm > 0`: `alarm_state = 0`, schedule the second alarm
     at now + `second_alarm`; when it fires: `alarm_state = 1` +
     generate test (a) again (this IS the "are you still awake" alarm);
   - else: `alarm_state = 0`, stop buzzers, deactivate (v1 end sequence).
4. `submit_answer` rejected: alarm keeps ringing; a fresh test replaces
   the active one (so retries always get a fresh maze).
5. Ringing has NO software timeout. (Garage key is the failsafe.)

## Maze generation & validation (server-side)

- Grid maze `cols × rows` from `test_params` (defaults: 21 × 15).
- Generated by randomized DFS (recursive backtracker) on the grid;
  `start` = cell (0,0); `exit` = cell (cols-1, rows-1).
- `walls` lists every remaining wall as `[c, r, side]` (a wall exists
  between cell (c,r) and its neighbor in direction `side`).
- **Validation of a submitted path** (all must pass, in this order):
  1. `sig` matches the active test → else `bad_sig`.
  2. `test_id` is active and unconsumed → else `unknown_test` / `consumed`.
  3. `len(path) >= min_path_points` (default 10) → else `too_few_points`.
  4. First point inside start cell, last point inside exit cell
     (a point (c,r) is "inside" cell (c0,r0) when c0 <= c < c0+1 and
     r0 <= r < r0+1) → else `bad_start` / `bad_exit`.
  5. Every point inside grid bounds [0, cols] × [0, rows] → else
     `out_of_bounds`.
  6. Consecutive points within distance 1.5 cells (no teleport) → else
     `teleport`.
  7. No segment crosses a wall: for each consecutive pair, sample the
     segment at 8 equally-spaced points; a sample lying in cell (c,r)
     must not be on a wall side of that cell pointing outward to the
     adjacent cell it came from — implement as: for each sample,
     determine its cell; if the sample crossed a wall into that cell
     (i.e., the wall between the previous sample's cell and this cell
     exists), fail → else `crossed_wall`.

## Client (dumb terminal) state machine

States: `CONNECTING → POLLING → SHOWING_TEST → SUBMITTING → RESULT`,
looping while the client runs.

- `POLLING`: every 1s send `get_alarm_state` (+ reconnect with backoff
  on error). On `1`: `get_test` → `SHOWING_TEST`.
- `SHOWING_TEST`: render the maze full-window; capture path (below);
  on mouse release: if the path ends in the exit cell → `SUBMITTING`
  with `submit_answer`; else show "did not reach the exit — try again"
  and stay in `SHOWING_TEST` (path clears).
- `SUBMITTING`: send `submit_answer`, wait for response → `RESULT`.
- `RESULT`: show `accepted` / `rejected <reason>`; back to `POLLING`.
  (If the server rejected, a fresh test is active — `get_test` on next
  poll fetches it.)
- The client must ALWAYS be able to render and submit (v1's failure was
  flaky rendering). Socket errors never wedge the UI; auto-retry.

## Client GUI reliability requirements (the v1 bug fix)

v1 "got confused where the mouse pointer was relative to the window".
Fix — do NOT trust screen coordinates or window offsets:

1. **Single authoritative Canvas** inside one fixed-size,
   non-resizable Toplevel; the canvas fills the window entirely
   (no other widgets, no title-bar interaction area used for input).
2. **All input via `event.x, event.y`** (canvas-relative coordinates)
   from `<Button-1>`, `<B1-Motion>` bound to the canvas. Never
   `event.x_root`/`y_root`, never manual window-offset math.
3. **Redraw from state every frame**: maze + current path are pure
   functions of (active test, recorded path points); no incremental
   canvas state that can drift. Cell size fixed at 24 px; canvas size =
   cols*24 × rows*24.
4. Path capture: on press, if the point is in the start cell begin
   recording (else hint "start in the green cell"); on motion append
   canvas→cell floats `(x/24, y/24)` (throttle: append only when moved
   ≥ 0.25 cell from the last point); on release stop.
5. Send the path normalized to cell units (floats), per the protocol.
6. Keep a `mock_test` dev flag (settings.ini) = render a locally-built
   sample maze with NO network and NO submission. It cannot affect a
   real alarm (only server-side validation can). Default: off.

## Files

- Server repo: `server.py` (protocol + lifecycle + crypto + maze gen/
  validation; new helper modules allowed, e.g. `maze.py`, `crypto.py`).
  `server_setup.py` only if the new DB tables require it.
- Client repo: `client.py` rewritten per the state machine above;
  `settings.ini` keys updated (drop line_thickness /
  precision_mouse_threshold; keep server address/port, window size
  derived from test, mock_test flag).

## Definition of done (each repo)

- `python3 -m py_compile` passes on every .py file.
- No reference anywhere to `set_alarm_state`, `line_thickness`,
  `precision_mouse_threshold`.
- Server: a scripted test (python, using the protocol) proves:
  (a) `submit_answer` with a precomputed CORRECT maze solution for the
  ACTIVE test → `accepted` and `alarm_state` → 0 (then second alarm
  fires after the delay, `alarm_state` → 1, new active test);
  (b) resubmitting the same test_id → `rejected consumed`;
  (c) tampered sig → `rejected bad_sig`;
  (d) path with a teleport gap → `rejected teleport`;
  (e) path crossing a wall → `rejected crossed_wall`.
  (Run the checks, paste results into the commit message.)
- Client: `py_compile` passes; `mock_test` mode renders a maze and a
  hand-drawn path can be recorded (can be verified by running the
  client headless is NOT required — but the code path must be
  unit-checkable, e.g. path recording factorable from the Tk event
  handler so a test can feed it points directly).
