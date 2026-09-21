<script lang="ts">
	import type { PitVisit, ReplayDriver } from './types';
	import { formatClock } from './format';
	let {
		visit,
		visits,
		allVisits,
		drivers,
		time,
		watching,
		onwatch,
		oncontinue,
		onclose,
		onselect
	}: {
		visit: PitVisit;
		visits: PitVisit[];
		allVisits: PitVisit[];
		drivers: ReplayDriver[];
		time: number;
		watching: boolean;
		onwatch: () => void;
		oncontinue: () => void;
		onclose: () => void;
		onselect: (visit: PitVisit) => void;
	} = $props();
	const index = $derived(visits.findIndex((v) => v.id === visit.id));
	const visible = $derived([
		visit,
		...allVisits.filter(
			(v) => v.id !== visit.id && v.window && time >= v.window.start && time <= v.window.end
		)
	]);
	function progress(v: PitVisit) {
		return v.window
			? Math.max(
					0,
					Math.min(100, (100 * (time - v.window.start)) / (v.window.end - v.window.start))
				)
			: 0;
	}
	function phase(v: PitVisit) {
		return !v.window
			? 'Timing incomplete'
			: time < v.window.start
				? 'Before entry'
				: time > v.window.end
					? 'Exited'
					: 'In pit lane';
	}
</script>

<aside class="pit-inspector" aria-label="Pit stop inspector">
	<header>
		<div>
			<small>PIT VISIT · LAP {visit.lap}</small>
			<h2 tabindex="-1">{visit.driver} · {visit.tyreChange ? 'Tyre change' : 'Pit visit'}</h2>
		</div>
		<button onclick={onclose} aria-label="Close pit stop inspector">×</button>
	</header>
	<p class="evidence">
		{visit.source === 'recorded'
			? 'Recorded entry and exit'
			: visit.source === 'estimated'
				? 'Estimated timing from a stint transition'
				: 'Incomplete recorded timing'}{visit.source === 'incomplete' && visit.window
			? ' · estimated playback window'
			: ''}
	</p>
	<div class="facts">
		<div>
			<small>TYRES</small><strong
				>{visit.tyreChange
					? `${visit.fromCompound ?? 'Unknown'} → ${visit.toCompound ?? 'Unknown'}`
					: 'Change unconfirmed'}</strong
			>
		</div>
		<div>
			<small>TIME IN PIT LANE</small><strong
				>{visit.source === 'recorded' && visit.entry != null && visit.exit != null
					? `${(visit.exit - visit.entry).toFixed(1)} s`
					: 'Unavailable'}</strong
			>
		</div>
	</div>
	<p class="boundaries">
		Entry {visit.entry == null ? 'unavailable' : formatClock(visit.entry)} · Exit {visit.exit ==
		null
			? 'unavailable'
			: formatClock(visit.exit)}
	</p>
	<section class="inset" aria-label="Schematic pit lane">
		<div class="lane-head"><span>ENTRY →</span><span>→ EXIT</span></div>
		<div class="lane-list" role="region" aria-label="Cars in the schematic pit lane">
			{#each visible as v (v.id)}
				{@const driver = drivers.find((d) => d.code === v.driver)}
				<button
					class="lane-row"
					onclick={() => onselect(v)}
					aria-label={`Inspect ${v.driver} pit visit, lap ${v.lap}`}
					style={`--team:${driver?.color ?? '#94a3b8'}`}
				>
					<span class="lane-label"><strong>{v.driver}</strong><small>{phase(v)}</small></span>
					<span class="lane"
						><span class="car" style={`left:${progress(v)}%`}>{v.driver}</span></span
					>
				</button>
			{/each}
		</div>
		<p>
			Schematic travel, not garage positions. Movement between entry and exit is animated;
			stationary service time is unavailable.
		</p>
	</section>
	<div class="actions">
		<button class="watch" disabled={!visit.window} onclick={onwatch}
			>{watching ? 'Replay stop' : 'Watch this stop'}</button
		><button onclick={oncontinue}>Continue race</button>
	</div>
	<p class="clip-note">
		1× · five seconds before entry to five seconds after exit · pauses at the end
	</p>
	<nav aria-label="Browse pit visits">
		<button disabled={index <= 0} onclick={() => onselect(visits[index - 1])}
			>← Previous visit</button
		><button
			disabled={index < 0 || index >= visits.length - 1}
			onclick={() => onselect(visits[index + 1])}>Next visit →</button
		>
	</nav>
</aside>

<style>
	.lane-list {
		max-height: 240px;
		overflow-y: auto;
		padding: 0 3px;
	}

	.pit-inspector {
		border: 1px solid #365666;
		border-radius: 14px;
		background: #101922;
		padding: 18px;
		color: #e8edf4;
		min-width: 0;
		margin: 14px 0;
	}
	header,
	.facts,
	.actions,
	nav,
	.lane-head,
	.lane-label {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		align-items: center;
	}
	header h2 {
		scroll-margin-top: 80px;
		font-size: 19px;
		margin: 6px 0;
	}
	small {
		font-size: 10px;
		letter-spacing: 0.04em;
		color: #aab8c8;
	}
	.evidence,
	.boundaries,
	.clip-note {
		font-size: 12px;
		color: #b5c6d7;
		line-height: 1.5;
	}
	.facts {
		align-items: start;
		padding: 12px 0;
	}
	.facts div {
		display: grid;
		gap: 6px;
	}
	.facts strong {
		font-size: 13px;
	}
	.inset {
		background: #080f16;
		border-radius: 10px;
		padding: 14px;
	}
	.lane-head {
		font-size: 10px;
		color: #69d5df;
	}
	.lane-row {
		display: block;
		width: 100%;
		background: transparent;
		border: 0;
		padding: 14px 0;
		text-align: left;
	}
	.lane-label {
		margin-bottom: 18px;
	}
	.lane-label strong {
		color: var(--team);
	}
	.lane {
		display: block;
		height: 5px;
		background: #344350;
		margin: 0 23px 10px;
		position: relative;
	}
	.car {
		position: absolute;
		top: -8px;
		transform: translateX(-50%);
		background: var(--team);
		color: #080f16;
		font-size: 10px;
		font-weight: 900;
		padding: 3px;
		border-radius: 4px;
	}
	.inset p {
		font-size: 11px;
		line-height: 1.5;
		color: #96a8bb;
		margin-bottom: 0;
	}
	button {
		min-height: 44px;
		border: 1px solid #394a5b;
		border-radius: 7px;
		padding: 8px 12px;
		background: #172532;
		color: #edf6ff;
		cursor: pointer;
	}
	button:disabled {
		opacity: 0.4;
		cursor: default;
	}
	button:focus-visible {
		outline: 2px solid #66e1ea;
		outline-offset: 3px;
	}
	.actions {
		margin-top: 14px;
	}
	.watch {
		background: #23525a;
	}
	.actions button,
	nav button {
		flex: 1;
	}
	nav {
		margin-top: 12px;
	}
	nav button {
		font-size: 12px;
	}
	.clip-note {
		font-size: 11px;
	}
</style>
