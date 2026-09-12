<script>
    export let data = [];
    export let title = 'Technique profile with 90% intervals';

    const COLORS = ['#32d3f4', '#ff4050'];
    const num = (value) => value == null ? null : Number(value);
    let clientWidth = 900;

    $: rows = (data || []).map((row) => ({
        ...row,
        estimate: num(row.estimate),
        lo: num(row.lo),
        hi: num(row.hi)
    })).filter((row) => row.estimate != null);
    $: metrics = [...new Set(rows.map((row) => row.metric_label))];
    $: drivers = [...new Set(rows.map((row) => row.driver_name))];
    $: width = Math.max(300, clientWidth || 900);
    $: mobile = width < 560;
    $: pad = { left: mobile ? 118 : 190, right: 28, top: 48, bottom: 34 };
    $: rowHeight = mobile ? 74 : 68;
    $: height = pad.top + Math.max(1, metrics.length) * rowHeight + pad.bottom;
    $: values = rows.flatMap((row) => [row.estimate, row.lo, row.hi]).filter((value) => value != null);
    $: extent = Math.max(1, ...values.map((value) => Math.abs(value))) * 1.15;
    $: x = (value) => pad.left + ((value + extent) / (2 * extent)) * (width - pad.left - pad.right);
    $: y = (metric) => pad.top + metrics.indexOf(metric) * rowHeight + rowHeight / 2;
</script>

<div class="dna-profile" bind:clientWidth data-testid="driver-dna-profile">
    <div class="heading">
        <strong>{title}</strong>
        <span>0 = teammate-normalised median</span>
    </div>
    <div class="legend">
        {#each drivers as driver, index}
            <span><i style="background:{COLORS[index % COLORS.length]}"></i>{driver}</span>
        {/each}
    </div>
    {#if rows.length}
        <svg viewBox="0 0 {width} {height}" width="100%" height={height} role="img" aria-label={title}>
            {#each metrics as metric}
                <line class="axis-line" x1={pad.left} x2={width-pad.right} y1={y(metric)} y2={y(metric)} />
                <line class="zero-line" x1={x(0)} x2={x(0)} y1={y(metric)-24} y2={y(metric)+24} />
                <text class="metric-label" x={pad.left-12} y={y(metric)+4} text-anchor="end">{metric}</text>
                <text class="edge-label" x={pad.left} y={y(metric)+25} text-anchor="start">less</text>
                <text class="edge-label" x={width-pad.right} y={y(metric)+25} text-anchor="end">more</text>
                {#each rows.filter((row) => row.metric_label === metric) as row}
                    {@const index = drivers.indexOf(row.driver_name)}
                    {@const cy = y(metric) + (index === 0 ? -8 : 8)}
                    {#if row.lo != null && row.hi != null}
                        <line class="interval" x1={x(row.lo)} x2={x(row.hi)} y1={cy} y2={cy} stroke={COLORS[index % COLORS.length]} />
                    {/if}
                    <circle cx={x(row.estimate)} cy={cy} r="5" fill={COLORS[index % COLORS.length]} tabindex="0">
                        <title>{row.driver_name} · {metric}: {row.estimate.toFixed(2)} ({row.lo?.toFixed(2) ?? '—'} to {row.hi?.toFixed(2) ?? '—'})</title>
                    </circle>
                {/each}
            {/each}
            <text class="scale-label" x={pad.left} y="24">robust standard deviations from teammate</text>
        </svg>
    {:else}
        <div class="empty" role="status">No publishable profile for this selection. A driver needs at least five eligible teammate comparisons.</div>
    {/if}
</div>

<style>
    .dna-profile { width: 100%; margin: 1rem 0 1.5rem; padding: 1rem; border: 1px solid rgba(160,174,201,.18); border-radius: .95rem; background: rgba(255,255,255,.025); }
    .heading { display: flex; justify-content: space-between; gap: 1rem; color: #f4f7fb; }
    .heading span, .edge-label, .scale-label { fill: #8f9bae; color: #8f9bae; font-size: 11px; }
    .legend { display: flex; flex-wrap: wrap; gap: 1rem; margin-top: .35rem; color: #aeb8c7; font-size: 13px; }
    .legend span { display: inline-flex; align-items: center; gap: 5px; }
    .legend i { width: 12px; height: 3px; border-radius: 2px; }
    .axis-line { stroke: currentColor; stroke-opacity: .17; }
    .zero-line { stroke: currentColor; stroke-opacity: .42; stroke-dasharray: 3 3; }
    .interval { stroke-width: 3; stroke-opacity: .55; stroke-linecap: round; }
    .metric-label { fill: #dce3ed; font-size: 12px; font-weight: 650; }
    .empty { margin-top: 1rem; padding: 2rem 1rem; border: 1px dashed rgba(160,174,201,.25); border-radius: .7rem; color: #9ba7ba; text-align: center; }
    @media (max-width: 560px) {
        .dna-profile { padding: .75rem .4rem; }
        .heading { align-items: flex-start; flex-direction: column; padding: 0 .4rem; }
        .legend { padding: 0 .4rem; }
        .metric-label { font-size: 10px; }
    }
</style>
