<script>
    export let title = 'View details';
    export let open = false;
</script>

<details class="expandable" {open}>
    <summary>{title}</summary>
    <div class="body"><slot /></div>
</details>

<style>
    .expandable {
        margin: 1rem 0 1.5rem;
        border-top: 1px solid var(--color-base-300, #d7dce1);
        border-bottom: 1px solid var(--color-base-300, #d7dce1);
    }
    summary {
        padding: 0.75rem 0;
        cursor: pointer;
        font-size: 0.86rem;
        font-weight: 650;
        color: var(--color-primary, #2563eb);
    }
    summary:focus-visible {
        border-radius: 0.25rem;
        outline: 2px solid var(--color-primary, #2563eb);
        outline-offset: 2px;
    }
    .body { padding: 0 0 0.75rem; }
</style>
