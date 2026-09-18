<script>
    export let season;
    export let race;
    $: href = `/f1-data-analytics/pit-window-effectiveness/?season=${encodeURIComponent(season)}&race=${encodeURIComponent(race)}`;
</script>

<p>Compare matched rival cycles in <a {href}>Pit Window Analysis</a>.</p>
