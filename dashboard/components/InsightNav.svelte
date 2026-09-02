<script>
    const groups = [
        {
            title: 'Race analysis',
            links: [
                ['How did the latest race unfold?', 'latest-race', 'Result, controlled pace, execution and key evidence'],
                ['Where was the race won?', 'race-pace', 'Compare drivers and race phases without a 20-car spaghetti chart'],
                ['Which pit cycles changed the race?', 'pit-strategy', 'Separate stop speed, position swing and race-control context'],
                ['Watch the race unfold', 'race-replay', 'Replay positions, overtakes, incidents and team radio']
            ]
        },
        {
            title: 'Driver analysis',
            links: [
                ['Who is fastest beyond the car?', 'driver-ratings', 'Teammate-normalised career pace and current form'],
                ['Compare two drivers honestly', 'driver-comparison', 'Season form with uncertainty and shared-season evidence'],
                ['Who gains on Sunday?', 'saturday-vs-sunday', 'Qualifying pace versus controlled race pace'],
                ['Where does each driver gain time?', 'telemetry', 'Speed, cumulative time delta and pedal inputs']
            ]
        },
        {
            title: 'Strategy and conditions',
            links: [
                ['Which tyres faded?', 'tyre-strategy', 'Strategy timeline and adjusted stint fall-off'],
                ['How did conditions shape performance?', 'weather-and-speed', 'Weather context and straight-line speed'],
                ['Can I trust this result?', 'methodology', 'Coverage, uncertainty, data contract and limitations']
            ]
        }
    ];
</script>

<div class="insight-nav">
    {#each groups as group}
        <section>
            <h3>{group.title}</h3>
            <div class="cards">
                {#each group.links as link}
                    <a href={link[1]}>
                        <strong>{link[0]}</strong>
                        <span>{link[2]}</span>
                    </a>
                {/each}
            </div>
        </section>
    {/each}
</div>

<style>
    .insight-nav { margin: 1rem 0 1.75rem; }
    section { margin-bottom: 1.2rem; }
    h3 { margin: 0 0 0.55rem; font-size: 0.95rem; text-transform: uppercase; letter-spacing: 0.055em; opacity: 0.72; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 0.7rem; }
    a { display: flex; flex-direction: column; gap: 0.25rem; min-height: 5.3rem; padding: 0.9rem 1rem; border: 1px solid var(--color-base-300, #d7dce1); border-radius: 0.65rem; color: inherit; text-decoration: none; background: var(--color-base-100, #fff); transition: border-color 120ms ease, transform 120ms ease, box-shadow 120ms ease; }
    a:hover, a:focus-visible { border-color: var(--color-primary, #2563eb); transform: translateY(-1px); box-shadow: 0 5px 16px rgba(15, 23, 42, 0.07); outline: none; }
    strong { font-size: 0.93rem; }
    span { font-size: 0.79rem; line-height: 1.35; opacity: 0.7; }
    @media (prefers-reduced-motion: reduce) { a { transition: none; } }
</style>
