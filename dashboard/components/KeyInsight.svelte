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
        border: 1px solid rgba(50, 211, 244, 0.2);
        border-left: 4px solid var(--color-info, #32d3f4);
        border-radius: 0.75rem;
        background: linear-gradient(105deg, rgba(50, 211, 244, 0.09), rgba(255,255,255,.018));
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
        color: #7edff3;
        font-size: 0.72rem;
        font-weight: 750;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }
    .content { color: #dbe4ef; font-size: 0.96rem; line-height: 1.55; }
    :global(.content > :first-child) { margin-top: 0; }
    :global(.content > :last-child) { margin-bottom: 0; }
</style>
