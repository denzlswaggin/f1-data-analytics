<script>
    import { onMount } from 'svelte';

    const productionTarget = '/f1-data-analytics/replay/';
    let target = '#';

    onMount(() => {
        const current = new URL(window.location.href);
        const isLocal = ['localhost', '127.0.0.1', '[::1]', '::1'].includes(current.hostname)
            || current.port === '3000';

        if (isLocal) {
            current.port = '5173';
            current.pathname = '/';
            // Preserve the selected season and race when entering the replay.
            current.hash = '';
            target = current.toString();
        } else {
            target = productionTarget + current.search;
        }

        window.location.replace(target);
    });
</script>

<section class="redirect" aria-live="polite">
    <span class="eyebrow">Race replay</span>
    <h1>Opening the live replay&hellip;</h1>
    <p>The replay now runs in its own high-performance interface.</p>
    <a href={target}>Open race replay</a>
</section>

<style>
    .redirect {
        max-width: 38rem;
        margin: 12vh auto;
        padding: 2rem;
        border: 1px solid color-mix(in srgb, currentColor 14%, transparent);
        border-radius: 1rem;
        text-align: center;
    }

    .eyebrow {
        font-size: 0.72rem;
        font-weight: 750;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        opacity: 0.58;
    }

    h1 {
        margin: 0.6rem 0;
    }

    p {
        margin: 0 0 1.2rem;
        opacity: 0.72;
    }

    a {
        display: inline-block;
        padding: 0.7rem 1rem;
        border-radius: 0.55rem;
        background: #e10600;
        color: white;
        font-weight: 700;
        text-decoration: none;
    }
</style>
