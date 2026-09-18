<script>
    import DependentDropdown from './DependentDropdown.svelte';
    export let data = [];
    export let name;
    export let value;
    export let label = value;
</script>

<DependentDropdown {data} {name} {value} {label} {...$$restProps} />
