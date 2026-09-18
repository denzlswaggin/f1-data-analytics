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
    $: usable = row.usable_samples;
    $: hasUsable = usable != null && Number(usable) > 0;
    $: inputUnit = row.sample_unit || sampleLabel;
    $: usableUnit = row.usable_unit || 'usable observations';
    $: comparable = row.sample_unit && row.sample_unit === row.usable_unit;
    $: status = !hasData ? 'No published data'
        : usable != null && !hasUsable ? 'Insufficient usable evidence' : 'Data coverage';
    const number = (value) => value == null ? '—' : Number(value).toLocaleString('en-US');
</script>

<details class="data-trust">
    <summary>
        <span class="status" class:empty={!hasData} aria-hidden="true"></span>
        <strong>{status}</strong>
        <span>{hasData ? `${seasons} · ${number(row.sample_rows)} ${inputUnit}` : 'Try another selection'}</span>
        {#if usable != null}<span>→ {number(usable)} {usableUnit}</span>{/if}
    </summary>
    <div class="details" aria-label="Data coverage and method">
        <span><strong>Coverage</strong> {seasons}</span>
        <span><strong>Sample</strong> {number(row.sample_rows)} {inputUnit}</span>
        {#if usable != null}
        <span><strong>Usable</strong> {number(usable)} {usableUnit}{#if comparable && hasData} ({(100 * Number(usable) / Number(row.sample_rows)).toFixed(1)}%){/if}</span>
        {/if}
        {#if row.coverage_reason}<span><strong>Limitation</strong> {row.coverage_reason}</span>{/if}
        <span><strong>{entityLabel}</strong> {number(row.entity_count)}</span>
        <span><strong>Races</strong> {number(row.race_count)}</span>
        <span><strong>Latest event</strong> {latest}</span>
        <span><strong>Method</strong> {method}</span>
    </div>
</details>

<style>
    .data-trust {
        margin: 0.9rem 0 1.35rem;
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 0.75rem;
        background: linear-gradient(115deg, rgba(148, 163, 184, 0.075), rgba(255,255,255,.018));
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
    summary::after { content: 'View coverage'; margin-left: auto; color: #aab6c6; font-size: 0.8rem; font-weight: 700; }
    summary:focus-visible { outline: 2px solid var(--color-primary, #2563eb); outline-offset: 2px; }
    summary > span:not(.status) { color: #9facbc; }
    .status { width: 0.58rem; height: 0.58rem; border-radius: 50%; background: #94a3b8; }
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
