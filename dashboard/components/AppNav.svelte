<script>
    import { onMount } from 'svelte';

    const basePath = '/f1-data-analytics';
    const groups = [
        {
            label: 'Start here',
            items: [
                { label: 'Overview', path: '' },
                { label: 'Explore a race', path: 'race-cockpit' },
                { label: 'Compare drivers', path: 'driver-comparison' },
                { label: 'Methodology', path: 'methodology' }
            ]
        },
        {
            label: 'Race analyses',
            items: [
                { label: 'Latest race', path: 'latest-race' },
                { label: 'Race replay', path: 'race-replay' },
                { label: 'Race pace', path: 'race-pace' },
                { label: 'Traffic-adjusted pace', path: 'traffic-adjusted-pace' },
                { label: 'Pit strategy', path: 'pit-strategy' },
                { label: 'Pit-window effectiveness', path: 'pit-window-effectiveness' },
                { label: 'Pit timing sensitivity', path: 'pit-timing-sensitivity' },
                { label: 'Race-control impact', path: 'race-control-impact' },
                { label: 'Tyre strategy', path: 'tyre-strategy' },
                { label: 'Tyre pace settling', path: 'tyre-warmup' },
                { label: 'Telemetry', path: 'telemetry' },
                { label: 'Conditions & speed', path: 'weather-and-speed' }
            ]
        },
        {
            label: 'Driver intelligence',
            items: [
                { label: 'Driver DNA', path: 'driver-dna' },
                { label: 'Driver ratings', path: 'driver-ratings' },
                { label: 'Track fit & stability', path: 'driver-track-insights' },
                { label: 'Pace consistency', path: 'pace-consistency' },
                { label: 'Racecraft battles', path: 'racecraft-battles' },
                { label: 'Saturday vs Sunday', path: 'saturday-vs-sunday' }
            ]
        }
    ];

    let current = '';
    let mobileOpen = false;

    onMount(() => {
        current = window.location.pathname
            .replace(basePath, '')
            .replace(/^\/+|\/+$/g, '');
    });

    const href = (path) => `${basePath}/${path ? `${path}/` : ''}`;
</script>

<nav class="app-nav" aria-label="Primary navigation">
    <div class="nav-head">
        <a class="brand" href={href('')} aria-label="F1 Analytics overview">
            <span class="mark" aria-hidden="true"></span>
            <span class="brand-copy"><strong>F1</strong><span>Race Intelligence</span></span>
        </a>
        <button
            class="menu-toggle"
            type="button"
            aria-expanded={mobileOpen}
            aria-controls="analytics-navigation"
            on:click={() => mobileOpen = !mobileOpen}
        >
            <span>{mobileOpen ? 'Close' : 'All analyses'}</span>
            <i aria-hidden="true">{mobileOpen ? '×' : '☰'}</i>
        </button>
    </div>

    <div id="analytics-navigation" class="nav-groups" class:open={mobileOpen}>
        {#each groups as group, index}
            <details open={index === 0 || group.items.some(item => item.path === current)}>
                <summary class="group-label">{group.label}</summary>
                <div class="links">
                    {#each group.items as item}
                        <a
                            href={href(item.path)}
                            class:active={current === item.path}
                            aria-current={current === item.path ? 'page' : undefined}
                            on:click={() => mobileOpen = false}
                        >
                            <span class="dot" aria-hidden="true"></span>
                            {item.label}
                        </a>
                    {/each}
                </div>
            </details>
        {/each}
    </div>

    <div class="nav-foot">Published race data</div>
</nav>

<style>
    .app-nav {
        position: fixed;
        z-index: 30;
        top: 1rem;
        bottom: 1rem;
        left: max(0.75rem, calc(50vw - 900px));
        display: flex;
        align-items: stretch;
        flex-direction: column;
        width: 14rem;
        padding: 1rem;
        overflow: hidden;
        border: 1px solid rgba(160, 174, 201, 0.18);
        border-radius: 1rem;
        background: color-mix(in srgb, #11151d 92%, transparent);
        box-shadow: 0 24px 65px rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(16px);
    }
    .nav-head { display: flex; flex-shrink: 0; align-items: center; justify-content: space-between; }
    .brand,
    .links a { color: inherit; text-decoration: none; }
    .brand { display: inline-flex; align-items: center; gap: 0.7rem; flex: none; font-weight: 760; }
    .mark {
        width: 1.45rem;
        height: 0.85rem;
        border-top: 0.25rem solid #ff4050;
        border-right: 0.42rem solid #32d3f4;
        transform: skewX(-18deg);
    }
    .brand-copy { display: flex; align-items: flex-start; flex-direction: column; gap: 0.05rem; }
    .brand-copy strong { color: #f8fafc; font-size: 1.02rem; letter-spacing: -0.04em; }
    .brand-copy span { color: #9ba7ba; font-size: 0.75rem; font-weight: 650; letter-spacing: 0.04em; }
    .nav-groups {
        display: flex;
        flex-direction: column;
        gap: 1.15rem;
        margin-top: 1.5rem;
        min-height: 0;
        overflow-y: auto;
        overflow-x: hidden;
        overscroll-behavior: contain;
        scrollbar-width: thin;
        scrollbar-color: #566174 transparent;
    }
    details { margin: 0; }
    .group-label {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: .5rem;
        list-style: none;
        margin: 0 0 0.35rem 0.65rem;
        color: #aab6c6;
        font-size: 0.75rem;
        cursor: pointer;
        padding: 0.5rem 0;
        font-weight: 780;
        letter-spacing: 0.11em;
        text-transform: uppercase;
    }
    summary::-webkit-details-marker { display: none; }
    summary::after { content: ''; width: .4rem; height: .4rem; margin-right: .4rem; flex: none; border-right: 1px solid currentColor; border-bottom: 1px solid currentColor; transform: rotate(45deg); }
    details[open] > summary::after { transform: rotate(225deg); }
    .links { display: flex; flex-direction: column; gap: 0.15rem; }
    .links a {
        display: flex;
        align-items: center;
        gap: 0.55rem;
        padding: 0.48rem 0.65rem;
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
        border-color: rgba(160, 174, 201, 0.3);
        background: rgba(160, 174, 201, 0.12);
        color: #f8fafc;
    }
    .dot { width: 0.35rem; height: 0.35rem; flex: none; border: 1px solid #657084; border-radius: 50%; }
    .links a.active .dot { border-color: #aab6c6; background: #aab6c6; }
    .links a:focus-visible, summary:focus-visible, .menu-toggle:focus-visible { outline: 2px solid #9bc3ff; outline-offset: 2px; }
    .menu-toggle {
        display: none;
        align-items: center;
        gap: 0.55rem;
        border: 0;
        background: transparent;
        color: #cbd4e0;
        font: inherit;
        font-size: 0.8rem;
        font-weight: 700;
        cursor: pointer;
    }
    .menu-toggle i { font-style: normal; font-size: 1rem; }
    .nav-foot {
        flex-shrink: 0;
        display: flex;
        align-items: center;
        gap: 0.45rem;
        margin-top: auto;
        padding: 1rem 0.65rem 0;
        border-top: 1px solid rgba(160, 174, 201, 0.13);
        color: #778397;
        font-size: 0.7rem;
        font-weight: 650;
    }
    @media (min-width: 1101px) and (max-height: 1100px) {
        .app-nav { padding: 0.75rem; }
        .nav-groups { gap: 0.65rem; margin-top: 0.85rem; }
        .links a { padding: 0.32rem 0.55rem; line-height: 1.25; }
        .group-label { margin-bottom: 0.25rem; }
        .nav-foot { padding-top: 0.6rem; }
    }
    @media (max-width: 1100px) {
        .app-nav {
            position: sticky;
            top: 0.5rem;
            bottom: auto;
            left: auto;
            width: auto;
            margin: 0.5rem 0 1rem;
            padding: 0.85rem 1rem;
            overflow: visible;
        }
        .brand-copy { align-items: baseline; flex-direction: row; gap: 0.5rem; }
        .menu-toggle { display: flex; }
        .nav-groups {
            display: none;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1.2rem;
            margin: 1rem 0 0.25rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(160, 174, 201, 0.16);
        }
        .nav-groups.open { display: grid; }
        .nav-foot { display: none; }
    }
    @media (max-width: 640px) {
        .nav-groups { grid-template-columns: 1fr; max-height: calc(100vh - 7rem); overflow-y: auto; }
        .brand-copy span { display: none; }
    }
</style>
