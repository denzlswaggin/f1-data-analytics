<script>
    // Animated race-replay track map. Draws the circuit once on a background
    // canvas, then animates one dot per car on an overlay via requestAnimationFrame,
    // interpolating each car's position between time ticks for smooth motion. Fed by
    // two Evidence queries: `data` (the big per-car-per-tick replay feed) and `meta`
    // (per-driver names/teams/colours), joined here by driver_code.
    import { onMount, onDestroy } from 'svelte';

    export let data = [];
    export let meta = [];
    export let title = '';

    const SPEEDS = [1, 2, 4, 6, 12, 24, 48];

    let containerWidth = 900;
    $: width = Math.max(320, containerWidth);
    $: height = Math.round(width * 0.6);

    let trackCanvas, carsCanvas, trackCtx, carsCtx;
    let playing = false;
    let t = 0;
    let speed = 6;
    let tMax = 0;
    let raf = null;
    let lastTs = null;

    let drivers = [];
    let bounds = null;
    let leaderboard = [];

    const asNum = (v) => (v == null ? null : Number(v));

    $: build(data, meta);

    function build(rows, metaRows) {
        if (!rows || !rows.length) {
            drivers = [];
            bounds = null;
            tMax = 0;
            return;
        }
        const metaMap = {};
        for (const m of metaRows || []) metaMap[m.driver_code] = m;

        const groups = new Map();
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, tmax = 0;
        for (const row of rows) {
            let g = groups.get(row.driver_code);
            if (!g) {
                g = { code: row.driver_code, samples: [] };
                groups.set(row.driver_code, g);
            }
            const x = Number(row.x), y = Number(row.y), tt = Number(row.t_s);
            g.samples.push({
                t: tt, x, y,
                order: asNum(row.running_order),
                gap: asNum(row.gap_to_leader_s),
                ahead: asNum(row.gap_to_ahead_s),
            });
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
            if (tt > tmax) tmax = tt;
        }

        const out = [];
        for (const g of groups.values()) {
            g.samples.sort((a, b) => a.t - b.t);
            g.tmin = g.samples[0].t;
            g.tmax = g.samples[g.samples.length - 1].t;
            const m = metaMap[g.code] || {};
            g.name = m.driver_name || g.code;
            g.team = m.team || '';
            g.color = m.team_color || '#9aa0a6';
            out.push(g);
        }
        drivers = out;
        bounds = { minX, maxX, minY, maxY };
        tMax = tmax;
        if (t > tMax) t = 0;
        queueDraw();
    }

    function transform() {
        const pad = 28;
        const bw = (bounds.maxX - bounds.minX) || 1;
        const bh = (bounds.maxY - bounds.minY) || 1;
        const s = Math.min((width - 2 * pad) / bw, (height - 2 * pad) / bh);
        return { s, ox: (width - s * bw) / 2, oy: (height - s * bh) / 2 };
    }
    const px = (x, tf) => tf.ox + (x - bounds.minX) * tf.s;
    const py = (y, tf) => tf.oy + (bounds.maxY - y) * tf.s; // flip vertical for canvas

    function drawTrack() {
        if (!trackCtx || !bounds || !drivers.length) return;
        trackCtx.clearRect(0, 0, width, height);
        const tf = transform();
        // Reference line = the car with the most samples; its full path traces the
        // circuit (overlaid laps reinforce the outline).
        let ref = drivers[0];
        for (const d of drivers) if (d.samples.length > ref.samples.length) ref = d;
        trackCtx.lineWidth = Math.max(8, tf.s * 260);
        trackCtx.strokeStyle = 'rgba(255,255,255,0.07)';
        trackCtx.lineJoin = 'round';
        trackCtx.lineCap = 'round';
        trackCtx.beginPath();
        ref.samples.forEach((p, i) => {
            const X = px(p.x, tf), Y = py(p.y, tf);
            i === 0 ? trackCtx.moveTo(X, Y) : trackCtx.lineTo(X, Y);
        });
        trackCtx.stroke();
    }

    function sampleAt(g, time) {
        if (time < g.tmin || time > g.tmax) return null;
        const s = g.samples;
        let lo = 0, hi = s.length - 1;
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (s[mid].t < time) lo = mid + 1;
            else hi = mid;
        }
        if (lo <= 0) return s[0];
        const a = s[lo - 1], b = s[lo];
        const f = (time - a.t) / ((b.t - a.t) || 1);
        return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, order: a.order, gap: a.gap };
    }

    function render() {
        if (!carsCtx || !bounds) return;
        const tf = transform();
        carsCtx.clearRect(0, 0, width, height);
        const board = [];
        for (const g of drivers) {
            const p = sampleAt(g, t);
            if (!p) continue;
            const X = px(p.x, tf), Y = py(p.y, tf);
            carsCtx.beginPath();
            carsCtx.arc(X, Y, 5.5, 0, Math.PI * 2);
            carsCtx.fillStyle = g.color;
            carsCtx.fill();
            carsCtx.lineWidth = 1.5;
            carsCtx.strokeStyle = 'rgba(0,0,0,0.65)';
            carsCtx.stroke();
            carsCtx.font = '600 10px system-ui, sans-serif';
            carsCtx.fillStyle = 'rgba(255,255,255,0.92)';
            carsCtx.fillText(g.code, X + 8, Y + 3);
            if (p.order != null) board.push({ code: g.code, color: g.color, order: p.order, gap: p.gap });
        }
        board.sort((a, b) => a.order - b.order);
        leaderboard = board;
    }

    function queueDraw() {
        // No-op during server-side prerender (no rAF / canvas); onMount redraws.
        if (typeof requestAnimationFrame === 'undefined') return;
        requestAnimationFrame(() => {
            drawTrack();
            render();
        });
    }

    function loop(ts) {
        if (!playing) return;
        if (lastTs == null) lastTs = ts;
        t = Math.min(tMax, t + ((ts - lastTs) / 1000) * speed);
        lastTs = ts;
        render();
        if (t >= tMax) {
            playing = false;
            lastTs = null;
            return;
        }
        raf = requestAnimationFrame(loop);
    }
    function play() {
        if (playing) return;
        if (t >= tMax) t = 0;
        playing = true;
        lastTs = null;
        raf = requestAnimationFrame(loop);
    }
    function pause() {
        playing = false;
        if (raf) cancelAnimationFrame(raf);
        raf = null;
        lastTs = null;
    }
    const toggle = () => (playing ? pause() : play());
    function onScrub(e) {
        t = Number(e.target.value);
        if (!playing) render();
    }

    function fmtClock(sec) {
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${String(s).padStart(2, '0')}`;
    }
    const fmtGap = (g) => (g == null ? '' : g <= 0 ? 'LEADER' : '+' + g.toFixed(1) + 's');

    onMount(() => {
        trackCtx = trackCanvas.getContext('2d');
        carsCtx = carsCanvas.getContext('2d');
        queueDraw();
    });
    onDestroy(pause);

    // Redraw on resize / new data (does not depend on `t`, so playback is unaffected).
    $: if (trackCtx && width && height && bounds) queueDraw();
</script>

<div class="tm" bind:clientWidth={containerWidth}>
    {#if title}<div class="tm-title">{title}</div>{/if}
    <div class="tm-stage" style="width:{width}px;height:{height}px">
        <canvas bind:this={trackCanvas} {width} {height}></canvas>
        <canvas bind:this={carsCanvas} {width} {height} class="cars"></canvas>
        <div class="tm-board">
            <div class="tm-board-h">Order</div>
            {#each leaderboard as row (row.code)}
                <div class="tm-brow">
                    <span class="pos">{row.order}</span>
                    <span class="sw" style="background:{row.color}"></span>
                    <span class="cd">{row.code}</span>
                    <span class="gp">{fmtGap(row.gap)}</span>
                </div>
            {/each}
        </div>
        <div class="tm-clock">{fmtClock(t)} / {fmtClock(tMax)}</div>
    </div>
    <div class="tm-controls">
        <button on:click={toggle} class="tm-play">{playing ? '❚❚ Pause' : '▶ Play'}</button>
        <input type="range" min="0" max={tMax} step="0.5" value={t} on:input={onScrub} class="tm-scrub" />
        <label class="tm-speed">
            Speed
            <select bind:value={speed}>
                {#each SPEEDS as sp}<option value={sp}>{sp}×</option>{/each}
            </select>
        </label>
    </div>
</div>

<style>
    .tm {
        width: 100%;
        margin: 0.5rem 0 1.25rem;
        font-family: system-ui, sans-serif;
    }
    .tm-title {
        font-weight: 600;
        margin-bottom: 0.4rem;
    }
    .tm-stage {
        position: relative;
        background: #0b0f14;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
        max-width: 100%;
    }
    .tm-stage canvas {
        position: absolute;
        left: 0;
        top: 0;
    }
    .tm-board {
        position: absolute;
        top: 10px;
        left: 10px;
        background: rgba(8, 12, 18, 0.72);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 6px 8px;
        color: #e8eaed;
        font-size: 11px;
        min-width: 118px;
        backdrop-filter: blur(2px);
    }
    .tm-board-h {
        font-size: 9px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        opacity: 0.6;
        margin-bottom: 3px;
    }
    .tm-brow {
        display: flex;
        align-items: center;
        gap: 6px;
        line-height: 1.5;
    }
    .tm-brow .pos {
        width: 16px;
        text-align: right;
        opacity: 0.7;
        font-variant-numeric: tabular-nums;
    }
    .tm-brow .sw {
        width: 9px;
        height: 9px;
        border-radius: 2px;
        flex: none;
    }
    .tm-brow .cd {
        font-weight: 600;
        width: 34px;
    }
    .tm-brow .gp {
        margin-left: auto;
        opacity: 0.75;
        font-variant-numeric: tabular-nums;
    }
    .tm-clock {
        position: absolute;
        right: 10px;
        bottom: 8px;
        color: #e8eaed;
        font-variant-numeric: tabular-nums;
        font-size: 13px;
        background: rgba(8, 12, 18, 0.6);
        padding: 2px 8px;
        border-radius: 6px;
    }
    .tm-controls {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 10px;
    }
    .tm-play {
        cursor: pointer;
        border: 1px solid rgba(128, 128, 128, 0.4);
        background: transparent;
        color: inherit;
        border-radius: 6px;
        padding: 5px 12px;
        font-weight: 600;
        min-width: 92px;
    }
    .tm-play:hover {
        border-color: rgba(128, 128, 128, 0.8);
    }
    .tm-scrub {
        flex: 1;
        min-width: 120px;
    }
    .tm-speed {
        font-size: 13px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
</style>
