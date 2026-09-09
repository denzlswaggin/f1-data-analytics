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
        margin: 1.1rem 0 1.4rem;
        padding: 1rem 1.05rem;
        border: 1px solid rgba(160, 174, 201, 0.2);
        border-radius: 0.85rem;
        background: linear-gradient(115deg, rgba(50, 211, 244, 0.075), rgba(255, 255, 255, 0.025));
    }
    .filter-heading {
        display: flex;
        flex-direction: column;
        gap: 0.15rem;
        min-width: 8rem;
    }
    .filter-heading strong { color: #f3f6fa; font-size: 0.92rem; }
    .filter-heading span { max-width: 28rem; color: #9ba7ba; font-size: 0.81rem; line-height: 1.4; }
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
