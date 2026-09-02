<script>
    export let section = 'race';
    export let current = '';
    export let season = null;
    export let race = null;

    const basePath = '/f1-data-analytics';
    const groups = {
        race: [
            ['Race story', 'latest-race'],
            ['Race replay', 'race-replay'],
            ['Race pace', 'race-pace'],
            ['Pit strategy', 'pit-strategy'],
            ['Tyre strategy', 'tyre-strategy'],
            ['Telemetry', 'telemetry'],
            ['Conditions', 'weather-and-speed']
        ],
        drivers: [
            ['Driver ratings', 'driver-ratings'],
            ['Compare drivers', 'driver-comparison'],
            ['Saturday vs Sunday', 'saturday-vs-sunday']
        ],
        trust: [
            ['Overview', ''],
            ['Driver ratings', 'driver-ratings'],
            ['Methodology', 'methodology']
        ]
    };

    $: links = (groups[section] || groups.race).filter((item) => item[1] !== current);

    function href(path) {
        const params = [];
        if (season !== null && season !== undefined && season !== '') params.push(`season=${encodeURIComponent(season)}`);
        if (race !== null && race !== undefined && race !== '') params.push(`race=${encodeURIComponent(race)}`);
        return `${basePath}/${path ? `${path}/` : ''}${params.length ? `?${params.join('&')}` : ''}`;
    }
</script>

<nav class="related" aria-label="Related analysis">
    <strong>Continue exploring</strong>
    <div>
        {#each links as item}<a href={href(item[1])}>{item[0]} <span aria-hidden="true">→</span></a>{/each}
    </div>
</nav>

<style>
    .related {
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid var(--color-base-300, #d7dce1);
    }
    .related > strong { display: block; margin-bottom: 0.6rem; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.055em; opacity: 0.62; }
    .related div { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    a {
        padding: 0.42rem 0.65rem;
        border: 1px solid var(--color-base-300, #d7dce1);
        border-radius: 999px;
        color: inherit;
        font-size: 0.82rem;
        text-decoration: none;
    }
    a:hover, a:focus-visible { border-color: var(--color-primary, #2563eb); color: var(--color-primary, #2563eb); outline: none; }
</style>
