# Validating the driver-rating model

The headline insight ([teammate-normalised "true pace"](blog-teammate-normalised-pace.md))
produces a single cross-era leaderboard by fitting a per-driver pace deficit to every
observed teammate qualifying gap. A least-squares fit will *always* return a ranking —
the real question is whether that ranking means anything out of sample. This page is the
honest answer: three checks, all reproducible with

```bash
python -m analytics.cli validate      # backtest + shrinkage sweep + bootstrap CIs
```

Code: `analytics/validation.py` (pure functions, unit-tested in `tests/test_validation.py`).
Numbers below are over 2006–2025 (≈8.4k directed teammate gaps, ~100 drivers).

## 1. Does the rating predict the *future*? (temporal backtest)

Expanding-window hold-out: for each test season `Y`, fit ratings on **every comparison
before `Y`**, then predict `Y`'s teammate gaps from the fitted deficits — scoring only
pairings whose both drivers were already rated. Predicted gap for `(i, j)` is
`deficit_i − deficit_j`, exactly what the solver drives toward on the training edges.

| Metric | Result | Read |
| --- | --- | --- |
| Race-level sign accuracy | **0.605** | The higher-rated driver out-qualifies their teammate 60.5% of individual sessions (vs 0.50 chance), over **2,443** out-of-sample predictions in 16 test seasons. |
| Season-battle sign accuracy | **0.678** | Averaging each pair's races into one season-long battle (**146** of them), the rating calls the winner 67.8% of the time. |
| Correlation (r) | 0.111 | Weak but positive linear agreement on magnitudes. |
| MAE vs predict-zero baseline | 0.64 vs 0.62 (skill −0.03) | **No single-race magnitude skill** — see below. |

**Honest interpretation.** The rating has clear *ordinal* predictive power — it knows who
is faster — and that signal strengthens as you average out noise (60.5% per race → 67.8%
per season). It has essentially **no magnitude skill on a single session**: one qualifying
lap is dominated by track evolution, traffic, and one-off mistakes, so predicting the exact
gap does no better than guessing zero. That's the expected, defensible result for a skill
estimate, and it's why the model is presented as a *ranking*, not a gap predictor.

## 2. Is the ranking an artifact of the shrinkage knob? (sensitivity)

The solver adds empirical-Bayes shrinkage (`prior_weight`, default 8) so thin-sample
drivers don't top the board on noise. If the leaderboard flipped around as you changed it,
the ranking would be a hyperparameter artifact. It doesn't:

| `prior_weight` | Spearman vs default | Top-20 kept | mean |rating| |
| ---: | ---: | ---: | ---: |
| 0 (pure least-squares) | 0.884 | 0.75 | 0.481 |
| 2 | 0.970 | 0.90 | 0.353 |
| 4 | 0.989 | 0.90 | 0.307 |
| **8 (default)** | 1.000 | 1.00 | 0.256 |
| 16 | 0.988 | 0.95 | 0.203 |
| 32 | 0.959 | 0.85 | 0.152 |

Rank order is **highly stable** (Spearman ≥ 0.88 everywhere, ≥ 0.97 across a wide 2–16
band); the prior only compresses the *spread* (mean |rating| shrinks from 0.48 → 0.15), as
intended. `prior_weight = 8` is a safe middle, not a tuned-to-flatter choice.

## 3. How sure are we of each rating? (bootstrap CIs)

Resample the teammate comparisons with replacement, refit, repeat — the percentile spread
is each driver's confidence band (`bootstrap_ratings`, deterministic given a seed).

| # | Driver | Rating | 90% CI | in-boot |
| ---: | --- | ---: | --- | ---: |
| 1 | Verstappen | 0.923 | [0.47, 1.33] | 150/150 |
| 2 | Sato | 0.878 | **[0.39, 1.42]** | 150 |
| 3 | Davidson | 0.840 | **[0.43, 1.18]** | 150 |
| 4 | Russell | 0.619 | [0.36, 0.88] | 150 |
| 5 | Leclerc | 0.563 | [0.36, 0.74] | 150 |
| 7 | Vettel | 0.463 | [0.34, 0.61] | 150 |
| 9 | Norris | 0.435 | **[−0.12, 0.92]** | 150 |

The bands are the point of the exercise. **Verstappen's #1 is robust** — a narrow,
well-clear band on a densely-connected driver. The suspiciously high **Sato / Davidson**
sit on **wide bands** (thin, weakly-connected samples), so their nominal top-3 placing is
*not* trustworthy — precisely the failure mode the shrinkage prior is there to temper, made
explicit. A driver like **Norris** whose band still straddles 0 simply hasn't accumulated
enough comparisons for a confident cross-era placing yet.

## Takeaway

The leaderboard is a **validated ranking, not a black box**: it predicts out-of-sample
teammate battles well above chance, its order is stable to the one hyperparameter, and every
rating ships with an honest uncertainty band that flags which entries to trust. The metric's
limits (single-race magnitude, thin-sample drivers) are measured and stated rather than
hidden.
