<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { resolve } from '$app/paths';
	import {
		buildDrivers,
		buildEvents,
		buildTrackPath,
		filterEvents,
		isInPitWindow,
		positionAtTrackProgress,
		sampleAt,
		timingAt
	} from './model';
	import { loadManifest, loadRace } from './data';
	import type {
		LoadedRace,
		RadioRow,
		ReplayDriver,
		ReplayEvent,
		ReplayManifest,
		RaceSummary,
		TrackPath,
		TimingRow
	} from './types';

	const SPEEDS = [1, 2, 4, 6, 12, 24, 48];
	const PAD = 44;
	let manifest = $state<ReplayManifest | null>(null);
	let selectedSeason = $state(0),
		selectedRaceKey = $state('');
	let loaded = $state<LoadedRace | null>(null),
		loading = $state(true),
		loadError = $state('');
	let playing = $state(false),
		currentTime = $state(0),
		speed = $state(6);
	let selectedCode = $state(''),
		leaderboard = $state<TimingRow[]>([]);
	let drivers = $state<ReplayDriver[]>([]),
		allEvents = $state<ReplayEvent[]>([]);
	let eventFilter = $state('all'),
		nowPlaying = $state<ReplayEvent | null>(null),
		audioError = $state('');
	let hovered = $state<ScreenCar | null>(null),
		dragging = $state(false);
	let view = $state({ zoom: 1, ox: 0, oy: 0 });
	let root: HTMLElement;
	let canvas: HTMLCanvasElement = $state()!;
	let audio: HTMLAudioElement = $state()!;
	let context: CanvasRenderingContext2D | null = null,
		canvasWidth = $state(800),
		canvasHeight = 500;
	let replayTime = 0,
		duration = $state(0),
		animationFrame = 0,
		previousFrame = 0,
		previousUi = -Infinity;
	let abortController: AbortController | null = null,
		resizeObserver: ResizeObserver | null = null,
		bounds: Bounds | null = null;
	let trackPoints: { x: number; y: number }[] = [],
		screenCars: ScreenCar[] = [];
	let trackPath: TrackPath | null = null;
	let dragStart: [number, number] = [0, 0],
		dragMoved = false;
	type Bounds = { minX: number; maxX: number; minY: number; maxY: number };
	type ScreenCar = {
		code: string;
		name: string;
		team: string;
		color: string;
		x: number;
		y: number;
		order: number | null;
		gap: number | null;
		ahead: number | null;
	};

	let seasons = $derived([...new Set(manifest?.races.map((race) => race.season) ?? [])]);
	let seasonRaces = $derived(
		manifest?.races.filter((race) => race.season === selectedSeason) ?? []
	);
	let selectedSummary = $derived(
		manifest?.races.find((race) => race.key === selectedRaceKey) ?? null
	);
	let selectedDriver = $derived(leaderboard.find((driver) => driver.code === selectedCode) ?? null);
	let filteredEvents = $derived(filterEvents(allEvents, selectedCode, eventFilter));
	let nearbyEvents = $derived(
		[...filteredEvents]
			.sort((a, b) => Math.abs(a.time - currentTime) - Math.abs(b.time - currentTime))
			.slice(0, 8)
			.sort((a, b) => a.time - b.time)
	);
	let recentMessages = $derived(
		allEvents
			.filter((event) => event.type === 'control' && event.time <= currentTime)
			.slice(-5)
			.reverse()
	);
	let totalLaps = $derived(
		Math.max(0, ...(loaded?.bundle.laps.map((lap) => lap.lap_number) ?? []))
	);
	let currentLap = $derived(Math.max(0, ...leaderboard.map((driver) => driver.lap ?? 0)));
	let racePhase = $derived(
		currentTime >= duration && duration > 0
			? 'Finished'
			: recentMessages[0]?.subtype === 'red'
				? 'Red flag'
				: recentMessages[0]?.subtype === 'safety'
					? 'Safety car'
					: playing
						? 'Replay running'
						: currentTime > 0
							? 'Paused'
							: 'Ready'
	);

	onMount(() => {
		resizeObserver = new ResizeObserver(resizeCanvas);
		window.addEventListener('keydown', onKeyDown);
		animationFrame = requestAnimationFrame(loop);
		void initialise();
		return () => {
			abortController?.abort();
			resizeObserver?.disconnect();
			canvas?.removeEventListener('wheel', onWheel);
			window.removeEventListener('keydown', onKeyDown);
			cancelAnimationFrame(animationFrame);
		};
	});

	async function initialise() {
		try {
			manifest = await loadManifest();
			const initial =
				manifest.races.find((r) => r.key === manifest?.default_race) ?? manifest.races[0];
			selectedSeason = initial.season;
			selectedRaceKey = initial.key;
			await selectRace(initial);
		} catch (error) {
			loading = false;
			loadError = error instanceof Error ? error.message : 'The replay could not be loaded.';
		}
	}
	async function selectRace(summary: RaceSummary) {
		abortController?.abort();
		const controller = new AbortController();
		abortController = controller;
		resizeObserver?.disconnect();
		loading = true;
		loadError = '';
		playing = false;
		stopRadio();
		try {
			const race = await loadRace(summary, controller.signal);
			loaded = race;
			drivers = buildDrivers(race.positions, race.bundle.drivers, race.bundle.laps);
			allEvents = buildEvents(
				race.bundle.race_control,
				race.bundle.overtakes,
				race.bundle.radio,
				race.bundle.laps
			);
			duration = Math.max(summary.duration_s, ...drivers.map((d) => d.tmax));
			replayTime = 0;
			currentTime = 0;
			selectedCode = '';
			eventFilter = 'all';
			leaderboard = timingAt(drivers, 0);
			buildTrack();
			resetView();
			loading = false;
			await tick();
			setupCanvas();
			draw();
		} catch (error) {
			if (error instanceof DOMException && error.name === 'AbortError') return;
			loadError = error instanceof Error ? error.message : 'The replay could not be loaded.';
			loaded = null;
			drivers = [];
			leaderboard = [];
		} finally {
			if (abortController === controller) loading = false;
		}
	}

	function setupCanvas() {
		if (!(canvas instanceof HTMLCanvasElement)) return;
		resizeObserver?.disconnect();
		resizeObserver?.observe(canvas);
		canvas.removeEventListener('wheel', onWheel);
		canvas.addEventListener('wheel', onWheel, { passive: false });
		context = canvas.getContext('2d');
		resizeCanvas();
	}
	function chooseSeason(event: Event) {
		selectedSeason = Number((event.currentTarget as HTMLSelectElement).value);
		const next = manifest?.races.find((r) => r.season === selectedSeason);
		if (next) {
			selectedRaceKey = next.key;
			void selectRace(next);
		}
	}
	function chooseRace(event: Event) {
		selectedRaceKey = (event.currentTarget as HTMLSelectElement).value;
		const next = manifest?.races.find((r) => r.key === selectedRaceKey);
		if (next) void selectRace(next);
	}
	function buildTrack() {
		trackPath = buildTrackPath(drivers);
		if (!trackPath) {
			bounds = null;
			trackPoints = [];
			return;
		}
		trackPoints = trackPath.points;
		let minX = Infinity,
			maxX = -Infinity,
			minY = Infinity,
			maxY = -Infinity;
		for (const point of trackPoints) {
			minX = Math.min(minX, point.x);
			maxX = Math.max(maxX, point.x);
			minY = Math.min(minY, point.y);
			maxY = Math.max(maxY, point.y);
		}
		bounds = { minX, maxX, minY, maxY };
	}
	function displaySample(driver: ReplayDriver, time: number) {
		const sample = sampleAt(driver, time);
		if (!sample || !trackPath || sample.lapProgress == null || isInPitWindow(driver, time))
			return sample;
		return { ...sample, ...positionAtTrackProgress(trackPath, sample.lapProgress) };
	}
	function resizeCanvas() {
		const rect = canvas.getBoundingClientRect(),
			ratio = Math.min(window.devicePixelRatio || 1, 2);
		canvasWidth = Math.max(280, rect.width);
		canvasHeight = Math.max(340, rect.height);
		canvas.width = Math.round(canvasWidth * ratio);
		canvas.height = Math.round(canvasHeight * ratio);
		context = canvas.getContext('2d');
		context?.setTransform(ratio, 0, 0, ratio, 0, 0);
		resetView();
		draw();
	}
	function baseScale() {
		if (!bounds) return 1;
		return Math.min(
			(canvasWidth - PAD * 2) / (bounds.maxX - bounds.minX || 1),
			(canvasHeight - PAD * 2) / (bounds.maxY - bounds.minY || 1)
		);
	}
	function resetView() {
		if (!bounds) return;
		const scale = baseScale();
		view = {
			zoom: 1,
			ox: (canvasWidth - (bounds.maxX - bounds.minX) * scale) / 2,
			oy: (canvasHeight - (bounds.maxY - bounds.minY) * scale) / 2
		};
		draw();
	}
	function screenX(x: number) {
		return view.ox + (x - Number(bounds?.minX)) * baseScale() * view.zoom;
	}
	function screenY(y: number) {
		return view.oy + (Number(bounds?.maxY) - y) * baseScale() * view.zoom;
	}
	function centerFollowed() {
		if (!selectedCode || view.zoom <= 1 || !bounds) return;
		const driver = drivers.find((d) => d.code === selectedCode),
			sample = driver ? displaySample(driver, replayTime) : null;
		if (!sample) return;
		const scale = baseScale() * view.zoom;
		view.ox = canvasWidth / 2 - (sample.x - bounds.minX) * scale;
		view.oy = canvasHeight / 2 - (bounds.maxY - sample.y) * scale;
	}
	function draw() {
		if (!context || !bounds) return;
		centerFollowed();
		context.clearRect(0, 0, canvasWidth, canvasHeight);
		context.lineJoin = 'round';
		context.lineCap = 'round';
		context.beginPath();
		trackPoints.forEach((p, i) =>
			i ? context?.lineTo(screenX(p.x), screenY(p.y)) : context?.moveTo(screenX(p.x), screenY(p.y))
		);
		context.lineWidth = Math.min(30, Math.max(12, baseScale() * view.zoom * 230));
		context.strokeStyle = 'rgba(0,0,0,.75)';
		context.stroke();
		context.lineWidth = Math.min(20, Math.max(7, baseScale() * view.zoom * 155));
		context.strokeStyle = '#535d6d';
		context.stroke();
		const cars: ScreenCar[] = [];
		for (const driver of drivers) {
			const sample = displaySample(driver, replayTime);
			if (!sample) continue;
			const x = screenX(sample.x),
				y = screenY(sample.y),
				selected = selectedCode === driver.code,
				dimmed = Boolean(selectedCode && !selected);
			context.globalAlpha = dimmed ? 0.2 : 1;
			context.beginPath();
			context.arc(x, y, selected ? 8 : 6, 0, Math.PI * 2);
			context.fillStyle = driver.color;
			context.fill();
			context.lineWidth = selected ? 3 : 1.5;
			context.strokeStyle = selected ? '#fff' : '#080a0e';
			context.stroke();
			if (!dimmed) {
				context.font = `${selected ? 800 : 700} 10px system-ui`;
				context.fillStyle = '#fff';
				context.strokeStyle = '#080a0e';
				context.lineWidth = 3;
				context.strokeText(driver.code, x + 10, y + 4);
				context.fillText(driver.code, x + 10, y + 4);
			}
			context.globalAlpha = 1;
			cars.push({
				code: driver.code,
				name: driver.name,
				team: driver.team,
				color: driver.color,
				x,
				y,
				order: sample.order,
				gap: sample.gap,
				ahead: sample.ahead
			});
		}
		screenCars = cars;
		const pass = loaded?.bundle.overtakes.find(
			(p) =>
				replayTime - p.t_s >= -0.6 &&
				replayTime - p.t_s <= 2 &&
				(!selectedCode || p.passer_code === selectedCode || p.passed_code === selectedCode)
		);
		if (pass) {
			const a = cars.find((c) => c.code === pass.passer_code),
				b = cars.find((c) => c.code === pass.passed_code);
			if (a && b) {
				context.strokeStyle = '#46d49a';
				context.lineWidth = 2;
				context.beginPath();
				context.moveTo(a.x, a.y);
				context.lineTo(b.x, b.y);
				context.stroke();
				context.beginPath();
				context.arc(a.x, a.y, 14, 0, Math.PI * 2);
				context.stroke();
			}
		}
	}
	function loop(timestamp: number) {
		if (!previousFrame) previousFrame = timestamp;
		if (playing) {
			replayTime = Math.min(duration, replayTime + ((timestamp - previousFrame) / 1000) * speed);
			if (replayTime >= duration) playing = false;
		}
		previousFrame = timestamp;
		draw();
		if (timestamp - previousUi >= 66) {
			currentTime = replayTime;
			leaderboard = timingAt(drivers, replayTime);
			previousUi = timestamp;
		}
		animationFrame = requestAnimationFrame(loop);
	}
	function seek(time: number) {
		replayTime = Math.max(0, Math.min(duration, time));
		currentTime = replayTime;
		leaderboard = timingAt(drivers, replayTime);
		draw();
	}
	function togglePlayback() {
		if (replayTime >= duration) seek(0);
		playing = !playing;
	}
	function toggleDriver(code: string) {
		selectedCode = selectedCode === code ? '' : code;
		if (selectedCode && eventFilter === 'control') eventFilter = 'all';
		draw();
	}
	function jumpLap(direction: number) {
		const starts = [...new Set(loaded?.bundle.laps.map((lap) => lap.lap_start_t_s) ?? [])].sort(
			(a, b) => a - b
		);
		if (!starts.length) return;
		const index = Math.max(
			0,
			starts.findLastIndex((s) => s <= replayTime + 0.5)
		);
		seek(starts[Math.max(0, Math.min(starts.length - 1, index + direction))]);
	}
	function followDriver() {
		if (!selectedCode) return;
		view.zoom = view.zoom > 1 ? 1 : 2.6;
		if (view.zoom === 1) resetView();
		draw();
	}
	function toggleFullscreen() {
		if (document.fullscreenElement) void document.exitFullscreen();
		else void root.requestFullscreen();
	}
	function onKeyDown(event: KeyboardEvent) {
		const tag = (event.target as HTMLElement)?.tagName?.toLowerCase();
		if (['input', 'select', 'textarea', 'button', 'a', 'audio'].includes(tag)) return;
		if (event.code === 'Space') togglePlayback();
		else if (event.key === 'ArrowLeft') seek(replayTime - 5);
		else if (event.key === 'ArrowRight') seek(replayTime + 5);
		else return;
		event.preventDefault();
	}
	function localPoint(event: PointerEvent | WheelEvent): [number, number] {
		const r = canvas.getBoundingClientRect();
		return [event.clientX - r.left, event.clientY - r.top];
	}
	function nearest(x: number, y: number) {
		let closest: ScreenCar | null = null,
			distance = 18 ** 2;
		for (const car of screenCars) {
			const d = (car.x - x) ** 2 + (car.y - y) ** 2;
			if (d < distance) {
				closest = car;
				distance = d;
			}
		}
		return closest;
	}
	function onPointerDown(event: PointerEvent) {
		canvas.setPointerCapture(event.pointerId);
		dragging = true;
		dragMoved = false;
		dragStart = localPoint(event);
	}
	function onPointerMove(event: PointerEvent) {
		const point = localPoint(event);
		if (dragging) {
			if (Math.abs(point[0] - dragStart[0]) > 3 || Math.abs(point[1] - dragStart[1]) > 3)
				dragMoved = true;
			view.ox += point[0] - dragStart[0];
			view.oy += point[1] - dragStart[1];
			dragStart = point;
			draw();
		} else hovered = nearest(...point);
	}
	function onPointerUp(event: PointerEvent) {
		if (!dragMoved) {
			const car = nearest(...localPoint(event));
			if (car) toggleDriver(car.code);
			else if (selectedCode) toggleDriver(selectedCode);
		}
		dragging = false;
	}
	function onWheel(event: WheelEvent) {
		event.preventDefault();
		const [x, y] = localPoint(event),
			zoom = Math.min(8, Math.max(1, view.zoom * (event.deltaY < 0 ? 1.12 : 1 / 1.12))),
			ratio = zoom / view.zoom;
		view = { zoom, ox: x - (x - view.ox) * ratio, oy: y - (y - view.oy) * ratio };
		draw();
	}
	async function playRadio(event: ReplayEvent) {
		if (event.type !== 'radio') return;
		const clip = event.raw as RadioRow;
		seek(event.time);
		speed = 1;
		nowPlaying = event;
		audioError = '';
		await tick();
		audio.pause();
		audio.src = clip.recording_url;
		audio.load();
		try {
			await audio.play();
			playing = true;
		} catch {
			audioError = 'Playback was blocked. Press play in the audio controls to retry.';
		}
	}
	function activateEvent(event: ReplayEvent) {
		if (event.type === 'radio') void playRadio(event);
		else seek(event.time);
	}
	function stopRadio() {
		if (audio?.src) {
			audio.pause();
			audio.removeAttribute('src');
			audio.load();
		}
		nowPlaying = null;
		audioError = '';
	}
	function formatClock(seconds: number) {
		const value = Math.max(0, Math.floor(seconds || 0)),
			hours = Math.floor(value / 3600),
			minutes = Math.floor((value % 3600) / 60),
			secs = value % 60;
		return hours
			? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
			: `${minutes}:${String(secs).padStart(2, '0')}`;
	}
	function formatGap(value: number | null, leader = false) {
		if (value == null) return '—';
		if (value <= 0) return leader ? 'LEADER' : '—';
		return `+${value.toFixed(3)}`;
	}
	function compoundCode(value: string | null) {
		return value ? value[0].toUpperCase() : '—';
	}
	function currentLapTime(driver: TimingRow | null) {
		if (!driver || !loaded) return null;
		return loaded.bundle.laps.find(
			(lap) => lap.driver_code === driver.code && lap.lap_number === driver.lap
		)?.lap_time_sec;
	}
	function formatDate(value: string | null | undefined) {
		if (!value) return 'unknown';
		return new Intl.DateTimeFormat('en-GB', {
			day: '2-digit',
			month: 'short',
			year: 'numeric'
		}).format(new Date(value));
	}
</script>

<div class="app-shell" bind:this={root}>
	<header class="topbar">
		<a class="brand" href={resolve('/')} aria-label="F1 Analytics home"
			><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><span
				><strong>F1</strong> ANALYTICS</span
			></a
		>
		<nav aria-label="Primary navigation"><a href="#replay">Race replay</a></nav>
		<div class="snapshot">
			<span></span> Snapshot · {formatDate(manifest?.snapshot.generated_at)}
		</div>
	</header>
	<main id="replay">
		<section class="session-bar" aria-label="Race selection and status">
			<div class="event-title">
				<span class="round">R{selectedSummary?.round ?? '—'}</span>
				<div>
					<p>{selectedSummary?.season ?? '—'} FIA Formula One World Championship</p>
					<h1>{selectedSummary?.race_name ?? 'Race replay'}</h1>
				</div>
			</div>
			<div class="session-facts">
				<div><span>SESSION</span><strong>Race</strong></div>
				<div><span>LAP</span><strong>{currentLap || '—'}<em>/ {totalLaps || '—'}</em></strong></div>
				<div><span>TIME</span><strong>{formatClock(currentTime)}</strong></div>
				<div>
					<span>STATUS</span><strong class:green={racePhase !== 'Red flag'}
						><i></i>{racePhase}</strong
					>
				</div>
			</div>
			<div class="race-picker">
				<label
					>Season<select value={selectedSeason} onchange={chooseSeason} disabled={!manifest}
						>{#each seasons as season (season)}<option value={season}>{season}</option
							>{/each}</select
					></label
				><label
					>Race<select value={selectedRaceKey} onchange={chooseRace} disabled={!manifest}
						>{#each seasonRaces as race (race.key)}<option value={race.key}
								>R{race.round} · {race.race_name.replace(' Grand Prix', '')}</option
							>{/each}</select
					></label
				>
			</div>
		</section>
		{#if loading}<section class="state-card" aria-live="polite">
				<span class="spinner"></span><strong>Loading race replay</strong>
				<p>Preparing timing, circuit positions and race events…</p>
			</section>
		{:else if loadError}<section class="state-card error" role="alert">
				<strong>Replay unavailable</strong>
				<p>{loadError}</p>
				{#if selectedSummary}<button type="button" onclick={() => selectRace(selectedSummary!)}
						>Retry</button
					>{/if}
			</section>
		{:else if loaded}
			<section class="replay-grid">
				<aside id="drivers" class="timing-panel panel" aria-label="Live timing">
					<div class="panel-head">
						<div><span>LIVE TIMING</span><strong>Race order</strong></div>
						<b>GAP</b>
					</div>
					<ol>
						{#each leaderboard as driver (driver.code)}<li
								class:selected={selectedCode === driver.code}
								class:dimmed={Boolean(selectedCode && selectedCode !== driver.code)}
							>
								<button
									type="button"
									onclick={() => toggleDriver(driver.code)}
									aria-pressed={selectedCode === driver.code}
									><span class="position">{driver.order}</span><span
										class="team-line"
										style={`--team:${driver.color}`}
									></span><span class="driver"
										><strong>{driver.code}</strong><small>{driver.team}</small></span
									><span class="tyre {compoundCode(driver.compound).toLowerCase()}"
										>{compoundCode(driver.compound)}</span
									><span class="gap">{formatGap(driver.gap, true)}</span></button
								>
							</li>{/each}
					</ol>
					<div class="tower-footer">
						<span>{leaderboard.length} drivers</span><span>{racePhase}</span>
					</div>
				</aside>
				<section class="track-panel panel" aria-label="Circuit map">
					<div class="track-meta">
						<div><span>CIRCUIT VIEW</span><strong>{loaded.bundle.race.circuit_name}</strong></div>
						<div class="track-actions">
							<button type="button" onclick={followDriver} disabled={!selectedCode}
								>{view.zoom > 1 ? 'Release camera' : 'Follow driver'}</button
							><button type="button" onclick={resetView}>Reset view</button><button
								type="button"
								onclick={toggleFullscreen}>Fullscreen</button
							>
						</div>
					</div>
					<div class="circuit">
						<canvas
							aria-label="Animated circuit map. Select cars from the timing tower or directly on the circuit."
							onpointerdown={onPointerDown}
							onpointermove={onPointerMove}
							onpointerup={onPointerUp}
							onpointerleave={() => {
								dragging = false;
								hovered = null;
							}}
							class:dragging
							bind:this={canvas}
						></canvas>{#if hovered}<div
								class="tooltip"
								style={`left:${Math.min(canvasWidth - 155, hovered.x + 14)}px;top:${Math.max(55, hovered.y - 45)}px`}
							>
								<strong><i style={`background:${hovered.color}`}></i>{hovered.name}</strong><span
									>P{hovered.order ?? '—'} · {hovered.team}</span
								><span>{formatGap(hovered.ahead, true)} interval</span>
							</div>{/if}
						<div class="map-help">Scroll to zoom · drag to pan · click a car to follow</div>
					</div>
					{#if recentMessages.length}<div class="race-control">
							<span>RACE CONTROL</span>{#each recentMessages as event (event.id)}<button
									type="button"
									onclick={() => seek(event.time)}
									><time>{formatClock(event.time)}</time><i class={event.subtype}></i><strong
										>{event.label}</strong
									></button
								>{/each}
						</div>{/if}
				</section>
				<aside id="strategy" class="driver-panel panel" aria-label="Selected driver detail">
					{#if selectedDriver}<div
							class="driver-accent"
							style={`--team:${selectedDriver.color}`}
						></div>
						<div class="selected-head">
							<div>
								<span>SELECTED DRIVER</span>
								<h2>{selectedDriver.name}</h2>
								<p>{selectedDriver.team} · {selectedDriver.code}</p>
							</div>
							<strong>P{selectedDriver.order}</strong>
						</div>
						<div class="status-row">
							<span><i></i>{selectedDriver.status}</span><strong
								>Lap {selectedDriver.lap ?? '—'} / {totalLaps}</strong
							>
						</div>
						<div class="metric-grid">
							<div>
								<span>INTERVAL</span><strong>{formatGap(selectedDriver.ahead, true)}</strong><small
									>to car ahead</small
								>
							</div>
							<div>
								<span>LEADER GAP</span><strong>{formatGap(selectedDriver.gap)}</strong><small
									>race time</small
								>
							</div>
							<div>
								<span>POSITIONS</span><strong class:gain={(selectedDriver.positionChange ?? 0) > 0}
									>{selectedDriver.positionChange == null
										? '—'
										: `${selectedDriver.positionChange > 0 ? '+' : ''}${selectedDriver.positionChange}`}</strong
								><small>from the grid</small>
							</div>
							<div>
								<span>LAP TIME</span><strong
									>{currentLapTime(selectedDriver)?.toFixed(3) ?? '—'}</strong
								><small>current recorded lap</small>
							</div>
						</div>
						<div class="stint-card">
							<span class="tyre-visual {compoundCode(selectedDriver.compound).toLowerCase()}"
								>{compoundCode(selectedDriver.compound)}</span
							>
							<div>
								<span>CURRENT STINT</span><strong
									>{selectedDriver.compound ?? 'Unknown compound'}</strong
								><small
									>{selectedDriver.tyreLife == null
										? 'Tyre age unavailable'
										: `${Math.round(selectedDriver.tyreLife)} laps on this set`}</small
								>
							</div>
							<div class="stops">
								<span>STOPS</span><strong>{selectedDriver.stops ?? '—'}</strong>
							</div>
						</div>
						<button
							class="clear-driver"
							type="button"
							onclick={() => toggleDriver(selectedDriver.code)}>Clear driver selection</button
						>{:else}<div class="driver-empty">
							<span>01</span>
							<h2>Select a driver</h2>
							<p>Choose a car to inspect its live race state and filter radio and overtakes.</p>
						</div>{/if}
				</aside>
			</section>
			<section class="control-deck panel" aria-label="Replay controls">
				<div class="playback">
					<button
						class="play"
						type="button"
						onclick={togglePlayback}
						aria-label={playing ? 'Pause replay' : 'Play replay'}>{playing ? 'Ⅱ' : '▶'}</button
					><button type="button" onclick={() => seek(replayTime - 5)}>−5s</button><button
						type="button"
						onclick={() => seek(replayTime + 5)}>+5s</button
					><strong>{formatClock(currentTime)}</strong>
				</div>
				<div class="scrubber">
					<input
						aria-label="Replay time"
						type="range"
						min="0"
						max={duration}
						step="0.5"
						value={currentTime}
						oninput={(event) => seek(Number(event.currentTarget.value))}
					/>
					<div class="ticks">
						<span>START</span><span>{formatClock(duration / 2)}</span><span>FINISH</span>
					</div>
				</div>
				<div class="lap-controls">
					<button type="button" onclick={() => jumpLap(-1)}>← Lap</button><button
						type="button"
						onclick={() => jumpLap(1)}>Lap →</button
					>
				</div>
				<label class="speed-control"
					>SPEED<select bind:value={speed}
						>{#each SPEEDS as option (option)}<option value={option}>{option}×</option
							>{/each}</select
					></label
				>
			</section>
			<section class="timeline panel" aria-label="Race intelligence timeline">
				<div class="timeline-head">
					<div>
						<span>RACE INTELLIGENCE</span>
						<h2>Event timeline</h2>
					</div>
					{#if selectedCode}<p>
							Showing pit stops, radio & overtakes for <strong>{selectedCode}</strong><button
								type="button"
								onclick={() => toggleDriver(selectedCode)}>Clear</button
							>
						</p>{/if}
				</div>
				<div class="filters" aria-label="Filter race events">
					{#each ['all', 'control', 'overtake', 'pit', 'radio'] as filter (filter)}{#if !selectedCode || filter !== 'control'}<button
								type="button"
								class:active={eventFilter === filter}
								onclick={() => (eventFilter = filter)}
								>{filter === 'all'
									? 'All events'
									: filter === 'control'
										? 'Race control'
										: filter === 'overtake'
											? 'Overtakes'
											: filter === 'pit'
												? 'Pit stops'
												: 'Radio'}<span>{filterEvents(allEvents, selectedCode, filter).length}</span
								></button
							>{/if}{/each}
				</div>
				<div class="event-rail">
					<button
						type="button"
						aria-label="Seek on event timeline"
						onclick={(event) => {
							const r = event.currentTarget.getBoundingClientRect();
							seek(((event.clientX - r.left) / r.width) * duration);
						}}
						><span class="elapsed" style={`width:${duration ? (currentTime / duration) * 100 : 0}%`}
						></span><i
							class="playhead"
							style={`left:${duration ? (currentTime / duration) * 100 : 0}%`}
						></i></button
					>
					<div class="markers">
						{#each filteredEvents as event (event.id)}<button
								type="button"
								class={event.type}
								class:past={event.time <= currentTime}
								style={`left:${duration ? (event.time / duration) * 100 : 0}%`}
								title={`${formatClock(event.time)} · ${event.label}`}
								onclick={() => activateEvent(event)}
							></button>{/each}
					</div>
				</div>
				<div class="event-list">
					{#if nearbyEvents.length}{#each nearbyEvents as event (event.id)}<button
								class="event {event.type}"
								class:current={Math.abs(event.time - currentTime) < 4}
								type="button"
								onclick={() => activateEvent(event)}
								><i></i><time>{formatClock(event.time)}</time><span
									><strong>{event.label}</strong><small>{event.meta}</small></span
								>{#if event.type === 'radio'}<b>LISTEN</b>{/if}</button
							>{/each}{:else}<p class="empty-state">
							No events are available for this selection.
						</p>{/if}
				</div>
				<div class="radio-player" class:visible={Boolean(nowPlaying)}>
					<div>
						<span>TEAM RADIO</span><strong>{nowPlaying?.meta ?? 'Select a radio event'}</strong
						>{#if audioError}<small role="alert">{audioError}</small>{/if}
					</div>
					<audio
						bind:this={audio}
						controls
						preload="none"
						onerror={() =>
							nowPlaying && (audioError = 'The source could not load this radio clip.')}
					></audio><button type="button" aria-label="Close radio player" onclick={stopRadio}
						>×</button
					>
				</div>
			</section>
			<footer>
				<p>
					Immutable snapshot {manifest?.snapshot.version} · only this race's position feed was loaded
				</p>
				<div>
					<span>{loaded.summary.driver_count} drivers</span><span
						>{loaded.bundle.overtakes.length} passes</span
					><span>{loaded.bundle.radio.length} radio clips</span>
				</div>
			</footer>
		{/if}
	</main>
</div>

<style>
	.app-shell {
		min-height: 100vh;
	}
	.app-shell:fullscreen {
		overflow: auto;
		background: var(--bg);
	}
	.topbar {
		position: sticky;
		z-index: 20;
		top: 0;
		display: flex;
		align-items: center;
		gap: 42px;
		height: 58px;
		padding: 0 24px;
		background: rgba(8, 10, 14, 0.9);
		border-bottom: 1px solid var(--line);
		backdrop-filter: blur(14px);
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		color: var(--text);
		font-size: 12px;
		font-weight: 760;
		letter-spacing: 0.16em;
		text-decoration: none;
	}
	.brand strong {
		color: var(--accent);
	}
	.brand-mark {
		display: grid;
		gap: 2px;
		width: 25px;
		transform: skewX(-18deg);
	}
	.brand-mark i {
		display: block;
		height: 3px;
		background: var(--accent);
		border-radius: 1px;
	}
	.brand-mark i:nth-child(2) {
		width: 18px;
	}
	.brand-mark i:nth-child(3) {
		width: 11px;
	}
	nav {
		align-self: stretch;
	}
	nav a {
		position: relative;
		display: grid;
		place-items: center;
		height: 100%;
		color: var(--text);
		font-size: 11px;
		font-weight: 650;
		text-decoration: none;
	}
	nav a:after {
		position: absolute;
		inset: auto 0 -1px;
		height: 2px;
		background: var(--accent);
		content: '';
	}
	.snapshot {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-left: auto;
		color: var(--muted);
		font-size: 10px;
	}
	.snapshot > span {
		width: 7px;
		height: 7px;
		background: var(--green);
		border-radius: 50%;
	}
	main {
		width: min(1760px, 100%);
		margin: auto;
		padding: 18px 22px 12px;
	}
	.panel,
	.session-bar,
	.state-card {
		background: linear-gradient(145deg, rgba(20, 25, 34, 0.96), rgba(11, 14, 20, 0.98));
		border: 1px solid var(--line);
		border-radius: var(--radius);
		box-shadow: 0 18px 50px rgba(0, 0, 0, 0.18);
	}
	.session-bar {
		display: flex;
		align-items: center;
		min-height: 68px;
		margin-bottom: 12px;
		padding: 7px 16px;
	}
	.event-title {
		display: flex;
		align-items: center;
		gap: 13px;
		min-width: 330px;
	}
	.round {
		display: grid;
		place-items: center;
		width: 38px;
		height: 38px;
		color: #fff;
		background: var(--accent);
		border-radius: 8px;
		font-size: 11px;
		font-weight: 800;
	}
	.event-title p,
	.event-title h1 {
		margin: 0;
	}
	.event-title p {
		color: var(--muted);
		font-size: 8px;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.event-title h1 {
		margin-top: 3px;
		font-size: 18px;
	}
	.session-facts {
		display: flex;
		gap: 24px;
		margin-left: auto;
	}
	.session-facts div {
		min-width: 60px;
	}
	.session-facts span,
	.panel-head span,
	.track-meta span,
	.selected-head span,
	.metric-grid span,
	.stint-card > div > span,
	.timeline-head span,
	.radio-player span {
		display: block;
		color: var(--muted);
		font-size: 8px;
		font-weight: 750;
		letter-spacing: 0.12em;
	}
	.session-facts strong {
		display: block;
		margin-top: 5px;
		font-size: 11px;
	}
	.session-facts em {
		color: var(--muted);
		font-size: 8px;
		font-style: normal;
	}
	.session-facts .green {
		color: var(--green);
	}
	.session-facts i,
	.status-row i {
		display: inline-block;
		width: 6px;
		height: 6px;
		margin-right: 4px;
		background: currentColor;
		border-radius: 50%;
	}
	.race-picker {
		display: flex;
		gap: 6px;
		margin-left: 24px;
	}
	.race-picker label {
		color: var(--muted);
		font-size: 7px;
	}
	.race-picker select {
		display: block;
		max-width: 180px;
		margin-top: 3px;
		padding: 6px;
		color: #fff;
		background: #151a22;
		border: 1px solid var(--line);
		border-radius: 6px;
		font-size: 9px;
	}
	.state-card {
		display: grid;
		place-items: center;
		min-height: 420px;
		padding: 30px;
		text-align: center;
	}
	.state-card p {
		color: var(--muted);
		font-size: 11px;
	}
	.state-card button {
		padding: 8px 14px;
		color: #fff;
		background: var(--accent);
		border: 0;
		border-radius: 6px;
	}
	.spinner {
		width: 30px;
		height: 30px;
		border: 3px solid var(--line);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.replay-grid {
		display: grid;
		grid-template-columns: 238px minmax(460px, 1fr) 276px;
		gap: 12px;
		min-height: 540px;
	}
	.timing-panel,
	.driver-panel {
		overflow: hidden;
	}
	.panel-head {
		display: flex;
		align-items: end;
		justify-content: space-between;
		height: 59px;
		padding: 0 13px 11px;
		border-bottom: 1px solid var(--line);
	}
	.panel-head strong,
	.track-meta strong {
		display: block;
		margin-top: 5px;
		font-size: 13px;
	}
	.panel-head b {
		color: var(--muted);
		font-size: 8px;
	}
	.timing-panel ol {
		max-height: 470px;
		margin: 0;
		padding: 5px 0;
		overflow: auto;
		list-style: none;
	}
	.timing-panel li {
		transition:
			opacity 0.16s,
			background 0.16s;
	}
	.timing-panel li.selected {
		background: rgba(255, 255, 255, 0.075);
	}
	.timing-panel li.dimmed {
		opacity: 0.3;
	}
	.timing-panel li button {
		display: grid;
		grid-template-columns: 22px 3px 1fr 24px 56px;
		align-items: center;
		width: 100%;
		min-height: 43px;
		padding: 0 11px;
		color: inherit;
		background: transparent;
		border: 0;
		border-bottom: 1px solid rgba(255, 255, 255, 0.045);
		cursor: pointer;
		text-align: left;
	}
	.timing-panel li button:hover {
		background: rgba(255, 255, 255, 0.045);
	}
	.position {
		color: var(--muted);
		font-size: 11px;
		font-weight: 750;
	}
	.team-line {
		width: 3px;
		height: 24px;
		background: var(--team);
		border-radius: 3px;
	}
	.driver {
		min-width: 0;
		padding-left: 9px;
	}
	.driver strong {
		display: block;
		font-size: 12px;
	}
	.driver small {
		display: block;
		overflow: hidden;
		margin-top: 3px;
		color: var(--muted);
		font-size: 7px;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.tyre,
	.tyre-visual {
		display: grid;
		place-items: center;
		flex: 0 0 auto;
		color: #fff;
		border: 2px solid #fff;
		border-radius: 50%;
		font-weight: 800;
		letter-spacing: 0;
		line-height: 1;
	}
	.tyre {
		width: 18px;
		height: 18px;
		font-size: 7px;
	}
	.tyre.m,
	.tyre-visual.m {
		color: var(--yellow);
		border-color: var(--yellow);
	}
	.tyre.s,
	.tyre-visual.s {
		color: var(--accent);
		border-color: var(--accent);
	}
	.tyre.i,
	.tyre-visual.i {
		color: var(--green);
		border-color: var(--green);
	}
	.tyre.w,
	.tyre-visual.w {
		color: var(--blue);
		border-color: var(--blue);
	}
	.gap {
		text-align: right;
		font:
			9px Consolas,
			monospace;
	}
	.tower-footer {
		display: flex;
		justify-content: space-between;
		padding: 10px 12px;
		color: var(--muted);
		font-size: 8px;
	}
	.track-panel {
		position: relative;
		min-width: 0;
		overflow: hidden;
	}
	.track-meta {
		position: absolute;
		z-index: 5;
		top: 15px;
		left: 17px;
		display: flex;
		width: calc(100% - 34px);
		pointer-events: none;
	}
	.track-actions {
		display: flex;
		gap: 5px;
		margin-left: auto;
		pointer-events: auto;
	}
	.track-actions button,
	.clear-driver {
		padding: 6px 9px;
		color: var(--muted-strong);
		background: rgba(20, 25, 34, 0.85);
		border: 1px solid var(--line);
		border-radius: 6px;
		font-size: 8px;
		cursor: pointer;
	}
	.track-actions button:disabled {
		opacity: 0.4;
	}
	.circuit {
		position: relative;
		height: 100%;
		min-height: 540px;
		background: radial-gradient(circle at 48% 48%, rgba(52, 65, 89, 0.15), transparent 55%);
	}
	.circuit:before {
		position: absolute;
		inset: 0;
		opacity: 0.28;
		background-image:
			linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
			linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px);
		background-size: 28px 28px;
		content: '';
		mask-image: radial-gradient(circle, #000, transparent 78%);
	}
	canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		cursor: grab;
		touch-action: none;
	}
	canvas.dragging {
		cursor: grabbing;
	}
	.tooltip {
		position: absolute;
		z-index: 6;
		display: grid;
		gap: 3px;
		width: 145px;
		padding: 8px 10px;
		color: var(--muted-strong);
		background: #171c25;
		border: 1px solid var(--line-strong);
		border-radius: 7px;
		box-shadow: 0 8px 25px #000;
		font-size: 8px;
		pointer-events: none;
	}
	.tooltip strong {
		color: #fff;
		font-size: 10px;
	}
	.tooltip i {
		display: inline-block;
		width: 6px;
		height: 6px;
		margin-right: 5px;
		border-radius: 50%;
	}
	.map-help {
		position: absolute;
		right: 12px;
		bottom: 9px;
		color: #5c6575;
		font-size: 7px;
	}
	.race-control {
		position: absolute;
		z-index: 4;
		top: 64px;
		left: 12px;
		width: min(230px, 40%);
		padding: 9px;
		background: rgba(8, 10, 14, 0.78);
		border: 1px solid var(--line);
		border-radius: 8px;
	}
	.race-control > span {
		color: var(--muted);
		font-size: 7px;
		font-weight: 800;
	}
	.race-control button {
		display: grid;
		grid-template-columns: 34px 6px 1fr;
		align-items: center;
		gap: 5px;
		width: 100%;
		padding: 5px 0;
		color: inherit;
		background: none;
		border: 0;
		cursor: pointer;
		text-align: left;
	}
	.race-control time {
		color: var(--muted);
		font: 7px Consolas;
	}
	.race-control i {
		width: 5px;
		height: 5px;
		background: var(--yellow);
		border-radius: 50%;
	}
	.race-control i.red {
		background: var(--accent);
	}
	.race-control i.green {
		background: var(--green);
	}
	.race-control i.safety {
		background: #f6a13c;
	}
	.race-control strong {
		overflow: hidden;
		font-size: 7px;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.driver-panel {
		position: relative;
	}
	.driver-accent {
		height: 3px;
		background: var(--team);
	}
	.selected-head {
		display: flex;
		justify-content: space-between;
		padding: 17px 16px 14px;
	}
	.selected-head h2 {
		margin: 7px 0 0;
		font-size: 18px;
	}
	.selected-head p {
		margin: 4px 0 0;
		color: var(--muted);
		font-size: 9px;
	}
	.selected-head > strong {
		display: grid;
		place-items: center;
		width: 45px;
		height: 45px;
		background: rgba(255, 255, 255, 0.06);
		border: 1px solid var(--line);
		border-radius: 9px;
		font-size: 17px;
	}
	.status-row {
		display: flex;
		justify-content: space-between;
		padding: 9px 16px;
		color: var(--muted-strong);
		background: rgba(255, 255, 255, 0.025);
		border-block: 1px solid var(--line);
		font-size: 8px;
		text-transform: uppercase;
	}
	.status-row strong {
		color: #e7eaf0;
	}
	.metric-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		padding: 16px;
	}
	.metric-grid div {
		min-height: 74px;
		padding: 10px 12px;
		border: 1px solid var(--line);
	}
	.metric-grid div:nth-child(even) {
		border-left: 0;
	}
	.metric-grid div:nth-child(n + 3) {
		border-top: 0;
	}
	.metric-grid strong {
		display: block;
		margin-top: 8px;
		font: 14px Consolas;
	}
	.metric-grid .gain {
		color: var(--green);
	}
	.metric-grid small {
		display: block;
		margin-top: 4px;
		color: #596273;
		font-size: 7px;
	}
	.stint-card {
		display: flex;
		align-items: center;
		gap: 10px;
		margin: 0 16px;
		padding: 12px;
		background: rgba(255, 255, 255, 0.035);
		border: 1px solid var(--line);
		border-radius: 9px;
	}
	.tyre-visual {
		width: 34px;
		height: 34px;
		border-width: 4px;
		font-size: 10px;
	}
	.stint-card strong {
		display: block;
		margin-top: 4px;
		font-size: 11px;
	}
	.stint-card small {
		display: block;
		margin-top: 3px;
		color: var(--muted);
		font-size: 7px;
	}
	.stops {
		margin-left: auto;
		padding-left: 12px;
		border-left: 1px solid var(--line);
		text-align: center;
	}
	.stops strong {
		font-size: 16px;
	}
	.clear-driver {
		display: block;
		margin: 13px auto;
	}
	.driver-empty {
		display: grid;
		place-items: center;
		align-content: center;
		min-height: 500px;
		padding: 25px;
		text-align: center;
	}
	.driver-empty > span {
		display: grid;
		place-items: center;
		width: 52px;
		height: 52px;
		color: #6e778a;
		border: 1px dashed #50586a;
		border-radius: 50%;
	}
	.driver-empty h2 {
		margin: 14px 0 0;
	}
	.driver-empty p {
		max-width: 220px;
		color: var(--muted);
		font-size: 10px;
		line-height: 1.55;
	}
	.control-deck {
		display: grid;
		grid-template-columns: auto 1fr auto auto;
		align-items: center;
		gap: 16px;
		min-height: 72px;
		margin-top: 12px;
		padding: 10px 14px;
	}
	.playback,
	.lap-controls {
		display: flex;
		align-items: center;
		gap: 5px;
	}
	.playback button,
	.lap-controls button {
		min-width: 34px;
		height: 32px;
		color: var(--muted-strong);
		background: #171c25;
		border: 1px solid var(--line);
		border-radius: 7px;
		font-size: 9px;
		cursor: pointer;
	}
	.playback .play {
		color: #fff;
		background: var(--accent);
		border-color: var(--accent);
	}
	.playback strong {
		min-width: 64px;
		margin-left: 7px;
		font: 12px Consolas;
	}
	.scrubber input {
		width: 100%;
		accent-color: var(--accent);
	}
	.ticks {
		display: flex;
		justify-content: space-between;
		color: #555f70;
		font-size: 6px;
	}
	.speed-control {
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--muted);
		font-size: 7px;
	}
	.speed-control select {
		padding: 7px;
		color: #fff;
		background: #171c25;
		border: 1px solid var(--line);
		border-radius: 7px;
		font-size: 9px;
	}
	.timeline {
		position: relative;
		margin-top: 12px;
		padding: 14px 16px;
	}
	.timeline-head {
		display: flex;
		align-items: end;
		justify-content: space-between;
	}
	.timeline-head h2 {
		margin: 4px 0 0;
		font-size: 13px;
	}
	.timeline-head p {
		margin: 0;
		color: var(--muted);
		font-size: 8px;
	}
	.timeline-head p strong {
		color: #fff;
	}
	.timeline-head p button {
		margin-left: 7px;
		color: var(--muted-strong);
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid var(--line);
		border-radius: 4px;
		font-size: 7px;
	}
	.filters {
		display: flex;
		gap: 5px;
		margin-top: 12px;
	}
	.filters button {
		padding: 6px 8px;
		color: var(--muted);
		background: rgba(255, 255, 255, 0.03);
		border: 1px solid var(--line);
		border-radius: 6px;
		font-size: 8px;
	}
	.filters button.active {
		color: #fff;
		background: #293142;
	}
	.filters span {
		margin-left: 5px;
	}
	.event-rail {
		position: relative;
		margin: 18px 2px 8px;
	}
	.event-rail > button {
		position: relative;
		width: 100%;
		height: 8px;
		padding: 0;
		background: #292e39;
		border: 0;
		border-radius: 4px;
	}
	.elapsed {
		position: absolute;
		inset: 0 auto 0 0;
		background: #677691;
		border-radius: inherit;
	}
	.playhead {
		position: absolute;
		top: 50%;
		width: 3px;
		height: 23px;
		background: #fff;
		transform: translate(-50%, -50%);
	}
	.markers {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}
	.markers button {
		position: absolute;
		top: 50%;
		width: 8px;
		height: 14px;
		padding: 0;
		background: #11151c;
		border: 2px solid var(--yellow);
		border-radius: 3px;
		pointer-events: auto;
		transform: translate(-50%, -50%);
	}
	.markers .overtake {
		border-color: var(--blue);
		border-radius: 50%;
	}
	.markers .pit {
		border-color: var(--accent);
		transform: translate(-50%, -50%) rotate(45deg);
	}
	.markers .radio {
		height: 17px;
		border-color: var(--purple);
		border-radius: 5px;
	}
	.markers .past {
		background: currentColor;
	}
	.event-list {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 7px;
		margin-top: 16px;
	}
	.event {
		display: grid;
		grid-template-columns: 7px 48px 1fr auto;
		align-items: center;
		min-width: 0;
		padding: 9px;
		color: inherit;
		background: rgba(255, 255, 255, 0.025);
		border: 1px solid var(--line);
		border-radius: 7px;
		text-align: left;
	}
	.event:hover,
	.event.current {
		background: rgba(255, 255, 255, 0.065);
	}
	.event > i {
		width: 6px;
		height: 6px;
		background: var(--yellow);
		border-radius: 50%;
	}
	.event.overtake > i {
		background: var(--blue);
	}
	.event.pit > i {
		background: var(--accent);
	}
	.event.radio > i {
		background: var(--purple);
	}
	.event time {
		color: var(--muted);
		font: 8px Consolas;
	}
	.event > span {
		min-width: 0;
	}
	.event strong,
	.event small {
		display: block;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.event strong {
		font-size: 9px;
	}
	.event small {
		margin-top: 3px;
		color: var(--muted);
		font-size: 7px;
	}
	.event b {
		color: var(--purple);
		font-size: 7px;
	}
	.empty-state {
		grid-column: 1/-1;
		color: var(--muted);
		font-size: 9px;
		text-align: center;
	}
	.radio-player {
		display: none;
		grid-template-columns: auto minmax(200px, 1fr) auto;
		align-items: center;
		gap: 12px;
		margin-top: 12px;
		padding: 8px 10px;
		background: rgba(194, 139, 255, 0.08);
		border: 1px solid rgba(194, 139, 255, 0.22);
		border-radius: 8px;
	}
	.radio-player.visible {
		display: grid;
	}
	.radio-player strong {
		display: block;
		margin-top: 3px;
		font-size: 9px;
	}
	.radio-player small {
		display: block;
		color: #ff8b9b;
		font-size: 8px;
	}
	.radio-player audio {
		width: 100%;
		height: 30px;
	}
	.radio-player > button {
		color: var(--muted);
		background: none;
		border: 0;
		font-size: 18px;
	}
	footer {
		display: flex;
		justify-content: space-between;
		padding: 11px 2px 0;
		color: #596273;
		font-size: 7px;
	}
	footer p {
		margin: 0;
	}
	footer div {
		display: flex;
		gap: 18px;
	}
	button {
		cursor: pointer;
	}
	button:focus-visible,
	a:focus-visible,
	select:focus-visible,
	input:focus-visible {
		outline: 2px solid #80aaff;
		outline-offset: 2px;
	}
	@media (max-width: 1120px) {
		.replay-grid {
			grid-template-columns: 220px 1fr;
		}
		.driver-panel {
			grid-column: 1/-1;
		}
		.driver-empty {
			min-height: 190px;
		}
		.session-facts div:nth-child(3) {
			display: none;
		}
	}
	@media (max-width: 800px) {
		.topbar {
			padding: 0 14px;
		}
		.snapshot {
			font-size: 8px;
		}
		main {
			padding: 10px;
		}
		.session-bar {
			align-items: flex-start;
			flex-wrap: wrap;
			gap: 10px;
		}
		.event-title {
			min-width: 0;
		}
		.session-facts {
			order: 3;
			width: 100%;
			margin: 0;
			justify-content: space-between;
		}
		.race-picker {
			margin-left: auto;
		}
		.replay-grid {
			display: flex;
			flex-direction: column;
		}
		.track-panel {
			order: 1;
		}
		.timing-panel {
			order: 2;
		}
		.driver-panel {
			order: 3;
		}
		.circuit {
			min-height: 430px;
		}
		.timing-panel ol {
			display: grid;
			grid-template-columns: 1fr 1fr;
			max-height: none;
		}
		.control-deck {
			grid-template-columns: 1fr auto auto;
		}
		.scrubber {
			grid-column: 1/-1;
			grid-row: 2;
		}
		.race-control {
			display: none;
		}
		.timeline-head {
			align-items: flex-start;
			flex-direction: column;
			gap: 8px;
		}
		.radio-player {
			grid-template-columns: 1fr auto;
		}
		.radio-player audio {
			grid-column: 1/-1;
			grid-row: 2;
		}
		footer {
			flex-direction: column;
			gap: 7px;
		}
	}
	@media (max-width: 500px) {
		nav {
			display: none;
		}
		.event-title h1 {
			font-size: 15px;
		}
		.race-picker {
			width: 100%;
			margin: 0;
		}
		.race-picker label,
		.race-picker select {
			width: 100%;
			max-width: none;
		}
		.timing-panel ol {
			grid-template-columns: 1fr;
		}
		.track-actions button:nth-child(2) {
			display: none;
		}
		.circuit {
			min-height: 360px;
		}
		.map-help {
			display: none;
		}
		.control-deck {
			grid-template-columns: 1fr auto;
			padding: 9px;
		}
		.lap-controls {
			grid-column: 1/-1;
		}
		.event-list {
			grid-template-columns: 1fr;
		}
		.filters {
			overflow: auto;
		}
		.session-facts {
			gap: 8px;
		}
		.session-facts div {
			min-width: 0;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		* {
			animation-duration: 0.01ms !important;
			transition-duration: 0.01ms !important;
		}
	}
</style>
