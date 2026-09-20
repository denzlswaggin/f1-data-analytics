<script>
    export let label = 'Key insight';
    export let tone = 'info';
</script>

<aside class="insight {tone}" aria-label={label}>
    <div class="label">{label}</div>
    <div class="content"><slot /></div>
</aside>

<style>
    .insight {
        margin: 1rem 0 1.35rem;
        padding: 1rem 1.1rem;
        border-left: 2px solid #64748b;
        border-radius: 0 0.5rem 0.5rem 0;
        background: rgba(148, 163, 184, 0.04);
    }
    .insight.positive {
        border-left-color: var(--color-positive, #16a34a);
        background: color-mix(in srgb, var(--color-positive, #16a34a) 8%, transparent);
    }
    .insight.warning {
        border-left-color: var(--color-warning, #f8c900);
        background: color-mix(in srgb, var(--color-warning, #f8c900) 10%, transparent);
    }
    .label {
        margin-bottom: 0.25rem;
        color: #b9c5d5;
        font-size: 0.78rem;
        font-weight: 750;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }
    .content { color: #dbe4ef; font-size: 0.96rem; line-height: 1.55; }
    :global(.content > :first-child) { margin-top: 0; }
    :global(.content > :last-child) { margin-bottom: 0; }
</style>
