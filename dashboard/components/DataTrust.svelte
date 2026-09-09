<script>
    export let data = [];
    export let sampleLabel = 'samples';
    export let entityLabel = 'entities';
    export let method = 'descriptive';

    $: row = data?.[0] || {};
    $: seasons = row.first_season == null
        ? 'no data'
        : row.first_season === row.last_season
            ? String(row.first_season)
            : `${row.first_season}–${row.last_season}`;
    $: latest = row.latest_event_date == null ? '—' : String(row.latest_event_date);
    $: hasData = Number(row.sample_rows || 0) > 0;
    const number = (value) => value == null ? '—' : Number(value).toLocaleString('en-US');
</script>

<details class="data-trust">
    <summary>
        <span class="status" class:empty={!hasData} aria-hidden="true"></span>
        <strong>{hasData ? 'Data confidence' : 'No published data'}</strong>
        <span>{hasData ? `${seasons} · ${number(row.sample_rows)} ${sampleLabel}` : 'Try another selection'}</span>
    </summary>
    <div class="details" aria-label="Data coverage and method">
        <span><strong>Coverage</strong> {seasons}</span>
        <span><strong>Sample</strong> {number(row.sample_rows)} {sampleLabel}</span>
        <span><strong>{entityLabel}</strong> {number(row.entity_count)}</span>
        <span><strong>Races</strong> {number(row.race_count)}</span>
        <span><strong>Latest event</strong> {latest}</span>
        <span><strong>Method</strong> {method}</span>
    </div>
</details>

<style>
    .data-trust {
        margin: 0.9rem 0 1.35rem;
        border: 1px solid rgba(70, 211, 154, 0.22);
        border-radius: 0.75rem;
        background: linear-gradient(115deg, rgba(70, 211, 154, 0.075), rgba(255,255,255,.018));
        color: #dbe5ee;
        font-size: 0.88rem;
    }
    summary {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.8rem 0.9rem;
        cursor: pointer;
        list-style: none;
    }
    summary::-webkit-details-marker { display: none; }
    summary::after { content: 'View coverage'; margin-left: auto; color: #70dfb0; font-size: 0.8rem; font-weight: 700; }
    summary:focus-visible { outline: 2px solid var(--color-primary, #2563eb); outline-offset: 2px; }
    summary > span:not(.status) { color: #9facbc; }
    .status { width: 0.58rem; height: 0.58rem; border-radius: 50%; background: var(--color-positive, #46d39a); box-shadow: 0 0 0 3px rgba(70,211,154,.14); }
    .status.empty { background: currentColor; box-shadow: none; opacity: 0.35; }
    .details {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem 1rem;
        padding: 0 0.9rem 0.9rem 2rem;
        color: #aab6c6;
    }
    @media (max-width: 520px) {
        summary { flex-wrap: wrap; }
        summary::after { margin-left: 0; }
        .details { flex-direction: column; padding-left: 0.8rem; }
    }
</style>
