# Footpath Profiler

A single-page web app for surveying footpath widths from a phone photo. It uses a one-point perspective model — a vanishing point plus two edge lines — to convert pixel distances in a photo into real-world millimeters. It also runs a separate **batch pipeline** that reads pre-annotated photos (produced by another model) and computes widths automatically, without a human dragging anything.

Everything lives in one file (`footpath-profiler.html`); the only external dependency is a Google Apps Script Web App bound to a Google Sheet, used for logging measurements, calibrations, and surveyor profiles. The Apps Script side needs the functions in `apps_script_additions.gs` merged into whatever script is actually deployed — see [§8](#8-google-apps-script-setup).

---

## 1. Login

The login screen asks for, in order:

| Field | Notes |
|---|---|
| Email | Used as the calibration/profile identity key (lowercased, trimmed) |
| Phone Number | Free text |
| Your Name | Skipped for returning surveyors — see below |
| Your Height (cm) | Required, validated 100–230cm |
| Phone Model | Dropdown of common models, or "Other" for free text |

**Returning surveyors:** on leaving the Email field, the app looks up that email in the `Surveyors` sheet tab. If a name is already on file, the Name field is hidden and replaced with a "Welcome back, {name}" note — phone and height are pre-filled too, if this device doesn't already have them locally. Brand-new surveyors just see all the fields normally. This lookup fails silently (shows the Name field as a safe default) if offline or if Apps Script isn't configured.

On successful login:

- `eyeH` (assumed camera height) is computed as **`(height − 15cm) × 10`**, in millimeters. This is recomputed fresh from height on every login — it is never cached separately, and Method 1/2 calibration never edits it directly (see [§3](#3-calibration) for why an independently accurate eyeH turned out not to matter).
- Name, phone, and height are synced to the `Surveyors` tab (upsert by email — only the fields provided in a given sync are overwritten, so one save never blanks out another).
- The session is cached in `localStorage` (`fp_user`), so returning to the app on the same device skips the login screen entirely until the person logs out.

---

## 2. The perspective model

The app draws two lines on the photo — the **Building edge** and the **Kerb edge** — both converging toward a shared **vanishing point (VP)**. Dragging either line, or the VP itself, updates the model live. Tapping (not dragging) a handle locks it, useful for holding geometry steady across multiple shots from roughly the same spot.

The core formula (`toWorldMM`) converts a screen point to a real-world position on the ground plane:

```
X = (screen_x − vp.x) × eyeH / (screen_y − vp.y)
```

Camera focal length cancels out of this formula algebraically — it's fully determined by the vanishing point position and `eyeH`. Width is the ground-plane distance between the two edge lines at a given depth, times `scaleFactor` (see below). **This core formula has not changed since the app was first built** — verified by a direct diff against an earlier reference copy during this session.

---

## 3. Calibration

`scaleFactor` is a correction multiplier applied on top of the raw perspective formula, absorbing whatever the idealized model doesn't capture (lens distortion, small errors in `eyeH`, etc.).

**A wrong `eyeH` doesn't actually matter once `scaleFactor` is calibrated.** An `eyeH` error is a pure multiplicative constant in the width formula — a `scaleFactor` fit from any known width, at any depth, with a correctly-placed vanishing point, cancels that constant exactly, and the correction stays valid on future photos too. This is why Method 2 no longer tries to independently solve `eyeH` (it used to) — it added noise for no accuracy benefit. `eyeH` now always comes from login height.

### Method 1 — "I know the exact footpath width"

1. Position the Building edge and Kerb edge lines on a feature of known width in the photo (a measured footpath section, a paver, etc.).
2. Enter that width in mm.
3. `scaleFactor(method1) = knownWidth / rawComputedWidth`.

This reuses whatever photo is already loaded for measurement — no fresh capture required. The Building/Kerb overlay stays visible and draggable specifically during this step (it's hidden for every other calibration step, where it'd just be stale clutter).

### Method 2 — "Place an A4 sheet on the footpath"

Tap the sheet's 4 corners **in order: top-left, top-right, bottom-right, bottom-left**. The app draws the rectangle as you go, connecting taps in that same order — a mis-tap shows up immediately as a visibly crossed/twisted shape rather than a clean rectangle. On the 4th tap it computes automatically; there's no follow-up question.

What it solves, geometrically, from those 4 points:
- **Vanishing point** — the sheet's two long sides (top-left↔bottom-left and top-right↔bottom-right) are parallel in reality, so their intersection in the photo *is* the vanishing point. This is the one part of Method 2 that's sensitive to tap precision, because a single sheet's edges are short and close to the camera — see the tip below.
- **Scale factor** — using that vanishing point and the login-derived `eyeH`, the known 297mm width is checked at both the near and far edge of the sheet, and the two results are averaged.

**Tip for better accuracy: stack multiple A4 sheets front-to-back, in the direction of travel (not side-by-side), before tapping.** Tap the four *outer* corners of the stack. This lengthens the vanishing-point baseline without changing any of the math (the tapped width edges are still a single sheet's 297mm regardless of how many sheets are stacked behind it) — tested empirically this session: a single sheet's scale factor swung 0.73×–1.63× under ±2px of tap noise; four stacked sheets tightened that to 0.87×–1.18×, roughly a 3× improvement.

Side-by-side stacking would *not* work without a code change, since that changes the known-width constant.

### Merging both methods

Method 1 and Method 2 are calibrated **independently** — recalibrating one never overwrites the other. The active `scaleFactor` used for measurement is:
- The **average** of both, if both have been done.
- Whichever one exists, if only one has.
- `1.0` (uncalibrated), if neither has.

The result screen shows the breakdown, e.g. *"Averaged — Method 1: 1.020×, Method 2: 0.980×"*, or a nudge to add the second method if only one is on file.

### Calibration identity and sync

Calibration is keyed on **email + phone model** (`fp_cal_<model>` locally, scoped to the logged-in email's session). Both methods' scale factors, plus `eyeH`, are synced to the `Calibration` sheet tab on every successful calibration — see [§8](#8-google-apps-script-setup) for the schema. This lets:
- The same person resume on a second device without recalibrating.
- The batch pipeline ([§7](#7-batch-measurements-pipeline)) look up a surveyor's calibration by email, from any device.

**Reset** clears both methods' saved values for the current phone model and returns to the uncalibrated state.

---

## 4. Calibration screen flow

Tapping "Calibrate" (header flask-adjacent icon, or the status box's "Add Calibration"/"Recalibrate" button) swaps the section **below** the photo into a short flow — the photo itself never moves or gets covered by a modal:

1. **Choose method** — two cards, "1 · I know the exact footpath width" / "2 · Place an A4 sheet on the footpath", plus a "← Back to Measurement" link. An info card shows the current phone, scale, and camera height (read-only).
2. **Method interaction** — Method 1's width input, or Method 2's 4-corner tap flow (progress dots fill in as each corner is tapped).
3. **Result** — "Calibrated ✓ — Scale factor: X.XXX×" plus the method breakdown, and a single **Test Measurement →** button back to normal view.

**Calibration status box**, shown just below the photo at all times outside the flow itself:
- **Not calibrated:** a prompt + "Add Calibration" button.
- **Calibrated:** current scale factor (green) + "Recalibrate" button.

---

## 5. Measurement workflow

Once a photo is loaded and the Building/Kerb edges are positioned:

- **Footpath width (mm)** shown live, computed from the current geometry × `scaleFactor`.
- An optional **Tape measure (mm)** field compares the computed width against a physical spot-check measurement — separate from calibration.
- An optional **property line** (offset), activated via its corner knob, for a secondary width (e.g. a building setback).
- **Pan controls** (top-right, below the property-line knob) and pinch-zoom both work for precise line placement; pinch is amplified (exponent-based, not 1:1) for more responsive feel, and every touch point gets proper pointer capture so multi-finger gestures don't randomly drop.
- **Grading** is purely width-based:

  | Width | Grade |
  |---|---|
  | < 900mm | narrow |
  | 900–1799mm | marginal |
  | ≥ 1800mm | accessible |

- **Submit** logs the record to the Sheet and resets the view for the next photo (VP lock is preserved across resets; edge locks are not).
- Records also export locally as CSV (`footpath_widths_YYYY-MM-DD.csv`), independent of the Sheet.

---

## 6. Process Measurements (admin-only)

A separate feature from the interactive workflow above — a flask-icon button in the header that runs the batch pipeline ([§7](#7-batch-measurements-pipeline)) over every pending row in the `Measurements` sheet tab.

**Restricted to one email**, set in ⚙ Settings → Admin Email. Everyone else doesn't see the button, and the underlying function refuses to run for them even if triggered another way. This is a **UI-level restriction only** — there's no real backend authentication, so it's not protection against someone deliberately working around it via dev tools, just against ordinary surveyors stumbling into a tool that isn't meant for them.

Requires: signed in with Google (for reading photos from Drive), Apps Script URL configured, and each surveyor whose rows are being processed must already have a calibration on file.

---

## 7. Batch Measurements pipeline

This is a **separate system** from everything above — it doesn't touch `scaleFactor`, `eyeH`, or any of the interactive calibration logic beyond reading the final numbers. It runs entirely client-side (needs real pixel access via `<canvas>`, which Apps Script cannot do at all).

**Input:** each pending row supplies an annotated photo (`original_image` preferred — a plain style with just the two lines and a vp marker, no legend clutter; `annotated_image` as a fallback for older rows with a fuller segmentation overlay and a legend box).

**Color convention in the annotated image** (confirmed against real samples, not guessed):
- **Pink** = road/kerb edge — RGB(~220,115,160), matched by `r>170 && b>130 && (r-g)>40 && (b-g)>20`
- **Green** = building edge — RGB(~40,165,20), matched by `g>140 && (g-r)>50 && (g-b)>50`
- **Vanishing point marker** — a small dot the annotation model already computed, trusted over any self-derived estimate:
  - **Yellow** (RGB ≈250,250,30) is tried first — the `original_image` style's marker, no legend to worry about.
  - **Blue** (RGB ≈10-40,50-75,200-235) is tried next, with a fixed bottom-right legend-corner exclusion zone (the fully-annotated style's own legend has a blue "vanishing point" swatch there).
  - Only if neither marker is found does it fall back to computing its own vp from the pink/green lines' intersection, with a plausibility check (must sit above the detected lines, not wildly outside the frame) before trusting it.

**Processing steps per row**, all in the browser:
1. Fetch calibration for `row.surveyor` (by email) — skip with a clear "needs calibration" flag if none on file, collected into an end-of-run summary so it's obvious who to follow up with.
2. Download the image via the Drive API (using the signed-in Google token — avoids canvas cross-origin taint issues that a plain `<img>` fetch would hit).
3. Scan for pink/green pixels, fit a line to each (`x = m·y + c` regression, robust to a light single-pass outlier rejection).
4. Find the vp marker (see above).
5. Compute the width as the **median across many rows sampled in the bottom 35% of the detected line range** — not a single reference row. Rows close to the vanishing point are extremely sensitive to tiny fitting errors (tested: estimates spiked as high as 10,000mm from the same detection, evaluated a few dozen pixels closer to the horizon); the bottom-band + median approach is far more stable. The spread across those samples (median absolute deviation) doubles as a confidence check — over 25% relative spread and the row is rejected rather than written.
6. Sanity-check the final width (300–6000mm plausible range) before writing.
7. Write back to `footpath_width_by_model`, matched by `(s_code, point_code)` first (falls back to the row index from the initial read only if no key match is found) — safer given the sheet keeps growing between when a run starts and when each row finishes.

**Auth expiry mid-run** is handled explicitly — if the Google token expires partway through a long batch, the run stops with one clear message instead of cascading a confusing error on every remaining row.

---

## 8. Google Apps Script setup

The app talks to a single Apps Script Web App endpoint (`APPS_SCRIPT_URL`) via `POST`, dispatching on an `action` field. The functions your script needs are in `apps_script_additions.gs` — merge them into whatever `doPost()` dispatcher you already have (it likely already handles `logRow`/`ping`).

| Action | Purpose |
|---|---|
| `ping` | Connectivity check |
| `logRow` | Appends a measurement record (existing, from before this doc) |
| `logCalibration` | Appends a row to the `Calibration` tab |
| `getCalibration` | Looks up the most recent `{eyeH, scaleFactor}` for a surveyor email |
| `logHeight` | Upserts a surveyor's `{name, phone, heightCM}` in the `Surveyors` tab (only overwrites fields actually provided) |
| `getHeight` | Looks up a surveyor's `{name, phone, heightCM}` by email |
| `listMeasurements` | Returns pending `Measurements` rows (missing `footpath_width_by_model`, has an image) |
| `updateMeasurementWidth` | Writes a computed width back, matched by `(s_code, point_code)` |

### `Calibration` tab schema (append-only history; `getCalibration` reads the most recent per email)

| Column | Field |
|---|---|
| A | `surveyor` (email) |
| B | `model` |
| C | `eyeH` |
| D | `scaleFactor` — the active, already-averaged value; this is what the batch pipeline reads |
| E | `method1ScaleFactor` — stored for transparency/debugging only |
| F | `method2ScaleFactor` — stored for transparency/debugging only |
| G | `time` |

### `Surveyors` tab schema (one row per email, upserted)

| Column | Field |
|---|---|
| A | `surveyor` (email) |
| B | `name` |
| C | `phone` |
| D | `heightCM` |
| E | `time` |

### `Measurements` tab — expected columns

`s_code`, `point_code`, `surveyor` (email — the sheet's own header was seen written as `suryevor` at one point; both spellings are read defensively, worth double-checking which is actually there), `Lat_long`, `annotated_image`, `original_image` (assumed header name — not confirmed against the real sheet), `footpath_width_surveyor`, `footpath_width_by_model`. Missing required columns cause `listMeasurements` to fail loudly with the specific missing name, rather than silently reading `undefined` into rows.

---

## 9. Known limitations / things worth knowing

- `scaleFactor` is an average correction and can't fully compensate for lens distortion that varies by position in frame (worse on wide/ultra-wide lenses) — a well-composed photo still matters.
- Method 2's vanishing-point estimate is the most tap-sensitive part of the whole app, because it comes from a physically small object close to the camera — see the stacking tip in §3.
- Neither calibration method independently verifies its own accuracy against ground truth; averaging Method 1 and Method 2 reduces noise but doesn't catch a *shared* bias (e.g. both done with a mis-measured reference).
- The batch pipeline's color thresholds are calibrated against two real sample photos, not a large dataset — if detection starts failing on new samples, that's the first place to check.
- `original_image` as a column name is an assumption, not a confirmed fact — verify against the actual sheet header.
- The admin-only restriction on Process Measurements is UI-level, not real backend security.
