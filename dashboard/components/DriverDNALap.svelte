<script>
    export let data = [];

    const num = (value) => value == null ? null : Number(value);
    let clientWidth = 900;
    let active = 0;
    $: rows = (data || []).map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, key.endsWith('_m') || key.endsWith('_sec') || key.endsWith('_kph') || key.includes('throttle') || key.includes('brake_share') ? num(value) : value]))).filter((row) => row.x != null && row.y != null);
    $: width = Math.max(300, clientWidth || 900);
    $: mobile = width < 680;
    $: mapWidth = mobile ? width - 24 : width * .48;
    $: mapHeight = mobile ? 330 : 430;
    $: traceWidth = mobile ? width - 24 : width * .46;
    $: traceHeight = 112;
    $: xs = rows.map((row) => row.x); $: ys = rows.map((row) => row.y);
    $: x0 = Math.min(...xs, 0); $: x1 = Math.max(...xs, 1); $: y0 = Math.min(...ys, 0); $: y1 = Math.max(...ys, 1);
    $: scale = Math.min((mapWidth-34)/Math.max(1,x1-x0), (mapHeight-34)/Math.max(1,y1-y0));
    $: mapX = (value) => 17 + (value-x0)*scale;
    $: mapY = (value) => mapHeight-17-(value-y0)*scale;
    $: maxDistance = Math.max(1, ...rows.map((row) => row.end_distance_m));
    $: traceX = (distance) => 34 + (distance/maxDistance)*(traceWidth-46);
    $: selected = rows[Math.min(active, Math.max(0, rows.length-1))];
    const color = (delta) => delta >= 0 ? '#32d3f4' : '#ff4050';
    const tracePath = (field, minimum, maximum) => rows.map((row, index) => {
        const y = 8 + ((maximum-row[field])/Math.max(.001, maximum-minimum))*(traceHeight-24);
        return `${index ? 'L' : 'M'} ${traceX(row.end_distance_m)} ${y}`;
    }).join(' ');
    $: speedValues = rows.flatMap((row) => [row.driver_speed_kph, row.teammate_speed_kph]);
    $: speedMin = Math.min(...speedValues, 0); $: speedMax = Math.max(...speedValues, 1);
</script>

<div class="lap" bind:clientWidth data-testid="driver-dna-lap">
    {#if rows.length}
        <div class="layout">
            <section>
                <div class="panel-title">200 m gain / loss map</div>
                <svg viewBox="0 0 {mapWidth} {mapHeight}" width="100%" height={mapHeight} role="img" aria-label="Track map coloured by teammate-relative time delta">
                    {#each rows as row, index}
                        {#if index > 0}
                            <line
                                x1={mapX(rows[index-1].x)} y1={mapY(rows[index-1].y)}
                                x2={mapX(row.x)} y2={mapY(row.y)}
                                stroke={color(row.segment_delta_sec)}
                                stroke-opacity={active === index ? 1 : .72}
                                stroke-width={active === index ? 8 : 5}
                                stroke-linecap="round"
                                tabindex="0"
                                on:mouseenter={() => active = index}
                                on:focus={() => active = index}
                            >
                                <title>Segment {row.segment_number}: {row.segment_delta_sec >= 0 ? '+' : ''}{row.segment_delta_sec.toFixed(3)} s</title>
                            </line>
                        {/if}
                    {/each}
                </svg>
                <div class="map-key"><span class="loss"></span>loss <i></i> gain<span class="gain"></span></div>
            </section>
            <section class="traces">
                <div class="panel-title">Synchronized technique traces</div>
                {#each [
                    { label: 'Speed (km/h)', a: 'driver_speed_kph', b: 'teammate_speed_kph', min: speedMin, max: speedMax },
                    { label: 'Throttle (%)', a: 'driver_throttle', b: 'teammate_throttle', min: 0, max: 100 },
                    { label: 'Brake share', a: 'driver_brake_share', b: 'teammate_brake_share', min: 0, max: 1 }
                ] as trace}
                    <div class="trace-label">{trace.label}</div>
                    <svg viewBox="0 0 {traceWidth} {traceHeight}" width="100%" height={traceHeight} role="img" aria-label={trace.label}>
                        <line class="grid" x1="34" x2={traceWidth-12} y1={traceHeight-16} y2={traceHeight-16} />
                        {#if selected}<line class="cursor" x1={traceX(selected.end_distance_m)} x2={traceX(selected.end_distance_m)} y1="5" y2={traceHeight-16} />{/if}
                        <path d={tracePath(trace.a, trace.min, trace.max)} fill="none" stroke="#32d3f4" stroke-width="2" />
                        <path d={tracePath(trace.b, trace.min, trace.max)} fill="none" stroke="#ff4050" stroke-width="2" />
                    </svg>
                {/each}
            </section>
        </div>
        {#if selected}
            <div class="tooltip" role="status">
                <strong>Segment {selected.segment_number} · {selected.start_distance_m.toFixed(0)}–{selected.end_distance_m.toFixed(0)} m</strong>
                <span class:positive={selected.segment_delta_sec >= 0}>{selected.segment_delta_sec >= 0 ? '+' : ''}{selected.segment_delta_sec.toFixed(3)} s vs {selected.teammate_name}</span>
                <span>{selected.driver_speed_kph.toFixed(0)} vs {selected.teammate_speed_kph.toFixed(0)} km/h</span>
                <span>{selected.driver_throttle.toFixed(0)}% vs {selected.teammate_throttle.toFixed(0)}% throttle</span>
                <span>{(selected.driver_brake_share*100).toFixed(0)}% vs {(selected.teammate_brake_share*100).toFixed(0)}% braking</span>
            </div>
        {/if}
    {:else}
        <div class="empty" role="status">No eligible same-compound green-flag lap is available for this race.</div>
    {/if}
</div>

<style>
    .lap { margin: 1rem 0 1.5rem; padding: 1rem; border: 1px solid rgba(160,174,201,.18); border-radius: .95rem; background: rgba(255,255,255,.025); }
    .layout { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 1.2rem; }
    section { min-width: 0; }
    .panel-title { margin-bottom: .3rem; color: #dce3ed; font-size: 13px; font-weight: 700; }
    .traces svg { display: block; }
    .trace-label { margin-top: .2rem; color: #8f9bae; font-size: 10px; }
    .grid { stroke: currentColor; stroke-opacity: .16; }
    .cursor { stroke: #f7c948; stroke-width: 1.5; stroke-dasharray: 3 3; }
    .map-key { display: flex; align-items: center; justify-content: center; gap: .4rem; color: #8f9bae; font-size: 11px; }
    .map-key span { width: 28px; height: 5px; border-radius: 4px; }
    .loss { background: #ff4050; } .gain { background: #32d3f4; } .map-key i { width: 1px; height: 12px; background: #657084; }
    .tooltip { display: flex; flex-wrap: wrap; gap: .45rem 1rem; margin-top: .9rem; padding: .75rem; border-radius: .6rem; background: rgba(9,12,18,.72); color: #aeb8c7; font-size: 12px; }
    .tooltip strong { color: #f4f7fb; } .tooltip span:nth-child(2) { color: #ff7180; font-weight: 700; } .tooltip span.positive { color: #32d3f4; }
    .empty { padding: 2rem 1rem; color: #9ba7ba; text-align: center; }
    @media (max-width: 680px) { .layout { grid-template-columns: 1fr; } .lap { padding: .7rem; } }
</style>
