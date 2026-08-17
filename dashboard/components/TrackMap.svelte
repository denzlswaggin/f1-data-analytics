<script>
    // Animated, interactive race-replay track map. Draws the circuit once on a
    // background canvas, then animates one dot per car on an overlay via
    // requestAnimationFrame, interpolating between time ticks for smooth motion.
    // Interactions: click a car to follow it, hover for a tooltip, scroll to zoom
    // and drag to pan. Fed by two Evidence queries: `data` (the per-car-per-tick
    // replay feed) and `meta` (per-driver names/teams/colours), joined by driver_code.
    import { onMount, onDestroy } from 'svelte';

    export let data = [];
    export let meta = [];
    export let title = '';

    const SPEEDS = [1, 2, 4, 6, 12, 24, 48];
    const PAD = 28;
    const HIT_PX = 16; // click/hover pick radius

    let containerWidth = 900;
    $: width = Math.max(320, containerWidth);
    $: height = Math.round(width * 0.6);

    let trackCanvas, carsCanvas, trackCtx, carsCtx;
    let playing = false;
    let t = 0, speed = 6, tMax = 0, raf = null, lastTs = null;

    let drivers = [];
    let bounds = null;
    let leaderboard = [];

    // View (zoom / pan) and interaction state.
    let view = { zoom: 1, ox: 0, oy: 0 };
    let selected = null; // driver_code being followed
    let hovered = null; // {code, name, team, order, gap, ahead, cx, cy}
    let screenPos = []; // last-rendered car screen positions, for hit-testing
    let dragging = false, dragMoved = false, dragStart = null;

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
        if (selected && !groups.has(selected)) selected = null;
        resetView();
        queueDraw();
    }

    // --- world <-> screen transform (base fit * zoom + pan offset) ---
    function baseScale() {
        const bw = (bounds.maxX - bounds.minX) || 1;
        const bh = (bounds.maxY - bounds.minY) || 1;
        return Math.min((width - 2 * PAD) / bw, (height - 2 * PAD) / bh);
    }
    function resetView() {
        if (!bounds) return;
        const s = baseScale();
        const bw = (bounds.maxX - bounds.minX) || 1;
        const bh = (bounds.maxY - bounds.minY) || 1;
        view = { zoom: 1, ox: (width - bw * s) / 2, oy: (height - bh * s) / 2 };
        queueDraw();
    }
    const wx = (x) => view.ox + (x - bounds.minX) * baseScale() * view.zoom;
    const wy = (y) => view.oy + (bounds.maxY - y) * baseScale() * view.zoom;

    function drawTrack() {
        if (!trackCtx || !bounds || !drivers.length) return;
        trackCtx.clearRect(0, 0, width, height);
        let ref = drivers[0];
        for (const d of drivers) if (d.samples.length > ref.samples.length) ref = d;
        trackCtx.lineWidth = Math.max(6, baseScale() * view.zoom * 260);
        trackCtx.strokeStyle = 'rgba(255,255,255,0.07)';
        trackCtx.lineJoin = 'round';
        trackCtx.lineCap = 'round';
        trackCtx.beginPath();
        ref.samples.forEach((p, i) => {
            const X = wx(p.x), Y = wy(p.y);
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
        return {
            x: a.x + (b.x - a.x) * f,
            y: a.y + (b.y - a.y) * f,
            order: a.order, gap: a.gap, ahead: a.ahead,
        };
    }

    function render() {
        if (!carsCtx || !bounds) return;
        carsCtx.clearRect(0, 0, width, height);
        const board = [], sp = [];
        for (const g of drivers) {
            const p = sampleAt(g, t);
            if (!p) continue;
            const X = wx(p.x), Y = wy(p.y);
            const isSel = selected != null && g.code === selected;
            const dim = selected != null && !isSel;
            carsCtx.globalAlpha = dim ? 0.25 : 1;
            carsCtx.beginPath();
            carsCtx.arc(X, Y, isSel ? 7.5 : 5.5, 0, Math.PI * 2);
            carsCtx.fillStyle = g.color;
            carsCtx.fill();
            carsCtx.lineWidth = isSel ? 2.5 : 1.5;
            carsCtx.strokeStyle = isSel ? '#ffffff' : 'rgba(0,0,0,0.65)';
            carsCtx.stroke();
            if (!dim || isSel) {
                carsCtx.font = (isSel ? '700 ' : '600 ') + '10px system-ui, sans-serif';
                carsCtx.fillStyle = 'rgba(255,255,255,0.92)';
                carsCtx.fillText(g.code, X + 8, Y + 3);
            }
            carsCtx.globalAlpha = 1;
            sp.push({ code: g.code, name: g.name, team: g.team, color: g.color, X, Y,
                      order: p.order, gap: p.gap, ahead: p.ahead });
            if (p.order != null)
                board.push({ code: g.code, color: g.color, order: p.order, gap: p.gap, ahead: p.ahead });
        }
        board.sort((a, b) => a.order - b.order);
        leaderboard = board;
        screenPos = sp;
        // Keep the tooltip live while the race plays.
        if (hovered) {
            const h = sp.find((s) => s.code === hovered.code);
            hovered = h ? { ...hovered, order: h.order, gap: h.gap, ahead: h.ahead, cx: h.X, cy: h.Y } : null;
        }
    }

    function queueDraw() {
        if (typeof requestAnimationFrame === 'undefined') return; // SSR prerender
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

    // --- pointer interaction (hover, click-to-follow, drag-pan, wheel-zoom) ---
    function localXY(e) {
        const r = carsCanvas.getBoundingClientRect();
        return [(e.clientX - r.left) * (width / r.width), (e.clientY - r.top) * (height / r.height)];
    }
    function nearest(cx, cy) {
        let best = null, bestD = HIT_PX * HIT_PX;
        for (const s of screenPos) {
            const dx = s.X - cx, dy = s.Y - cy, d = dx * dx + dy * dy;
            if (d < bestD) { bestD = d; best = s; }
        }
        return best;
    }
    function onMove(e) {
        const [cx, cy] = localXY(e);
        if (dragging) {
            if (Math.abs(cx - dragStart[0]) > 3 || Math.abs(cy - dragStart[1]) > 3) dragMoved = true;
            view = { ...view, ox: view.ox + (cx - dragStart[0]), oy: view.oy + (cy - dragStart[1]) };
            dragStart = [cx, cy];
            queueDraw();
            return;
        }
        const n = nearest(cx, cy);
        hovered = n
            ? { code: n.code, name: n.name, team: n.team, color: n.color,
                order: n.order, gap: n.gap, ahead: n.ahead, cx: n.X, cy: n.Y }
            : null;
    }
    function onDown(e) {
        const [cx, cy] = localXY(e);
        dragging = true;
        dragMoved = false;
        dragStart = [cx, cy];
    }
    function onUp(e) {
        if (dragging && !dragMoved) {
            const [cx, cy] = localXY(e);
            const n = nearest(cx, cy);
            selected = n ? (selected === n.code ? null : n.code) : null;
            render();
        }
        dragging = false;
    }
    function onLeave() {
        hovered = null;
        dragging = false;
    }
    function onWheel(e) {
        e.preventDefault();
        const [cx, cy] = localXY(e);
        const nz = Math.min(8, Math.max(1, view.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
        const k = nz / view.zoom;
        view = { zoom: nz, ox: cx - (cx - view.ox) * k, oy: cy - (cy - view.oy) * k };
        queueDraw();
    }

    function fmtClock(sec) {
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${String(s).padStart(2, '0')}`;
    }
    // Interval to the car ahead, F1 timing-tower style, 3 decimals.
    const fmtInterval = (a) => (a == null ? '' : a <= 0 ? 'LEADER' : '+' + a.toFixed(3));
    const fmtGap = (g) => (g == null || g <= 0 ? '—' : '+' + g.toFixed(3));

    onMount(() => {
        trackCtx = trackCanvas.getContext('2d');
        carsCtx = carsCanvas.getContext('2d');
        // Wheel needs a non-passive listener to preventDefault the page scroll.
        carsCanvas.addEventListener('wheel', onWheel, { passive: false });
        queueDraw();
    });
    onDestroy(() => {
        pause();
        if (carsCanvas) carsCanvas.removeEventListener('wheel', onWheel);
    });

    // Redraw on resize / new data (independent of `t`, so playback is unaffected).
    $: if (trackCtx && width && height && bounds) queueDraw();
</script>

<div class="tm" bind:clientWidth={containerWidth}>
    {#if title}<div class="tm-title">{title}</div>{/if}
    <div class="tm-stage" style="width:{width}px;height:{height}px">
        <canvas bind:this={trackCanvas} {width} {height}></canvas>
        <canvas
            bind:this={carsCanvas}
            {width}
            {height}
            class="cars {dragging ? 'grabbing' : hovered ? 'pick' : 'grab'}"
            on:mousemove={onMove}
            on:mousedown={onDown}
            on:mouseup={onUp}
            on:mouseleave={onLeave}
        ></canvas>

        <div class="tm-board">
            <div class="tm-board-h">Order · interval</div>
            {#each leaderboard as row (row.code)}
                <div
                    class="tm-brow {selected === row.code ? 'sel' : ''}"
                    on:click={() => (selected = selected === row.code ? null : row.code)}
                    on:keydown={(e) => e.key === 'Enter' && (selected = selected === row.code ? null : row.code)}
                    role="button"
                    tabindex="0"
                >
                    <span class="pos">{row.order}</span>
                    <span class="sw" style="background:{row.color}"></span>
                    <span class="cd">{row.code}</span>
                    <span class="gp">{fmtInterval(row.ahead)}</span>
                </div>
            {/each}
        </div>

        {#if hovered}
            <div
                class="tm-tip"
                style="left:{Math.min(width - 130, hovered.cx + 12)}px; top:{Math.max(4, hovered.cy - 46)}px"
            >
                <div class="tm-tip-name"><span class="sw" style="background:{hovered.color}"></span>{hovered.name}</div>
                <div class="tm-tip-row">P{hovered.order ?? '–'} · {hovered.team}</div>
                <div class="tm-tip-row">interval {fmtInterval(hovered.ahead)} · leader {fmtGap(hovered.gap)}</div>
            </div>
        {/if}

        <div class="tm-clock">{fmtClock(t)} / {fmtClock(tMax)}</div>
        {#if selected}<div class="tm-follow">Following {selected} · click to release</div>{/if}
    </div>

    <div class="tm-controls">
        <button on:click={toggle} class="tm-btn tm-play">{playing ? '❚❚ Pause' : '▶ Play'}</button>
        <input type="range" min="0" max={tMax} step="0.5" value={t} on:input={onScrub} class="tm-scrub" />
        <label class="tm-speed">
            Speed
            <select bind:value={speed}>
                {#each SPEEDS as sp}<option value={sp}>{sp}×</option>{/each}
            </select>
        </label>
        <button on:click={resetView} class="tm-btn" title="Reset zoom & pan">Reset view</button>
    </div>
    <div class="tm-hint">Scroll to zoom · drag to pan · click a car to follow · hover for details</div>
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
    .cars.grab { cursor: grab; }
    .cars.grabbing { cursor: grabbing; }
    .cars.pick { cursor: pointer; }
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
        min-width: 138px;
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
        line-height: 1.55;
        cursor: pointer;
        border-radius: 3px;
        padding: 0 2px;
    }
    .tm-brow:hover { background: rgba(255, 255, 255, 0.08); }
    .tm-brow.sel { background: rgba(255, 255, 255, 0.16); }
    .tm-brow .pos {
        width: 16px;
        text-align: right;
        opacity: 0.7;
        font-variant-numeric: tabular-nums;
    }
    .sw {
        display: inline-block;
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
        opacity: 0.8;
        font-variant-numeric: tabular-nums;
    }
    .tm-tip {
        position: absolute;
        pointer-events: none;
        background: rgba(8, 12, 18, 0.92);
        border: 1px solid rgba(255, 255, 255, 0.16);
        border-radius: 6px;
        padding: 5px 8px;
        color: #e8eaed;
        font-size: 11px;
        min-width: 118px;
        z-index: 3;
    }
    .tm-tip-name {
        font-weight: 700;
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 2px;
    }
    .tm-tip-row { opacity: 0.8; font-variant-numeric: tabular-nums; }
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
    .tm-follow {
        position: absolute;
        left: 10px;
        bottom: 8px;
        color: #e8eaed;
        font-size: 11px;
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
    .tm-btn {
        cursor: pointer;
        border: 1px solid rgba(128, 128, 128, 0.4);
        background: transparent;
        color: inherit;
        border-radius: 6px;
        padding: 5px 12px;
        font-weight: 600;
    }
    .tm-btn:hover { border-color: rgba(128, 128, 128, 0.8); }
    .tm-play { min-width: 92px; }
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
    .tm-hint {
        margin-top: 6px;
        font-size: 11px;
        opacity: 0.55;
    }
</style>
