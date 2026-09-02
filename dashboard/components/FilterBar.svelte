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
        align-items: flex-end;
        justify-content: space-between;
        gap: 1rem;
        margin: 1rem 0 1.25rem;
        padding: 0.85rem 1rem;
        border: 1px solid var(--color-base-300, #d7dce1);
        border-radius: 0.65rem;
        background: color-mix(in srgb, var(--color-base-100, #fff) 94%, var(--color-primary, #2563eb));
    }
    .filter-heading {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        min-width: 8rem;
    }
    .filter-heading strong { font-size: 0.88rem; }
    .filter-heading span { font-size: 0.76rem; line-height: 1.35; opacity: 0.65; }
    .filter-controls {
        display: flex;
        align-items: flex-end;
        justify-content: flex-end;
        gap: 0.75rem;
        flex: 1;
        flex-wrap: wrap;
    }
    :global(.filter-controls > *) { margin: 0; min-width: 10rem; }
    @media (max-width: 680px) {
        .filter-bar { align-items: stretch; flex-direction: column; }
        .filter-controls { align-items: stretch; justify-content: stretch; }
        :global(.filter-controls > *) { width: 100%; min-width: 0; }
    }
</style>
