# Model estimates are not calibrated probabilities

The driver comparison page previously converted each marginal 90% rating range
to a normal standard error, combined the two as if independent and applied a
logistic approximation. Neither joint bootstrap draws nor their dependence were
available to that calculation. The resulting number was presented as the
probability that Driver A was faster. On the published 2026 Verstappen/Hamilton
ratings, the formula produced approximately 99.9%; this was an unvalidated
transformation, not an established faster-driver probability.

The page now displays the fitted rating difference, the original individual
resampling ranges and each driver's comparison count for shared seasons only.
It does not construct a paired interval or probability from marginal summaries.
Selecting the same driver gives a zero difference. Missing shared seasons show
an explicit empty state. The default Hamilton ID is corrected to `hamilton`.
The underlying ratings remain model estimates, with their existing modelling
assumptions and limitations; this change does not independently validate them.

Replay events previously multiplied the detector's heuristic confidence score
by 100 and displayed a percent confidence. The event label now identifies a
model-detected pass and says event accuracy is unverified. The underlying score
and detector evidence remain available in the data for audit, without presenting
the score as a probability to the viewer. The legacy embedded track map and its
event timeline use the same unverified-model wording.

The race cockpit removes average confidence percentages and obtains pass counts
from verified processing coverage. A processed zero stays zero; unavailable or
unverified processing shows an unavailable state. Tests cover both cases, shared
and disjoint seasons, same-driver comparisons, exact preservation of marginal
ranges and sample counts, and replay event wording. Browser smoke tests require
the default driver pair to render the model-difference metric.
