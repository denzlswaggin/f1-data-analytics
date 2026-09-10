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

<div class="insight-nav">
    {#each groups as group}
        <section>
            <h3>{group.title}</h3>
            <div class="cards">
                {#each group.links as link, index}
                    <a href={link[1]}>
                        <span class="index">0{index + 1}</span>
                        <strong>{link[0]} <i aria-hidden="true">→</i></strong>
                        <span>{link[2]}</span>
                    </a>
                {/each}
            </div>
        </section>
    {/each}
</div>

<style>
    .insight-nav { margin: 1rem 0 2rem; }
    section { margin-bottom: 2rem; }
    h3 { margin: 0 0 0.75rem; color: #9ba7ba; font-size: 0.75rem; font-weight: 760; text-transform: uppercase; letter-spacing: 0.12em; }
    .cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; }
    a { position: relative; display: flex; flex-direction: column; gap: 0.42rem; min-height: 8.2rem; padding: 1rem; overflow: hidden; border: 1px solid rgba(160, 174, 201, 0.18); border-radius: 0.85rem; color: inherit; text-decoration: none; background: linear-gradient(145deg, rgba(255,255,255,.055), rgba(255,255,255,.018)); transition: border-color 160ms ease, transform 160ms ease, background 160ms ease; }
    a::after { position: absolute; right: -1.4rem; bottom: -2rem; width: 5rem; height: 5rem; border: 1rem solid rgba(255,64,80,.06); border-radius: 50%; content: ''; }
    section:nth-child(2) a::after { border-color: rgba(50,211,244,.055); }
    section:nth-child(3) a::after { border-color: rgba(167,139,250,.06); }
    a:hover, a:focus-visible { border-color: rgba(255,64,80,.55); transform: translateY(-2px); background: linear-gradient(145deg, rgba(255,64,80,.1), rgba(255,255,255,.02)); outline: none; }
    section:nth-child(2) a:hover, section:nth-child(2) a:focus-visible { border-color: rgba(50,211,244,.5); background: linear-gradient(145deg, rgba(50,211,244,.09), rgba(255,255,255,.02)); }
    section:nth-child(3) a:hover, section:nth-child(3) a:focus-visible { border-color: rgba(167,139,250,.52); background: linear-gradient(145deg, rgba(167,139,250,.1), rgba(255,255,255,.02)); }
    strong { display: flex; justify-content: space-between; gap: .5rem; color: #f4f7fb; font-size: 0.96rem; line-height: 1.35; }
    strong i { color: #ff7180; font-style: normal; }
    a > span:last-child { color: #9ba7ba; font-size: 0.82rem; line-height: 1.45; }
    .index { color: #ff7180; font-family: ui-monospace, monospace; font-size: .68rem; font-weight: 780; letter-spacing: .08em; }
    section:nth-child(2) .index, section:nth-child(2) strong i { color: #52dcf6; }
    section:nth-child(3) .index, section:nth-child(3) strong i { color: #bda8fa; }
    @media (max-width: 1050px) { .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    @media (max-width: 560px) { .cards { grid-template-columns: 1fr; } a { min-height: 0; } }
    @media (prefers-reduced-motion: reduce) { a { transition: none; } }
</style>
