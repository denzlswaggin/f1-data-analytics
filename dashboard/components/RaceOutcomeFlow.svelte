<script>
    export let data = [];
    const position = (value) => value == null ? '—' : `P${Number(value)}`;
    const delta = (from, to) => {
        if (from == null || to == null) return '—';
        const value = Number(from) - Number(to);
        return value > 0 ? `+${value}` : String(value);
    };
</script>

<div class="outcome-flow" role="table" aria-label="Grid, controlled pace and finish flow">
    <div class="head" role="row">
        <span>Driver</span><span>Grid</span><span>Controlled pace</span><span>Finish</span>
    </div>
    {#each data as row}
        <div class="driver-row" role="row">
            <strong>{row.driver_name}</strong>
            <span class="node muted">{position(row.grid_position)}</span>
            <span class="connector" aria-hidden="true">→</span>
            <span class="node pace">{position(row.pace_rank)}</span>
            <span class="connector" aria-hidden="true">→</span>
            <span class:gain={Number(row.outcome_vs_pace) > 0} class:loss={Number(row.outcome_vs_pace) < 0} class="node finish">
                {position(row.finish_position)} <small>{delta(row.pace_rank, row.finish_position)}</small>
            </span>
        </div>
    {/each}
</div>

<style>
    .outcome-flow { display: grid; gap: .45rem; margin: 1rem 0 2rem; }
    .head { display: grid; grid-template-columns: minmax(9rem, 1.5fr) repeat(3, 1fr); gap: .5rem; padding: 0 .7rem; color: #8f9bad; font-size: .72rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }
    .driver-row { display: grid; grid-template-columns: minmax(9rem, 1.5fr) 1fr auto 1fr auto 1fr; align-items: center; gap: .45rem; padding: .55rem .7rem; border: 1px solid rgba(160,174,201,.14); border-radius: .65rem; background: rgba(255,255,255,.018); }
    .driver-row strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .node { display: inline-flex; align-items: center; justify-content: center; min-height: 2rem; border-radius: .45rem; background: rgba(255,255,255,.05); font-variant-numeric: tabular-nums; font-weight: 750; }
    .node small { margin-left: .35rem; opacity: .76; }
    .pace { border: 1px solid rgba(86,166,255,.35); color: #9dcbff; }
    .finish.gain { border: 1px solid rgba(70,211,154,.4); color: #70dfb0; }
    .finish.loss { border: 1px solid rgba(255,100,112,.35); color: #ff8993; }
    .muted, .connector { color: #8793a4; }
    @media (max-width: 650px) {
        .head { display: none; }
        .driver-row { grid-template-columns: 1fr auto auto auto auto auto; font-size: .82rem; }
        .node { min-width: 2.7rem; }
    }
</style>
