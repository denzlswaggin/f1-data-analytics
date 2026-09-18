<script>
    // Tyre-strategy gantt: one horizontal row per driver (ordered by finishing
    // position), each row segmented into compound-coloured stints on an absolute
    // lap axis, with a tick at every stint boundary. Pure SVG so it
    // prerenders cleanly under Evidence SSR (no canvas / requestAnimationFrame);
    // the only client-only bit is the responsive width via bind:clientWidth,
    // which falls back to a default during prerender. Fed by the `stint_strategy`
    // Evidence source (marts.mart_stint_strategy).
    export let data = [];
    export let title = '';
    export let shade = true; // fade each stint by its observed lap-time slope

    // FastF1 compound → F1 broadcast colour, single-letter badge, and a text
    // colour that stays legible on the fill.
    const COMPOUND = {
        SOFT: { color: '#e8002d', label: 'S', text: '#fff', name: 'Soft' },
        MEDIUM: { color: '#ffcf00', label: 'M', text: '#222', name: 'Medium' },
        HARD: { color: '#ebebeb', label: 'H', text: '#222', name: 'Hard' },
        INTERMEDIATE: { color: '#43b02a', label: 'I', text: '#fff', name: 'Intermediate' },
        WET: { color: '#0067ad', label: 'W', text: '#fff', name: 'Wet' },
        UNKNOWN: { color: '#9aa0a6', label: '?', text: '#fff', name: 'Unknown' }
    };
    const compoundOf = (c) => COMPOUND[c] || COMPOUND.UNKNOWN;
    // Evidence hands numbers back as strings/BigInt — coerce defensively.
    const num = (v) => (v == null ? null : Number(v));

    // Slope shading: each stint fades left→right toward dark in proportion to its
    // observed lap-time slope (deg_sec_per_lap), saturating at DEG_MAX s/lap.
    // Negative slopes get no fade.
    const DEG_MAX = 0.35;
    const DEG_MAX_ALPHA = 0.6;
    const degAlpha = (deg) =>
        deg == null || !(deg > 0) ? 0 : Math.min(deg / DEG_MAX, 1) * DEG_MAX_ALPHA;

    let clientWidth = 900;

    // Layout constants.
    const padL = 54; // left gutter for the driver code
    const padR = 14;
    const padT = 6;
    const rowH = 25;
    const barH = 16;
    const axisH = 25;

    $: rows = buildRows(data);
    $: maxLap = Math.max(1, ...rows.flatMap((r) => r.stints.map((s) => s.end_lap)));
    $: legend = Object.keys(COMPOUND).filter((k) => new Set((data || []).map((d) => d.compound)).has(k));

    $: width = Math.max(280, clientWidth || 900);
    $: height = padT + rows.length * rowH + axisH;
    $: plotL = padL;
    $: plotR = width - padR;
    $: plotW = Math.max(1, plotR - plotL);
    $: xOf = (lap) => plotL + (lap / maxLap) * plotW;
    $: ticks = buildTicks(maxLap, width);

    function buildRows(d) {
        const byDriver = new Map();
        for (const row of d || []) {
            const code = row.driver_code;
            if (!byDriver.has(code)) {
                byDriver.set(code, {
                    driver_code: code,
                    driver_name: row.driver_name,
                    finish: num(row.finish_position),
                    stints: []
                });
            }
            byDriver.get(code).stints.push({
                stint: num(row.stint),
                compound: row.compound,
                start_lap: num(row.start_lap),
                end_lap: num(row.end_lap),
                stint_laps: num(row.stint_laps),
                tyre_life_end: num(row.tyre_life_end),
                deg: num(row.deg_sec_per_lap),
                started_fresh: row.started_fresh === true || row.started_fresh === 'true'
            });
        }
        const out = [...byDriver.values()];
        for (const r of out) r.stints.sort((a, b) => a.stint - b.stint);
        out.sort(
            (a, b) => (a.finish ?? 999) - (b.finish ?? 999) || a.driver_code.localeCompare(b.driver_code)
        );
        return out;
    }

    function buildTicks(mx, chartWidth) {
        const step = chartWidth < 440 ? (mx > 60 ? 20 : 10) : (mx > 60 ? 10 : 5);
        const t = [];
        for (let l = 0; l <= mx; l += step) t.push(l);
        if (t[t.length - 1] !== mx) t.push(mx);
        return t;
    }

    function stintLabel(driver, stint) {
        const slope = stint.deg == null ? '' : `, ${stint.deg.toFixed(2)} seconds per lap observed slope`;
        return `${driver.driver_code}, ${compoundOf(stint.compound).name}, laps ${stint.start_lap} to ${stint.end_lap}, ${stint.stint_laps} laps${slope}`;
    }
</script>

<div class="stintchart" bind:clientWidth>
    {#if title}<div class="sc-title">Tyre strategy — {title}</div>{/if}

    <div class="sc-legend">
        {#each legend as key}
            <span class="sc-legend-item">
                <span class="sc-swatch" style="background:{compoundOf(key).color}"></span>
                {compoundOf(key).name}
            </span>
        {/each}
        <span class="sc-legend-item"><span class="sc-pit-swatch"></span> stint change</span>
        {#if shade}
            <span class="sc-legend-item"><span class="sc-deg-swatch"></span> lower → higher observed slope</span>
        {/if}
    </div>

    {#if rows.length === 0}
        <div class="sc-empty">No stint data for this race.</div>
    {:else}
        <svg
            viewBox="0 0 {width} {height}"
            width="100%"
            height={height}
            role="img"
            aria-label={title ? `Tyre strategy chart — ${title}` : 'Tyre strategy chart'}
        >
            <defs>
                <!-- Left→right transparent→black; each stint's overlay scales its
                     opacity by degradation so worn tyres darken toward the end. -->
                <linearGradient id="sc-degfade" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stop-color="#000" stop-opacity="0" />
                    <stop offset="100%" stop-color="#000" stop-opacity="1" />
                </linearGradient>
            </defs>
            {#each ticks as t}
                <line class="sc-grid" x1={xOf(t)} x2={xOf(t)} y1={padT} y2={padT + rows.length * rowH} />
                <text class="sc-axis" x={xOf(t)} y={height - 6} text-anchor="middle">{t}</text>
            {/each}
            <text class="sc-axis-title" x={plotR} y={height - 6} text-anchor="end">lap</text>

            {#each rows as r, i}
                {@const cy = padT + i * rowH}
                <text
                    class="sc-driver"
                    x={padL - 8}
                    y={cy + rowH / 2}
                    text-anchor="end"
                    dominant-baseline="middle">{r.driver_code}</text
                >

                {#each r.stints as s}
                    {@const x0 = xOf(s.start_lap - 1)}
                    {@const x1 = xOf(s.end_lap)}
                    <rect
                        class="sc-stint"
                        x={x0}
                        y={cy + (rowH - barH) / 2}
                        width={Math.max(1, x1 - x0)}
                        height={barH}
                        rx="2"
                        fill={compoundOf(s.compound).color}
                        tabindex="0"
                        role="img"
                        aria-label={stintLabel(r, s)}
                    >
                        <title
                            >{r.driver_code} · {compoundOf(s.compound).name} · laps {s.start_lap}–{s.end_lap}
                            ({s.stint_laps} laps){s.started_fresh ? '' : ' · used set'}, tyre age {s.tyre_life_end}{s.deg !=
                            null
                                ? ` · ${s.deg.toFixed(2)} s/lap observed slope`
                                : ''}</title
                        >
                    </rect>
                    {#if shade && degAlpha(s.deg) > 0}
                        <rect
                            class="sc-deg"
                            x={x0 + 0.75}
                            y={cy + (rowH - barH) / 2 + 0.75}
                            width={Math.max(0, x1 - x0 - 1.5)}
                            height={barH - 1.5}
                            rx="1.5"
                            fill="url(#sc-degfade)"
                            opacity={degAlpha(s.deg)}
                        />
                    {/if}
                    {#if x1 - x0 > 16}
                        <text
                            class="sc-letter"
                            x={(x0 + x1) / 2}
                            y={cy + rowH / 2}
                            fill={compoundOf(s.compound).text}
                            text-anchor="middle"
                            dominant-baseline="middle">{compoundOf(s.compound).label}</text
                        >
                    {/if}
                {/each}

                {#each r.stints.slice(0, -1) as s}
                    <line
                        class="sc-pit-tick"
                        x1={xOf(s.end_lap)}
                        x2={xOf(s.end_lap)}
                        y1={cy + (rowH - barH) / 2 - 2}
                        y2={cy + (rowH + barH) / 2 + 2}
                    />
                {/each}
            {/each}
        </svg>
    {/if}
</div>

<style>
    .stintchart {
        width: 100%;
        margin: 1rem 0 1.5rem;
        padding: 1rem;
        border: 1px solid rgba(160,174,201,.18);
        border-radius: .95rem;
        background: rgba(255,255,255,.025);
        font-family: inherit;
    }
    .sc-title {
        font-weight: 600;
        margin: 0 0 4px;
    }
    .sc-legend {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
        color: #aeb8c7;
        font-size: 13px;
        margin-bottom: 6px;
        opacity: 0.85;
    }
    .sc-legend-item {
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }
    .sc-swatch {
        width: 12px;
        height: 12px;
        border-radius: 2px;
        border: 0.75px solid rgba(120, 120, 120, 0.5);
        display: inline-block;
    }
    .sc-pit-swatch {
        width: 0;
        height: 14px;
        border-left: 2px solid currentColor;
        opacity: 0.6;
        display: inline-block;
    }
    .sc-grid {
        stroke: currentColor;
        stroke-opacity: 0.12;
        stroke-width: 1;
    }
    .sc-axis {
        fill: currentColor;
        opacity: 0.6;
        font-size: 12px;
    }
    .sc-axis-title {
        fill: currentColor;
        opacity: 0.5;
        font-size: 12px;
        font-style: italic;
    }
    .sc-driver {
        fill: currentColor;
        font-size: 13px;
        font-weight: 600;
    }
    .sc-letter {
        font-size: 11px;
        font-weight: 700;
        pointer-events: none;
    }
    .sc-stint {
        stroke: rgba(120, 120, 120, 0.55);
        stroke-width: 0.75;
        cursor: default;
    }
    .sc-stint:hover {
        stroke: currentColor;
        stroke-width: 1.25;
    }
    .sc-stint:focus { stroke: var(--color-primary, #2563eb); stroke-width: 2; outline: none; }
    .sc-pit-tick {
        stroke: currentColor;
        stroke-opacity: 0.55;
        stroke-width: 2;
    }
    .sc-deg {
        pointer-events: none;
    }
    .sc-deg-swatch {
        width: 26px;
        height: 12px;
        border-radius: 2px;
        border: 0.75px solid rgba(120, 120, 120, 0.5);
        background: linear-gradient(to right, #b9bcc0, #2b2d30);
        display: inline-block;
    }
    .sc-empty {
        opacity: 0.6;
        font-size: 13px;
        padding: 12px 0;
    }
</style>
