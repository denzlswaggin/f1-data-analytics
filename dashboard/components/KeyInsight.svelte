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
        padding: 0.9rem 1rem;
        border-left: 4px solid var(--color-info, #0284c7);
        border-radius: 0 0.55rem 0.55rem 0;
        background: color-mix(in srgb, var(--color-info, #0284c7) 8%, transparent);
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
        font-size: 0.7rem;
        font-weight: 750;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        opacity: 0.65;
    }
    .content { font-size: 0.93rem; line-height: 1.5; }
    :global(.content > :first-child) { margin-top: 0; }
    :global(.content > :last-child) { margin-bottom: 0; }
</style>
