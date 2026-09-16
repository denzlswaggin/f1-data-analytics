<script>
    export let data = [];
    export let title = 'How the profile evolved race by race';

    const num = (value) => value == null ? null : Number(value);
    let clientWidth = 900;
    $: rows = (data || []).map((row) => ({
        ...row,
        race_index: num(row.race_index),
        value: num(row.value),
        rolling_value: num(row.rolling_value)
    })).filter((row) => row.race_index != null && row.value != null);
    $: metrics = [...new Set(rows.map((row) => row.metric_label))];
    $: width = Math.max(300, clientWidth || 900);
    $: mobile = width < 620;
    $: pad = { left: mobile ? 116 : 180, right: 24, top: 36, bottom: 42 };
    $: panelHeight = mobile ? 100 : 92;
    $: height = pad.top + Math.max(1, metrics.length) * panelHeight + pad.bottom;
    $: maxIndex = Math.max(1, ...rows.map((row) => row.race_index));
    $: extent = Math.max(1, ...rows.flatMap((row) => [row.value, row.rolling_value]).filter((value) => value != null).map((value) => Math.abs(value))) * 1.12;
    $: x = (index) => pad.left + ((index - 1) / Math.max(1, maxIndex - 1)) * (width - pad.left - pad.right);
    $: panelTop = (metric) => pad.top + metrics.indexOf(metric) * panelHeight;
    $: y = (metric, value) => panelTop(metric) + panelHeight / 2 - (value / extent) * (panelHeight * .36);
    $: firstRace = rows.find((row) => row.race_index === 1)?.race_label ?? '';
    $: lastRace = rows.find((row) => row.race_index === maxIndex)?.race_label ?? '';
    const metricRows = (metric) => rows.filter((row) => row.metric_label === metric);
    const rollingPoints = (metric) => metricRows(metric)
        .filter((row) => row.rolling_value != null)
        .map((row) => `${x(row.race_index)},${y(metric, row.rolling_value)}`)
        .join(' ');
</script>

<section class="evolution" bind:clientWidth data-testid="driver-dna-evolution">
    <div class="heading">
        <strong>{title}</strong>
        <span><i class="dot"></i>race evidence <i class="line"></i>up-to-five-race median</span>
    </div>
    {#if rows.length}
        <svg viewBox="0 0 {width} {height}" width="100%" height={height} role="img" aria-label={title}>
            {#each metrics as metric}
                <line class="zero" x1={pad.left} x2={width-pad.right} y1={y(metric, 0)} y2={y(metric, 0)} />
                <text class="metric" x={pad.left-12} y={panelTop(metric)+panelHeight/2+4} text-anchor="end">{metric}</text>
                {#if rollingPoints(metric)}
                    <polyline class="rolling" points={rollingPoints(metric)} />
                {/if}
                {#each metricRows(metric) as row}
                    <circle class="race-point" cx={x(row.race_index)} cy={y(metric, row.value)} r="3.5" tabindex="0">
                        <title>{row.race_label} · {metric}: {row.value.toFixed(2)} z vs {row.teammate_name}</title>
                    </circle>
                {/each}
            {/each}
            <text class="race-label" x={pad.left} y={height-12}>{firstRace}</text>
            <text class="race-label" x={width-pad.right} y={height-12} text-anchor="end">{lastRace}</text>
        </svg>
    {:else}
        <div class="empty">No eligible race sequence for Driver A in this season window.</div>
    {/if}
</section>

<style>
    .evolution { width: 100%; margin: 1rem 0 1.5rem; padding: 1rem; border: 1px solid rgba(160,174,201,.18); border-radius: .95rem; background: rgba(255,255,255,.025); }
    .heading { display: flex; justify-content: space-between; gap: 1rem; color: #f4f7fb; }
    .heading span { display: flex; align-items: center; gap: .35rem; color: #8f9bae; font-size: .72rem; }
    .heading i { display: inline-block; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: rgba(174,184,199,.7); }
    .line { width: 18px; height: 3px; margin-left: .4rem; border-radius: 2px; background: #32d3f4; }
    .zero { stroke: currentColor; stroke-opacity: .25; stroke-dasharray: 3 3; }
    .rolling { fill: none; stroke: #32d3f4; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
    .race-point { fill: #aeb8c7; fill-opacity: .62; stroke: #11151d; stroke-width: 1; }
    .race-point:hover, .race-point:focus { fill: #fff; fill-opacity: 1; outline: none; }
    .metric { fill: #dce3ed; font-size: 11px; font-weight: 650; }
    .race-label { fill: #8f9bae; font-size: 10px; }
    .empty { padding: 2rem 1rem; color: #9ba7ba; text-align: center; }
    @media (max-width: 620px) {
        .evolution { padding: .75rem .4rem; }
        .heading { flex-direction: column; padding: 0 .4rem; }
        .metric { font-size: 9px; }
    }
</style>
