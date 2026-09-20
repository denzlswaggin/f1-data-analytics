<script>
    export let data = [];
    export let title = 'Race-by-race evidence';
    const num = (value) => value == null ? null : Number(value);
    $: rows = (data || []).map((row) => ({ ...row, value: num(row.value) })).filter((row) => row.value != null);
    $: races = [...new Set(rows.map((row) => row.race_label))];
    $: drivers = [...new Set(rows.map((row) => row.driver_name))];
    $: extent = Math.max(1, ...rows.map((row) => Math.abs(row.value)));
    const lookup = (driver, race) => rows.find((row) => row.driver_name === driver && row.race_label === race);
    let selected = null;
    $: selectedCell = selected ? rows.find(row => row.driver_name === selected.driver && row.race_label === selected.race) : null;
    const label = (cell) => `${cell.driver_name}, ${cell.race_label}: ${cell.metric_label} ${cell.value.toFixed(2)} vs ${cell.teammate_name}`;
    $: color = (value) => {
        const strength = Math.min(1, Math.abs(value) / extent);
        return value >= 0
            ? `rgba(50, 211, 244, ${0.15 + strength * 0.75})`
            : `rgba(255, 64, 80, ${0.15 + strength * 0.75})`;
    };
</script>

<div class="heatmap" data-testid="driver-dna-heatmap">
    <div class="title">{title}</div>
    {#if rows.length}
        <div class="scroll">
            <div class="grid" style="--columns:{races.length}">
                <div></div>
                {#each races as race}<div class="race">{race}</div>{/each}
                {#each drivers as driver}
                    <div class="driver">{driver}</div>
                    {#each races as race}
                        {@const cell = lookup(driver, race)}
                        {#if cell}
                            <button type="button" class="cell" style={`background:${color(cell.value)}`} aria-label={label(cell)} aria-pressed={selectedCell === cell} on:click={() => selected = selectedCell === cell ? null : { driver, race }}>
                                <span>{cell.value.toFixed(2)}</span>
                            </button>
                        {:else}
                            <span class="cell missing" aria-label={`${driver}, ${race}: no eligible evidence`}>—</span>
                        {/if}
                    {/each}
                {/each}
            </div>
        </div>
        <p class="selection" aria-live="polite">{selectedCell ? label(selectedCell) : 'Select a cell for race and teammate detail. Scroll horizontally for more races.'}</p>
        <div class="key"><span class="loss"></span>less than teammate <i>0</i> more than teammate<span class="gain"></span></div>
    {:else}
        <div class="empty">No eligible race evidence for these filters.</div>
    {/if}
</div>

<style>
    .heatmap { margin: 1rem 0 1.5rem; padding: 1rem; border: 1px solid rgba(160,174,201,.18); border-radius: .95rem; background: rgba(255,255,255,.025); }
    .title { margin-bottom: .7rem; color: #f4f7fb; font-weight: 700; }
    .scroll { overflow-x: auto; padding-bottom: .35rem; }
    .grid { display: grid; grid-template-columns: minmax(110px, 150px) repeat(var(--columns), minmax(58px, 1fr)); gap: 4px; min-width: max-content; }
    .race { width: 58px; min-height: 44px; display: grid; place-items: center; text-align: center; color: #aab6c6; font-size: 12px; line-height: 1.4; white-space: normal; }
    .driver { position: sticky; left: 0; z-index: 2; background: #11151d; padding-right: .5rem; display: flex; align-items: center; color: #dce3ed; font-size: 12px; font-weight: 650; }
    .cell { position: relative; display: grid; width: 58px; min-height: 44px; place-items: center; border: 0; border-radius: 5px; color: #f8fafc; font: inherit; font-size: 12px; font-variant-numeric: tabular-nums; }
    button.cell { cursor: pointer; }
    button.cell:hover, button.cell[aria-pressed="true"] { box-shadow: inset 0 0 0 2px #e8edf5; }
    button.cell:focus-visible { outline: 2px solid var(--ui-focus, #9bc3ff); outline-offset: -2px; }
    .cell.missing { background: rgba(255,255,255,.025); }
    .selection { min-height: 2.8em; margin: .75rem 0 0; color: #c5cedb; font-size: .85rem; line-height: 1.4; }
    .key { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: .4rem; margin-top: .65rem; color: #aab6c6; font-size: 12px; }
    .key span { width: 24px; height: 6px; border-radius: 4px; }
    .loss { background: #ff4050; } .gain { background: #32d3f4; } .key i { font-style: normal; }
    .empty { padding: 2rem 1rem; color: #9ba7ba; text-align: center; }
</style>
