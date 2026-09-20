<script>
    export let data = [];

    const formatDate = (value) => {
        if (value == null) return 'unknown';
        const parsed = new Date(value);
        return Number.isNaN(parsed.getTime())
            ? String(value)
            : parsed.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
    };

    $: row = data?.[0] || {};
    $: status = row.freshness_status || 'unknown';
    $: stale = status === 'stale';
    $: current = status === 'current';
    $: dataThrough = formatDate(row.latest_event_date);
    $: calendarThrough = formatDate(row.latest_completed_event_date);
    $: lag = Number(row.freshness_lag_days || 0);
</script>

<aside class="snapshot-status" class:stale class:unknown={!stale && !current} role={stale ? 'status' : undefined}>
    <span class="indicator" aria-hidden="true"></span>
    <div>
        <strong>{stale ? 'Snapshot needs a data refresh' : current ? 'Snapshot is current' : 'Data freshness unverified'}</strong>
        <span>Data through {dataThrough}</span>
    </div>
    {#if stale}
        <p>
            The calendar has a completed event on {calendarThrough}. This snapshot is
            {lag} {lag === 1 ? 'day' : 'days'} behind; newer races are intentionally not shown as current.
        </p>
    {/if}
</aside>

<style>
    .snapshot-status {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin: -0.6rem 0 1.6rem;
        padding: 0.8rem 1rem;
        border: 1px solid rgba(70, 211, 154, 0.24);
        border-radius: 0.75rem;
        background: rgba(70, 211, 154, 0.07);
        color: #dce7e2;
    }
    .snapshot-status.stale {
        border-color: rgba(247, 201, 72, 0.34);
        background: rgba(247, 201, 72, 0.08);
        color: #f4e8b4;
    }
    .snapshot-status.unknown { border-color: var(--dashboard-border); background: rgba(148, 163, 184, 0.05); color: #c5cedb; }
    .unknown .indicator { background: #9ba7ba; box-shadow: none; }
    .indicator {
        width: 0.58rem;
        height: 0.58rem;
        flex: none;
        border-radius: 50%;
        background: #46d39a;
        box-shadow: 0 0 0 4px rgba(70, 211, 154, 0.12);
    }
    .stale .indicator {
        background: #f7c948;
        box-shadow: 0 0 0 4px rgba(247, 201, 72, 0.12);
    }
    div { display: flex; flex-direction: column; min-width: 0; }
    strong { font-size: 0.86rem; }
    span, p { font-size: 0.78rem; }
    div span { color: #aab7b1; }
    .stale div span { color: #c9bd8e; }
    p { margin: 0 0 0 auto; color: #d5cda9; line-height: 1.45; }
    @media (max-width: 700px) {
        .snapshot-status { align-items: flex-start; flex-wrap: wrap; }
        p { width: 100%; margin-left: 1.35rem; }
    }
</style>
