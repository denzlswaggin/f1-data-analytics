<script>
    import { onMount } from 'svelte';

    const basePath = '/f1-data-analytics';
    const items = [
        { label: 'Overview', path: '', match: ['', 'latest-race'] },
        { label: 'Race analysis', path: 'latest-race', match: ['latest-race', 'race-pace', 'race-replay', 'pit-strategy', 'tyre-strategy', 'telemetry', 'weather-and-speed'] },
        { label: 'Drivers', path: 'driver-ratings', match: ['driver-ratings', 'driver-comparison', 'saturday-vs-sunday'] },
        { label: 'Methodology', path: 'methodology', match: ['methodology'] }
    ];

    let current = '';

    onMount(() => {
        current = window.location.pathname
            .replace(basePath, '')
            .replace(/^\/+|\/+$/g, '');
    });

    const href = (path) => `${basePath}/${path ? `${path}/` : ''}`;
</script>

<nav class="app-nav" aria-label="Primary navigation">
    <a class="brand" href={href('')} aria-label="F1 Analytics overview">
        <span class="mark" aria-hidden="true"></span>
        <span>F1 Analytics</span>
    </a>
    <div class="links">
        {#each items as item}
            <a href={href(item.path)} class:active={item.match.includes(current)} aria-current={item.match.includes(current) ? 'page' : undefined}>
                {item.label}
            </a>
        {/each}
    </div>
</nav>

<style>
    .app-nav {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin: 0 0 1.75rem;
        padding: 0.65rem 0;
        border-bottom: 1px solid var(--color-base-300, #d7dce1);
    }
    .brand,
    .links a {
        color: inherit;
        text-decoration: none;
    }
    .brand {
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        flex: none;
        font-weight: 750;
        letter-spacing: -0.015em;
    }
    .mark {
        width: 1.15rem;
        height: 0.72rem;
        border-top: 0.22rem solid var(--color-primary, #2563eb);
        border-right: 0.35rem solid var(--color-accent, #c2410c);
        transform: skewX(-18deg);
    }
    .links {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 0.25rem;
        flex-wrap: wrap;
    }
    .links a {
        padding: 0.42rem 0.65rem;
        border-radius: 0.4rem;
        font-size: 0.86rem;
        font-weight: 550;
        opacity: 0.72;
    }
    .links a:hover,
    .links a:focus-visible {
        background: color-mix(in srgb, var(--color-primary, #2563eb) 10%, transparent);
        opacity: 1;
        outline: none;
    }
    .links a.active {
        background: color-mix(in srgb, var(--color-primary, #2563eb) 14%, transparent);
        color: var(--color-primary, #2563eb);
        opacity: 1;
    }
    @media (max-width: 680px) {
        .app-nav {
            align-items: flex-start;
            flex-direction: column;
        }
        .links {
            justify-content: flex-start;
            width: 100%;
        }
        .links a {
            padding-left: 0;
            padding-right: 0.8rem;
            background: transparent;
        }
        .links a.active {
            background: transparent;
            text-decoration: underline;
            text-decoration-thickness: 2px;
            text-underline-offset: 0.3rem;
        }
    }
</style>
