<script>
    import { Dropdown } from '@evidence-dev/core-components';
    import { getInputContext } from '@evidence-dev/sdk/utils/svelte';

    export let data = [];
    export let name;
    export let value;
    export let label = value;
    export let title;
    export let order = undefined;
    export let season;
    export let round = undefined;
    export let defaultValue = undefined;
    export let fallbackIndex = 0;
    export let latest = false;
    export let preserveInitial = false;

    const inputs = getInputContext();
    const same = (a, b) => String(a ?? '') === String(b ?? '');
    let initialValue = preserveInitial ? $inputs[name]?.value : undefined;
    let previousScope;
    let previousOptions;
    let generation = 0;

    $: scope = JSON.stringify([season, round]);
    // Ignore an earlier query response while the parent selection is changing.
    $: rows = Array.from(data ?? []).filter(row => same(row.season, season)
        && (round === undefined || same(row.round, round)));
    $: optionsKey = JSON.stringify(rows.map(row => [row[value], row[label]]));
    $: {
        const scopeChanged = scope !== previousScope;
        if (scopeChanged && previousScope !== undefined) initialValue = undefined;
        const current = $inputs[name]?.value;
        const valid = rows.find(row => same(row[value], current));
        if (scopeChanged || optionsKey !== previousOptions || (!valid && rows.length)) {
            const requested = rows.find(row => same(row[value], initialValue));
            const preferred = rows.find(row => same(row[value], defaultValue));
            const fallback = latest
                ? rows.reduce((last, row) => !last || Number(row[value]) > Number(last[value]) ? row : last, undefined)
                : rows[Math.min(fallbackIndex, rows.length - 1)];
            const selected = (!scopeChanged && valid) || requested || preferred || fallback;
            if (selected) {
                $inputs[name] = { value: selected[value], label: selected[label],
                    rawValues: [{ value: selected[value], label: selected[label], selected: true }] };
            } else {
                // An unset Evidence input suspends dependent queries. Publishing
                // SQL NULL here would run them prematurely during prerendering.
                inputs.update(state => { delete state[name]; return state; });
            }
            if (rows.length) initialValue = undefined;
            previousScope = scope;
            previousOptions = optionsKey;
            generation += 1;
        }
    }
</script>

{#key generation}
    {#if rows.length}
        <Dropdown {data} {name} {value} {label} {order} {title} defaultValue={$inputs[name]?.value} />
    {:else}
        <label class="empty-dropdown">{title}<select disabled aria-label={title}><option>No available options</option></select></label>
    {/if}
{/key}

<style>
    .empty-dropdown { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.875rem; }
    select { min-width: 10rem; padding: 0.5rem; border: 1px solid #475569; border-radius: 0.375rem; background: transparent; color: inherit; opacity: 0.6; }
</style>
