<script>
    import { createEventDispatcher } from 'svelte';

    /** Selected driver's current replay state. */
    export let driver = null;
    export let title = 'Driver detail';
    export let totalLaps = null;
    export let showClose = true;
    export let onClose = null;

    const dispatch = createEventDispatcher();
    const num = (value) => (value == null || value === '' ? null : Number(value));
    const valueOf = (...keys) => keys.map((key) => driver?.[key]).find((value) => value != null);
    const upper = (value) => String(value || '').toUpperCase();

    $: code = valueOf('code', 'driver_code') || '—';
    $: name = valueOf('name', 'driver_name') || code;
    $: team = valueOf('team', 'team_name') || 'Team unavailable';
    $: color = valueOf('team_color', 'color') || '#8b93a7';
    $: position = num(valueOf('position', 'running_order', 'order'));
    $: interval = num(valueOf('interval', 'gap_to_ahead_s', 'ahead'));
    $: gap = num(valueOf('gap', 'gap_to_leader_s'));
    $: compound = upper(valueOf('compound', 'tyre_compound'));
    $: tyreAge = num(valueOf('tyre_age', 'tyre_life', 'stint_lap'));
    $: lap = num(valueOf('lap', 'lap_number'));
    $: stops = num(valueOf('pit_stops', 'stops'));
    $: change = num(valueOf('position_change', 'positions_gained'));
    $: status = String(valueOf('status', 'race_status') || 'Racing');

    function formatGap(value, leaderLabel = false) {
        if (leaderLabel && position === 1) return 'LEADER';
        if (value == null || !Number.isFinite(value)) return '—';
        return value <= 0 && leaderLabel ? 'LEADER' : `+${Math.max(0, value).toFixed(3)}`;
    }

    function compoundName(value) {
        if (value === 'INTERMEDIATE') return 'Intermediate';
        if (!value || value === 'UNKNOWN') return 'Unknown tyre';
        return value.charAt(0) + value.slice(1).toLowerCase();
    }

    function close() {
        const detail = { driver };
        if (typeof onClose === 'function') onClose(detail);
        dispatch('close', detail);
    }
</script>

<aside class="detail" style={`--team-color: ${color}`} aria-label={driver ? `${name} race details` : title}>
    {#if driver}
        <div class="accent"></div>
        <header>
            <div class="identity">
                <span class="eyebrow">{title}</span>
                <div class="name-line">
                    <span class="position">P{position ?? '—'}</span>
                    <div>
                        <h2>{name}</h2>
                        <p>{code} · {team}</p>
                    </div>
                </div>
            </div>
            {#if showClose}
                <button class="close" type="button" aria-label={`Close ${name} details`} on:click={close}>×</button>
            {/if}
        </header>

        <div class="status-line" aria-live="polite">
            <span class="status-dot"></span>
            <span>{status}</span>
            {#if lap != null}<strong>Lap {lap}{totalLaps != null ? ` / ${totalLaps}` : ''}</strong>{/if}
        </div>

        <div class="metrics">
            <div class="metric primary">
                <span>Interval</span>
                <strong>{formatGap(interval, true)}</strong>
                <small>to car ahead</small>
            </div>
            <div class="metric">
                <span>Leader gap</span>
                <strong>{position === 1 ? '—' : formatGap(gap)}</strong>
                <small>race time</small>
            </div>
            <div class="metric">
                <span>Positions</span>
                <strong class:gain={change > 0} class:loss={change < 0}>
                    {change == null ? '—' : change === 0 ? '0' : `${change > 0 ? '+' : ''}${change}`}
                </strong>
                <small>from the grid</small>
            </div>
        </div>

        <div class="stint">
            <div class="tyre {compound.toLowerCase()}" aria-hidden="true">
                {compound === 'INTERMEDIATE' ? 'I' : compound ? compound[0] : '—'}
            </div>
            <div class="stint-copy">
                <span>Current stint</span>
                <strong>{compoundName(compound)}</strong>
                <small>{tyreAge == null ? 'Tyre age unavailable' : `${tyreAge} lap${tyreAge === 1 ? '' : 's'} on this set`}</small>
            </div>
            <div class="stops">
                <span>Stops</span>
                <strong>{stops ?? '—'}</strong>
            </div>
        </div>
    {:else}
        <div class="empty">
            <div class="empty-icon" aria-hidden="true">01</div>
            <h2>{title}</h2>
            <p>Select a driver from the timing tower or circuit map to inspect their live race state.</p>
        </div>
    {/if}
</aside>

<style>
    .detail {
        position: relative;
        min-height: 220px;
        overflow: hidden;
        color: #f5f7fb;
        background:
            radial-gradient(circle at 90% -10%, color-mix(in srgb, var(--team-color) 20%, transparent), transparent 42%),
            linear-gradient(150deg, #171a22, #0b0d12 74%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 14px;
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.3), inset 0 1px rgba(255, 255, 255, 0.04);
        font-variant-numeric: tabular-nums;
    }
    .accent { position: absolute; inset: 0 auto 0 0; width: 4px; background: var(--team-color); }
    header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        padding: 18px 20px 14px 22px;
    }
    .eyebrow,
    .metric span,
    .stint-copy span,
    .stops span {
        color: #858da0;
        font-size: 9px;
        font-weight: 750;
        letter-spacing: 0.13em;
        line-height: 1;
        text-transform: uppercase;
    }
    .name-line { display: flex; align-items: center; gap: 13px; margin-top: 10px; }
    .position {
        display: grid;
        place-items: center;
        min-width: 48px;
        height: 48px;
        padding-inline: 6px;
        color: #fff;
        background: color-mix(in srgb, var(--team-color) 24%, #141720);
        border: 1px solid color-mix(in srgb, var(--team-color) 65%, #fff 10%);
        border-radius: 10px;
        font-size: 18px;
        font-weight: 800;
    }
    h2 { margin: 0; color: #fff; font-size: 20px; font-weight: 720; letter-spacing: -0.025em; line-height: 1.1; }
    .name-line p { margin: 5px 0 0; color: #949cad; font-size: 11px; line-height: 1.2; }
    .close {
        display: grid;
        place-items: center;
        width: 30px;
        height: 30px;
        color: #a3aabc;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 50%;
        cursor: pointer;
        font: 300 19px/1 system-ui, sans-serif;
    }
    .close:hover { color: #fff; background: rgba(255, 255, 255, 0.09); }
    .close:focus-visible { outline: 2px solid #80aaff; outline-offset: 2px; }
    .status-line {
        display: flex;
        align-items: center;
        gap: 7px;
        min-height: 32px;
        padding: 0 20px 0 22px;
        color: #a9b0be;
        background: rgba(255, 255, 255, 0.025);
        border-block: 1px solid rgba(255, 255, 255, 0.07);
        font-size: 10px;
        font-weight: 650;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }
    .status-line strong { margin-left: auto; color: #e8ebf1; font-size: 10px; }
    .status-dot { width: 6px; height: 6px; background: #3ed581; border-radius: 50%; box-shadow: 0 0 0 3px rgba(62, 213, 129, 0.12); }
    .metrics { display: grid; grid-template-columns: repeat(3, 1fr); padding: 17px 20px 15px 22px; }
    .metric { min-width: 0; padding: 0 14px; border-left: 1px solid rgba(255, 255, 255, 0.08); }
    .metric:first-child { padding-left: 0; border-left: 0; }
    .metric:last-child { padding-right: 0; }
    .metric strong { display: block; margin-top: 7px; color: #f1f3f7; font-size: 17px; font-weight: 720; }
    .metric.primary strong { color: #fff; }
    .metric strong.gain { color: #3ed581; }
    .metric strong.loss { color: #ff6076; }
    .metric small { display: block; margin-top: 4px; color: #697184; font-size: 8px; line-height: 1.2; }
    .stint {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 0 20px 18px 22px;
        padding: 12px;
        background: rgba(255, 255, 255, 0.035);
        border: 1px solid rgba(255, 255, 255, 0.075);
        border-radius: 10px;
    }
    .tyre {
        display: grid;
        place-items: center;
        flex: 0 0 34px;
        height: 34px;
        color: #c9ced8;
        border: 4px solid #687084;
        border-radius: 50%;
        font-size: 11px;
        font-weight: 850;
    }
    .tyre.soft { color: #ff3652; border-color: #ff3652; }
    .tyre.medium { color: #ffd329; border-color: #ffd329; }
    .tyre.hard { color: #f3f4f7; border-color: #f3f4f7; }
    .tyre.intermediate { color: #42c66b; border-color: #42c66b; }
    .tyre.wet { color: #3495ff; border-color: #3495ff; }
    .stint-copy { min-width: 0; }
    .stint-copy strong { display: block; margin-top: 5px; color: #f2f4f8; font-size: 12px; }
    .stint-copy small { display: block; margin-top: 2px; color: #788195; font-size: 9px; }
    .stops { margin-left: auto; padding-left: 14px; border-left: 1px solid rgba(255, 255, 255, 0.08); text-align: center; }
    .stops strong { display: block; margin-top: 4px; color: #fff; font-size: 18px; }
    .empty { display: grid; place-items: center; min-height: 220px; padding: 28px; text-align: center; }
    .empty-icon {
        display: grid;
        place-items: center;
        width: 52px;
        height: 52px;
        color: #6e778a;
        border: 1px dashed #50586a;
        border-radius: 50%;
        font-size: 11px;
        font-weight: 750;
    }
    .empty h2 { margin-top: 13px; font-size: 15px; }
    .empty p { max-width: 310px; margin: 7px 0 0; color: #858da0; font-size: 11px; line-height: 1.55; }

    @media (max-width: 520px) {
        header { padding: 15px 16px 12px 18px; }
        .name-line { gap: 10px; }
        .position { min-width: 42px; height: 42px; font-size: 16px; }
        h2 { font-size: 17px; }
        .status-line { padding-inline: 18px 16px; }
        .metrics { padding: 15px 16px 13px 18px; }
        .metric { padding-inline: 8px; }
        .metric strong { font-size: 14px; }
        .stint { margin: 0 16px 15px 18px; }
    }
</style>
