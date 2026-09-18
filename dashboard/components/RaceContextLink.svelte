<script>
    export let path = 'race-cockpit';
    export let season;
    export let race;
    export let label = 'Open race overview';
    $: params = new URLSearchParams({ season: String(season), race: String(race) });
    $: href = `/f1-data-analytics/${path}/?${params}`;
</script>

<a {href}>{label}</a>
