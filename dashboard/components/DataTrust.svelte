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

<div class="data-trust" aria-label="Data coverage and method">
    <span><strong>Coverage</strong> {seasons}</span>
    <span><strong>Sample</strong> {number(row.sample_rows)} {sampleLabel}</span>
    <span><strong>{entityLabel}</strong> {number(row.entity_count)}</span>
    <span><strong>Races</strong> {number(row.race_count)}</span>
    <span><strong>Latest event</strong> {latest}</span>
    <span><strong>Method</strong> {method}</span>
</div>

<style>
    .data-trust {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem 1rem;
        margin: 0.8rem 0 1.2rem;
        padding: 0.65rem 0.8rem;
        border: 1px solid var(--color-base-300, #d7dce1);
        border-radius: 0.4rem;
        background: var(--color-base-100, #f7f8fa);
        color: var(--color-base-content, #374151);
        font-size: 0.82rem;
    }
</style>
