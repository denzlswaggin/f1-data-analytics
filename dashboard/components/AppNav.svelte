<script>
    import { onMount } from 'svelte';

    const basePath = '/f1-data-analytics';
    const groups = [
        { label: 'Overview', items: [{ label: 'Dashboard', path: '' }] },
        {
            label: 'Race analysis',
            items: [
                { label: 'Latest race', path: 'latest-race' },
                { label: 'Race replay', path: 'race-replay' },
                { label: 'Race pace', path: 'race-pace' },
                { label: 'Traffic-adjusted pace', path: 'traffic-adjusted-pace' },
                { label: 'Pit strategy', path: 'pit-strategy' },
                { label: 'Pit-window effectiveness', path: 'pit-window-effectiveness' },
                { label: 'Tyre strategy', path: 'tyre-strategy' },
                { label: 'Telemetry', path: 'telemetry' },
                { label: 'Conditions & speed', path: 'weather-and-speed' }
            ]
        },
        {
            label: 'Driver intelligence',
            items: [
                { label: 'Driver ratings', path: 'driver-ratings' },
                { label: 'Compare drivers', path: 'driver-comparison' },
                { label: 'Saturday vs Sunday', path: 'saturday-vs-sunday' }
            ]
        },
        { label: 'Data', items: [{ label: 'Methodology & trust', path: 'methodology' }] }
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
        {#each groups as group}
            <section>
                <span class="group-label">{group.label}</span>
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
            </section>
        {/each}
    </div>

    <div class="nav-foot"><span aria-hidden="true"></span> Snapshot online</div>
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
        overflow-y: auto;
        border: 1px solid rgba(160, 174, 201, 0.18);
        border-radius: 1rem;
        background: color-mix(in srgb, #11151d 92%, transparent);
        box-shadow: 0 24px 65px rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(16px);
    }
    .nav-head { display: flex; align-items: center; justify-content: space-between; }
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
    .brand-copy span { color: #9ba7ba; font-size: 0.68rem; font-weight: 720; letter-spacing: 0.09em; text-transform: uppercase; }
    .nav-groups { display: flex; flex-direction: column; gap: 1.15rem; margin-top: 1.5rem; }
    section { margin: 0; }
    .group-label {
        display: block;
        margin: 0 0 0.35rem 0.65rem;
        color: #6f7b8e;
        font-size: 0.65rem;
        font-weight: 780;
        letter-spacing: 0.11em;
        text-transform: uppercase;
    }
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
        border-color: rgba(255, 64, 80, 0.36);
        background: rgba(255, 64, 80, 0.1);
        color: #ff7180;
    }
    .dot { width: 0.35rem; height: 0.35rem; flex: none; border: 1px solid #657084; border-radius: 50%; }
    .links a.active .dot { border-color: #ff4050; background: #ff4050; box-shadow: 0 0 0 3px rgba(255, 64, 80, 0.13); }
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
    .nav-foot span { width: 0.45rem; height: 0.45rem; border-radius: 50%; background: #46d39a; box-shadow: 0 0 0 3px rgba(70, 211, 154, 0.1); }
    @media (max-width: 1240px) {
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
