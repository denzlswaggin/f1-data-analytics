<script>
    export let section = 'race';
    export let current = '';
    export let season = null;
    export let race = null;

    const basePath = '/f1-data-analytics';
    const groups = {
        race: [
            ['Race cockpit', 'race-cockpit'],
            ['Race replay', 'race-replay'],
            ['Race pace', 'race-pace'],
            ['Traffic-adjusted pace', 'traffic-adjusted-pace'],
            ['Pit strategy', 'pit-strategy'],
            ['Pit-window effectiveness', 'pit-window-effectiveness'],
            ['Pit timing sensitivity', 'pit-timing-sensitivity'],
            ['Race-control impact', 'race-control-impact'],
            ['Tyre strategy', 'tyre-strategy'],
            ['Tyre pace settling', 'tyre-warmup'],
            ['Telemetry', 'telemetry'],
            ['Conditions', 'weather-and-speed']
        ],
        drivers: [
            ['Driver ratings', 'driver-ratings'],
            ['Compare drivers', 'driver-comparison'],
            ['Driver DNA', 'driver-dna'],
            ['Track fit & stability', 'driver-track-insights'],
            ['Pace consistency', 'pace-consistency'],
            ['Racecraft battles', 'racecraft-battles'],
            ['Saturday vs Sunday', 'saturday-vs-sunday']
        ],
        trust: [
            ['Overview', ''],
            ['Driver ratings', 'driver-ratings'],
            ['Methodology', 'methodology']
        ]
    };

    const relatedPaths = {
        'race-pace': ['traffic-adjusted-pace', 'pace-consistency', 'telemetry'],
        'traffic-adjusted-pace': ['race-pace', 'pace-consistency', 'race-replay'],
        'pit-strategy': ['pit-window-effectiveness', 'pit-timing-sensitivity', 'tyre-strategy'],
        'pit-window-effectiveness': ['pit-strategy', 'pit-timing-sensitivity', 'race-control-impact'],
        'pit-timing-sensitivity': ['pit-window-effectiveness', 'pit-strategy', 'tyre-strategy'],
        'tyre-strategy': ['tyre-warmup', 'pit-strategy', 'race-pace'],
        'tyre-warmup': ['tyre-strategy', 'race-pace', 'traffic-adjusted-pace'],
        'telemetry': ['driver-dna', 'driver-comparison', 'race-pace'],
        'driver-dna': ['driver-track-insights', 'driver-comparison', 'telemetry'],
        'driver-ratings': ['driver-comparison', 'saturday-vs-sunday', 'driver-dna'],
        'driver-comparison': ['driver-ratings', 'driver-dna', 'saturday-vs-sunday']
    };
    const allLinks = Object.values(groups).flat();
    $: links = relatedPaths[current]
        ? relatedPaths[current].map(path => allLinks.find(item => item[1] === path)).filter(Boolean)
        : (groups[section] || groups.race).filter(item => item[1] !== current).slice(0, 3);

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
        margin-top: 3.5rem;
        padding: 1.2rem;
        border: 1px solid rgba(160,174,201,.18);
        border-radius: .9rem;
        background: rgba(255,255,255,.018);
    }
    .related > strong { display: block; margin-bottom: 0.7rem; color: #aeb8c7; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.1em; }
    .related div { display: flex; flex-wrap: wrap; gap: 0.5rem; }
    a {
        padding: 0.42rem 0.65rem;
        border: 1px solid rgba(160,174,201,.2);
        border-radius: 999px;
        color: inherit;
        background: rgba(255,255,255,.025);
        color: #dbe3ee;
        font-size: 0.85rem;
        text-decoration: none;
    }
    a:hover { border-color: #9ba7ba; color: #f8fafc; }
    a:focus-visible { outline: 2px solid #9bc3ff; outline-offset: 2px; }
</style>
