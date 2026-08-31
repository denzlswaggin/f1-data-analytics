<script>
    export let data = [];
    export let title = 'Season-by-season form with 90% intervals';

    const COLORS = ['#2563eb', '#c2410c', '#16a34a', '#9333ea'];
    const num = (value) => value == null ? null : Number(value);
    let clientWidth = 840;

    $: width = Math.max(360, clientWidth || 840);
    $: height = 360;
    $: pad = { left: 52, right: 18, top: 34, bottom: 38 };
    $: rows = (data || []).map((row) => ({
        ...row,
        season: num(row.season),
        rating: num(row.rating),
        lo: num(row.rating_lo),
        hi: num(row.rating_hi)
    })).filter((row) => row.season != null && row.rating != null);
    $: seasons = [...new Set(rows.map((row) => row.season))].sort((a, b) => a - b);
    $: names = [...new Set(rows.map((row) => row.driver_name))];
    $: minSeason = seasons[0] ?? 0;
    $: maxSeason = seasons[seasons.length - 1] ?? minSeason + 1;
    $: yValues = rows.flatMap((row) => [row.lo ?? row.rating, row.hi ?? row.rating]);
    $: minY = yValues.length ? Math.min(...yValues) : -1;
    $: maxY = yValues.length ? Math.max(...yValues) : 1;
    $: yPad = Math.max(0.05, (maxY - minY) * 0.12);
    $: y0 = minY - yPad;
    $: y1 = maxY + yPad;
    $: x = (season) => pad.left + ((season - minSeason) / Math.max(1, maxSeason - minSeason)) * (width - pad.left - pad.right);
    $: y = (rating) => pad.top + ((y1 - rating) / Math.max(0.001, y1 - y0)) * (height - pad.top - pad.bottom);
    $: groups = names.map((name, index) => ({
        name,
        color: COLORS[index % COLORS.length],
        rows: rows.filter((row) => row.driver_name === name).sort((a, b) => a.season - b.season)
    }));
    $: yTicks = Array.from({ length: 5 }, (_, index) => y0 + (index * (y1 - y0)) / 4);
    const path = (group) => group.rows.map((row, index) => `${index ? 'L' : 'M'} ${x(row.season)} ${y(row.rating)}`).join(' ');
</script>

<div class="rating-chart" bind:clientWidth>
    <div class="title">{title}</div>
    <div class="legend">
        {#each groups as group}
            <span><i style="background:{group.color}"></i>{group.name}</span>
        {/each}
    </div>
    {#if rows.length}
        <svg viewBox="0 0 {width} {height}" width="100%" height={height} role="img" aria-label={title}>
            {#each yTicks as tick}
                <line class="grid" x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} />
                <text class="axis" x={pad.left - 8} y={y(tick) + 4} text-anchor="end">{tick.toFixed(2)}</text>
            {/each}
            {#each seasons as season}
                <text class="axis" x={x(season)} y={height - 12} text-anchor="middle">{season}</text>
            {/each}
            {#each groups as group}
                <path d={path(group)} fill="none" stroke={group.color} stroke-width="2.25" />
                {#each group.rows as row}
                    {#if row.lo != null && row.hi != null}
                        <line class="interval" x1={x(row.season)} x2={x(row.season)} y1={y(row.lo)} y2={y(row.hi)} stroke={group.color} />
                        <line class="cap" x1={x(row.season)-4} x2={x(row.season)+4} y1={y(row.lo)} y2={y(row.lo)} stroke={group.color} />
                        <line class="cap" x1={x(row.season)-4} x2={x(row.season)+4} y1={y(row.hi)} y2={y(row.hi)} stroke={group.color} />
                    {/if}
                    <circle cx={x(row.season)} cy={y(row.rating)} r="3.5" fill={group.color}>
                        <title>{group.name} {row.season}: {row.rating.toFixed(3)} ({row.lo?.toFixed(3) ?? '—'} to {row.hi?.toFixed(3) ?? '—'})</title>
                    </circle>
                {/each}
            {/each}
        </svg>
    {:else}
        <div class="empty">No overlapping rating data.</div>
    {/if}
</div>

<style>
    .rating-chart { width: 100%; margin: 0.75rem 0 1.25rem; font-family: inherit; }
    .title { font-weight: 600; margin-bottom: 0.35rem; }
    .legend { display: flex; gap: 1rem; flex-wrap: wrap; font-size: 12px; margin-bottom: 0.25rem; }
    .legend span { display: inline-flex; align-items: center; gap: 5px; }
    .legend i { width: 12px; height: 3px; border-radius: 2px; }
    .grid { stroke: currentColor; stroke-opacity: 0.11; }
    .axis { fill: currentColor; opacity: 0.62; font-size: 11px; }
    .interval { stroke-width: 1.5; stroke-opacity: 0.55; }
    .cap { stroke-width: 1.5; stroke-opacity: 0.75; }
    .empty { padding: 2rem 0; opacity: 0.6; }
</style>
