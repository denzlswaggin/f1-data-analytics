<script>
    export let data = [];

    const num = (value) => value == null ? null : Number(value);
    $: rows = (data || []).map((row) => ({
        ...row,
        estimate: num(row.estimate),
        lo: num(row.lo),
        hi: num(row.hi),
        sign_agreement_pct: num(row.sign_agreement_pct),
        leave_one_out_max_delta: num(row.leave_one_out_max_delta)
    })).filter((row) => row.estimate != null);
    $: stable = rows.filter((row) => row.status === 'Stable signature').slice(0, 3);
    $: driver = rows[0]?.driver_name ?? 'Selected driver';
    const statusClass = (status) => status?.toLowerCase().replaceAll(' ', '-');
</script>

<section class="insights" data-testid="driver-dna-insights">
    <div class="heading">
        <div>
            <span class="eyebrow">Interpretation</span>
            <h3>What defines {driver} in this sample?</h3>
        </div>
        <span class="scale">teammate-normalised robust-z</span>
    </div>

    {#if rows.length}
        {#if stable.length}
            <div class="headline-grid">
                {#each stable as row}
                    <article class="headline">
                        <span>{row.metric_label}</span>
                        <strong>{row.direction_text}</strong>
                        <small>{row.estimate >= 0 ? '+' : ''}{row.estimate.toFixed(2)} z · direction repeats in {row.sign_agreement_pct?.toFixed(0) ?? '—'}% of races</small>
                    </article>
                {/each}
            </div>
        {:else}
            <div class="no-headline">No directional trait clears both the uncertainty and repeatability gates in this selection.</div>
        {/if}

        <div class="trait-grid">
            {#each rows as row}
                <article class="trait">
                    <div class="trait-top">
                        <strong>{row.metric_label}</strong>
                        <span class="badge {statusClass(row.status)}">{row.status}</span>
                    </div>
                    <div class="estimate">{row.estimate >= 0 ? '+' : ''}{row.estimate.toFixed(2)} <small>z</small></div>
                    <div class="interval">90% interval {row.lo?.toFixed(2) ?? '—'} to {row.hi?.toFixed(2) ?? '—'}</div>
                    <div class="diagnostics">
                        <span>{row.n_races} races</span>
                        <span>{row.sign_agreement_pct?.toFixed(0) ?? '—'}% direction agreement</span>
                        <span>{row.leave_one_out_max_delta?.toFixed(2) ?? '—'} max leave-one-out shift</span>
                    </div>
                </article>
            {/each}
        </div>
    {:else}
        <div class="empty">No publishable stability profile for Driver A in this season window.</div>
    {/if}
</section>

<style>
    .insights { margin: 1rem 0 1.5rem; padding: 1rem; border: 1px solid rgba(160,174,201,.18); border-radius: .95rem; background: rgba(255,255,255,.025); }
    .heading, .trait-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
    .eyebrow { color: #32d3f4; font-size: .68rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
    h3 { margin: .15rem 0 0; color: #f4f7fb; font-size: 1.05rem; }
    .scale, .interval, .diagnostics, small { color: #8f9bae; font-size: .72rem; }
    .headline-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin-top: 1rem; }
    .headline { padding: .85rem; border-left: 3px solid #32d3f4; border-radius: .65rem; background: rgba(50,211,244,.07); }
    .headline span, .headline strong, .headline small { display: block; }
    .headline span { color: #93a2b8; font-size: .72rem; }
    .headline strong { margin: .22rem 0; color: #eef7fb; font-size: .9rem; }
    .trait-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .65rem; margin-top: 1rem; }
    .trait { min-width: 0; padding: .75rem; border: 1px solid rgba(160,174,201,.14); border-radius: .65rem; background: rgba(4,8,15,.22); }
    .trait-top strong { color: #dce3ed; font-size: .78rem; }
    .badge { flex: 0 0 auto; padding: .16rem .34rem; border-radius: 999px; background: rgba(148,163,184,.14); color: #aeb8c7; font-size: .58rem; font-weight: 750; text-transform: uppercase; }
    .badge.stable-signature { background: rgba(50,211,244,.13); color: #75e5f8; }
    .badge.context-dependent { background: rgba(248,201,0,.13); color: #f8d957; }
    .estimate { margin-top: .65rem; color: #f8fafc; font-size: 1.35rem; font-weight: 750; font-variant-numeric: tabular-nums; }
    .estimate small { font-size: .7rem; }
    .interval { margin-top: .05rem; }
    .diagnostics { display: grid; gap: .18rem; margin-top: .55rem; }
    .no-headline, .empty { margin-top: 1rem; padding: 1rem; border: 1px dashed rgba(160,174,201,.24); border-radius: .65rem; color: #9ba7ba; text-align: center; }
    @media (max-width: 960px) { .trait-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 680px) {
        .heading { flex-direction: column; }
        .headline-grid, .trait-grid { grid-template-columns: 1fr; }
    }
</style>
