<script>
    const featured = [
        ['What shaped a race?', 'race-cockpit', 'Start with the result, then compare pace, strategy and evidence.', 'Race overview'],
        ['How do two drivers compare?', 'driver-comparison', 'See shared-season form, uncertainty and supporting observations.', 'Driver comparison'],
        ['How did the race unfold?', 'race-replay', 'Follow positions, incidents and radio on one timeline.', 'Race replay']
    ];
    const groups = [
        {
            title: 'Race analysis',
            links: [
                ['How did the race unfold?', 'race-cockpit', 'Recorded result, peer-relative pace and evidence coverage'],
                ['Where was the race won?', 'race-pace', 'Compare drivers and race phases without a 20-car spaghetti chart'],
                ['Which pit cycles changed the race?', 'pit-strategy', 'Separate stop speed, position swing and race-control context'],
                ['What does the experimental pit-timing model assume?', 'pit-timing-sensitivity', 'Inspect model eligibility and conditional ±3-lap scenarios'],
                ['Watch the race unfold', 'race-replay', 'Replay positions, overtakes, incidents and team radio']
            ]
        },
        {
            title: 'Driver analysis',
            links: [
                ['How do teammates compare?', 'driver-ratings', 'Teammate-normalised 2024–2026 pace and season form'],
                ['Compare two drivers honestly', 'driver-comparison', 'Season form with uncertainty and shared-season evidence'],
                ['Who repeats their pace most reliably?', 'pace-consistency', 'Clean-air consistency and unexplained slow-lap tail'],
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

<nav class="insight-nav" aria-label="Explore analyses by question">
    <div class="featured">
        {#each featured as link}
            <a href={link[1]}><small class="topic">{link[3]}</small><strong>{link[0]} <i aria-hidden="true">→</i></strong><span>{link[2]}</span><small class="action">Explore analysis →</small></a>
        {/each}
    </div>
    {#each groups as group}
        <section>
            <h3>{group.title}</h3>
            <div class="cards">
                {#each group.links.filter(link => !featured.some(item => item[1] === link[1])) as link}
                    <a href={link[1]}>
                        <strong>{link[0]} <i aria-hidden="true">→</i></strong>
                        <span>{link[2]}</span>
                    </a>
                {/each}
            </div>
        </section>
    {/each}
</nav>

<style>
    .insight-nav { margin: 1rem 0 2rem; }
    .featured { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; margin-bottom: 2rem; }
    section { margin-bottom: 1.5rem; }
    h3 { margin: 0 0 .75rem; color: #aab6c6; font-size: .9rem; font-weight: 650; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); gap: .75rem; }
    a { display: flex; flex-direction: column; gap: .5rem; padding: 1rem; border: 1px solid var(--dashboard-border); border-radius: .75rem; color: inherit; text-decoration: none; background: var(--dashboard-surface); }
    .featured a { min-height: 11rem; padding: 1.25rem; border-color: rgba(160, 174, 201, 0.3); border-top: 3px solid var(--dashboard-red); background: var(--dashboard-surface-raised); }
    .featured a:nth-child(2) { border-top-color: var(--dashboard-cyan); }
    .featured a:nth-child(3) { border-top-color: var(--dashboard-violet); }
    .featured small { color: #b9d5f5; font-size: .78rem; font-weight: 750; }
    .featured .topic { color: #bbc7d6; letter-spacing: .06em; text-transform: uppercase; }
    .featured .action { margin-top: auto; }
    strong { display: flex; justify-content: space-between; gap: .5rem; color: #f4f7fb; font-size: .95rem; line-height: 1.4; }
    strong i { color: #aab6c6; font-style: normal; }
    a > span { color: #bbc7d6; font-size: .85rem; line-height: 1.5; }
    a:hover { border-color: #64748b; background: #1b2230; }
    a:focus-visible { outline: 2px solid #9bc3ff; outline-offset: 3px; }
    @media (max-width: 700px) { .featured { grid-template-columns: 1fr; } }
</style>
