<script>
    export let data = [];
    export let title = 'Rates and 90% intervals';
    $: rows = Array.from(data ?? []);
    const x = (value) => 250 + Math.max(0, Math.min(100, Number(value))) * 4.4;
</script>

<figure>
    <figcaption>{title}</figcaption>
    <div class="scroll">
        <svg viewBox={`0 0 860 ${50 + rows.length * 30}`} role="img" aria-label={title}>
            {#each [0, 25, 50, 75, 100] as tick}
                <line x1={x(tick)} x2={x(tick)} y1="25" y2={30 + rows.length * 30} class="grid" />
                <text x={x(tick)} y="15" text-anchor="middle">{tick}%</text>
            {/each}
            {#each rows as row, i}
                <g transform={`translate(0, ${43 + i * 30})`}>
                    <title>{row.driver_code} {row.role}: {Number(row.rate_pct).toFixed(1)}%, 90% interval {Number(row.lower_pct).toFixed(1)}?{Number(row.upper_pct).toFixed(1)}%, n={row.opportunities}</title>
                    <text x="0" y="4">{row.driver_code} ? {row.role}</text>
                    <line x1={x(row.lower_pct)} x2={x(row.upper_pct)} y1="0" y2="0" class="interval" />
                    <circle cx={x(row.rate_pct)} cy="0" r="4" />
                    <text x="710" y="4">{Number(row.rate_pct).toFixed(1)}% ? n={row.opportunities}</text>
                </g>
            {/each}
        </svg>
    </div>
</figure>

<style>
    figure { margin: 1.5rem 0; }
    figcaption { font-weight: 600; margin-bottom: 1rem; }
    .scroll { overflow-x: auto; }
    svg { width: 100%; min-width: 720px; color: var(--text-primary, #dce5ef); }
    text { fill: currentColor; font-size: 12px; }
    .grid { stroke: currentColor; opacity: 0.15; }
    .interval { stroke: #32d3f4; stroke-width: 3; }
    circle { fill: #f7c948; }
</style>
