# Dashboard design review

Implementation branch: `design/dashboard-polish`.

The review preserves the dark motorsport theme while giving charts and their
interpretation more prominence than navigation, metadata and decoration.

| Review area | Implemented change |
| --- | --- |
| Page hierarchy | Compact analytical headers; the homepage retains its hero. |
| Colour semantics | Neutral navigation, disclosures and links; categorical charts start with cyan rather than red. Warning and missing-evidence text remains explicit. |
| Chart placement | Pace and telemetry use one race/driver panel. Detailed eligibility explanations and the telemetry lap table are progressively disclosed. Essential comparison limits remain visible. |
| Navigation | Three native disclosure groups, unique destinations, a visible scrollbar, automatic opening of the active category, and three related links per analysis. |
| Decoration | Flat filter bars, restrained insight backgrounds, no decorative heading markers or chart shadows. |
| Metrics | Shared BigValue styling across layouts, adaptive homepage columns and tabular numerals; arbitrary card-position colours removed. Existing metric-specific units and precision are retained. |
| Readability | Larger navigation metadata, heatmap labels and replay captions; readable table headings. |
| Data disclosures | One chevron convention, consistent neutral focus and hover, responsive coverage text, and explicit insufficient-evidence states. |
| Homepage | Three featured entry points and an adaptive secondary catalogue. |
| Long analyses | Section links for DNA, ratings and telemetry; scope labels for local filters; repeated driver/season context at the DNA heatmap. |
| Freshness | Unknown freshness is not rendered as current. The sidebar no longer claims the snapshot is online. |
| Replay consistency | Matching panel colours, muted text, focus rings, control radii and minimum heights. Mobile replay controls have larger touch targets. |
| Narrow layouts | Two-column filter controls, compact rating intervals, horizontal heatmap labels, sticky driver labels, native button activation and a persistent detail area outside the scrolling heatmap. |

## Verification

- Evidence strict production build checks all dashboard pages.
- Replay Svelte check and production build check its styles and component output.
- `npm --prefix dashboard run test:presentation` checks freshness, related-link
  context, navigation uniqueness and preservation of rating uncertainty.
- `npm --prefix dashboard run test:interactions` checks heatmap activation,
  selection refresh, active navigation groups and mobile-menu state.
- `npm --prefix dashboard run test:dropdown` checks asynchronous option changes,
  linked selections and the combined four-control race/duel panel.
- Generated HTML is checked for valid section-link targets and filter scopes.

Visual verification at desktop, notebook and phone widths is still outstanding:
the Browser runtime reported no available browser. DOM tests and successful
builds do not establish visual layout quality or prove absence of overflow.
