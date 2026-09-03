<script>
    import { createEventDispatcher } from 'svelte';

    /**
     * Live running order. Rows may use either replay-source field names
     * (driver_code, running_order, gap_to_ahead_s) or their shorter UI aliases.
     */
    export let leaderboard = [];
    export let selectedCode = null;
    export let title = 'Live timing';
    export let maxRows = null;
    export let onSelect = null;
    export let statusLabel = 'Replay';
    export let active = false;

    const dispatch = createEventDispatcher();
    const num = (value) => (value == null || value === '' ? null : Number(value));
    const valueOf = (row, ...keys) => keys.map((key) => row?.[key]).find((value) => value != null);
    const codeOf = (row) => valueOf(row, 'code', 'driver_code') || '—';
    const positionOf = (row) => num(valueOf(row, 'position', 'running_order', 'order'));
    const teamColor = (row) => valueOf(row, 'team_color', 'color') || '#8b93a7';
    const compoundOf = (row) => String(valueOf(row, 'compound', 'tyre_compound') || '').toUpperCase();
    const statusOf = (row) => String(valueOf(row, 'status', 'race_status') || 'racing').toLowerCase();

    $: rows = [...(leaderboard || [])]
        .sort((a, b) => (positionOf(a) ?? 999) - (positionOf(b) ?? 999))
        .slice(0, maxRows == null ? undefined : Math.max(0, Number(maxRows)));

    function formatInterval(row) {
        const position = positionOf(row);
        const interval = num(valueOf(row, 'interval', 'gap_to_ahead_s', 'ahead'));
        if (position === 1) return 'LEADER';
        if (interval == null || !Number.isFinite(interval)) return '—';
        return `+${Math.max(0, interval).toFixed(3)}`;
    }

    function formatLeaderGap(row) {
        const position = positionOf(row);
        const gap = num(valueOf(row, 'gap', 'gap_to_leader_s'));
        if (position === 1) return 'race gap';
        if (gap == null || !Number.isFinite(gap)) return 'gap —';
        return `gap +${Math.max(0, gap).toFixed(1)}`;
    }

    function formatChange(row) {
        const change = num(valueOf(row, 'position_change', 'positions_gained'));
        if (change == null || !Number.isFinite(change) || change === 0) return { text: '—', className: 'neutral' };
        return { text: `${change > 0 ? '▲' : '▼'} ${Math.abs(change)}`, className: change > 0 ? 'up' : 'down' };
    }

    function compoundLetter(row) {
        const compound = compoundOf(row);
        if (compound === 'INTERMEDIATE') return 'I';
        if (compound === 'UNKNOWN' || !compound) return '—';
        return compound[0];
    }

    function selectDriver(row) {
        const code = codeOf(row);
        const detail = { code, driver: row };
        if (typeof onSelect === 'function') onSelect(detail);
        dispatch('select', detail);
    }

    function accessibleLabel(row) {
        const position = positionOf(row);
        const name = valueOf(row, 'name', 'driver_name') || codeOf(row);
        const team = valueOf(row, 'team', 'team_name');
        const lap = num(valueOf(row, 'lap', 'lap_number'));
        const tyreAge = num(valueOf(row, 'tyre_age', 'tyre_life', 'stint_lap'));
        return `${position == null ? 'Unclassified' : `Position ${position}`}, ${name}${team ? `, ${team}` : ''}, ${formatInterval(row)}${lap == null ? '' : `, lap ${lap}`}${tyreAge == null ? '' : `, tyre age ${tyreAge} laps`}`;
    }
</script>

<section class="tower" aria-label={title}>
    <header class="tower-header">
        <div>
            <span class="eyebrow">Race replay</span>
            <h2>{title}</h2>
        </div>
        <span class:active class="live"><i></i> {statusLabel}</span>
    </header>

    <div class="column-head" aria-hidden="true">
        <span>Pos</span><span>Driver</span><span>Tyre</span><span>Int. / gap</span><span>+/−</span>
    </div>

    {#if rows.length}
        <ol class="rows">
            {#each rows as row (codeOf(row))}
                {@const code = codeOf(row)}
                {@const change = formatChange(row)}
                {@const status = statusOf(row)}
                <li class:selected={selectedCode === code}>
                    <button
                        type="button"
                        class="driver-row"
                        style={`--team-color: ${teamColor(row)}`}
                        aria-label={accessibleLabel(row)}
                        aria-pressed={selectedCode === code}
                        on:click={() => selectDriver(row)}
                    >
                        <span class="position">{positionOf(row) ?? '—'}</span>
                        <span class="driver">
                            <strong>{code}</strong>
                            <small>
                                {valueOf(row, 'name', 'driver_name') || code}
                                {#if valueOf(row, 'team', 'team_name')} · {valueOf(row, 'team', 'team_name')}{/if}
                            </small>
                        </span>
                        <span class="tyre-cell" title={compoundOf(row) || 'Tyre unknown'}>
                            <span class="compound {compoundOf(row).toLowerCase()}">{compoundLetter(row)}</span>
                            {#if num(valueOf(row, 'tyre_age', 'tyre_life', 'stint_lap')) != null}
                                <small>{num(valueOf(row, 'tyre_age', 'tyre_life', 'stint_lap'))}L</small>
                            {/if}
                        </span>
                        <span class="gap-cell">
                            <strong>{formatInterval(row)}</strong>
                            <small>{formatLeaderGap(row)}</small>
                        </span>
                        <span class="change {change.className}">{change.text}</span>
                        {#if status !== 'racing' && status !== 'active' || num(valueOf(row, 'lap', 'lap_number')) != null}
                            <span class="status {status}">
                                {status !== 'racing' && status !== 'active' ? status : ''}
                                {#if num(valueOf(row, 'lap', 'lap_number')) != null}
                                    {status !== 'racing' && status !== 'active' ? ' · ' : ''}L{num(valueOf(row, 'lap', 'lap_number'))}
                                {/if}
                            </span>
                        {/if}
                    </button>
                </li>
            {/each}
        </ol>
    {:else}
        <div class="empty">Timing data is not available at this point in the race.</div>
    {/if}
</section>

<style>
    .tower {
        overflow: hidden;
        color: #f5f7fb;
        background: linear-gradient(165deg, #171a22 0%, #0d0f14 62%, #090b0f 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 14px;
        box-shadow: 0 18px 48px rgba(0, 0, 0, 0.3), inset 0 1px rgba(255, 255, 255, 0.04);
        font-variant-numeric: tabular-nums;
    }
    .tower-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 16px 18px 14px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.09);
    }
    .eyebrow {
        display: block;
        color: #939bad;
        font-size: 9px;
        font-weight: 750;
        letter-spacing: 0.16em;
        line-height: 1;
        text-transform: uppercase;
    }
    h2 {
        margin: 5px 0 0;
        color: inherit;
        font-size: 15px;
        font-weight: 680;
        letter-spacing: -0.01em;
        line-height: 1.1;
    }
    .live {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #dfe3eb;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.09em;
        text-transform: uppercase;
    }
    .live i {
        width: 7px;
        height: 7px;
        background: #7f8798;
        border-radius: 50%;
    }
    .live.active i { background: #ef304b; box-shadow: 0 0 0 4px rgba(239, 48, 75, 0.13); }
    .column-head,
    .driver-row {
        display: grid;
        grid-template-columns: 34px minmax(92px, 1fr) 32px 72px 34px;
        align-items: center;
        column-gap: 8px;
    }
    .column-head {
        padding: 8px 14px 6px;
        color: #747d91;
        font-size: 8px;
        font-weight: 750;
        letter-spacing: 0.1em;
        text-align: right;
        text-transform: uppercase;
    }
    .column-head span:nth-child(2) { text-align: left; }
    .rows {
        max-height: min(64vh, 760px);
        margin: 0;
        padding: 0 7px 8px;
        overflow-y: auto;
        list-style: none;
        scrollbar-color: #343a47 transparent;
    }
    .rows li { position: relative; margin: 1px 0; }
    .driver-row {
        position: relative;
        width: 100%;
        min-height: 45px;
        padding: 4px 7px;
        overflow: hidden;
        color: #e7eaf0;
        background: transparent;
        border: 0;
        border-radius: 7px;
        cursor: pointer;
        font: inherit;
        text-align: right;
        transition: background 120ms ease, transform 120ms ease;
    }
    .driver-row::before {
        position: absolute;
        inset: 7px auto 7px 0;
        width: 3px;
        background: var(--team-color);
        border-radius: 2px;
        content: '';
    }
    .driver-row:hover { background: rgba(255, 255, 255, 0.055); }
    .driver-row:active { transform: translateY(1px); }
    .driver-row:focus-visible { outline: 2px solid #80aaff; outline-offset: -2px; }
    li.selected .driver-row {
        background: linear-gradient(90deg, color-mix(in srgb, var(--team-color) 18%, transparent), rgba(255, 255, 255, 0.055));
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.09);
    }
    .position { color: #f8f9fc; font-size: 15px; font-weight: 750; text-align: center; }
    .driver { min-width: 0; padding-left: 3px; text-align: left; }
    .driver strong {
        display: block;
        color: #fff;
        font-size: 13px;
        font-weight: 790;
        letter-spacing: 0.07em;
        line-height: 1.1;
    }
    .driver small {
        display: block;
        margin-top: 3px;
        overflow: hidden;
        color: #858da0;
        font-size: 9px;
        line-height: 1;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .compound {
        display: inline-grid;
        place-items: center;
        width: 20px;
        height: 20px;
        color: #c9ced8;
        border: 2px solid #687084;
        border-radius: 50%;
        font-size: 9px;
        font-weight: 800;
    }
    .tyre-cell { display: grid; place-items: center; gap: 2px; }
    .tyre-cell small { color: #747d91; font-size: 7px; font-weight: 700; line-height: 1; }
    .compound.soft { color: #ff3652; border-color: #ff3652; }
    .compound.medium { color: #ffd329; border-color: #ffd329; }
    .compound.hard { color: #f3f4f7; border-color: #f3f4f7; }
    .compound.intermediate { color: #42c66b; border-color: #42c66b; }
    .compound.wet { color: #3495ff; border-color: #3495ff; }
    .gap-cell { min-width: 0; text-align: right; }
    .gap-cell strong { display: block; color: #c9ced8; font-size: 11px; font-weight: 650; }
    .gap-cell small { display: block; margin-top: 2px; color: #626b7e; font-size: 7px; line-height: 1; }
    .change { font-size: 10px; font-weight: 760; }
    .change.up { color: #38d980; }
    .change.down { color: #ff6076; }
    .change.neutral { color: #5f687a; }
    .status {
        position: absolute;
        right: 10px;
        bottom: 2px;
        color: #f4c853;
        font-size: 7px;
        font-weight: 800;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }
    .status.retired,
    .status.dnf,
    .status.out { color: #ff6076; }
    .status.finished { color: #67d99b; }
    .empty { padding: 28px 20px; color: #858da0; font-size: 12px; line-height: 1.5; text-align: center; }

    @media (max-width: 520px) {
        .tower-header { padding: 13px 14px 12px; }
        .column-head,
        .driver-row { grid-template-columns: 30px minmax(75px, 1fr) 28px 64px 30px; column-gap: 5px; }
        .column-head { padding-inline: 11px; }
        .rows { max-height: none; padding-inline: 4px; }
        .driver-row { min-height: 42px; padding-inline: 5px; }
        .driver small { display: none; }
    }

    @media (prefers-reduced-motion: reduce) {
        .driver-row { transition: none; }
    }
</style>
