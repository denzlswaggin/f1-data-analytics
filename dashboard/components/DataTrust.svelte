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
    $: status = !hasData ? 'No published data for this selection'
        : usable != null && !hasUsable ? 'No usable evidence for this selection' : 'Evidence behind this view';
    const number = (value) => value == null ? '—' : Number(value).toLocaleString('en-US');
</script>

<details class="data-trust">
    <summary>
        <span class="status" class:empty={!hasData} aria-hidden="true"></span>
        <span class="summary-copy">
            <strong>{status}</strong>
            {#if hasData}
                <span>Coverage: {seasons}</span>
                <span>Inputs: {number(row.sample_rows)} {inputUnit}</span>
                {#if usable != null}<span>Usable: {number(usable)} {usableUnit}</span>{/if}
            {:else}
                <span>Try another selection or open details</span>
            {/if}
        </span>
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
        background: rgba(148, 163, 184, 0.035);
        color: #dbe5ee;
        font-size: 0.88rem;
        font-variant-numeric: tabular-nums;
    }
    summary {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        align-items: center;
        gap: 0.5rem;
        padding: 0.8rem 0.9rem;
        cursor: pointer;
        list-style: none;
    }
    summary::-webkit-details-marker { display: none; }
    summary::after { content: ''; margin-left: auto; flex: none; width: 0.45rem; height: 0.45rem; border-right: 2px solid #9ba7ba; border-bottom: 2px solid #9ba7ba; transform: rotate(45deg); }
    details[open] summary::after { transform: rotate(225deg); }
    summary:hover { background: rgba(160, 174, 201, 0.06); }
    summary:focus-visible { outline: 2px solid var(--ui-focus, #9bc3ff); outline-offset: 2px; }
    .summary-copy { display: flex; flex-wrap: wrap; column-gap: .7rem; row-gap: .15rem; }
    .summary-copy strong { flex-basis: 100%; color: #f0f4f8; }
    .summary-copy > span { color: #b9c5d5; }
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
        .details { flex-direction: column; padding-left: 0.8rem; }
    }
</style>
