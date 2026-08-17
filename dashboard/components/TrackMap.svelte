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
    export let messages = [];
    export let radio = [];
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

    // --- race-control message feed (aligned to the replay clock via t_s) ---
    const EVT_COLOR = {
        sc: '#e8a33d', red: '#e8002d', chequered: '#e8eaed', green: '#2fbf71',
        yellow: '#e8d33d', drs: '#39a0ff', penalty: '#ff7ab3', info: '#9aa0b0',
    };
    let msgs = [];
    let keyEvents = [];
    function classify(m) {
        const f = (m.flag || '').toUpperCase();
        const c = (m.category || '').toUpperCase();
        const s = (m.message || '').toUpperCase();
        if (c === 'SAFETYCAR' || s.includes('SAFETY CAR') || s.includes('VSC')) return 'sc';
        if (f === 'RED' || s.includes('RED FLAG')) return 'red';
        if (f === 'CHEQUERED') return 'chequered';
        if (s.includes('PENALTY')) return 'penalty';
        if (f === 'GREEN') return 'green';
        if (f.includes('YELLOW')) return 'yellow';
        if (s.includes('DRS ENABLED') || s.includes('OVERTAKE ENABLED')) return 'drs';
        return 'info';
    }
    $: {
        const list = (messages || []).map((r) => ({
            t: Number(r.t_s), category: r.category || '', flag: r.flag || '',
            message: r.message || '', code: r.driver_code || '',
        }));
        list.sort((a, b) => a.t - b.t);
        for (const m of list) m.type = classify(m);
        msgs = list;
        keyEvents = list.filter((m) => ['sc', 'red', 'chequered', 'penalty'].includes(m.type));
    }
    // Newest-first messages up to the current time (recomputes as `t` advances).
    $: recentMsgs = msgs.filter((m) => m.t <= t).slice(-7).reverse();
    function jumpTo(sec) {
        t = Math.max(0, Math.min(tMax, sec));
        if (!playing) render();
    }
    function onTimelineClick(e) {
        const r = e.currentTarget.getBoundingClientRect();
        jumpTo(((e.clientX - r.left) / r.width) * tMax);
    }
    function onTimelineKey(e) {
        if (e.key === 'ArrowLeft') jumpTo(t - 5);
        else if (e.key === 'ArrowRight') jumpTo(t + 5);
    }

    // --- team radio (OpenF1 audio clips; partial coverage) ---
    let radioClips = [];
    $: radioClips = (radio || [])
        .map((r) => ({
            t: Number(r.t_s), code: r.driver_code || '', url: r.recording_url,
            transcript: r.transcript || null,
        }))
        .sort((a, b) => a.t - b.t);
    // Followed a driver? show only their clips — otherwise show the whole field's.
    $: displayedRadio = selected ? radioClips.filter((c) => c.code === selected) : radioClips;
    $: codeColor = Object.fromEntries(drivers.map((d) => [d.code, d.color]));
    let audioEl;
    let nowPlaying = null;
    function playRadio(clip) {
        nowPlaying = clip;
        jumpTo(clip.t);
        if (audioEl) {
            audioEl.src = clip.url;
            audioEl.currentTime = 0;
            audioEl.play().catch(() => {});
        }
        play(); // roll the replay on from this moment
    }
    function stopRadio() {
        if (audioEl) audioEl.pause();
        nowPlaying = null;
    }

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

        {#if msgs.length}
            <div class="tm-msgs">
                <div class="tm-board-h">Race control</div>
                {#each recentMsgs as m (m.t + '|' + m.message)}
                    <div class="tm-msg">
                        <span class="mdot" style="background:{EVT_COLOR[m.type]}"></span>
                        <span class="mt">{fmtClock(Math.max(0, m.t))}</span>
                        <span class="mm">{m.message}</span>
                    </div>
                {/each}
                {#if !recentMsgs.length}<div class="tm-msg tm-empty">— no messages yet —</div>{/if}
            </div>
        {/if}

        {#if nowPlaying && nowPlaying.transcript}
            <div class="tm-radio-caption">📻 {nowPlaying.code}: “{nowPlaying.transcript}”</div>
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

    {#if keyEvents.length && tMax > 0}
        <div
            class="tm-timeline"
            on:click={onTimelineClick}
            on:keydown={onTimelineKey}
            role="slider"
            tabindex="0"
            aria-label="event timeline — click to seek"
            aria-valuemin="0"
            aria-valuemax={Math.round(tMax)}
            aria-valuenow={Math.round(t)}
        >
            <div class="tm-timeline-fill" style="width:{(t / tMax) * 100}%"></div>
            {#each keyEvents as e (e.t + '|' + e.message)}
                <button
                    class="tm-mark {e.type}"
                    style="left:{(Math.max(0, e.t) / tMax) * 100}%"
                    title="{fmtClock(Math.max(0, e.t))} — {e.message}"
                    aria-label={e.message}
                    on:click|stopPropagation={() => jumpTo(e.t)}
                ></button>
            {/each}
        </div>
    {/if}

    {#if tMax > 0}
        <div class="tm-radio">
            <span class="tm-radio-label">
                📻 Team radio{#if selected} · {selected}{/if}
                {#if nowPlaying}
                    <button class="tm-radio-stop" on:click={stopRadio}>⏹ {nowPlaying.code}</button>
                {/if}
            </span>
            {#if displayedRadio.length}
                <div class="tm-radio-track">
                    {#each displayedRadio as c (c.url)}
                        <button
                            class="tm-radio-mark {nowPlaying && nowPlaying.url === c.url ? 'on' : ''}"
                            style="left:{(c.t / tMax) * 100}%; background:{codeColor[c.code] || '#2dd4bf'}"
                            title="{fmtClock(c.t)} — {c.code}: {c.transcript || 'team radio'} (click to play)"
                            aria-label="{c.code} team radio at {fmtClock(c.t)}"
                            on:click={() => playRadio(c)}
                        ></button>
                    {/each}
                </div>
            {:else if selected}
                <span class="tm-radio-none">no team radio for {selected} in this race</span>
            {:else if radioClips.length}
                <div class="tm-radio-track"></div>
            {:else}
                <span class="tm-radio-none">none available for this race — try Barcelona or Hungary</span>
            {/if}
        </div>
    {/if}

    <!-- Keep nowPlaying (and its transcript caption) after the clip ends so it stays
         readable; it's replaced by the next clip or cleared with the stop button. -->
    <audio bind:this={audioEl} preload="none"></audio>

    <div class="tm-hint">
        Scroll to zoom · drag to pan · hover for details · click a car to follow it (and filter its
        team radio) · click an event marker to jump to safety cars / penalties · click a 📻 marker to
        play that team radio and roll the race on from there
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
    .tm-radio-caption {
        position: absolute;
        left: 50%;
        transform: translateX(-50%);
        bottom: 34px;
        max-width: 72%;
        text-align: center;
        color: #eafffb;
        font-size: 12.5px;
        line-height: 1.4;
        background: rgba(8, 12, 18, 0.82);
        border: 1px solid rgba(45, 212, 191, 0.35);
        padding: 5px 12px;
        border-radius: 8px;
    }
    .tm-msgs {
        position: absolute;
        top: 10px;
        right: 10px;
        width: 244px;
        max-width: 46%;
        background: rgba(8, 12, 18, 0.72);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 6px 8px;
        color: #e8eaed;
        backdrop-filter: blur(2px);
    }
    .tm-msg {
        display: flex;
        align-items: baseline;
        gap: 6px;
        font-size: 10.5px;
        line-height: 1.35;
        padding: 1px 0;
    }
    .tm-msg .mdot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        flex: none;
        transform: translateY(1px);
    }
    .tm-msg .mt {
        opacity: 0.6;
        font-variant-numeric: tabular-nums;
        flex: none;
    }
    .tm-msg .mm {
        opacity: 0.92;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .tm-empty {
        opacity: 0.5;
        font-style: italic;
    }
    .tm-timeline {
        position: relative;
        height: 12px;
        margin-top: 8px;
        border-radius: 6px;
        background: rgba(128, 128, 128, 0.18);
        cursor: pointer;
    }
    .tm-timeline-fill {
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        background: rgba(128, 128, 128, 0.32);
        border-radius: 6px 0 0 6px;
    }
    .tm-mark {
        position: absolute;
        top: -2px;
        width: 3px;
        height: 16px;
        margin-left: -1.5px;
        padding: 0;
        border: none;
        border-radius: 2px;
        cursor: pointer;
        transition: transform 0.1s;
    }
    .tm-mark:hover {
        transform: scaleY(1.35);
    }
    .tm-mark.sc { background: #e8a33d; }
    .tm-mark.red { background: #e8002d; }
    .tm-mark.chequered { background: #e8eaed; }
    .tm-mark.penalty { background: #ff7ab3; }
    .tm-radio {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 8px;
    }
    .tm-radio-label {
        font-size: 11px;
        opacity: 0.75;
        white-space: nowrap;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .tm-radio-stop {
        cursor: pointer;
        border: 1px solid rgba(45, 212, 191, 0.5);
        background: rgba(45, 212, 191, 0.12);
        color: inherit;
        border-radius: 5px;
        padding: 1px 6px;
        font-size: 10.5px;
    }
    .tm-radio-track {
        position: relative;
        flex: 1;
        height: 12px;
        border-radius: 6px;
        background: rgba(45, 212, 191, 0.12);
    }
    .tm-radio-none {
        font-size: 11px;
        opacity: 0.45;
        font-style: italic;
    }
    .tm-radio-mark {
        position: absolute;
        top: 1px;
        width: 10px;
        height: 10px;
        margin-left: -5px;
        padding: 0;
        border: 1px solid rgba(8, 12, 18, 0.6);
        border-radius: 50%;
        background: #2dd4bf;
        cursor: pointer;
        transition: transform 0.1s;
    }
    .tm-radio-mark:hover { transform: scale(1.4); }
    .tm-radio-mark.on {
        background: #eafffb;
        box-shadow: 0 0 0 2px rgba(45, 212, 191, 0.7);
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
