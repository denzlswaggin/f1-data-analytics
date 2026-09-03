<script>
    // Animated, interactive race-replay track map. Draws the circuit once on a
    // background canvas, then animates one dot per car on an overlay via
    // requestAnimationFrame, interpolating between time ticks for smooth motion.
    // Interactions: click a car to follow it, hover for a tooltip, scroll to zoom
    // and drag to pan. Fed by two Evidence queries: `data` (the per-car-per-tick
    // replay feed) and `meta` (per-driver names/teams/colours), joined by driver_code.
    import { onMount, onDestroy } from 'svelte';
    import TimingTower from './replay/TimingTower.svelte';
    import DriverDetail from './replay/DriverDetail.svelte';
    import EventTimeline from './replay/EventTimeline.svelte';

    export let data = [];
    export let laps = [];
    export let meta = [];
    export let messages = [];
    export let radio = [];
    export let overtakes = [];
    export let title = '';

    const SPEEDS = [1, 2, 4, 6, 12, 24, 48];
    const PAD = 28;
    const HIT_PX = 16; // click/hover pick radius
    const PASS_HL_S = 2.0; // seconds an overtake stays highlighted on the map
    // DOM (tower / clock / feed) refresh cap during playback (~15fps). The canvas
    // still animates every frame; only the reactive Svelte state is throttled, so the
    // 20-row tower doesn't re-render 60x/s and compete with the map on the main thread.
    const UI_MS = 66;

    let containerWidth = 900;
    $: splitLayout = containerWidth >= 980;
    $: width = Math.max(280, splitLayout ? containerWidth - 352 : containerWidth);
    $: compact = width < 620;
    $: height = Math.round(width * (compact ? 0.82 : 0.6));

    let rootEl, trackCanvas, carsCanvas, trackCtx, carsCtx;
    let playing = false;
    let t = 0, speed = 6, tMax = 0, raf = null, lastTs = null;
    let uiT = 0; // throttled copy of `t` that drives the DOM (see UI_MS)
    let lastUiMs = -1e9; // wall-clock of the last DOM refresh during playback

    let drivers = [];
    let bounds = null;
    let trackPts = null; // cached single-lap circuit outline (see build)
    let leaderboard = [];
    let totalLaps = null;
    let lapStarts = [];

    // View (zoom / pan) and interaction state.
    let view = { zoom: 1, ox: 0, oy: 0 };
    let selected = null; // driver_code being followed
    $: selectedDriver = selected
        ? leaderboard.find((driver) => driver.code === selected) || null
        : null;
    let hovered = null; // {code, name, team, order, gap, ahead, cx, cy}
    let activePass = null; // overtake currently highlighted on the map
    let screenPos = []; // last-rendered car screen positions, for hit-testing
    let dragging = false, dragMoved = false, dragStart = null;

    const asNum = (v) => (v == null ? null : Number(v));

    let loadedReplay = null;
    $: build(data, meta, laps, title);

    // --- race-control message feed (aligned to the replay clock via t_s) ---
    const EVT_COLOR = {
        sc: '#e8a33d', red: '#e8002d', chequered: '#e8eaed', green: '#2fbf71',
        yellow: '#e8d33d', drs: '#39a0ff', penalty: '#ff7ab3', info: '#9aa0b0',
    };
    let msgs = [];
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
    }
    // Newest-first messages up to the current time (recomputes as `t` advances).
    $: recentMsgs = msgs.filter((m) => m.t <= uiT).slice(-7).reverse();
    $: currentMsg = recentMsgs[0] || null;
    $: currentLap = leaderboard.length
        ? Math.max(0, ...leaderboard.map((driver) => driver.lap_number || 0)) || null
        : null;
    $: racePhase = uiT >= tMax && tMax > 0
        ? 'Finished'
        : currentMsg?.type === 'red'
            ? 'Red flag'
            : currentMsg?.type === 'sc'
                ? 'Safety car'
                : playing
                    ? 'Replay running'
                    : uiT > 0
                        ? 'Paused'
                        : 'Ready';
    function jumpTo(sec) {
        t = Math.max(0, Math.min(tMax, sec));
        if (!playing) drawFrame();
    }
    function jumpLap(direction) {
        if (!lapStarts.length) return;
        const currentIndex = Math.max(0, lapStarts.findLastIndex((start) => start <= t + 0.5));
        const target = lapStarts[Math.max(0, Math.min(lapStarts.length - 1, currentIndex + direction))];
        jumpTo(target);
    }
    function toggleFullscreen() {
        if (!rootEl || typeof document === 'undefined') return;
        if (document.fullscreenElement) document.exitFullscreen?.();
        else rootEl.requestFullscreen?.();
    }
    function onGlobalKey(e) {
        const tag = e.target?.tagName?.toLowerCase();
        if (['input', 'select', 'textarea', 'button', 'a'].includes(tag)) return;
        if (e.code === 'Space') toggle();
        else if (e.key === 'ArrowLeft') jumpTo(t - 5);
        else if (e.key === 'ArrowRight') jumpTo(t + 5);
        else return;
        e.preventDefault();
    }

    function onDriverKey(e, code) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggleSelect(code);
        }
    }

    // --- team radio (OpenF1 audio clips; partial coverage) ---
    let radioClips = [];
    $: radioClips = (radio || [])
        .map((r) => ({
            t: Number(r.t_s), code: r.driver_code || '', url: r.recording_url,
            transcript: r.transcript || null,
        }))
        .sort((a, b) => a.t - b.t);
    // --- overtakes (detected on-track passes, aligned to the replay clock) ---
    let passes = [];
    $: passes = (overtakes || [])
        .map((r) => ({
            t: Number(r.t_s), pos: asNum(r.for_position),
            passer: r.passer_code || '', passed: r.passed_code || '', gap: asNum(r.gap_at_pass_s),
            confidence: asNum(r.confidence), evidence: r.evidence || '', reason: r.reason || '',
        }))
        .sort((a, b) => a.t - b.t);
    // Following a car? show only passes it was involved in (as passer or passed).
    $: displayedPasses = selected
        ? passes.filter((p) => p.passer === selected || p.passed === selected)
        : passes;

    let audioEl;
    let nowPlaying = null;
    function playRadio(clip) {
        nowPlaying = clip;
        jumpTo(clip.t);
        // Watch the moment in real time: at the default 6x the replay races ~50 s of
        // track through an 8 s clip — steppy and out of sync with the audio. 1x is
        // smooth and matches the radio.
        speed = 1;
        if (audioEl) {
            audioEl.src = clip.url;
            audioEl.currentTime = 0;
            audioEl.play().catch(() => {});
        }
        play(); // roll the replay on from this moment
    }
    function playTimelineRadio({ clip }) {
        const url = clip?.recording_url || clip?.url;
        const match = radioClips.find((item) => item.url === url);
        if (match) playRadio(match);
    }
    function stopRadio() {
        // Pause AND fully release the media resource. A merely-paused <audio> keeps
        // its decoded clip + media pipeline resident, which can bog the page's canvas
        // compositing down after a clip plays; clearing src + load() frees it so the
        // replay stays smooth afterwards. The `if (audioEl.src)` guard stops the
        // load() from re-entering via the element's own error/emptied event.
        if (audioEl && audioEl.src) {
            audioEl.pause();
            audioEl.removeAttribute('src');
            audioEl.load();
        }
        nowPlaying = null;
    }

    function build(rows, metaRows, lapRows, replayTitle) {
        if (loadedReplay !== null && loadedReplay !== replayTitle) {
            pause();
            stopRadio();
            t = 0;
            uiT = 0;
            selected = null;
            hovered = null;
        }
        loadedReplay = replayTitle;
        if (!rows || !rows.length) {
            drivers = [];
            bounds = null;
            tMax = 0;
            return;
        }
        const metaMap = {};
        for (const m of metaRows || []) metaMap[m.driver_code] = m;
        const lapList = Array.from(lapRows || []);
        const lapMap = new Map();
        for (const lap of lapList) {
            const code = lap.driver_code;
            if (!lapMap.has(code)) lapMap.set(code, []);
            lapMap.get(code).push({
                lap: asNum(lap.lap_number),
                start: asNum(lap.lap_start_t_s),
                duration: asNum(lap.lap_time_sec),
                stint: asNum(lap.stint),
                compound: lap.compound || null,
                tyreLife: asNum(lap.tyre_life),
            });
        }
        for (const context of lapMap.values()) context.sort((a, b) => a.start - b.start);

        function lapState(code, time) {
            const context = lapMap.get(code) || [];
            let lo = 0, hi = context.length;
            while (lo < hi) {
                const mid = (lo + hi) >> 1;
                if (context[mid].start <= time) lo = mid + 1;
                else hi = mid;
            }
            const lap = context[lo - 1];
            if (!lap) return null;
            return {
                ...lap,
                progress: lap.duration > 0 ? Math.max(0, Math.min(1, (time - lap.start) / lap.duration)) : null,
            };
        }

        const groups = new Map();
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, tmax = 0;
        for (const row of rows) {
            let g = groups.get(row.driver_code);
            if (!g) {
                g = { code: row.driver_code, samples: [] };
                groups.set(row.driver_code, g);
            }
            const x = Number(row.x), y = Number(row.y), tt = Number(row.t_s);
            const lap = lapState(row.driver_code, tt);
            g.samples.push({
                t: tt, x, y,
                order: asNum(row.running_order),
                gap: asNum(row.gap_to_leader_s),
                ahead: asNum(row.gap_to_ahead_s),
                lap: asNum(row.lap_number) ?? lap?.lap ?? null,
                lapProgress: asNum(row.lap_progress) ?? lap?.progress ?? null,
                stint: asNum(row.stint) ?? lap?.stint ?? null,
                compound: row.compound || lap?.compound || null,
                tyreLife: asNum(row.tyre_life) ?? lap?.tyreLife ?? null,
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
            g.finishPosition = asNum(m.finish_position);
            g.isClassified = m.is_classified == null ? null : Boolean(m.is_classified);
            g.resultStatus = m.status || null;
            g.startOrder = asNum(m.grid_position);
            if (g.startOrder != null && g.startOrder <= 0) g.startOrder = null;
            out.push(g);
        }
        drivers = out;
        let maxLap = 0;
        for (const lap of lapList) maxLap = Math.max(maxLap, asNum(lap.lap_number) || 0);
        if (!maxLap) {
            for (const driver of out) {
                for (const sample of driver.samples) maxLap = Math.max(maxLap, sample.lap || 0);
            }
        }
        totalLaps = maxLap || null;
        const starts = new Map();
        for (const row of lapList) {
            const lap = asNum(row.lap_number);
            const time = asNum(row.lap_start_t_s);
            if (lap == null || time == null) continue;
            starts.set(lap, Math.min(starts.get(lap) ?? Infinity, time));
        }
        lapStarts = [...starts.entries()].sort((a, b) => a[0] - b[0]).map(([, time]) => time);
        bounds = { minX, maxX, minY, maxY };
        // Cache a single clean lap of the circuit for the track outline. The reference
        // driver's samples retrace the same track once per lap (dozens of times over a
        // race); take just the first lap — a contiguous run from the start until the path
        // returns near where it began — so drawTrack strokes ~100 points instead of tens
        // of thousands. That's the difference between the follow-cam at 60fps and 2fps.
        let ref = null;
        for (const g of out) if (!ref || g.samples.length > ref.samples.length) ref = g;
        trackPts = [];
        if (ref && ref.samples.length) {
            const diag = Math.hypot(maxX - minX, maxY - minY) || 1;
            const near = diag * 0.02, far = diag * 0.15;
            const s0 = ref.samples[0];
            trackPts.push(s0);
            let left = false;
            for (let i = 1; i < ref.samples.length; i++) {
                const p = ref.samples[i];
                trackPts.push(p);
                const d = Math.hypot(p.x - s0.x, p.y - s0.y);
                if (d > far) left = true;
                if (left && d < near) break; // returned to the start line → one lap
            }
        }
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
        if (!trackCtx || !bounds || !trackPts || !trackPts.length) return;
        trackCtx.clearRect(0, 0, width, height);
        // Cap the width: baseScale*zoom*260 balloons to hundreds of px when zoomed in,
        // and a very wide stroke is expensive to paint every frame under the follow-cam.
        trackCtx.lineWidth = Math.min(30, Math.max(6, baseScale() * view.zoom * 260));
        // One lap drawn once, so a single visible alpha (the old faint 0.07 relied on
        // dozens of overlapping laps stacking up).
        trackCtx.strokeStyle = 'rgba(255,255,255,0.42)';
        trackCtx.lineJoin = 'round';
        trackCtx.lineCap = 'round';
        trackCtx.beginPath();
        for (let i = 0; i < trackPts.length; i++) {
            const X = wx(trackPts[i].x), Y = wy(trackPts[i].y);
            i === 0 ? trackCtx.moveTo(X, Y) : trackCtx.lineTo(X, Y);
        }
        trackCtx.stroke();
    }

    // Uniform Catmull-Rom through four points — a smooth curve that passes through
    // p1 and p2, so the dot follows the racing line through corners instead of the
    // straight-line kinks that linear interpolation gives on 1 s ticks.
    function catmull(q0, q1, q2, q3, f) {
        const f2 = f * f, f3 = f2 * f;
        return 0.5 * (2 * q1 + (-q0 + q2) * f + (2 * q0 - 5 * q1 + 4 * q2 - q3) * f2 + (-q0 + 3 * q1 - 3 * q2 + q3) * f3);
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
        // Spline through the two neighbours either side (clamped at the ends). Fall
        // back to linear across a time gap (a red-flag stoppage leaves non-adjacent
        // samples) so the curve can't fly off between disconnected points.
        const p0 = s[lo - 2] || a, p3 = s[lo + 1] || b;
        const smooth = (b.t - a.t) <= 1.5 && (a.t - p0.t) <= 1.5 && (p3.t - b.t) <= 1.5;
        return {
            x: smooth ? catmull(p0.x, a.x, b.x, p3.x, f) : a.x + (b.x - a.x) * f,
            y: smooth ? catmull(p0.y, a.y, b.y, p3.y, f) : a.y + (b.y - a.y) * f,
            order: a.order, gap: a.gap, ahead: a.ahead,
            lap: a.lap, lapProgress: a.lapProgress, stint: a.stint,
            compound: a.compound, tyreLife: a.tyreLife,
        };
    }

    function timingRow(g, p, status = 'racing') {
        return {
            code: g.code,
            name: g.name,
            team: g.team,
            color: g.color,
            order: p.order,
            gap: p.gap,
            ahead: p.ahead,
            lap_number: p.lap,
            lap_progress: p.lapProgress,
            stint: p.stint,
            compound: p.compound,
            tyre_life: p.tyreLife,
            pit_stops: p.stint == null ? null : Math.max(0, p.stint - 1),
            position_change:
                g.startOrder == null || p.order == null ? null : g.startOrder - p.order,
            status,
        };
    }

    function render(uiUpdate = true) {
        if (!carsCtx || !bounds) return;
        carsCtx.clearRect(0, 0, width, height);
        const board = [], sp = [];
        for (const g of drivers) {
            const p = sampleAt(g, t);
            if (!p) {
                if (t > g.tmax && g.samples.length) {
                    const last = g.samples[g.samples.length - 1];
                    const status = g.isClassified === true
                        ? 'finished'
                        : g.isClassified === false
                            ? 'retired'
                            : 'out';
                    board.push(timingRow(g, last, status));
                }
                continue;
            }
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
            if (p.order != null) board.push(timingRow(g, p));
        }
        board.sort((a, b) => a.order - b.order);
        screenPos = sp;
        // Highlight overtakes around the current time: a ring on the passer and a
        // connector to the car it passed, fading out over the seconds after the move.
        const byCode = {};
        for (const s of sp) byCode[s.code] = s;
        let active = null;
        for (const p of displayedPasses) {
            const dt = t - p.t;
            if (dt < -0.6 || dt > PASS_HL_S) continue;
            const A = byCode[p.passer], B = byCode[p.passed];
            if (!A || !B) continue;
            const a = dt < 0 ? 1 : 1 - dt / PASS_HL_S;
            carsCtx.strokeStyle = '#2fbf71';
            carsCtx.globalAlpha = 0.55 * a;
            carsCtx.lineWidth = 2;
            carsCtx.beginPath();
            carsCtx.moveTo(A.X, A.Y);
            carsCtx.lineTo(B.X, B.Y);
            carsCtx.stroke();
            carsCtx.globalAlpha = a;
            carsCtx.lineWidth = 2.5;
            carsCtx.beginPath();
            carsCtx.arc(A.X, A.Y, 12, 0, Math.PI * 2);
            carsCtx.stroke();
            active = p;
        }
        carsCtx.globalAlpha = 1;
        // Reactive/DOM state (tower, clock, caption, tooltip) refreshes at the UI_MS
        // cadence during playback, not every animation frame — the map keeps moving at
        // 60fps while the surrounding DOM updates ~15fps, which is what stops the jank.
        if (uiUpdate) {
            leaderboard = board;
            uiT = t;
            activePass = active;
            if (hovered) {
                const h = sp.find((s) => s.code === hovered.code);
                hovered = h ? { ...hovered, order: h.order, gap: h.gap, ahead: h.ahead, cx: h.X, cy: h.Y } : null;
            }
        }
    }

    // Follow-cam: while a car is followed AND the user has zoomed in, keep it centred
    // so the camera tracks it around the lap. (At zoom 1 the whole circuit is in view,
    // so there's nothing to follow.) Returns whether it moved the view.
    function centerFollowed() {
        if (selected == null || !bounds || view.zoom <= 1) return false;
        const g = drivers.find((d) => d.code === selected);
        if (!g) return false;
        const p = sampleAt(g, t);
        if (!p) return false;
        const s = baseScale() * view.zoom;
        view.ox = width / 2 - (p.x - bounds.minX) * s;
        view.oy = height / 2 - (bounds.maxY - p.y) * s;
        return true;
    }
    // One drawn frame: recentre on the followed car first; if that moved the view the
    // static track layer must be redrawn too, otherwise just the cars overlay.
    function drawFrame(uiUpdate = true) {
        if (centerFollowed()) drawTrack();
        render(uiUpdate);
    }
    // Follow/unfollow a car; recentre immediately when paused (playback redraws anyway).
    function toggleSelect(code) {
        selected = selected === code ? null : code;
        if (!playing) drawFrame();
    }

    let _drawScheduled = false;
    function queueDraw() {
        if (typeof requestAnimationFrame === 'undefined') return; // SSR prerender
        if (_drawScheduled) return; // coalesce many calls in one frame into a single draw
        _drawScheduled = true;
        requestAnimationFrame(() => {
            _drawScheduled = false;
            centerFollowed();
            drawTrack();
            render();
        });
    }

    function loop(ts) {
        if (!playing) return;
        if (lastTs == null) lastTs = ts;
        t = Math.min(tMax, t + ((ts - lastTs) / 1000) * speed);
        lastTs = ts;
        const doUi = ts - lastUiMs >= UI_MS; // throttle the DOM, not the canvas
        if (doUi) lastUiMs = ts;
        drawFrame(doUi);
        if (t >= tMax) {
            playing = false;
            lastTs = null;
            render(true); // final DOM sync at the finish line
            return;
        }
        raf = requestAnimationFrame(loop);
    }
    function play() {
        if (playing) return;
        if (t >= tMax) t = 0;
        playing = true;
        lastTs = null;
        lastUiMs = -1e9; // refresh the DOM on the first frame
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
        if (!playing) drawFrame();
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
            if (n) toggleSelect(n.code);
            else if (selected != null) toggleSelect(selected); // click empty space = release
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
    const fmtConfidence = (value) => value == null ? 'confidence unavailable' : `${Math.round(value * 100)}% confidence`;

    onMount(() => {
        trackCtx = trackCanvas.getContext('2d');
        carsCtx = carsCanvas.getContext('2d');
        // Wheel needs a non-passive listener to preventDefault the page scroll.
        carsCanvas.addEventListener('wheel', onWheel, { passive: false });
        window.addEventListener('keydown', onGlobalKey);
        queueDraw();
    });
    onDestroy(() => {
        pause();
        if (carsCanvas) carsCanvas.removeEventListener('wheel', onWheel);
        if (typeof window !== 'undefined') window.removeEventListener('keydown', onGlobalKey);
    });

    // Redraw on resize / new data (independent of `t`, so playback is unaffected).
    // Redraw when the canvas size or track data actually changes. Guarded by a value
    // key so a same-value reassignment (e.g. a ResizeObserver re-firing on containerWidth)
    // can't re-trigger this thousands of times a second.
    let _drawKey = '';
    $: {
        const key =
            trackCtx && bounds
                ? `${width}x${height}|${bounds.minX},${bounds.maxX},${bounds.minY},${bounds.maxY}`
                : '';
        if (key && key !== _drawKey) {
            _drawKey = key;
            queueDraw();
        }
    }
</script>

<div class="tm" bind:this={rootEl} bind:clientWidth={containerWidth}>
    <header class="tm-header">
        <div>
            <span class="tm-eyebrow">Race replay</span>
            {#if title}<h2 class="tm-title">{title}</h2>{/if}
        </div>
        <div class="tm-session" aria-live="polite">
            <span class="tm-session-dot" class:active={playing}></span>
            <strong>{racePhase}</strong>
            {#if currentLap}<span>Lap {currentLap}{totalLaps ? ` / ${totalLaps}` : ''}</span>{/if}
        </div>
    </header>
    <div class="tm-broadcast">
    <div class="tm-stage" style="width:{width}px;height:{height}px">
        <canvas bind:this={trackCanvas} {width} {height}></canvas>
        <canvas
            bind:this={carsCanvas}
            {width}
            {height}
            class="cars {dragging ? 'grabbing' : hovered ? 'pick' : 'grab'}"
            role="img"
            aria-label="Animated circuit map. Use the running order to select a driver."
            on:mousemove={onMove}
            on:mousedown={onDown}
            on:mouseup={onUp}
            on:mouseleave={onLeave}
        ></canvas>

        {#if !data || !data.length}
            <div class="tm-no-data">
                Replay data is not available for this race.
            </div>
        {/if}

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
            <div class="tm-radio-caption">
                <span>📻 {nowPlaying.code}: “{nowPlaying.transcript}”</span>
                <button type="button" on:click={stopRadio} aria-label="Stop team radio">Stop</button>
            </div>
        {/if}

        {#if activePass}
            <div class="tm-pass-caption">
                ⇄ {activePass.passer} ▸ {activePass.passed} · P{activePass.pos} · {fmtConfidence(activePass.confidence)}
            </div>
        {/if}

        <div class="tm-clock">{fmtClock(uiT)} / {fmtClock(tMax)}</div>
        {#if selected}<div class="tm-follow">{`Following ${selected}${view.zoom > 1 ? ' · camera locked' : ''} · click to release`}</div>{/if}
    </div>
    <TimingTower
        {leaderboard}
        selectedCode={selected}
        title="Live timing"
        maxRows={splitLayout ? null : compact ? 10 : null}
        statusLabel={racePhase}
        active={playing}
        onSelect={({ code }) => toggleSelect(code)}
    />
    </div>

    {#if currentMsg}
        <div class="tm-mobile-event" aria-live="polite">
            <span class="mdot" style="background:{EVT_COLOR[currentMsg.type]}"></span>
            <strong>{fmtClock(Math.max(0, currentMsg.t))}</strong>
            <span>{currentMsg.message}</span>
        </div>
    {/if}

    <div class="tm-controls">
        <button on:click={toggle} class="tm-btn tm-play">{playing ? '❚❚ Pause' : '▶ Play'}</button>
        <button on:click={() => jumpTo(t - 5)} class="tm-btn tm-skip" aria-label="Back 5 seconds">−5s</button>
        <button on:click={() => jumpTo(t + 5)} class="tm-btn tm-skip" aria-label="Forward 5 seconds">+5s</button>
        <input type="range" min="0" max={tMax} step="0.5" value={uiT} on:input={onScrub} class="tm-scrub" aria-label="Replay time" />
        <label class="tm-speed">
            Speed
            <select bind:value={speed}>
                {#each SPEEDS as sp}<option value={sp}>{sp}×</option>{/each}
            </select>
        </label>
        <button on:click={() => jumpLap(-1)} class="tm-btn tm-lap" aria-label="Previous lap">← Lap</button>
        <button on:click={() => jumpLap(1)} class="tm-btn tm-lap" aria-label="Next lap">Lap →</button>
        <button on:click={resetView} class="tm-btn" title="Reset zoom & pan">Reset view</button>
        <button on:click={toggleFullscreen} class="tm-btn" title="Open replay fullscreen">Fullscreen</button>
    </div>

    {#if selectedDriver}
        <DriverDetail
            driver={selectedDriver}
            {totalLaps}
            onClose={() => toggleSelect(selected)}
        />
    {/if}

    {#if tMax > 0}
        <EventTimeline
            duration={tMax}
            currentTime={uiT}
            {messages}
            {overtakes}
            {radio}
            selectedCode={selected}
            onSeek={({ time }) => jumpTo(time)}
            onPlayRadio={playTimelineRadio}
        />
    {/if}

    <!-- The transcript caption shows only while the clip is playing: `ended` (or a
         load error) clears nowPlaying so it disappears once the conversation is over
         instead of staying stuck on screen. The stop button clears it early. -->
    <audio bind:this={audioEl} preload="none" on:ended={stopRadio} on:error={stopRadio}></audio>

    <div class="tm-hint">
        Space plays or pauses · arrows jump five seconds · scroll to zoom · drag to pan · select a
        driver to follow their race and filter the unified event timeline
    </div>
</div>

<style>
    .tm {
        width: 100%;
        margin: 0.5rem 0 1.25rem;
        font-family: system-ui, sans-serif;
    }
    .tm:fullscreen {
        box-sizing: border-box;
        padding: 1.25rem;
        overflow: auto;
        color: #f5f7fb;
        background: #080a0e;
    }
    .tm-header {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.65rem;
    }
    .tm-eyebrow {
        display: block;
        margin-bottom: 0.3rem;
        color: #747d91;
        font-size: 0.6rem;
        font-weight: 750;
        letter-spacing: 0.16em;
        text-transform: uppercase;
    }
    .tm-title {
        margin: 0;
        font-size: 1.05rem;
        font-weight: 700;
        letter-spacing: -0.015em;
    }
    .tm-session {
        display: flex;
        align-items: center;
        gap: 0.45rem;
        color: #6f7889;
        font-size: 0.68rem;
        font-variant-numeric: tabular-nums;
    }
    .tm-session strong { color: inherit; font-size: inherit; text-transform: uppercase; }
    .tm-session span:last-child {
        padding-left: 0.45rem;
        border-left: 1px solid rgba(128, 128, 128, 0.3);
    }
    .tm-session-dot {
        width: 0.45rem;
        height: 0.45rem;
        background: #8b93a7;
        border-radius: 50%;
    }
    .tm-session-dot.active {
        background: #ef304b;
        box-shadow: 0 0 0 4px rgba(239, 48, 75, 0.12);
    }
    .tm-broadcast {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 336px;
        align-items: start;
        gap: 1rem;
    }
    .tm-broadcast :global(.tower) { height: 100%; }
    .tm > :global(.detail) { margin-top: 0.75rem; }
    .tm > :global(.timeline) { margin-top: 0.75rem; }
    @media (max-width: 979px) {
        .tm-broadcast { grid-template-columns: minmax(0, 1fr); }
        .tm-broadcast :global(.tower) { height: auto; }
    }
    .tm-stage {
        position: relative;
        background: #0b0f14;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08);
        max-width: 100%;
        /* Isolate the animated map's layout/paint from the (very tall, in dev) page:
           the canvas repaints every frame, and without containment the browser can
           repaint page regions under it, which shows up as heavy per-frame cost. */
        contain: content;
    }
    .tm-stage canvas {
        position: absolute;
        left: 0;
        top: 0;
    }
    .tm-no-data {
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        color: #c7cbd1;
        font-size: 0.95rem;
    }
    .cars.grab { cursor: grab; }
    .cars.grabbing { cursor: grabbing; }
    .cars.pick { cursor: pointer; }
    .tm-board-h {
        font-size: 9px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        opacity: 0.6;
        margin-bottom: 3px;
    }
    .sw {
        display: inline-block;
        width: 9px;
        height: 9px;
        border-radius: 2px;
        flex: none;
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
        display: flex;
        align-items: center;
        gap: 0.65rem;
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
    .tm-radio-caption span {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .tm-radio-caption button {
        flex: none;
        padding: 2px 7px;
        color: inherit;
        background: rgba(45, 212, 191, 0.12);
        border: 1px solid rgba(45, 212, 191, 0.45);
        border-radius: 5px;
        cursor: pointer;
        font: inherit;
        font-size: 10px;
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
    .tm-mobile-event { display: none; }
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
    .tm-pass-caption {
        position: absolute;
        left: 50%;
        top: 8px;
        transform: translateX(-50%);
        color: #eafff1;
        font-size: 12.5px;
        font-weight: 600;
        background: rgba(8, 12, 18, 0.82);
        border: 1px solid rgba(47, 191, 113, 0.4);
        padding: 4px 12px;
        border-radius: 8px;
        pointer-events: none;
        z-index: 2;
    }
    .tm-controls {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 10px;
        flex-wrap: wrap;
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
    .tm-btn:focus-visible,
    .tm-radio-caption button:focus-visible {
        outline: 2px solid #71b9f4;
        outline-offset: 2px;
    }
    .tm-play { min-width: 92px; }
    .tm-skip, .tm-lap { padding-inline: 9px; font-variant-numeric: tabular-nums; }
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
    @media (max-width: 619px) {
        .tm-msgs { display: none; }
        .tm-header { align-items: flex-start; flex-direction: column; gap: 0.45rem; }
        .tm-clock { font-size: 11px; }
        .tm-follow { right: 8px; bottom: 28px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .tm-radio-caption { max-width: 88%; font-size: 11px; }
        .tm-mobile-event {
            display: flex;
            align-items: flex-start;
            gap: 0.45rem;
            min-height: 2.3rem;
            margin-top: 0.5rem;
            padding: 0.5rem 0.65rem;
            border-radius: 0.45rem;
            background: rgba(128, 128, 128, 0.1);
            font-size: 0.72rem;
            line-height: 1.35;
        }
        .tm-mobile-event .mdot { width: 7px; height: 7px; margin-top: 0.25rem; border-radius: 50%; flex: none; }
        .tm-mobile-event strong { font-variant-numeric: tabular-nums; }
        .tm-controls { flex-wrap: wrap; gap: 8px; }
        .tm-scrub { flex-basis: 100%; order: -1; min-width: 0; }
        .tm-play { min-width: 82px; }
        .tm-speed { margin-left: auto; }
        .tm-hint { line-height: 1.45; }
    }
</style>
