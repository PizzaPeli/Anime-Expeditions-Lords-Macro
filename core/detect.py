"""Detect block -- the macro's one branching primitive.

A `detect` block searches for an image (or a combination of images, or a raw
condition expression) and runs one of two nested block lists: `then` when the
condition holds, `else` when it doesn't.

The runner executes a FLAT block list with a single index (see
core.runner_blocks). To leave that engine essentially unchanged, flatten()
expands each detect block into a flat instruction stream with two synthetic
control ops:

    detect(_else_offset=E)     # evaluate; if the condition is FALSE, the
     ...then blocks...          #   engine does index += E to land on the
    _jump(_offset=J)           #   first else block. If TRUE, it falls through.
     ...else blocks...          # _jump skips the else branch after then ran.

Both branches stay inline in the flat list, so place_unit blocks are numbered
by their static position (then before else) no matter which branch runs at
runtime -- the same order ui/app.js's listPlacedUnits() walks, so "unit #N"
means the same unit on both sides.
"""
import ast

import cv2

from . import vision

DETECT_LOOP_DEFAULT_INTERVAL_MS = 1000
DETECT_LOOP_MIN_INTERVAL_MS = 100
DETECT_LOOP_MAX_INTERVAL_MS = 60000


def loop_settings(block):
    """Return (enabled, max_attempts, interval_seconds) for a Detect loop.

    A zero max-attempt value means keep searching until the condition is
    found. The interval is clamped so a self-loop cannot turn into a tight
    screen-capture/click poll by accident.
    """
    enabled = bool(block.get("loop"))
    try:
        max_attempts = max(0, int(block.get("loopAttempts", block.get("loop_attempts", 0)) or 0))
    except (TypeError, ValueError):
        max_attempts = 0
    try:
        interval_ms = int(block.get(
            "loopIntervalMs", block.get("loop_interval_ms", DETECT_LOOP_DEFAULT_INTERVAL_MS))
            or DETECT_LOOP_DEFAULT_INTERVAL_MS)
    except (TypeError, ValueError):
        interval_ms = DETECT_LOOP_DEFAULT_INTERVAL_MS
    interval_ms = max(DETECT_LOOP_MIN_INTERVAL_MS, min(DETECT_LOOP_MAX_INTERVAL_MS, interval_ms))
    return enabled, max_attempts, interval_ms / 1000.0


# ---------------------------------------------------------------------------
# flatten
# ---------------------------------------------------------------------------
def flatten(blocks, ordinal_start: int = 1):
    """(flat_list, next_ordinal).

    Expand nested detect then/else into one flat list with detect/_jump
    control entries, and stamp every place_unit (nested ones included) with
    its positional `_ordinal`, continuing from `ordinal_start`. Non-detect
    blocks pass through. next_ordinal is where a later phase should resume the
    count -- Battle continues Pre Start's unit numbering."""
    flat = []
    ordinal = _flatten_into(blocks or [], flat, ordinal_start)
    return flat, ordinal


def _flatten_into(blocks, flat, ordinal):
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "place_unit":
            # Shallow copy so stamping never mutates the saved template dict
            # (flatten can run more than once across a session).
            block = dict(block)
            block["_ordinal"] = ordinal
            ordinal += 1
            flat.append(block)
        elif btype == "detect":
            ctrl = dict(block)
            flat.append(ctrl)
            detect_index = len(flat) - 1
            ordinal = _flatten_into(block.get("then") or [], flat, ordinal)
            jump = {"type": "_jump"}
            flat.append(jump)
            jump_index = len(flat) - 1
            ordinal = _flatten_into(block.get("else") or [], flat, ordinal)
            end_index = len(flat)
            # A FALSE condition jumps from the detect entry to the first else
            # block (right after the _jump). With no else blocks that lands on
            # end_index, i.e. straight past the whole construct.
            ctrl["_else_offset"] = (jump_index + 1) - detect_index
            # A self-looped Detect that has already succeeded must skip both
            # branches when its containing Loop A/B comes back around. This
            # offset lands after the complete Detect construct.
            ctrl["_end_offset"] = end_index - detect_index
            # After the then branch runs and falls through to _jump, skip the
            # else branch entirely.
            jump["_offset"] = end_index - jump_index
        else:
            flat.append(block)
    return ordinal


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------
def evaluate(runner, hwnd, block):
    """(found: bool, matches: list[dict]).

    `matches` are location dicts (as vision.find_image returns) for the
    single-image path, best score first -- used only for logging where it
    matched. Multi-image and expression conditions return an empty match list
    (their "where" isn't a single point).

    mode="counter" (added 0.20.9) attaches a per-runner counter map so a
    Detect block can branch on "have I been hit N times yet?" instead of
    on an image match. Empty/zero/missing limit means infinite (branch
    stays TRUE forever, same shape as a plain always-true detect). See
    _eval_counter for the semantics. 0.22 also passes the runner's current
    task through, so a counter block can take its limit from the task's own
    field (`limit_from_task`) instead of a number baked into the template."""
    log = getattr(runner, "_log", None)
    if not hasattr(runner, "_detect_counters"):
        runner._detect_counters = {}
    ctx = _Ctx(hwnd, _region_tuple(block.get("region")), block.get("threshold"), log,
               counters=runner._detect_counters,
               task=getattr(runner, "_current_task", None))
    return _evaluate_context(ctx, block, log)


def _evaluate_context(ctx, block, log=None):
    """Evaluate a block against any context exposing find/count helpers."""
    mode = block.get("mode") or "single"

    if mode == "counter":
        # Counter-based branch (0.20.9): no image search, just a hit count.
        # Empty/zero/missing limit is infinite -> branch stays TRUE forever.
        # See _eval_counter for the full semantics + log format.
        return bool(_eval_counter(ctx, block, log)), []

    if mode == "expr":
        return bool(_eval_expr(block.get("expr") or "", ctx, log)), []

    if mode == "multi":
        names = [str(n) for n in (block.get("images") or []) if n]
        if not names:
            return False, []
        results = [ctx.find(n) for n in names]
        found = any(results) if (block.get("logic") == "or") else all(results)
        return found, []

    # single
    name = str(block.get("image") or "")
    if not name:
        return False, []
    if block.get("showAll"):
        matches = ctx.find_all(name)
        return (len(matches) > 0), matches
    match = ctx.find_match(name)
    return (match is not None), ([match] if match else [])


def diagnose_frame(frame_bgr, block, log=None):
    """Evaluate one Detect block against one already-captured full frame.

    The normal runner captures independently on every poll. Diagnostics use a
    single frame so the returned scores, match boxes, and preview image all
    describe exactly the same moment. The returned details include the best
    candidate even when it is below the configured threshold.
    """
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return {"found": False, "matches": [], "details": [], "region": None}
    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    region = _region_tuple(block.get("region"))
    ctx = _FrameCtx(frame_gray, region, block.get("threshold"), log)
    found, matches = _evaluate_context(ctx, block, log)
    return {
        "found": bool(found),
        "matches": matches,
        "details": list(ctx.details.values()),
        "region": region,
    }


def _region_tuple(region):
    """A saved {x,y,w,h} region dict as vision's (x, y, w, h) tuple, or None
    for a missing/whole-screen/invalid region."""
    if not isinstance(region, dict):
        return None
    try:
        x, y, w, h = int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"])
    except (KeyError, TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


class _Ctx:
    """Holds the search parameters for one detect evaluation and exposes the
    find/count helpers the expression evaluator calls. A missing reference
    image is warned about once, then treated as "not found" so a typo'd name
    can never hard-fail a run.

    `counters` (added 0.20.9) is a dict shared with the runner
    (runner._detect_counters) so mode="counter" blocks can carry a hit
    count across a full macro session -- reset naturally on the next
    macro start when the runner re-creates its state."""

    def __init__(self, hwnd, region, threshold, log, counters=None, task=None):
        self.hwnd = hwnd
        self.region = region
        self.threshold = threshold
        self.log = log
        self.counters = counters if counters is not None else {}
        # The task dict the runner is currently executing, or None outside a
        # task (Macro Manager test runs, diagnostics). Only read by
        # mode="counter" blocks carrying `limit_from_task` -- see
        # _counter_limit.
        self.task = task if isinstance(task, dict) else None
        self._missing = set()

    def _dir_and_thr(self, name):
        tdir = vision.detect_template_dir(name)
        thr = vision.DEFAULT_THRESHOLD if self.threshold is None else float(self.threshold)
        return tdir, thr

    def find_match(self, name):
        name = str(name)
        try:
            tdir, thr = self._dir_and_thr(name)
            return vision.find_image(self.hwnd, name, region=self.region, threshold=thr, template_dir=tdir)
        except vision.TemplateNotFound:
            self._warn_missing(name)
            return None

    def find_all(self, name):
        name = str(name)
        try:
            tdir, thr = self._dir_and_thr(name)
            return vision.find_image_all(self.hwnd, name, region=self.region, threshold=thr, template_dir=tdir)
        except vision.TemplateNotFound:
            self._warn_missing(name)
            return []

    def find(self, name):
        return self.find_match(name) is not None

    def count(self, name):
        return len(self.find_all(name))

    def _warn_missing(self, name):
        if name not in self._missing and self.log:
            self._missing.add(name)
            self.log(f'[Macro] Detect: no reference image named "{name}" -- treating it as not found. '
                     f'Add one in Image Manager > Detection Images.')


class _FrameCtx(_Ctx):
    """The Detect context used by ``diagnose_frame``."""

    def __init__(self, frame_gray, region, threshold, log):
        # No counter map for diagnostics -- diagnose_frame evaluates a
        # single frame in isolation, so a counter branch would be
        # meaningless. An empty dict is fine.
        super().__init__(None, region, threshold, log, counters={})
        self.frame_gray = frame_gray
        self.details = {}

    def _region_frame(self):
        if self.region is None:
            return self.frame_gray
        x, y, w, h = self.region
        return self.frame_gray[max(0, y):y + h, max(0, x):x + w]

    def _offset(self, match):
        if match is None or self.region is None:
            return dict(match) if match is not None else None
        x, y, _w, _h = self.region
        result = dict(match)
        for key in ("x", "cx"):
            result[key] += x
        for key in ("y", "cy"):
            result[key] += y
        return result

    def _record(self, name, threshold, best=None, match=None, matches=None, error=None):
        entry = self.details.setdefault(str(name), {
            "name": str(name), "matched": False, "score": None,
            "threshold": float(threshold), "best_match": None,
            "match": None, "matches": [], "error": None,
        })
        entry["threshold"] = float(threshold)
        entry["matched"] = bool(match is not None or matches)
        entry["score"] = best.get("score") if best else None
        entry["best_match"] = best
        entry["match"] = match
        if matches is not None:
            entry["matches"] = matches
        if error:
            entry["error"] = error

    def find_match(self, name):
        name = str(name)
        tdir, raw_threshold = self._dir_and_thr(name)
        threshold = vision._effective_threshold(name, raw_threshold)
        try:
            result = vision.find_in_gray_multiscale_diagnostic(
                self._region_frame(), name, template_dir=tdir, threshold=threshold)
        except vision.TemplateNotFound:
            self._warn_missing(name)
            self._record(name, threshold, error="missing")
            return None
        best = self._offset(result["best"])
        match = self._offset(result["match"])
        self._record(name, threshold, best=best, match=match,
                     matches=[match] if match else [])
        return match

    def find_all(self, name):
        name = str(name)
        tdir, raw_threshold = self._dir_and_thr(name)
        threshold = vision._effective_threshold(name, raw_threshold)
        try:
            matches = vision.find_all_in_gray(
                self._region_frame(), name, template_dir=tdir,
                threshold=threshold)
            best = vision.find_in_gray_multiscale_diagnostic(
                self._region_frame(), name, template_dir=tdir, threshold=threshold)["best"]
        except vision.TemplateNotFound:
            self._warn_missing(name)
            self._record(name, threshold, error="missing")
            return []
        matches = [self._offset(match) for match in matches]
        self._record(name, threshold, best=self._offset(best),
                     match=matches[0] if matches else None, matches=matches)
        return matches


def render_diagnostic(frame_bgr, report):
    """Draw the Detect region, match candidates, and verdict on a frame."""
    import numpy as np

    image = np.array(frame_bgr, dtype=np.uint8, copy=True, order="C")
    region = report.get("region")
    if region is not None:
        x, y, w, h = region
        cv2.rectangle(image, (x, y), (x + w, y + h), (255, 190, 0), 2)
        cv2.putText(image, f"search region {x},{y} {w}x{h}", (x + 4, max(16, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 190, 0), 1, cv2.LINE_AA)

    for detail in report.get("details", []):
        matched = bool(detail.get("matched"))
        boxes = detail.get("matches") or []
        if not boxes and (detail.get("match") or detail.get("best_match")):
            boxes = [detail.get("match") or detail.get("best_match")]
        # BGR colors: accepted matches are red so they stand out from the
        # cyan/yellow near-miss boxes and the cyan search-region outline.
        color = (0, 0, 255) if matched else (0, 210, 255)
        for index, match in enumerate(boxes):
            x, y = int(match["x"]), int(match["y"])
            w, h = int(match["w"]), int(match["h"])
            cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
            score = float(match.get("score", 0.0))
            suffix = "" if index == 0 else f" #{index + 1}"
            cv2.putText(image, f"{detail['name']}{suffix} {score:.2f}",
                        (x, max(14, y - 5)), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, color, 1, cv2.LINE_AA)

    status = "FOUND - Then branch" if report.get("found") else "NOT FOUND - Else branch"
    cv2.rectangle(image, (0, 0), (image.shape[1], 28), (20, 25, 35), -1)
    cv2.putText(image, status, (8, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 220, 80) if report.get("found") else (80, 170, 255), 1, cv2.LINE_AA)
    return image


# ---------------------------------------------------------------------------
# counter mode (0.20.9) -- branch on hit count instead of image match
# ---------------------------------------------------------------------------
def _counter_limit(ctx, block, log=None):
    """The hit limit for one counter block, as a non-negative int (0 = none).

    Normally just the block's own `limit`. When the block sets
    `limit_from_task` (0.22), that names a field on the task the runner is
    currently running -- e.g. "extract_after", which the Portals task type
    reuses as "how many portals before exiting". The task value wins when it
    resolves to a number; anything else (no task at all, because this is a
    Macro Manager test run; a missing field; junk in a hand-edited task file)
    falls back to the block's `limit`, so a template stays runnable outside a
    task instead of erroring.

    Everything unparseable ends at 0 = infinite, matching the pre-0.22
    behaviour of an empty limit: a counter that can't resolve a bound should
    keep the loop going, never silently exit on the first pass.
    """
    def _as_limit(raw):
        if raw is None or isinstance(raw, bool):
            return None
        if isinstance(raw, str) and not raw.strip():
            return None
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            return None
        return max(0, value)

    field = block.get("limit_from_task")
    if field:
        field = str(field)
        if not isinstance(ctx.task, dict):
            if log:
                log(f"[Macro] Counter: `limit_from_task`={field!r} but no task is "
                    f"running -- falling back to the block's own limit.")
        else:
            from_task = _as_limit(ctx.task.get(field))
            if from_task is None:
                if log:
                    log(f"[Macro] Counter: task field {field!r} is "
                        f"{ctx.task.get(field)!r}, not a whole number -- falling "
                        f"back to the block's own limit.")
            else:
                return from_task

    own = _as_limit(block.get("limit"))
    if own is None:
        raw = block.get("limit")
        if raw not in (None, "", 0, "0") and log:
            log(f"[Macro] Counter: `limit`={raw!r} is not a whole number -- "
                f"treating as infinite.")
        return 0
    return own


def _eval_counter(ctx, block, log=None):
    """Increment the block's hit count and return True while it's <= limit.

    Semantics chosen to match what the user asked for ("empty -> infinite,
    number N -> N runs then exit"): the THEN branch fires for the first N
    hits, the ELSE branch fires from hit N+1 onward. Callers put the
    "keep looping" click (e.g. Select next portal) in THEN and the "stop"
    click (e.g. Exit to lobby) in ELSE, and the counter is naturally
    persistent across loop_a/loop_b wraparounds because it lives on the
    runner (runner._detect_counters), not on the per-phase state dict
    that gets reset each wraparound.

    Empty/zero/missing limit means infinite -- branch stays TRUE forever
    so an empty-limit template behaves the same as the pre-0.20.9
    "continuous portals" example.

    counter_id (optional) lets two blocks share one counter (e.g. one in
    loop_a, one in loop_b for a dual-check). Falls back to id(block) so
    each block has its own count by default.

    limit_from_task (optional, 0.22) names a field on the running task to
    read the limit from instead of the block's own `limit` -- see
    _counter_limit. That is how one bundled template serves every
    "N portals then exit" value without the user editing the template.
    """
    key = str(block.get("counter_id") or id(block))
    ctx.counters[key] = ctx.counters.get(key, 0) + 1
    hits = ctx.counters[key]

    limit = _counter_limit(ctx, block, log)

    label = str(block.get("label") or block.get("counter_id") or "counter")
    if limit <= 0:
        if log:
            log(f"[Macro] Counter '{label}': hit {hits} (no limit).")
        return True
    keep_going = hits <= limit
    if log:
        state = "continuing" if keep_going else "limit reached -> else branch"
        log(f"[Macro] Counter '{label}': {hits}/{limit} -- {state}.")
    return keep_going


# ---------------------------------------------------------------------------
# raw condition expression -- AST allowlist, fail-safe to "not found"
# ---------------------------------------------------------------------------
_ALLOWED_CALLS = {"find", "count"}
_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.USub, ast.UAdd, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE, ast.Constant, ast.Load,
)


def _check_nodes(tree):
    """Reject anything outside a tiny boolean/comparison grammar over
    find(...)/count(...) calls with quoted-name arguments. No attribute
    access, subscripts, comprehensions, lambdas, or arbitrary names."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if (not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS
                    or node.keywords or any(isinstance(a, ast.Starred) for a in node.args)):
                raise ValueError("only find(...) and count(...) calls are allowed")
            for arg in node.args:
                if not isinstance(arg, ast.Constant):
                    raise ValueError("find()/count() take a plain image name in quotes")
            continue
        if isinstance(node, ast.Name):
            if node.id not in _ALLOWED_CALLS:
                raise ValueError(f"unknown name `{node.id}`")
            continue
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"`{type(node).__name__}` is not allowed in a condition")


def _eval_expr(expr, ctx, log=None):
    expr = (expr or "").strip()
    if not expr:
        return False
    try:
        tree = ast.parse(expr, mode="eval")
        _check_nodes(tree)
    except (SyntaxError, ValueError) as exc:
        if log:
            log(f"[Macro] Detect: can't read condition `{expr}` -- {exc}. Treating as not found.")
        return False
    env = {
        "find": lambda n: ctx.find(str(n)),
        "count": lambda n: ctx.count(str(n)),
    }
    try:
        return bool(eval(compile(tree, "<detect>", "eval"), {"__builtins__": {}}, env))  # noqa: S307
    except Exception as exc:  # any runtime hiccup -> fail safe, never crash the run
        if log:
            log(f"[Macro] Detect: condition `{expr}` failed to run -- {exc}. Treating as not found.")
        return False
