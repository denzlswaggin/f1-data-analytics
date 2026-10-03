# Validating the driver-rating model

This report preserves an evaluation on a wider historical dataset. The active
product now uses [2024–2026 only](data-context.md); the figures below are not
valid measurements for that shorter window. Re-run the validation before citing
current model performance.

The headline insight ([teammate-normalised "true pace"](blog-teammate-normalised-pace.md))
produces a single cross-era leaderboard by fitting a per-driver pace deficit to every
observed teammate qualifying gap. A least-squares fit will *always* return a ranking —
the real question is whether that ranking means anything out of sample. This page is the
honest answer: three checks, all reproducible with

```bash
python -m analytics.cli validate      # backtest + shrinkage sweep + bootstrap CIs
```

Code: `analytics/validation.py` (pure functions, unit-tested in `tests/test_validation.py`).
Numbers below describe the historical 2006–2026 evaluation (8,424 directed
teammate gaps, 101 rated drivers). They are not automatically refreshed when
a new serving snapshot is published.

## 1. Does the rating predict the *future*? (temporal backtest)

Expanding-window hold-out: for each test season `Y`, fit ratings on **every comparison
before `Y`**, then predict `Y`'s teammate gaps from the fitted deficits — scoring only
pairings whose both drivers were already rated. Predicted gap for `(i, j)` is
`deficit_i − deficit_j`, exactly what the solver drives toward on the training edges.

| Metric | Result | Read |
| --- | --- | --- |
| Race-level sign accuracy | **0.605** | The higher-rated driver out-qualifies their teammate 60.5% of individual sessions (vs 0.50 chance), over **2,453** out-of-sample predictions in 16 test seasons. |
| Season-battle sign accuracy | **0.680** | Averaging each pair's races into one season-long battle (**147** of them), the rating calls the winner 68.0% of the time. |
| Correlation (r) | 0.111 | Weak but positive linear agreement on magnitudes. |
| MAE vs predict-zero baseline | 0.64 vs 0.62 (skill −0.03) | **No single-race magnitude skill** — see below. |

**Honest interpretation.** The rating has clear *ordinal* predictive power — it knows who
is faster — and that signal strengthens as you average out noise (60.5% per race → 68.0%
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
| 0 (pure least-squares) | 0.883 | 0.75 | 0.483 |
| 2 | 0.970 | 0.90 | 0.354 |
| 4 | 0.989 | 0.90 | 0.307 |
| **8 (default)** | 1.000 | 1.00 | 0.256 |
| 16 | 0.989 | 0.95 | 0.202 |
| 32 | 0.961 | 0.85 | 0.152 |

Rank order is **highly stable** (Spearman ≥ 0.88 everywhere, ≥ 0.97 across a wide 2–16
band); the prior only compresses the *spread* (mean |rating| shrinks from 0.48 → 0.15), as
intended. `prior_weight = 8` is a safe middle, not a tuned-to-flatter choice.

## 3. How sure are we of each rating? (bootstrap CIs)

Resample undirected teammate comparison edges with replacement, restore both
directions, refit and repeat. The percentile spread is each driver's sampling
interval (`bootstrap_ratings`, deterministic given a seed). This static-model
procedure does not cluster different teams from the same weekend. The dynamic
model uses a separate weekend-cluster bootstrap.

| # | Driver | Rating | 90% CI | in-boot |
| ---: | --- | ---: | --- | ---: |
| 1 | Verstappen | 0.919 | [0.48, 1.56] | 300/300 |
| 2 | Sato | 0.878 | **[0.35, 1.39]** | 300 |
| 3 | Davidson | 0.840 | **[0.42, 1.20]** | 300 |
| 4 | Russell | 0.619 | [0.37, 0.92] | 300 |
| 5 | Leclerc | 0.559 | [0.37, 0.75] | 300 |
| 7 | Vettel | 0.462 | [0.33, 0.59] | 300 |
| 9 | Norris | 0.433 | **[−0.07, 0.88]** | 300 |

The intervals describe uncertainty in individual ratings, not the probability
of occupying an exact rank. Verstappen has the highest point estimate in this
historical fit, but these intervals alone do not establish a robust number-one
position. Sato and Davidson have wide intervals and sparse network connections;
their nominal positions should be treated cautiously. Norris's interval crosses
the model's zero baseline; this is not a test of every pairwise ranking.

## Takeaway

The historical backtest supports some directional predictive signal, while
single-session magnitude prediction does not beat the zero-gap baseline. The
reported sensitivity checks and individual intervals help assess uncertainty;
they do not certify exact rank order, isolate driver talent or establish future
accuracy on a newly published snapshot.
