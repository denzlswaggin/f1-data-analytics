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
        overflow: hidden;
        border: 1px solid rgba(160, 174, 201, 0.18);
        border-radius: 0.75rem;
        background: rgba(255,255,255,.018);
    }
    summary {
        padding: 0.85rem 1rem;
        cursor: pointer;
        color: #ff7180;
        font-size: 0.89rem;
        font-weight: 650;
    }
    summary:focus-visible {
        border-radius: 0.25rem;
        outline: 2px solid var(--color-primary, #2563eb);
        outline-offset: 2px;
    }
    summary::after { float: right; color: #9ba7ba; content: '+'; font-size: 1.1rem; }
    details[open] summary::after { content: '−'; }
    .body { padding: 0.2rem 1rem 1rem; }
</style>
