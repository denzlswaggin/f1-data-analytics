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
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        list-style: none;
        padding: 0.85rem 1rem;
        cursor: pointer;
        color: #c5cedb;
        font-size: 0.89rem;
        font-weight: 650;
    }
    summary:hover {
        background: rgba(160, 174, 201, 0.06);
    }
    summary:focus-visible {
        border-radius: 0.25rem;
        outline: 2px solid var(--dashboard-muted, #9ba7ba);
        outline-offset: 2px;
    }
    summary::-webkit-details-marker { display: none; }
    summary::after { content: ''; flex: none; width: 0.45rem; height: 0.45rem; border-right: 2px solid #9ba7ba; border-bottom: 2px solid #9ba7ba; transform: rotate(45deg); }
    details[open] summary::after { transform: rotate(225deg); }
    .body { padding: 0.2rem 1rem 1rem; }
</style>
