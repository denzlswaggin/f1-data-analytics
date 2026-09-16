<script>
    export let data = [];
    const num = (value) => value == null ? null : Number(value);
    $: rows = (data || []).map((row) => ({ ...row, score: num(row.score), dominant_delta: num(row.dominant_delta) }));
</script>

<section class="race-insights" data-testid="driver-dna-race-insights">
    {#if rows.length}
        <div class="grid">
            {#each rows as row}
                <article>
                    <span class="label">{row.insight_label}</span>
                    <strong>{row.race_label}</strong>
                    <p>vs {row.teammate_name}</p>
                    <div class="axis">{row.dominant_metric} <b>{row.dominant_delta >= 0 ? '+' : ''}{row.dominant_delta?.toFixed(2) ?? '—'} z</b></div>
                    <small>{row.score_label}: {row.score?.toFixed(2) ?? '—'} z RMS</small>
                </article>
            {/each}
        </div>
    {:else}
        <div class="empty">At least five eligible races are required for representative and unusual-race insights.</div>
    {/if}
</section>

<style>
    .race-insights { margin: 1rem 0 1.5rem; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; }
    article { padding: 1rem; border: 1px solid rgba(160,174,201,.18); border-radius: .8rem; background: rgba(255,255,255,.025); }
    .label { display: block; margin-bottom: .35rem; color: #32d3f4; font-size: .67rem; font-weight: 750; letter-spacing: .07em; text-transform: uppercase; }
    strong { display: block; color: #f4f7fb; font-size: 1rem; }
    p { margin: .2rem 0 .75rem; color: #8f9bae; font-size: .76rem; }
    .axis { color: #dce3ed; font-size: .78rem; }
    .axis b { color: #f8fafc; font-variant-numeric: tabular-nums; }
    small { display: block; margin-top: .25rem; color: #8f9bae; font-size: .68rem; }
    .empty { padding: 1.5rem; border: 1px dashed rgba(160,174,201,.24); border-radius: .7rem; color: #9ba7ba; text-align: center; }
    @media (max-width: 680px) { .grid { grid-template-columns: 1fr; } }
</style>
