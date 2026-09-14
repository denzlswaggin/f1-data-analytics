<script>
    import { createEventDispatcher } from 'svelte';

    export let duration = 0;
    export let currentTime = 0;
    export let messages = [];
    export let overtakes = [];
    export let radio = [];
    export let selectedCode = null;
    export let onSeek = null;
    export let onPlayRadio = null;

    const dispatch = createEventDispatcher();
    const FILTERS = [
        { id: 'all', label: 'All' },
        { id: 'control', label: 'Race control' },
        { id: 'overtake', label: 'Overtakes' },
        { id: 'radio', label: 'Radio' }
    ];
    const COLORS = {
        control: '#f1c94c',
        safety: '#f5a33a',
        red: '#ff3553',
        green: '#3bd486',
        overtake: '#51a8ff',
        radio: '#c28bff'
    };

    let activeFilter = 'all';

    const num = (value) => (value == null || value === '' ? null : Number(value));
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const eventTime = (row) => num(row?.t_s ?? row?.time ?? row?.timestamp_s);

    $: totalDuration = Math.max(0, num(duration) || 0);
    $: playhead = clamp(num(currentTime) || 0, 0, totalDuration);
    $: visibleFilters = selectedCode
        ? FILTERS.filter((filter) => filter.id !== 'control')
        : FILTERS;
    $: if (selectedCode && activeFilter === 'control') activeFilter = 'all';
    // Keep selectedCode as an explicit reactive dependency. Svelte cannot infer
    // dependencies hidden inside a function passed to Array.filter().
    $: scopedEvents = mergedEvents.filter((event) => relevantToSelection(event, selectedCode));
    $: filteredEvents = scopedEvents.filter((event) => activeFilter === 'all' || event.category === activeFilter);
    $: nearbyEvents = [...filteredEvents]
        .sort((a, b) => Math.abs(a.time - playhead) - Math.abs(b.time - playhead) || a.time - b.time)
        .slice(0, 5)
        .sort((a, b) => a.time - b.time);
    $: counts = Object.fromEntries(
        FILTERS.map((filter) => [
            filter.id,
            filter.id === 'all' ? scopedEvents.length : scopedEvents.filter((event) => event.category === filter.id).length
        ])
    );
    $: mergedEvents = buildEvents(messages, overtakes, radio);

    function buildEvents(messageRows, overtakeRows, radioRows) {
        const events = [];

        for (const [index, raw] of (messageRows || []).entries()) {
            const time = eventTime(raw);
            if (time == null || !Number.isFinite(time)) continue;
            const driverCode = raw.driver_code || raw.code || '';
            const label = raw.message || raw.category || raw.flag || 'Race control update';
            events.push({
                id: `control|${time}|${driverCode}|${label}|${index}`,
                category: 'control',
                subtype: classifyMessage(raw),
                time,
                driverCode,
                label,
                meta: [raw.flag, raw.category].filter(Boolean).join(' · '),
                raw
            });
        }

        for (const [index, raw] of (overtakeRows || []).entries()) {
            const time = eventTime(raw);
            if (time == null || !Number.isFinite(time)) continue;
            const passer = raw.passer_code || raw.passer || '';
            const passed = raw.passed_code || raw.passed || '';
            const position = num(raw.for_position ?? raw.position);
            events.push({
                id: `overtake|${time}|${passer}|${passed}|${index}`,
                category: 'overtake',
                subtype: 'overtake',
                time,
                driverCode: passer,
                participants: [passer, passed].filter(Boolean),
                label: `${passer || 'Driver'} passes ${passed || 'driver'}`,
                meta: `${position == null ? 'Position unavailable' : `For P${position}`} · Unverified model event`,
                raw
            });
        }

        for (const [index, raw] of (radioRows || []).entries()) {
            const time = eventTime(raw);
            if (time == null || !Number.isFinite(time)) continue;
            const driverCode = raw.driver_code || raw.code || '';
            events.push({
                id: `radio|${time}|${driverCode}|${raw.recording_url || ''}|${index}`,
                category: 'radio',
                subtype: 'radio',
                time,
                driverCode,
                label: raw.transcript || `${driverCode || 'Team'} radio`,
                meta: driverCode ? `${driverCode} team radio` : 'Team radio',
                raw
            });
        }

        return events.sort((a, b) => a.time - b.time || a.id.localeCompare(b.id));
    }

    function classifyMessage(row) {
        const flag = String(row.flag || '').toUpperCase();
        const category = String(row.category || '').toUpperCase();
        const message = String(row.message || '').toUpperCase();
        if (flag === 'RED' || message.includes('RED FLAG')) return 'red';
        if (flag === 'GREEN') return 'green';
        if (category === 'SAFETYCAR' || message.includes('SAFETY CAR') || message.includes('VSC')) return 'safety';
        return 'control';
    }

    function relevantToSelection(event, driverCode) {
        if (!driverCode) return true;
        if (event.category === 'overtake') return event.participants.includes(driverCode);
        if (event.category === 'radio') return event.driverCode === driverCode;
        return false;
    }

    function formatTime(seconds) {
        const safe = Math.max(0, Math.floor(num(seconds) || 0));
        const hours = Math.floor(safe / 3600);
        const minutes = Math.floor((safe % 3600) / 60);
        const secs = safe % 60;
        return hours > 0
            ? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
            : `${minutes}:${String(secs).padStart(2, '0')}`;
    }

    function labelFor(event) {
        return `${formatTime(event.time)} — ${event.label}${event.meta ? `, ${event.meta}` : ''}`;
    }

    function colorFor(event) {
        return COLORS[event.subtype] || COLORS[event.category] || COLORS.control;
    }

    function seek(time, event = null) {
        const detail = { time: clamp(num(time) || 0, 0, totalDuration), event, raw: event?.raw ?? null };
        if (typeof onSeek === 'function') onSeek(detail);
        dispatch('seek', detail);
    }

    function playRadio(event) {
        const detail = { time: event.time, clip: event.raw, event };
        if (typeof onPlayRadio === 'function') onPlayRadio(detail);
        dispatch('playradio', detail);
    }

    function activateMarker(event) {
        if (event.category === 'radio') playRadio(event);
        else seek(event.time, event);
    }

    function onRailClick(event) {
        const bounds = event.currentTarget.getBoundingClientRect();
        if (!bounds.width || !totalDuration) return;
        seek(((event.clientX - bounds.left) / bounds.width) * totalDuration);
    }

    function onRailKeydown(event) {
        const steps = { ArrowLeft: -5, ArrowRight: 5, PageDown: -30, PageUp: 30 };
        if (event.key in steps) seek(playhead + steps[event.key]);
        else if (event.key === 'Home') seek(0);
        else if (event.key === 'End') seek(totalDuration);
        else return;
        event.preventDefault();
    }
</script>

<section class="timeline" aria-label="Race event timeline">
    <header>
        <div>
            <span class="eyebrow">Race intelligence</span>
            <h2>Event timeline</h2>
        </div>
        <div class="clock" aria-label={`Replay time ${formatTime(playhead)} of ${formatTime(totalDuration)}`}>
            <strong>{formatTime(playhead)}</strong><span>/ {formatTime(totalDuration)}</span>
        </div>
    </header>

    <div class="filters" aria-label="Filter race events">
        {#each visibleFilters as filter}
            <button
                type="button"
                class:active={activeFilter === filter.id}
                aria-pressed={activeFilter === filter.id}
                on:click={() => (activeFilter = filter.id)}
            >
                {filter.label}<span>{counts[filter.id] || 0}</span>
            </button>
        {/each}
        {#if selectedCode}<p>Showing overtakes &amp; radio for <strong>{selectedCode}</strong></p>{/if}
    </div>

    <div class="track-wrap">
        <button
            type="button"
            class="rail"
            aria-label="Seek race replay. Use left and right arrows for five seconds, Page Up and Page Down for thirty seconds."
            on:click={onRailClick}
            on:keydown={onRailKeydown}
        >
            <span class="elapsed" style={`width: ${totalDuration ? (playhead / totalDuration) * 100 : 0}%`}></span>
            <span class="playhead" style={`left: ${totalDuration ? (playhead / totalDuration) * 100 : 0}%`}></span>
        </button>

        <div class="markers" aria-label={`${filteredEvents.length} visible race events`}>
            {#each filteredEvents as event (event.id)}
                <button
                    type="button"
                    class="marker {event.category}"
                    class:past={event.time <= playhead}
                    style={`left: ${totalDuration ? clamp((event.time / totalDuration) * 100, 0, 100) : 0}%; --event-color: ${colorFor(event)}`}
                    title={labelFor(event)}
                    aria-label={`${event.category === 'radio' ? 'Play' : 'Seek to'} ${labelFor(event)}`}
                    on:click={() => activateMarker(event)}
                >
                    <span class="tooltip" aria-hidden="true"><strong>{formatTime(event.time)}</strong>{event.label}</span>
                </button>
            {/each}
        </div>
        <div class="scale" aria-hidden="true">
            <span>Start</span><span>{formatTime(totalDuration / 2)}</span><span>Finish</span>
        </div>
    </div>

    <div class="nearby">
        <div class="nearby-head">
            <h3>Nearby events</h3>
            <span>around {formatTime(playhead)}</span>
        </div>
        {#if nearbyEvents.length}
            <ol>
                {#each nearbyEvents as event (event.id)}
                    <li class:current={Math.abs(event.time - playhead) <= 3}>
                        <button type="button" class="event-main" on:click={() => seek(event.time, event)}>
                            <span class="event-icon" style={`--event-color: ${colorFor(event)}`}></span>
                            <time>{formatTime(event.time)}</time>
                            <span class="event-copy">
                                <strong>{event.label}</strong>
                                <small>{event.meta}</small>
                            </span>
                        </button>
                        {#if event.category === 'radio'}
                            <button
                                type="button"
                                class="listen"
                                aria-label={`Play ${event.meta} at ${formatTime(event.time)}`}
                                on:click={() => playRadio(event)}
                            >▶ Listen</button>
                        {/if}
                    </li>
                {/each}
            </ol>
        {:else}
            <p class="empty">No {activeFilter === 'all' ? '' : `${FILTERS.find((item) => item.id === activeFilter)?.label.toLowerCase()} `}events are available for this selection.</p>
        {/if}
    </div>
</section>

<style>
    .timeline {
        color: #f4f6fa;
        background: linear-gradient(160deg, #171a22, #0a0c11 72%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 14px;
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.3), inset 0 1px rgba(255, 255, 255, 0.04);
        font-variant-numeric: tabular-nums;
    }
    header { display: flex; align-items: flex-end; justify-content: space-between; padding: 17px 19px 14px; }
    .eyebrow { color: #858da0; font-size: 9px; font-weight: 760; letter-spacing: 0.15em; line-height: 1; text-transform: uppercase; }
    h2 { margin: 5px 0 0; color: #fff; font-size: 16px; font-weight: 700; letter-spacing: -0.015em; line-height: 1; }
    .clock { display: flex; align-items: baseline; gap: 5px; }
    .clock strong { color: #fff; font-size: 17px; font-weight: 720; }
    .clock span { color: #687184; font-size: 10px; }
    .filters { display: flex; align-items: center; gap: 5px; padding: 0 19px 13px; overflow-x: auto; scrollbar-width: none; }
    .filters::-webkit-scrollbar { display: none; }
    .filters button {
        flex: 0 0 auto;
        padding: 6px 8px;
        color: #9aa2b3;
        background: rgba(255, 255, 255, 0.035);
        border: 1px solid rgba(255, 255, 255, 0.075);
        border-radius: 6px;
        cursor: pointer;
        font: 650 9px/1 inherit;
        letter-spacing: 0.03em;
    }
    .filters button span { margin-left: 5px; color: #657084; font-size: 8px; }
    .filters button:hover { color: #fff; background: rgba(255, 255, 255, 0.07); }
    .filters button.active { color: #fff; background: #293142; border-color: #46536d; }
    .filters button:focus-visible,
    .rail:focus-visible,
    .marker:focus-visible,
    .event-main:focus-visible,
    .listen:focus-visible { outline: 2px solid #80aaff; outline-offset: 2px; }
    .filters p { flex: 0 0 auto; margin: 0 0 0 auto; color: #737c90; font-size: 9px; }
    .filters p strong { color: #cdd2dc; }
    .track-wrap { position: relative; padding: 18px 19px 7px; background: rgba(255, 255, 255, 0.018); border-block: 1px solid rgba(255, 255, 255, 0.07); }
    .rail { position: relative; display: block; width: 100%; height: 9px; padding: 0; overflow: visible; background: #292e39; border: 0; border-radius: 5px; cursor: crosshair; }
    .elapsed { position: absolute; inset: 0 auto 0 0; background: linear-gradient(90deg, #48546c, #7888aa); border-radius: inherit; pointer-events: none; }
    .playhead { position: absolute; z-index: 4; top: 50%; width: 3px; height: 25px; background: #fff; border-radius: 2px; box-shadow: 0 0 0 4px rgba(255, 255, 255, 0.09), 0 2px 8px #000; pointer-events: none; transform: translate(-50%, -50%); }
    .markers { position: absolute; inset: 18px 19px auto; height: 9px; pointer-events: none; }
    .marker { position: absolute; z-index: 3; top: 50%; width: 10px; height: 16px; padding: 0; background: #11151c; border: 2px solid var(--event-color); border-radius: 3px; box-shadow: 0 1px 5px rgba(0, 0, 0, 0.65); cursor: pointer; pointer-events: auto; transform: translate(-50%, -50%); }
    .marker.overtake { border-radius: 50%; }
    .marker.radio { width: 9px; height: 19px; border-radius: 5px; }
    .marker.past { background: var(--event-color); }
    .marker:hover,
    .marker:focus-visible { z-index: 10; transform: translate(-50%, -50%) scale(1.25); }
    .tooltip { position: absolute; z-index: 20; bottom: calc(100% + 9px); left: 50%; display: none; width: max-content; max-width: 220px; padding: 7px 9px; color: #e9edf4; background: #222732; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; box-shadow: 0 8px 22px rgba(0, 0, 0, 0.4); font-size: 9px; line-height: 1.35; pointer-events: none; transform: translateX(-50%); }
    .tooltip strong { margin-right: 6px; color: var(--event-color); }
    .marker:hover .tooltip,
    .marker:focus-visible .tooltip { display: block; }
    .scale { display: flex; justify-content: space-between; margin-top: 9px; color: #5e6779; font-size: 8px; }
    .nearby { padding: 13px 12px 12px; }
    .nearby-head { display: flex; align-items: baseline; justify-content: space-between; padding: 0 7px 8px; }
    h3 { margin: 0; color: #cdd2dc; font-size: 10px; font-weight: 720; letter-spacing: 0.07em; text-transform: uppercase; }
    .nearby-head span { color: #687184; font-size: 8px; }
    ol { margin: 0; padding: 0; list-style: none; }
    li { display: flex; align-items: center; min-height: 40px; border-radius: 7px; }
    li.current { background: rgba(255, 255, 255, 0.045); box-shadow: inset 2px 0 #fff; }
    li:hover { background: rgba(255, 255, 255, 0.035); }
    .event-main { display: grid; grid-template-columns: 8px 42px minmax(0, 1fr); align-items: center; gap: 8px; flex: 1; min-width: 0; padding: 6px 7px; color: inherit; background: transparent; border: 0; border-radius: 6px; cursor: pointer; font: inherit; text-align: left; }
    .event-icon { width: 7px; height: 7px; background: var(--event-color); border-radius: 50%; box-shadow: 0 0 0 3px color-mix(in srgb, var(--event-color) 15%, transparent); }
    time { color: #778195; font-size: 9px; font-weight: 650; }
    .event-copy { min-width: 0; }
    .event-copy strong { display: block; overflow: hidden; color: #e1e5ec; font-size: 10px; font-weight: 620; line-height: 1.25; text-overflow: ellipsis; white-space: nowrap; }
    .event-copy small { display: block; margin-top: 2px; color: #697285; font-size: 8px; line-height: 1; }
    .listen { flex: 0 0 auto; margin-right: 7px; padding: 5px 7px; color: #d7b8ff; background: rgba(194, 139, 255, 0.1); border: 1px solid rgba(194, 139, 255, 0.22); border-radius: 5px; cursor: pointer; font: 700 8px/1 inherit; }
    .listen:hover { color: #fff; background: rgba(194, 139, 255, 0.18); }
    .empty { margin: 0; padding: 18px 8px; color: #717a8d; font-size: 10px; line-height: 1.5; text-align: center; }

    @media (max-width: 560px) {
        header { padding: 14px 14px 12px; }
        .clock strong { font-size: 14px; }
        .filters { padding: 0 14px 11px; }
        .filters p { display: none; }
        .track-wrap { padding-inline: 14px; }
        .markers { inset-inline: 14px; }
        .tooltip { display: none !important; }
        .event-copy strong { max-width: 46vw; }
    }

    @media (prefers-reduced-motion: reduce) {
        .marker:hover,
        .marker:focus-visible { transform: translate(-50%, -50%); }
    }
</style>
