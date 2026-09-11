<script>
    import DependentDropdown from './DependentDropdown.svelte';

    export let data = [];
    export let season;
    export let round;

</script>

<DependentDropdown {data} {season} {round} name=event value=event_id label=event_label
    order="event_number asc" title="Event" />
