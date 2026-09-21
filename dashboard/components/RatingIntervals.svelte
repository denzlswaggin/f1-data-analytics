<script>
    export let data = [];
    export let title = 'Model estimates and 90% resampling intervals';
    export let valueLabel = 'rating';
    export let note = 'Points are fitted ratings; lines are individual 90% resampling intervals. * Interval unavailable.';
    const finite = (value) => value != null && Number.isFinite(Number(value));
    $: rows = Array.from(data ?? []).filter((row) => finite(row.rating));
    $: values = rows.flatMap((row) => [row.rating, row.rating_lo, row.rating_hi]).filter(finite).map(Number);
    $: lower = Math.min(0, ...values);
    $: upper = Math.max(0, ...values);
    $: span = Math.max(0.1, upper - lower);
    $: x = (value) => 205 + ((Number(value) - lower) / span) * 390;
    $: ticks = Array.from({ length: 5 }, (_, index) => lower + span * index / 4);
</script>

<figure>
    <figcaption>{title}</figcaption>
    {#if rows.length > 0}
    <div class="scroll">
        <svg viewBox={`0 0 800 ${50 + rows.length * 32}`} role="img" aria-label={title}>
            {#each ticks as value}
                <line class="grid" x1={x(value)} x2={x(value)} y1="26" y2={rows.length * 32 + 28} />
                <text x={x(value)} y="15" text-anchor="middle">{value.toFixed(2)}</text>
            {/each}
            {#each rows as row, index}
                <g transform={`translate(0, ${44 + index * 32})`}>
                    <title>{row.driver_name}: {Number(row.rating).toFixed(3)}; 90% interval {row.rating_lo ?? 'unavailable'} to {row.rating_hi ?? 'unavailable'}; {row.n_comparisons} comparisons</title>
                    <text x="0" y="4">{row.driver_name}</text>
                    {#if finite(row.rating_lo) && finite(row.rating_hi)}
                        <line class="interval" x1={x(row.rating_lo)} x2={x(row.rating_hi)} y1="0" y2="0" />
                    {/if}
                    <circle cx={x(row.rating)} cy="0" r="4" />
                    <text x="620" y="4">{Number(row.rating).toFixed(3)} / n={row.n_comparisons}{!finite(row.rating_lo) || !finite(row.rating_hi) ? ' *' : ''}</text>
                </g>
            {/each}
        </svg>
    </div>
    <div class="compact">
        {#each rows as row}
            <div class="rating-row">
                <strong>{row.driver_name}</strong><span>{Number(row.rating).toFixed(3)}</span>
                <p>90% interval: {finite(row.rating_lo) && finite(row.rating_hi) ? `${Number(row.rating_lo).toFixed(3)} to ${Number(row.rating_hi).toFixed(3)}` : 'unavailable'} · {row.n_comparisons} comparisons</p>
                <svg viewBox="195 -8 410 16" role="img" aria-label={`${row.driver_name}: ${valueLabel} ${Number(row.rating).toFixed(3)}`}>
                    <line class="grid" x1={x(0)} x2={x(0)} y1="-8" y2="8" />
                    {#if finite(row.rating_lo) && finite(row.rating_hi)}
                        <line class="interval" x1={x(row.rating_lo)} x2={x(row.rating_hi)} y1="0" y2="0" />
                    {/if}
                    <circle cx={x(row.rating)} cy="0" r="4" />
                </svg>
            </div>
        {/each}
    </div>
    <p>{note}</p>
    {:else}
    <p>No estimates meet the selected evidence filter.</p>
    {/if}
</figure>

<style>
    figure { margin: 1.5rem 0; max-width: 100%; }
    figcaption { font-weight: 650; margin-bottom: 1rem; }
    .scroll { overflow-x: auto; max-width: 100%; }
    svg { width: 100%; min-width: 760px; }
    text { fill: currentColor; font-size: 12px; }
    .grid { stroke: currentColor; opacity: .15; }
    .interval { stroke: #32d3f4; stroke-width: 3; }
    circle { fill: #f7c948; }
    p { color: #aab6c6; font-size: .85rem; }
    .compact { display: none; }
    .rating-row { display: grid; grid-template-columns: 1fr auto; gap: .4rem; padding: .85rem 0; border-bottom: 1px solid var(--dashboard-border); font-variant-numeric: tabular-nums; }
    .rating-row p { grid-column: 1 / -1; margin: 0; }
    .rating-row svg { grid-column: 1 / -1; min-width: 0; height: 24px; }
    @media (max-width: 640px) { .scroll { display: none; } .compact { display: block; } }
</style>
