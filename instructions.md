# Feature Plan: Two-Period Comparison & Acquisition Date Reporting

Status: Proposal
Scope: `app.py`, `functions2.py`, `run.ipynb`, tests

---

## 1. Goals

1. **Compare two periods.** Let a user define two date ranges (`period_a`, `period_b`)
   over the same polygon and product, then produce:
   - both individual composites (as today), and
   - a **difference product** (B − A) for the selected index or band set.
2. **Report when the imagery was taken.** Surface, for each period:
   - the requested date range (already known), and
   - the **acquisition datetimes of the Sentinel scenes that actually contributed**,
     plus a per-scene cloud-cover summary where available.

Non-goals (this document): chatbot/LLM summaries, SAR two-period diff, persistent
job history, database storage.

---

## 2. Current behaviour (baseline)

- One polygon, one date range, one product per run.
- Product is a **temporal mean** composite over the range → no single capture time.
- Bounds enforced by config:
  - `EO_MAX_AREA_KM2` (default `100`) — geodesic bounding-box area.
  - `EO_MAX_DAYS` (default `90`) — max interval, inclusive start / exclusive end.
- One batch job at a time; progress polled every 5 s.
- Results are temporary (~1 h inactivity); a new run or logout clears the previous run.
- Functions: `tcc`, `tcc_masked`, `fcc`, `fcc_masked`, `nbr`, `ndvi`, `sar`.
- `submit_product` creates an unstarted job; `collect_product` gathers results.
- Returns `ProcessingResult` (raster paths, preview path, caller-owned figure).

**Constraint to respect:** two periods ≈ double quota, double wall time, and two
temporary result sets. The UI must make this explicit.

---

## 3. Part 1 — Two-Period Comparison

### 3.1 Data model changes

Introduce a period descriptor instead of bare start/end strings:

```python
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Period:
    label: str          # "A" or "B" (or user-supplied)
    start: date         # inclusive
    end: date           # exclusive
    product: str        # one of: tcc, tcc_masked, fcc, fcc_masked, nbr, ndvi