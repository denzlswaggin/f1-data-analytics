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
    const number = (value) => value == null ? '—' : Number(value).toLocaleString('en-US');
</script>

<details class="data-trust">
    <summary>
        <span class="status" aria-hidden="true"></span>
        <strong>Data confidence</strong>
        <span>{seasons} · {number(row.sample_rows)} {sampleLabel}</span>
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
        margin: 0.8rem 0 1.2rem;
        border: 1px solid var(--color-base-300, #d7dce1);
        border-radius: 0.55rem;
        background: var(--color-base-100, #f7f8fa);
        color: var(--color-base-content, #374151);
        font-size: 0.82rem;
    }
    summary {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.65rem 0.8rem;
        cursor: pointer;
        list-style: none;
    }
    summary::-webkit-details-marker { display: none; }
    summary::after { content: 'Details'; margin-left: auto; color: var(--color-primary, #2563eb); font-size: 0.75rem; font-weight: 650; }
    summary:focus-visible { outline: 2px solid var(--color-primary, #2563eb); outline-offset: 2px; }
    summary > span:not(.status) { opacity: 0.68; }
    .status { width: 0.55rem; height: 0.55rem; border-radius: 50%; background: var(--color-positive, #16a34a); box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-positive, #16a34a) 15%, transparent); }
    .details {
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem 1rem;
        padding: 0 0.8rem 0.75rem 1.85rem;
    }
    @media (max-width: 520px) {
        summary { flex-wrap: wrap; }
        summary::after { margin-left: 0; }
        .details { flex-direction: column; padding-left: 0.8rem; }
    }
</style>
