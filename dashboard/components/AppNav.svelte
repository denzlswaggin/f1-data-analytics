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
        <span class="brand-copy"><strong>F1</strong><span>Race Intelligence</span></span>
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
        position: sticky;
        z-index: 30;
        top: 0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin: 0 0 1rem;
        padding: 0.85rem 0;
        border-bottom: 1px solid rgba(160, 174, 201, 0.18);
        background: color-mix(in srgb, #090c12 88%, transparent);
        backdrop-filter: blur(16px);
    }
    .brand,
    .links a {
        color: inherit;
        text-decoration: none;
    }
    .brand {
        display: inline-flex;
        align-items: center;
        gap: 0.7rem;
        flex: none;
        font-weight: 760;
    }
    .mark {
        width: 1.45rem;
        height: 0.85rem;
        border-top: 0.25rem solid #ff4050;
        border-right: 0.42rem solid #32d3f4;
        transform: skewX(-18deg);
    }
    .brand-copy { display: flex; align-items: baseline; gap: 0.5rem; }
    .brand-copy strong { color: #f8fafc; font-size: 1.02rem; letter-spacing: -0.04em; }
    .brand-copy span { color: #9ba7ba; font-size: 0.68rem; font-weight: 720; letter-spacing: 0.09em; text-transform: uppercase; }
    .links {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 0.3rem;
        flex-wrap: wrap;
    }
    .links a {
        padding: 0.5rem 0.72rem;
        border: 1px solid transparent;
        border-radius: 0.55rem;
        color: #aeb9c8;
        font-size: 0.82rem;
        font-weight: 650;
    }
    .links a:hover,
    .links a:focus-visible {
        border-color: rgba(160, 174, 201, 0.18);
        background: rgba(255, 255, 255, 0.045);
        color: #f8fafc;
        outline: none;
    }
    .links a.active {
        border-color: rgba(255, 64, 80, 0.36);
        background: rgba(255, 64, 80, 0.1);
        color: #ff7180;
    }
    @media (max-width: 680px) {
        .app-nav { align-items: flex-start; flex-direction: column; }
        .links {
            justify-content: flex-start;
            width: 100%;
        }
        .links a {
            padding: 0.35rem 0.65rem 0.35rem 0;
            border: 0;
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
