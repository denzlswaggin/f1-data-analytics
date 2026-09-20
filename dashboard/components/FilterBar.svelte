<script>
    export let title = 'Filters';
    export let description = '';
</script>

<section class="filter-bar" aria-label={title}>
    <div class="filter-heading">
        <strong>{title}</strong>
        {#if description}<span>{description}</span>{/if}
    </div>
    <div class="filter-controls"><slot /></div>
</section>

<style>
    .filter-bar {
        display: flex;
        flex-wrap: wrap;
        min-width: 0;
        align-items: flex-end;
        justify-content: space-between;
        gap: 1rem;
        margin: 1.1rem 0 1.4rem;
        padding: 0.75rem 0;
        border-bottom: 1px solid var(--dashboard-border);
        background: transparent;
    }
    .filter-heading {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        flex: 1 1 100%;
        min-width: 0;
    }
    .filter-heading strong { color: #f3f6fa; font-size: 0.92rem; }
    .filter-heading span { max-width: 28rem; color: #9ba7ba; font-size: 0.81rem; line-height: 1.4; }
    .filter-controls {
        display: flex;
        align-items: flex-end;
        justify-content: flex-start;
        gap: 0.75rem;
        flex: 1;
        min-width: 0;
        flex-wrap: wrap;
    }
    :global(.filter-controls > *) { margin: 0; min-width: min(10rem, 100%); max-width: 100%; }
    :global(.filter-controls [role="combobox"]) {
        max-width: 100%;
        height: auto;
        min-height: 2rem;
        white-space: normal;
        overflow-wrap: anywhere;
        text-align: left;
    }
    @media (max-width: 680px) {
        .filter-bar { align-items: stretch; flex-direction: column; }
        .filter-heading { flex-basis: auto; }
        .filter-controls { align-items: stretch; justify-content: stretch; }
        .filter-controls { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
        :global(.filter-controls > *) { width: 100%; min-width: 0; }
        :global(.filter-controls [role="combobox"]) { width: 100%; min-height: 2.75rem; }
    }
</style>
