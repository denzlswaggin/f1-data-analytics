<script lang="ts">
	import { onMount, tick } from 'svelte';
	import PitInspector from './PitInspector.svelte';
	import { SvelteURL } from 'svelte/reactivity';
	import {
		buildDrivers,
		buildEvents,
		buildPitLanePath,
		buildTrackPath,
		filterEvents,
		formatLapTime,
		projectedSampleAt,
		radioEventsForPhase,
		sampleAt,
		timingAt,
		weatherAtTime
	} from './model';
	import { loadManifest, loadRace } from './data';
	import {
		compassDirection,
		compoundCode,
		formatClock,
		formatDate,
		formatGap,
		formatWeather
	} from './format';
	import { sourceLabel, sourceMarker } from './provenance';
	import { initialRace, latestRaceForSeason } from './selection';
	import type {
		LoadedRace,
		RadioPhase,
		RadioRow,
		ReplayDriver,
		ReplayEvent,
		ReplayManifest,
		RaceSummary,
		PitLanePath,
		PitVisit,
		TrackPath,
		TimingRow
	} from './types';

	const SPEEDS = [1, 2, 4, 6, 12, 24, 48];
	const PAD = 44;
	let manifest = $state<ReplayManifest | null>(null);
	let dashboardUrl = $state('/f1-data-analytics/');
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
	let timingExpanded = $state(false);
	let drivers = $state<ReplayDriver[]>([]),
		allEvents = $state<ReplayEvent[]>([]);
	let eventFilter = $state('all'),
		timelinePhase = $state<RadioPhase>('race'),
		nowPlaying = $state<ReplayEvent | null>(null),
		audioError = $state('');
	let radioPlaying = $state(false),
		radioLoading = $state(false),
		radioMuted = $state(false),
		radioCurrentTime = $state(0),
		radioDuration = $state(0);
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
	let pitLane: PitLanePath | null = null;
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

	let selectedPit = $state<PitVisit | null>(null);
	let clipEnd = $state<number | null>(null);
	let savedSpeed = $state<number | null>(null);
	let markerWidth = $state(800);
	let markerChoices = $state<ReplayEvent[]>([]);
	let pitVisits = $derived(allEvents.flatMap((e) => (e.pitVisit ? [e.pitVisit] : [])));
	let scopedPits = $derived(pitVisits.filter((v) => !selectedCode || v.driver === selectedCode));
	let markerGroups = $derived.by(() => {
		const groups: ReplayEvent[][] = [];
		for (const event of [...filteredEvents].sort((a, b) => a.time - b.time)) {
			const last = groups.at(-1);
			if (last && ((event.time - last[0].time) / Math.max(1, duration)) * markerWidth < 48)
				last.push(event);
			else groups.push([event]);
		}
		return groups;
	});
	function isPitting(code: string, time: number) {
		return pitVisits.some(
			(v) => v.driver === code && v.window && time >= v.window.start && time <= v.window.end
		);
	}
	function cancelClip() {
		clipEnd = null;
		if (savedSpeed != null) {
			speed = savedSpeed;
			savedSpeed = null;
		}
	}
	async function selectPit(visit: PitVisit) {
		cancelClip();
		selectedPit = visit;
		if (selectedCode && selectedCode !== visit.driver) selectedCode = visit.driver;
		markerChoices = [];
		await tick();
		const heading = root?.querySelector<HTMLElement>('.pit-inspector h2');
		heading?.focus({ preventScroll: true });
		heading?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
	}
	function closePit() {
		cancelClip();
		playing = false;
		selectedPit = null;
	}
	function watchPit() {
		if (!selectedPit?.window) return;
		const restore = savedSpeed ?? speed;
		seek(selectedPit.window.start - 5);
		savedSpeed = restore;
		speed = 1;
		selectedCode = selectedPit.driver;
		view.zoom = 1;
		resetView();
		clipEnd = Math.min(duration, selectedPit.window.end + 5);
		playing = true;
	}
	function continueRace() {
		cancelClip();
		playing = true;
	}

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
	let preRaceRadioEvents = $derived(
		radioEventsForPhase(loaded?.bundle.radio ?? [], 'pre-race', selectedCode)
	);
	let postRaceRadioEvents = $derived(
		radioEventsForPhase(loaded?.bundle.radio ?? [], 'post-race', selectedCode)
	);
	let preRaceRadioCount = $derived(
		radioEventsForPhase(loaded?.bundle.radio ?? [], 'pre-race').length
	);
	let raceRadioCount = $derived(filterEvents(allEvents, '', 'radio').length);
	let postRaceRadioCount = $derived(
		radioEventsForPhase(loaded?.bundle.radio ?? [], 'post-race').length
	);
	let currentWeather = $derived(weatherAtTime(loaded?.bundle.weather ?? [], currentTime));
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
		if (['localhost', '127.0.0.1', '[::1]', '::1'].includes(window.location.hostname)) {
			const localDashboard = new SvelteURL('/f1-data-analytics/', window.location.href);
			localDashboard.port = '3000';
			dashboardUrl = localDashboard.href;
		}
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
			const initial = initialRace(
				manifest.races,
				manifest.default_race,
				new SvelteURL(window.location.href).searchParams
			);
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
		closePit();
		markerChoices = [];
		loadError = '';
		playing = false;
		stopRadio();
		try {
			const race = await loadRace(summary, controller.signal);
			loaded = race;
			drivers = buildDrivers(
				race.positions,
				race.bundle.drivers,
				race.bundle.laps,
				race.bundle.race.circuit_name
			);
			duration = Math.max(summary.duration_s, ...drivers.map((d) => d.tmax));
			allEvents = buildEvents(
				race.bundle.race_control,
				race.bundle.overtakes,
				race.bundle.radio,
				race.bundle.laps,
				race.bundle.race.circuit_name,
				duration
			);
			replayTime = 0;
			currentTime = 0;
			selectedCode = '';
			eventFilter = 'all';
			timelinePhase = 'race';
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
		const next = latestRaceForSeason(manifest?.races ?? [], selectedSeason);
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
			pitLane = null;
			return;
		}
		trackPoints = trackPath.points;
		pitLane = buildPitLanePath(trackPath, loaded?.bundle.race.circuit_name);
		let minX = Infinity,
			maxX = -Infinity,
			minY = Infinity,
			maxY = -Infinity;
		for (const point of [...trackPoints, ...(pitLane?.points ?? [])]) {
			minX = Math.min(minX, point.x);
			maxX = Math.max(maxX, point.x);
			minY = Math.min(minY, point.y);
			maxY = Math.max(maxY, point.y);
		}
		bounds = { minX, maxX, minY, maxY };
	}
	function displaySample(driver: ReplayDriver, time: number) {
		return trackPath ? projectedSampleAt(driver, time, trackPath, pitLane) : sampleAt(driver, time);
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
		if (pitLane) {
			context.beginPath();
			pitLane.points.forEach((point, index) =>
				index
					? context?.lineTo(screenX(point.x), screenY(point.y))
					: context?.moveTo(screenX(point.x), screenY(point.y))
			);
			context.lineWidth = Math.min(14, Math.max(7, baseScale() * view.zoom * 90));
			context.strokeStyle = 'rgba(0, 0, 0, .8)';
			context.stroke();
			context.lineWidth = Math.min(8, Math.max(4, baseScale() * view.zoom * 50));
			context.strokeStyle = drivers.some((d) => isPitting(d.code, replayTime))
				? '#6cdee6'
				: '#8791a0';
			context.stroke();
			const boxX = screenX(pitLane.box.x);
			const boxY = screenY(pitLane.box.y);
			context.fillStyle = '#dce2ea';
			context.fillRect(boxX - 3, boxY - 3, 6, 6);
			context.font = '700 8px system-ui';
			context.fillText('PIT LANE · SCHEMATIC', boxX + 8, boxY - 7);
			for (const [point, label] of [
				[pitLane.points[0], 'IN →'],
				[pitLane.points.at(-1)!, 'OUT →']
			] as const) {
				context.fillText(label, screenX(point.x) + 8, screenY(point.y) - 12);
			}
		}
		const cars: ScreenCar[] = [];
		for (const driver of drivers) {
			const sample = displaySample(driver, replayTime);
			if (!sample) continue;
			const x = screenX(sample.x),
				y = screenY(sample.y),
				selected = selectedCode === driver.code,
				dimmed = Boolean(selectedCode && !selected);
			context.globalAlpha = dimmed ? 0.2 : 1;
			if (selected) {
				context.save();
				context.globalAlpha = 0.38;
				context.beginPath();
				context.arc(x, y, 14, 0, Math.PI * 2);
				context.strokeStyle = driver.color;
				context.lineWidth = 3;
				context.shadowColor = driver.color;
				context.shadowBlur = 10;
				context.stroke();
				context.restore();
			}
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
				context.strokeText(
					driver.code + (isPitting(driver.code, replayTime) ? ' PIT' : ''),
					x + 10,
					y + 4
				);
				context.fillText(
					driver.code + (isPitting(driver.code, replayTime) ? ' PIT' : ''),
					x + 10,
					y + 4
				);
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
			if (clipEnd != null && replayTime >= clipEnd) {
				replayTime = clipEnd;
				playing = false;
			}
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
		cancelClip();
		replayTime = Math.max(0, Math.min(duration, time));
		currentTime = replayTime;
		leaderboard = timingAt(drivers, replayTime);
		draw();
	}
	function togglePlayback() {
		if (!playing && clipEnd != null && replayTime >= clipEnd) cancelClip();
		if (replayTime >= duration) seek(0);
		playing = !playing;
	}
	function toggleDriver(code: string) {
		closePit();
		markerChoices = [];
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
		const phase = clip.phase ?? 'race';
		if (phase === 'race') {
			seek(event.time);
			speed = 1;
		}
		nowPlaying = event;
		audioError = '';
		radioPlaying = false;
		radioLoading = true;
		radioCurrentTime = 0;
		radioDuration = 0;
		await tick();
		audio.pause();
		audio.src = clip.recording_url;
		audio.load();
		try {
			await audio.play();
			if (phase === 'race') playing = true;
		} catch {
			radioLoading = false;
			audioError = 'Playback was blocked. Press play to retry.';
		}
	}
	async function toggleRadioPlayback() {
		if (!audio?.src) return;
		if (!audio.paused) {
			audio.pause();
			return;
		}
		audioError = '';
		try {
			await audio.play();
		} catch {
			radioLoading = false;
			audioError = 'This browser could not play the selected radio clip.';
		}
	}
	function seekRadio(value: number) {
		if (!audio?.src || !Number.isFinite(value)) return;
		audio.currentTime = Math.max(0, Math.min(radioDuration, value));
		radioCurrentTime = audio.currentTime;
	}
	function toggleRadioMute() {
		if (!audio) return;
		audio.muted = !audio.muted;
		radioMuted = audio.muted;
	}
	function setRadioDuration() {
		radioDuration = Number.isFinite(audio.duration) ? audio.duration : 0;
		radioLoading = false;
	}
	function activateEvent(event: ReplayEvent) {
		if (event.type === 'radio') void playRadio(event);
		else if (event.pitVisit) selectPit(event.pitVisit);
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
		radioPlaying = false;
		radioLoading = false;
		radioCurrentTime = 0;
		radioDuration = 0;
	}
	function timelinePosition(time: number) {
		return duration ? Math.max(0, Math.min(100, (time / duration) * 100)) : 0;
	}
	function formatPhaseClock(event: ReplayEvent, phase: RadioPhase) {
		if (phase === 'pre-race') return `T-${formatClock(Math.abs(event.time))}`;
		if (phase === 'post-race') return `T+${formatClock(Math.max(0, event.time - duration))}`;
		return formatClock(event.time);
	}
	function currentLapTime(driver: TimingRow | null) {
		if (!driver || !loaded) return null;
		return loaded.bundle.laps.find(
			(lap) => lap.driver_code === driver.code && lap.lap_number === driver.lap
		)?.lap_time_sec;
	}
</script>

<div class="app-shell" bind:this={root}>
	<header class="topbar">
		<!-- The Evidence dashboard is outside this SvelteKit app and its base path. -->
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
		<a
			class="brand"
			href={dashboardUrl}
			aria-label="F1 Analytics home"
			rel="external"
			data-sveltekit-reload
			><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><span
				><strong>F1</strong> ANALYTICS</span
			></a
		>
		<nav aria-label="Primary navigation">
			<!-- Navigate to the separate Evidence app without applying the replay base path. -->
			<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
			<a href={dashboardUrl} rel="external" data-sveltekit-reload
				><svg
					width="18"
					height="18"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="2"
					aria-hidden="true"><path d="m12 5-7 7 7 7M5 12h14" /></svg
				>Back to home</a
			>
		</nav>
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
					<span>STATUS</span><strong
						class="status-badge"
						class:critical={racePhase === 'Red flag'}
						class:warning={racePhase === 'Safety car'}
						class:complete={racePhase === 'Finished'}><i></i>{racePhase}</strong
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
			<details class="provenance-panel">
				<summary>Replay evidence: recorded, estimated and animated</summary>
				<p>
					Timing tower: plain values use aligned OpenF1 samples, ≈ marks lap-progress estimates, and
					? means the source is unavailable. Values are held between source samples; missing timing
					is not a measured zero. Hover a position or gap for its source.
				</p>
				<p>
					The circuit shape comes from loaded position traces. Car movement is interpolated and
					projected from lap progress; the pit lane is schematic. Pit entry and exit use recorded
					timestamps where available, with labeled estimated fallbacks. Animation is not an observed
					racing line or proof of a physical pass.
				</p>
				<p>
					Pass events are experimental timing-model detections. Race-control messages, weather
					samples and radio clips are source observations with separate coverage.
				</p>
				<p>
					This race has {loaded.bundle.race_control.length} control messages,
					{loaded.bundle.weather.length} weather samples and {loaded.bundle.radio.length} radio clips.
					An empty feed means no observations in this bundle, not proof that no event occurred.
				</p>
			</details>
			<section class="replay-grid">
				<aside
					id="drivers"
					class="timing-panel panel"
					class:expanded={timingExpanded}
					aria-label="Live timing"
				>
					<div class="panel-head">
						<div><span>LIVE TIMING</span><strong>Race order</strong></div>
						<div class="panel-head-actions">
							<b>GAP</b><button
								type="button"
								class="timing-toggle"
								aria-expanded={timingExpanded}
								onclick={() => (timingExpanded = !timingExpanded)}
								>{timingExpanded ? 'Hide order' : 'Show all drivers'}</button
							>
						</div>
					</div>
					<ol>
						{#each leaderboard as driver (driver.code)}<li
								class:selected={selectedCode === driver.code}
								class:dimmed={Boolean(selectedCode && selectedCode !== driver.code)}
								style={`--team:${driver.color}`}
							>
								<button
									type="button"
									onclick={() => toggleDriver(driver.code)}
									aria-pressed={selectedCode === driver.code}
									><span
										class="position"
										title={sourceLabel(driver.orderSource)}
										class:gain={(driver.positionChange ?? 0) > 0}
										class:loss={(driver.positionChange ?? 0) < 0}
										>{sourceMarker(driver.orderSource)}{driver.order}</span
									><span class="team-line" style={`--team:${driver.color}`}></span><span
										class="driver"
										><strong
											>{driver.code}{#if isPitting(driver.code, currentTime)}
												<em class="pit-badge">PIT</em>{/if}</strong
										><small>{driver.team}</small></span
									><span class="tyre {compoundCode(driver.compound).toLowerCase()}"
										>{compoundCode(driver.compound)}</span
									><span class="gap" title={sourceLabel(driver.gapSource)}
										>{driver.gap == null ? '' : sourceMarker(driver.gapSource)}{formatGap(
											driver.gap,
											true
										)}</span
									></button
								>
							</li>{/each}
					</ol>
					<div class="tower-footer">
						<span>{leaderboard.length} drivers</span><span>{racePhase}</span>
					</div>
				</aside>
				<div class="center-stage">
					<section
						class="track-panel panel"
						class:inspecting={Boolean(selectedPit)}
						aria-label="Circuit map"
					>
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
						<div class="pit-layout" class:inspecting={Boolean(selectedPit)}>
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
										<strong><i style={`background:${hovered.color}`}></i>{hovered.name}</strong
										><span>P{hovered.order ?? '—'} · {hovered.team}</span><span
											>{formatGap(hovered.ahead, true)} interval</span
										>
									</div>{/if}
								<div class="map-help">Scroll to zoom · drag to pan · click a car to follow</div>
							</div>
							{#if selectedPit}<PitInspector
									visit={selectedPit}
									visits={scopedPits}
									allVisits={pitVisits}
									{drivers}
									time={currentTime}
									watching={clipEnd != null}
									onwatch={watchPit}
									oncontinue={continueRace}
									onclose={closePit}
									onselect={selectPit}
								/>{/if}
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
							>SPEED<select
								value={speed}
								onchange={(event) => {
									cancelClip();
									speed = Number(event.currentTarget.value);
								}}
								>{#each SPEEDS as option (option)}<option value={option}>{option}×</option
									>{/each}</select
							></label
						>
					</section>
				</div>
				<aside
					id="strategy"
					class="driver-panel panel"
					style={`--team:${selectedDriver?.color ?? '#64748b'}`}
					aria-label="Selected driver detail"
				>
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
							<div class="interval-metric">
								<span>INTERVAL</span><strong>{formatGap(selectedDriver.ahead, true)}</strong><small
									>to car ahead</small
								>
							</div>
							<div class="gap-metric">
								<span>LEADER GAP</span><strong>{formatGap(selectedDriver.gap)}</strong><small
									>race time</small
								>
							</div>
							<div class="position-metric">
								<span>POSITIONS</span><strong
									class:gain={(selectedDriver.positionChange ?? 0) > 0}
									class:loss={(selectedDriver.positionChange ?? 0) < 0}
									>{selectedDriver.positionChange == null
										? '—'
										: `${selectedDriver.positionChange > 0 ? '+' : ''}${selectedDriver.positionChange}`}</strong
								><small>from the grid</small>
							</div>
							<div class="lap-metric">
								<span>LAP TIME</span><strong>{formatLapTime(currentLapTime(selectedDriver))}</strong
								><small>current recorded lap</small>
							</div>
						</div>
						<div class="stint-card {compoundCode(selectedDriver.compound).toLowerCase()}">
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
				<section class="weather-panel panel" aria-label="Track weather">
					<div class="weather-heading">
						<div>
							<span>TRACK CONDITIONS</span>
							<h2>Weather</h2>
						</div>
						{#if currentWeather}<strong class:wet={currentWeather.rainfall}
								><i></i>{currentWeather.rainfall ? 'Rainfall' : 'Dry track'}</strong
							>{/if}
					</div>
					{#if currentWeather}
						<div class="weather-metrics">
							<div>
								<span>AIR</span><strong
									>{formatWeather(currentWeather.air_temperature, '°C')}</strong
								><small>Ambient temperature</small>
							</div>
							<div>
								<span>TRACK</span><strong
									>{formatWeather(currentWeather.track_temperature, '°C')}</strong
								><small>Surface temperature</small>
							</div>
							<div>
								<span>HUMIDITY</span><strong
									>{formatWeather(currentWeather.humidity, '%', 0)}</strong
								><small>Relative humidity</small>
							</div>
							<div>
								<span>PRESSURE</span><strong
									>{formatWeather(currentWeather.pressure, ' mbar', 0)}</strong
								><small>Air pressure</small>
							</div>
							<div class="wind-metric">
								<span>WIND</span><strong
									><i
										style={`transform:rotate(${currentWeather.wind_direction ?? 0}deg)`}
										aria-hidden="true">↑</i
									>{formatWeather(currentWeather.wind_speed, ' m/s')}</strong
								><small
									>{compassDirection(currentWeather.wind_direction)} · {formatWeather(
										currentWeather.wind_direction,
										'°',
										0
									)}</small
								>
							</div>
							<div>
								<span>SAMPLE</span><strong>{formatClock(currentWeather.t_s)}</strong><small
									>{formatDate(loaded.bundle.race.race_date)} · Race session</small
								>
							</div>
						</div>
						<footer class="weather-source">
							<span><i></i>FastF1 weather feed</span><span
								>{loaded.bundle.weather.length} samples · updated approximately every minute</span
							>
						</footer>
					{:else}
						<div class="weather-empty">
							<strong>Weather feed unavailable</strong><span
								>This race has no time-aligned conditions in the current snapshot.</span
							>
						</div>
					{/if}
				</section>
			</section>
			<section class="timeline panel" aria-label="Race intelligence timeline">
				<div class="timeline-head">
					<div>
						<span>RACE INTELLIGENCE</span>
						<h2>Event timeline</h2>
					</div>
					{#if selectedCode}<p>
							Showing {timelinePhase === 'race' ? 'race events' : 'radio'} for
							<strong>{selectedCode}</strong><button
								type="button"
								onclick={() => toggleDriver(selectedCode)}>Clear</button
							>
						</p>{/if}
				</div>
				<div class="timeline-phases" aria-label="Select event timeline phase">
					<button
						type="button"
						class:active={timelinePhase === 'pre-race'}
						onclick={() => (timelinePhase = 'pre-race')}
						><span>PRE-RACE</span><strong>Team radio</strong><b>{preRaceRadioCount}</b></button
					><button
						type="button"
						class:active={timelinePhase === 'race'}
						onclick={() => (timelinePhase = 'race')}
						><span>RACE</span><strong>Live timeline</strong><b
							>{filterEvents(allEvents, selectedCode).length}</b
						></button
					><button
						type="button"
						class:active={timelinePhase === 'post-race'}
						onclick={() => (timelinePhase = 'post-race')}
						><span>POST-RACE</span><strong>Team radio</strong><b>{postRaceRadioCount}</b></button
					>
				</div>
				{#if timelinePhase === 'race'}
					<div class="filters" aria-label="Filter race events">
						{#each ['all', 'control', 'overtake', 'pit', 'radio'] as filter (filter)}{#if !selectedCode || filter !== 'control'}<button
									type="button"
									class="filter-{filter}"
									class:active={eventFilter === filter}
									onclick={() => {
										eventFilter = filter;
										markerChoices = [];
									}}
									>{filter === 'all'
										? 'All events'
										: filter === 'control'
											? 'Race control'
											: filter === 'overtake'
												? 'Overtakes'
												: filter === 'pit'
													? 'Pit stops'
													: 'Radio'}<span
										>{filterEvents(allEvents, selectedCode, filter).length}</span
									></button
								>{/if}{/each}
					</div>
					<div class="event-rail-scroll" role="region" aria-label="Scrollable race event timeline">
						<div class="event-rail" bind:clientWidth={markerWidth}>
							<button
								type="button"
								aria-label="Seek on event timeline"
								onclick={(event) => {
									const r = event.currentTarget.getBoundingClientRect();
									seek(((event.clientX - r.left) / r.width) * duration);
								}}
								><span class="elapsed" style={`width:${timelinePosition(currentTime)}%`}></span><i
									class="playhead"
									style={`left:${timelinePosition(currentTime)}%`}
								></i></button
							>
							<div class="markers">
								{#each markerGroups as group (group[0].id)}
									<button
										type="button"
										class={group.some((e) => e.type === 'pit') ? 'pit' : group[0].type}
										class:multiple={group.length > 1}
										class:past={group[0].time <= currentTime}
										class:selected={markerChoices[0]?.id === group[0].id}
										style={`left:${timelinePosition(group[0].time)}%`}
										aria-expanded={group.length > 1
											? markerChoices[0]?.id === group[0].id
											: undefined}
										aria-label={group.length > 1
											? `${group.length} events near ${formatClock(group[0].time)}`
											: `${group[0].label}, ${group[0].meta}`}
										title={group.map((e) => `${e.label} · ${e.meta}`).join(' / ')}
										onclick={() =>
											group.length > 1 ? (markerChoices = group) : activateEvent(group[0])}
										><span class="marker-symbol" aria-hidden="true"
											>{group.length > 1 ? group.length : ''}</span
										></button
									>
								{/each}
							</div>
							<div class="rail-scale" aria-hidden="true">
								<span>RACE START</span><span>FINISH</span>
							</div>
						</div>
					</div>
					<p class="rail-scroll-hint">Scroll sideways to explore the race timeline</p>
					{#if markerChoices.length}<section
							class="marker-choices"
							aria-label="Nearby timeline events"
						>
							<div class="marker-choices-head">
								<div>
									<strong
										>{markerChoices.length} events around {formatClock(
											markerChoices[0].time
										)}</strong
									><span>Choose an event to jump to it</span>
								</div>
								<button
									type="button"
									aria-label="Close event list"
									onclick={() => (markerChoices = [])}>Close</button
								>
							</div>
							<div class="marker-choices-list">
								{#each markerChoices as event (event.id)}<button
										type="button"
										class="event {event.type}"
										onclick={() => {
											markerChoices = [];
											activateEvent(event);
										}}
										><i></i><time>{formatClock(event.time)}</time><span
											><strong>{event.label}</strong><small>{event.meta}</small></span
										>{#if event.type === 'radio'}<b>LISTEN</b>{/if}</button
									>{/each}
							</div>
						</section>{/if}
					{#if eventFilter === 'pit'}<div class="pit-choices" aria-label="All pit visits">
							{#each scopedPits as visit (visit.id)}<button
									aria-pressed={selectedPit?.id === visit.id}
									onclick={() => selectPit(visit)}
									>{visit.driver} · Lap {visit.lap}<small
										>{visit.tyreChange
											? `${visit.fromCompound ?? '?'} → ${visit.toCompound ?? '?'}`
											: 'Pit visit'} · {visit.source}</small
									></button
								>{/each}
						</div>{/if}
					<div class="phase-summary">
						<strong>Events near {formatClock(currentTime)}</strong><span
							>{nearbyEvents.length} closest matching events</span
						>
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
				{:else}
					{@const phaseRadioEvents =
						timelinePhase === 'pre-race' ? preRaceRadioEvents : postRaceRadioEvents}
					<div class="phase-summary">
						<strong>{timelinePhase === 'pre-race' ? 'Before lights out' : 'After the flag'}</strong
						><span>Every available team-radio clip from this phase is shown below.</span>
					</div>
					<div class="event-list phase-event-list">
						{#if phaseRadioEvents.length}{#each phaseRadioEvents as event (event.id)}<button
									class="event radio"
									type="button"
									onclick={() => playRadio(event)}
									><i></i><time>{formatPhaseClock(event, timelinePhase)}</time><span
										><strong>{event.label}</strong><small>{event.meta}</small></span
									><b>LISTEN</b></button
								>{/each}{:else}<p class="empty-state">
								No radio is available for this phase{selectedCode ? ` and ${selectedCode}` : ''}.
							</p>{/if}
					</div>
				{/if}
				<div class="radio-player" class:visible={Boolean(nowPlaying)}>
					<div class="radio-copy">
						<span>TEAM RADIO</span><strong>{nowPlaying?.meta ?? 'Select a radio event'}</strong
						>{#if audioError}<small role="alert">{audioError}</small>{/if}
					</div>
					<div class="custom-audio-controls">
						<button
							class="radio-play"
							type="button"
							disabled={!nowPlaying}
							aria-label={radioPlaying ? 'Pause team radio' : 'Play team radio'}
							onclick={() => void toggleRadioPlayback()}
							>{radioLoading ? '…' : radioPlaying ? 'Ⅱ' : '▶'}</button
						>
						<time>{formatClock(radioCurrentTime)} / {formatClock(radioDuration)}</time>
						<input
							class="radio-progress"
							type="range"
							min="0"
							max={radioDuration || 0}
							step="0.01"
							value={radioCurrentTime}
							disabled={!radioDuration}
							aria-label="Team radio playback position"
							oninput={(event) => seekRadio(Number(event.currentTarget.value))}
						/>
						<button
							class="radio-volume"
							type="button"
							aria-label={radioMuted ? 'Unmute team radio' : 'Mute team radio'}
							onclick={toggleRadioMute}>{radioMuted ? 'MUTED' : 'VOLUME'}</button
						>
					</div>
					<audio
						class="radio-engine"
						bind:this={audio}
						preload="none"
						onloadedmetadata={setRadioDuration}
						ondurationchange={setRadioDuration}
						oncanplay={() => (radioLoading = false)}
						onwaiting={() => (radioLoading = true)}
						onplaying={() => {
							radioPlaying = true;
							radioLoading = false;
						}}
						onpause={() => (radioPlaying = false)}
						onended={() => (radioPlaying = false)}
						ontimeupdate={() => (radioCurrentTime = audio.currentTime)}
						onerror={() => {
							radioLoading = false;
							radioPlaying = false;
							if (nowPlaying) audioError = 'The source could not load this radio clip.';
						}}
					></audio><button
						class="radio-close"
						type="button"
						aria-label="Close radio player"
						onclick={stopRadio}>×</button
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
					><span
						>{loaded.bundle.radio.length} radio clips · {preRaceRadioCount} pre · {raceRadioCount}
						race · {postRaceRadioCount} post</span
					>
				</div>
			</footer>
		{/if}
	</main>
</div>

<style>
	.pit-layout {
		min-width: 0;
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		align-items: start;
	}
	@media (min-width: 1400px) {
		.pit-layout.inspecting {
			grid-template-columns: minmax(0, 1fr) 330px;
			gap: 12px;
		}
	}

	.pit-badge {
		margin-left: 4px;
		padding: 1px 3px;
		border: 1px solid #34656c;
		border-radius: 3px;
		font-size: 9px;
		color: #65e3ee;
		font-style: normal;
	}
	.pit-choices {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		padding: 12px;
		max-height: 260px;
		overflow: auto;
	}
	.pit-choices button {
		min-height: 44px;
		border: 1px solid #3b5366;
		border-radius: 8px;
		background: #14212d;
		color: #e6f3ff;
		padding: 8px;
		text-align: left;
	}
	.pit-choices small {
		display: block;
		color: #aabed0;
		font-size: 11px;
		margin-top: 4px;
	}
	.pit-choices button:focus-visible {
		outline: 2px solid #69dce5;
	}

	.provenance-panel {
		margin: 0 0 1rem;
		padding: 0.8rem 1rem;
		border: 1px solid #354052;
		border-radius: 0.6rem;
		color: #c7d0de;
		font-size: 0.85rem;
	}
	.provenance-panel summary {
		cursor: pointer;
		font-weight: 600;
	}
	.provenance-panel p {
		max-width: 90ch;
		margin: 0.7rem 0 0;
		line-height: 1.5;
	}

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
		background:
			linear-gradient(90deg, rgba(255, 77, 87, 0.035), transparent 28%), rgba(8, 10, 14, 0.92);
		border-bottom: 1px solid var(--line);
		backdrop-filter: blur(14px);
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 10px;
		color: var(--text);
		font-size: var(--text-body);
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
		display: flex;
		align-self: stretch;
	}
	nav a {
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: 8px;
		white-space: nowrap;
		height: 100%;
		color: var(--text);
		font-size: var(--text-small);
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
		font-size: var(--text-meta);
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
		position: relative;
		display: grid;
		grid-template-columns: minmax(280px, 1fr) auto auto;
		align-items: center;
		gap: 24px;
		min-height: 68px;
		margin-bottom: 12px;
		padding: 7px 16px;
		overflow: hidden;
		background:
			radial-gradient(circle at 8% 0%, rgba(255, 77, 87, 0.09), transparent 18rem),
			linear-gradient(145deg, rgba(20, 25, 34, 0.98), rgba(11, 14, 20, 0.98));
	}
	.event-title {
		display: flex;
		align-items: center;
		gap: 13px;
		min-width: 0;
	}
	.round {
		display: grid;
		place-items: center;
		width: 38px;
		height: 38px;
		color: #fff;
		background: linear-gradient(145deg, #ff6972, #d91f35);
		border-radius: 8px;
		box-shadow: 0 5px 14px rgba(255, 77, 87, 0.2);
		font-size: var(--text-meta);
		font-weight: 800;
	}
	.event-title p,
	.event-title h1 {
		margin: 0;
	}
	.event-title p {
		color: var(--muted);
		font-size: var(--text-caption);
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}
	.event-title h1 {
		margin-top: 3px;
		font-size: var(--text-display);
	}
	.session-facts {
		display: flex;
		gap: 18px;
		margin-left: 0;
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
		font-size: var(--text-caption);
		font-weight: 750;
		letter-spacing: 0.12em;
	}
	.session-facts strong {
		display: block;
		margin-top: 5px;
		font-size: var(--text-body);
	}
	.session-facts em {
		color: var(--muted);
		font-size: var(--text-meta);
		font-style: normal;
	}
	.status-badge {
		display: inline-flex !important;
		align-items: center;
		min-height: 27px;
		padding: 4px 8px;
		color: var(--status-live);
		background: var(--green-soft);
		border: 1px solid rgba(70, 212, 154, 0.25);
		border-radius: 999px;
	}
	.status-badge i {
		box-shadow: 0 0 5px currentColor;
		animation: status-pulse 2s ease-in-out infinite;
	}
	@keyframes status-pulse {
		50% {
			opacity: 0.48;
			box-shadow: 0 0 2px currentColor;
		}
	}
	.status-badge.warning {
		color: var(--status-warning);
		background: var(--yellow-soft);
		border-color: rgba(244, 201, 79, 0.28);
	}
	.status-badge.critical {
		color: var(--status-critical);
		background: var(--red-soft);
		border-color: rgba(255, 77, 87, 0.3);
	}
	.status-badge.complete {
		color: var(--purple);
		background: var(--purple-soft);
		border-color: rgba(194, 139, 255, 0.28);
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
		margin-left: 0;
	}
	.race-picker label {
		color: var(--muted);
		font-size: var(--text-caption);
	}
	.race-picker select {
		display: block;
		max-width: 180px;
		min-height: 38px;
		margin-top: 3px;
		padding: 6px;
		color: #fff;
		background: #151a22;
		border: 1px solid var(--line);
		border-radius: 6px;
		font-size: var(--text-small);
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
		font-size: var(--text-body);
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
		grid-template-areas:
			'weather weather weather'
			'timing center driver';
		grid-template-columns: minmax(260px, 280px) minmax(520px, 1fr) minmax(300px, 320px);
		grid-template-rows: auto 1fr;
		gap: 12px;
		align-items: stretch;
	}
	.center-stage {
		grid-area: center;
		display: grid;
		grid-template-rows: minmax(540px, 1fr) auto;
		gap: 12px;
		min-width: 0;
	}
	.timing-panel,
	.driver-panel {
		overflow: hidden;
	}
	.timing-panel {
		grid-area: timing;
		display: flex;
		flex-direction: column;
		background:
			linear-gradient(180deg, rgba(85, 170, 255, 0.035), transparent 35%),
			linear-gradient(145deg, rgba(20, 25, 34, 0.98), rgba(11, 14, 20, 0.98));
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
		font-size: var(--text-title);
	}
	.panel-head b {
		color: var(--muted);
		font-size: var(--text-caption);
	}
	.panel-head-actions {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.timing-toggle {
		display: none;
		min-height: 36px;
		padding: 0 10px;
		color: var(--muted-strong);
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid var(--line);
		border-radius: 6px;
		font-size: var(--text-caption);
	}
	.timing-panel ol {
		flex: 1;
		max-height: 536px;
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
		background: linear-gradient(
			90deg,
			color-mix(in srgb, var(--team) 20%, transparent),
			transparent 88%
		);
		box-shadow: inset 3px 0 var(--team);
	}
	.timing-panel li.dimmed {
		opacity: 0.42;
	}
	.timing-panel li button {
		display: grid;
		grid-template-columns: 22px 3px 1fr 24px 56px;
		align-items: center;
		width: 100%;
		min-height: 48px;
		padding: 0 11px;
		color: inherit;
		background: transparent;
		border: 0;
		border-bottom: 1px solid rgba(255, 255, 255, 0.045);
		cursor: pointer;
		text-align: left;
	}
	.timing-panel li button:hover {
		background: linear-gradient(
			90deg,
			color-mix(in srgb, var(--team) 11%, transparent),
			transparent
		);
	}
	.position {
		color: var(--muted);
		font-size: var(--text-small);
		font-weight: 750;
	}
	.position.gain {
		color: var(--green);
	}
	.position.loss {
		color: var(--accent);
	}
	.team-line {
		width: 3px;
		height: 24px;
		background: var(--team);
		border-radius: 3px;
		box-shadow: 0 0 6px color-mix(in srgb, var(--team) 35%, transparent);
	}
	.driver {
		min-width: 0;
		padding-left: 9px;
	}
	.driver strong {
		display: block;
		font-size: var(--text-body);
	}
	.driver small {
		display: block;
		overflow: hidden;
		margin-top: 3px;
		color: var(--muted);
		font-size: var(--text-meta);
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
		font-size: var(--text-caption);
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
			var(--text-small) Consolas,
			monospace;
	}
	.tower-footer {
		display: flex;
		justify-content: space-between;
		padding: 10px 12px;
		color: var(--muted);
		font-size: var(--text-caption);
	}
	.track-panel {
		position: relative;
		min-width: 0;
		overflow: hidden;
		border-color: rgba(85, 170, 255, 0.17);
	}
	.track-panel.inspecting .track-meta {
		position: relative;
		top: auto;
		left: auto;
		width: auto;
		margin: 15px 17px;
		flex-wrap: wrap;
		gap: 8px;
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
		min-height: 36px;
		padding: 6px 9px;
		color: var(--muted-strong);
		background: rgba(20, 25, 34, 0.85);
		border: 1px solid var(--line);
		border-radius: 6px;
		font-size: var(--text-meta);
		cursor: pointer;
	}
	.track-actions button:disabled {
		opacity: 0.4;
	}
	.track-actions button:not(:disabled):hover,
	.clear-driver:hover {
		color: #fff;
		background: var(--blue-soft);
		border-color: rgba(85, 170, 255, 0.35);
	}
	.circuit {
		position: relative;
		height: 100%;
		min-height: 540px;
		background:
			radial-gradient(circle at 48% 48%, rgba(85, 170, 255, 0.08), transparent 47%),
			radial-gradient(circle at 78% 18%, rgba(194, 139, 255, 0.05), transparent 34%),
			linear-gradient(160deg, rgba(12, 19, 30, 0.96), rgba(9, 12, 18, 0.98));
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
		font-size: var(--text-meta);
		pointer-events: none;
	}
	.tooltip strong {
		color: #fff;
		font-size: var(--text-small);
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
		color: var(--muted);
		font-size: var(--text-caption);
	}
	.race-control {
		position: absolute;
		z-index: 4;
		top: 64px;
		left: 12px;
		width: min(230px, 40%);
		padding: 9px;
		background: linear-gradient(145deg, rgba(16, 20, 28, 0.93), rgba(8, 10, 14, 0.9));
		border: 1px solid rgba(244, 201, 79, 0.18);
		border-radius: 8px;
	}
	.race-control > span {
		color: var(--muted);
		font-size: var(--text-caption);
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
	.race-control button:hover {
		background: var(--yellow-soft);
	}
	.race-control time {
		color: var(--muted);
		font: var(--text-caption) Consolas;
	}
	.race-control i {
		width: 5px;
		height: 5px;
		background: var(--yellow);
		border-radius: 50%;
		box-shadow: 0 0 5px var(--yellow);
	}
	.race-control i.red {
		background: var(--accent);
		box-shadow: 0 0 5px var(--accent);
	}
	.race-control i.green {
		background: var(--green);
		box-shadow: 0 0 5px var(--green);
	}
	.race-control i.safety {
		background: #f6a13c;
		box-shadow: 0 0 5px var(--orange);
	}
	.race-control strong {
		overflow: hidden;
		font-size: var(--text-meta);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.driver-panel {
		grid-area: driver;
		position: relative;
		--team: #64748b;
		background:
			radial-gradient(
				circle at 100% 0%,
				color-mix(in srgb, var(--team) 16%, transparent),
				transparent 17rem
			),
			linear-gradient(145deg, rgba(20, 25, 34, 0.98), rgba(11, 14, 20, 0.98));
	}
	.driver-accent {
		height: 4px;
		background: var(--team);
		box-shadow: 0 0 10px color-mix(in srgb, var(--team) 40%, transparent);
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
		font-size: var(--text-meta);
	}
	.selected-head > strong {
		display: grid;
		place-items: center;
		width: 45px;
		height: 45px;
		background: color-mix(in srgb, var(--team) 14%, rgba(255, 255, 255, 0.04));
		border: 1px solid color-mix(in srgb, var(--team) 38%, var(--line));
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
		font-size: var(--text-meta);
		text-transform: uppercase;
	}
	.status-row strong {
		color: #e7eaf0;
	}
	.metric-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
		padding: 16px;
	}
	.metric-grid div {
		position: relative;
		min-height: 74px;
		padding: 13px 12px 10px;
		background: rgba(255, 255, 255, 0.025);
		border: 1px solid var(--line);
		border-radius: 8px;
	}
	.metric-grid div:before {
		position: absolute;
		inset: 0 auto auto 12px;
		width: 26px;
		height: 2px;
		background: color-mix(in srgb, var(--team) 65%, #fff);
		border-radius: 0 0 2px 2px;
		content: '';
	}
	.metric-grid strong {
		display: block;
		margin-top: 9px;
		color: var(--text);
		font: var(--text-title) Consolas;
	}
	.metric-grid .gain {
		color: var(--green);
	}
	.metric-grid .loss {
		color: var(--accent);
	}
	.metric-grid small {
		display: block;
		margin-top: 4px;
		color: var(--muted);
		font-size: var(--text-meta);
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
	.stint-card.s {
		background: var(--red-soft);
		border-color: rgba(255, 77, 87, 0.24);
	}
	.stint-card.m {
		background: var(--yellow-soft);
		border-color: rgba(244, 201, 79, 0.24);
	}
	.stint-card.h {
		background: rgba(255, 255, 255, 0.055);
		border-color: rgba(255, 255, 255, 0.16);
	}
	.stint-card.i {
		background: var(--green-soft);
		border-color: rgba(70, 212, 154, 0.24);
	}
	.stint-card.w {
		background: var(--blue-soft);
		border-color: rgba(85, 170, 255, 0.24);
	}
	.tyre-visual {
		width: 34px;
		height: 34px;
		border-width: 4px;
		font-size: var(--text-caption);
	}
	.stint-card strong {
		display: block;
		margin-top: 4px;
		font-size: var(--text-small);
	}
	.stint-card small {
		display: block;
		margin-top: 3px;
		color: var(--muted);
		font-size: var(--text-meta);
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
		font-size: var(--text-small);
		line-height: 1.55;
	}
	.weather-panel {
		grid-area: weather;
		margin-top: 0;
		padding: 14px 16px 10px;
		overflow: hidden;
		background:
			radial-gradient(circle at 92% -40%, rgba(77, 217, 231, 0.12), transparent 24rem),
			linear-gradient(145deg, rgba(15, 27, 36, 0.98), rgba(10, 15, 22, 0.98));
		border-color: rgba(77, 217, 231, 0.18);
	}
	.weather-heading {
		display: flex;
		align-items: center;
		justify-content: space-between;
	}
	.weather-heading h2 {
		margin: 4px 0 0;
		color: #e9fcff;
		font-size: var(--text-title);
	}
	.weather-heading > strong {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 6px 9px;
		color: var(--green);
		background: rgba(70, 212, 154, 0.08);
		border: 1px solid rgba(70, 212, 154, 0.24);
		border-radius: 999px;
		font-size: var(--text-caption);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.weather-heading > strong.wet {
		color: var(--blue);
		background: rgba(85, 170, 255, 0.08);
		border-color: rgba(85, 170, 255, 0.3);
	}
	.weather-heading > strong i,
	.weather-source i {
		width: 6px;
		height: 6px;
		background: currentColor;
		border-radius: 50%;
		box-shadow: 0 0 5px currentColor;
	}
	.weather-metrics {
		display: grid;
		grid-template-columns: repeat(6, minmax(0, 1fr));
		margin-top: 13px;
		background: rgba(255, 255, 255, 0.018);
		border: 1px solid var(--line);
		border-radius: 8px;
	}
	.weather-metrics > div {
		position: relative;
		min-width: 0;
		padding: 11px 13px;
		border-left: 1px solid var(--line);
	}
	.weather-metrics > div:before {
		position: absolute;
		top: 0;
		left: 13px;
		width: 22px;
		height: 2px;
		background: currentColor;
		border-radius: 2px;
		content: '';
	}
	.weather-metrics > div:nth-child(1) {
		color: var(--orange);
	}
	.weather-metrics > div:nth-child(2) {
		color: var(--accent);
	}
	.weather-metrics > div:nth-child(3) {
		color: var(--blue);
	}
	.weather-metrics > div:nth-child(4) {
		color: var(--purple);
	}
	.weather-metrics > div:nth-child(5) {
		color: var(--cyan);
	}
	.weather-metrics > div:nth-child(6) {
		color: var(--green);
	}
	.weather-metrics > div:first-child {
		border-left: 0;
	}
	.weather-metrics span,
	.weather-metrics strong,
	.weather-metrics small {
		display: block;
	}
	.weather-metrics span {
		color: currentColor;
		font-size: var(--text-caption);
		font-weight: 700;
		letter-spacing: 0.1em;
	}
	.weather-metrics strong {
		margin-top: 5px;
		color: var(--text);
		font: var(--text-title) Consolas;
	}
	.weather-metrics > div:nth-child(-n + 2) {
		background: rgba(255, 255, 255, 0.025);
	}
	.weather-metrics > div:nth-child(-n + 2) strong {
		font-size: 18px;
	}
	.weather-metrics small {
		margin-top: 3px;
		overflow: hidden;
		color: var(--muted);
		font-size: var(--text-meta);
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.wind-metric strong {
		display: flex;
		align-items: center;
		gap: 7px;
	}
	.wind-metric strong i {
		display: inline-block;
		color: var(--cyan);
		font: 15px sans-serif;
		transform-origin: center;
	}
	footer.weather-source {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 9px 2px 0;
		color: var(--muted);
		font-size: var(--text-caption);
	}
	.weather-source span:first-child {
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--muted);
	}
	.weather-empty {
		display: flex;
		align-items: baseline;
		gap: 8px;
		margin-top: 13px;
		padding: 13px;
		color: var(--muted);
		background: rgba(255, 255, 255, 0.018);
		border: 1px dashed var(--line);
		border-radius: 8px;
		font-size: var(--text-meta);
	}
	.weather-empty strong {
		color: var(--muted-strong);
		font-size: var(--text-small);
	}
	.control-deck {
		display: grid;
		grid-template-columns: auto 1fr auto auto;
		align-items: center;
		gap: 16px;
		min-height: 72px;
		margin-top: 0;
		padding: 10px 14px;
		background:
			linear-gradient(90deg, rgba(255, 77, 87, 0.035), transparent 34%),
			linear-gradient(145deg, rgba(20, 25, 34, 0.98), rgba(11, 14, 20, 0.98));
	}
	.playback,
	.lap-controls {
		display: flex;
		align-items: center;
		gap: 5px;
	}
	.playback button,
	.lap-controls button {
		min-width: 40px;
		height: 40px;
		color: var(--muted-strong);
		background: #171c25;
		border: 1px solid var(--line);
		border-radius: 7px;
		font-size: var(--text-small);
		cursor: pointer;
	}
	.playback button:not(.play):hover,
	.lap-controls button:hover {
		color: #fff;
		background: var(--red-soft);
		border-color: rgba(255, 77, 87, 0.32);
	}
	.playback .play {
		color: #fff;
		background: linear-gradient(145deg, #ff6972, #d91f35);
		border-color: var(--accent);
		box-shadow: 0 4px 12px rgba(255, 77, 87, 0.18);
	}
	.playback strong {
		min-width: 64px;
		margin-left: 7px;
		font: var(--text-body) Consolas;
	}
	.scrubber input {
		width: 100%;
		accent-color: var(--accent);
	}
	.ticks {
		display: flex;
		justify-content: space-between;
		color: var(--muted);
		font-size: var(--text-caption);
	}
	.speed-control {
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--muted);
		font-size: var(--text-caption);
	}
	.speed-control select {
		min-height: 40px;
		padding: 7px;
		color: #fff;
		background: #171c25;
		border: 1px solid var(--line);
		border-radius: 7px;
		font-size: var(--text-small);
	}
	.timeline {
		position: relative;
		margin-top: 12px;
		padding: 14px 16px;
		background:
			radial-gradient(circle at 100% 0%, rgba(194, 139, 255, 0.05), transparent 28rem),
			linear-gradient(145deg, rgba(20, 25, 34, 0.98), rgba(11, 14, 20, 0.98));
	}
	.timeline-head {
		display: flex;
		align-items: end;
		justify-content: space-between;
	}
	.timeline-head h2 {
		margin: 4px 0 0;
		font-size: var(--text-title);
	}
	.timeline-head p {
		margin: 0;
		color: var(--muted);
		font-size: var(--text-meta);
	}
	.timeline-head p strong {
		color: #fff;
	}
	.timeline-head p button {
		min-height: 32px;
		margin-left: 7px;
		color: var(--muted-strong);
		background: rgba(255, 255, 255, 0.04);
		border: 1px solid var(--line);
		border-radius: 4px;
		font-size: var(--text-caption);
	}
	.timeline-phases {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 7px;
		margin-top: 14px;
	}
	.timeline-phases button {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 3px 10px;
		min-height: 52px;
		padding: 9px 11px;
		color: var(--muted);
		background: rgba(255, 255, 255, 0.025);
		border: 1px solid var(--line);
		border-radius: 7px;
		text-align: left;
	}
	.timeline-phases button:hover {
		color: #fff;
		border-color: var(--line-strong);
	}
	.timeline-phases button.active {
		color: #fff;
	}
	.timeline-phases button:nth-child(1).active {
		background: var(--purple-soft);
		border-color: rgba(194, 139, 255, 0.46);
		box-shadow: inset 3px 0 var(--purple);
	}
	.timeline-phases button:nth-child(2).active {
		background: var(--red-soft);
		border-color: rgba(255, 77, 87, 0.42);
		box-shadow: inset 3px 0 var(--accent);
	}
	.timeline-phases button:nth-child(3).active {
		background: var(--cyan-soft);
		border-color: rgba(77, 217, 231, 0.42);
		box-shadow: inset 3px 0 var(--cyan);
	}
	.timeline-phases span {
		grid-column: 1;
		font-size: var(--text-caption);
		font-weight: 700;
		letter-spacing: 0.12em;
	}
	.timeline-phases strong {
		grid-column: 1;
		font-size: var(--text-small);
	}
	.timeline-phases b {
		grid-column: 2;
		grid-row: 1 / span 2;
		align-self: center;
		color: var(--purple);
		font: var(--text-body) Consolas;
	}
	.timeline-phases button:nth-child(2) b {
		color: var(--accent);
	}
	.timeline-phases button:nth-child(3) b {
		color: var(--cyan);
	}
	.phase-summary {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 9px;
		margin-top: 18px;
		color: var(--muted);
		font-size: var(--text-meta);
	}
	.phase-summary strong {
		color: #fff;
		font-size: var(--text-small);
	}
	.phase-event-list {
		max-height: 520px;
		padding-right: 4px;
		overflow-y: auto;
		scrollbar-color: #3b4352 transparent;
	}
	.filters {
		display: flex;
		gap: 5px;
		margin-top: 12px;
	}
	.filters button {
		min-height: 36px;
		padding: 6px 8px;
		color: var(--muted);
		background: rgba(255, 255, 255, 0.03);
		border: 1px solid var(--line);
		border-radius: 6px;
		font-size: var(--text-meta);
	}
	.filters button:hover {
		color: #fff;
		border-color: color-mix(in srgb, var(--filter-color, var(--blue)) 34%, transparent);
	}
	.filters button.active {
		color: #fff;
		background: color-mix(in srgb, var(--filter-color, var(--blue)) 16%, transparent);
		border-color: color-mix(in srgb, var(--filter-color, var(--blue)) 48%, transparent);
	}
	.filters .filter-all {
		--filter-color: var(--muted-strong);
	}
	.filters .filter-control {
		--filter-color: var(--event-control);
	}
	.filters .filter-overtake {
		--filter-color: var(--event-overtake);
	}
	.filters .filter-pit {
		--filter-color: var(--event-pit);
	}
	.filters .filter-radio {
		--filter-color: var(--event-radio);
	}
	.filters span {
		margin-left: 5px;
		color: var(--filter-color, inherit);
	}
	.event-rail-scroll {
		min-width: 0;
		overflow-x: auto;
		scrollbar-color: #495365 transparent;
	}
	.event-rail {
		position: relative;
		margin: 12px 22px 4px;
		padding: 7px 0 20px;
	}
	.rail-scroll-hint {
		display: none;
	}
	.event-rail > button {
		position: relative;
		width: 100%;
		height: 44px;
		padding: 0;
		background: transparent;
		border: 0;
	}
	.event-rail > button::before {
		position: absolute;
		inset: 19px 0;
		background: #29313e;
		border-radius: 3px;
		content: '';
	}
	.elapsed {
		position: absolute;
		inset: 19px auto 19px 0;
		background: linear-gradient(90deg, #b74f5b, #ea7180);
		border-radius: 3px;
	}
	.playhead {
		position: absolute;
		top: 50%;
		width: 3px;
		height: 34px;
		background: #fff;
		border-radius: 2px;
		box-shadow:
			0 0 0 4px rgba(255, 255, 255, 0.12),
			0 0 12px rgba(255, 255, 255, 0.3);
		transform: translate(-50%, -50%);
	}
	.markers {
		position: absolute;
		inset: 7px 0 auto;
		height: 44px;
		overflow: visible;
		pointer-events: none;
	}
	.markers button {
		--marker-color: var(--event-control);
		position: absolute;
		top: 50%;
		width: 44px;
		height: 44px;
		padding: 0;
		background: transparent;
		border: 0;
		color: var(--marker-color);
		pointer-events: auto;
		transform: translate(-50%, -50%);
	}
	.marker-symbol {
		display: grid;
		place-items: center;
		width: 10px;
		height: 10px;
		margin: auto;
		background: #151b24;
		border: 2px solid var(--marker-color);
		border-radius: 50%;
		box-shadow: 0 0 0 3px #111720;
	}
	.markers button.multiple .marker-symbol {
		width: 26px;
		height: 22px;
		border-radius: 12px;
		font:
			700 10px/1 Consolas,
			monospace;
	}
	.markers button:hover .marker-symbol,
	.markers button.selected .marker-symbol {
		background: color-mix(in srgb, var(--marker-color) 24%, #151b24);
		box-shadow: 0 0 0 4px color-mix(in srgb, var(--marker-color) 16%, transparent);
	}
	.markers .overtake {
		--marker-color: var(--event-overtake);
	}
	.markers .pit {
		--marker-color: var(--event-pit);
	}
	.markers .radio {
		--marker-color: var(--event-radio);
	}
	.markers .past .marker-symbol {
		background: color-mix(in srgb, var(--marker-color) 25%, #151b24);
	}
	.rail-scale {
		display: flex;
		justify-content: space-between;
		margin-top: 1px;
		color: var(--muted);
		font-size: var(--text-caption);
		letter-spacing: 0.08em;
	}
	.marker-choices {
		margin: 8px 0 4px;
		padding: 11px;
		background: #111923;
		border: 1px solid var(--line-strong);
		border-radius: 8px;
	}
	.marker-choices-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		margin-bottom: 9px;
	}
	.marker-choices-head strong,
	.marker-choices-head span {
		display: block;
	}
	.marker-choices-head strong {
		font-size: var(--text-small);
	}
	.marker-choices-head span {
		margin-top: 2px;
		color: var(--muted);
		font-size: var(--text-meta);
	}
	.marker-choices-head button {
		min-height: 32px;
		padding: 5px 10px;
		color: var(--muted-strong);
		background: transparent;
		border: 1px solid var(--line);
		border-radius: 5px;
	}
	.marker-choices-list {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 6px;
		max-height: 264px;
		overflow-y: auto;
	}
	.marker-choices-list .event {
		width: 100%;
	}
	.event-list {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 8px;
		margin-top: 10px;
	}
	.event {
		--event-color: var(--event-control);
		display: grid;
		grid-template-columns: 8px 64px minmax(0, 1fr) auto;
		align-items: center;
		min-width: 0;
		min-height: 52px;
		padding: 9px;
		color: inherit;
		background: color-mix(in srgb, var(--event-color) 4%, transparent);
		border: 1px solid var(--line);
		border-left: 3px solid var(--event-color);
		border-radius: 7px;
		text-align: left;
	}
	.event:hover,
	.event.current {
		background: color-mix(in srgb, var(--event-color) 12%, transparent);
		border-color: color-mix(in srgb, var(--event-color) 40%, transparent);
		border-left-color: var(--event-color);
	}
	.event.current {
		box-shadow: 0 0 12px color-mix(in srgb, var(--event-color) 8%, transparent);
	}
	.event > i {
		width: 6px;
		height: 6px;
		background: var(--event-color);
		border-radius: 50%;
		box-shadow: 0 0 5px var(--event-color);
	}
	.event.overtake {
		--event-color: var(--event-overtake);
	}
	.event.pit {
		--event-color: var(--event-pit);
	}
	.event.radio {
		--event-color: var(--event-radio);
	}
	.event time {
		color: var(--muted);
		font: var(--text-meta) Consolas;
	}
	.event > span {
		min-width: 0;
	}
	.event strong,
	.event small {
		display: block;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.event strong {
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		font-size: var(--text-small);
		line-height: 1.35;
	}
	.event small {
		margin-top: 3px;
		color: var(--muted);
		font-size: var(--text-meta);
		line-height: 1.45;
		white-space: normal;
	}
	@media (max-width: 800px) {
		.event-rail {
			min-width: 1400px;
		}
		.rail-scroll-hint {
			display: block;
			margin: 2px 0 0;
			color: var(--muted);
			font-size: var(--text-caption);
		}
		.event-list,
		.marker-choices-list {
			grid-template-columns: 1fr;
		}
	}
	.event b {
		color: var(--event-color);
		font-size: var(--text-caption);
	}
	.empty-state {
		grid-column: 1/-1;
		color: var(--muted);
		font-size: var(--text-small);
		text-align: center;
	}
	.radio-player {
		display: none;
		grid-template-columns: minmax(170px, 0.7fr) minmax(360px, 1.3fr) auto;
		align-items: center;
		gap: 12px;
		margin-top: 12px;
		padding: 8px 10px;
		background: linear-gradient(90deg, rgba(194, 139, 255, 0.12), rgba(97, 70, 128, 0.05)), #10141b;
		border: 1px solid rgba(194, 139, 255, 0.28);
		border-left: 3px solid var(--purple);
		border-radius: 8px;
	}
	.radio-player.visible {
		display: grid;
		position: sticky;
		z-index: 10;
		bottom: 12px;
		box-shadow: 0 14px 36px rgba(0, 0, 0, 0.42);
	}
	.radio-player strong {
		display: block;
		margin-top: 3px;
		font-size: var(--text-small);
	}
	.radio-player small {
		display: block;
		color: #ff8b9b;
		font-size: var(--text-meta);
	}
	.radio-copy {
		min-width: 0;
	}
	.radio-copy strong {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.custom-audio-controls {
		display: grid;
		grid-template-columns: 38px auto minmax(120px, 1fr) auto;
		align-items: center;
		gap: 10px;
		min-width: 0;
		padding: 5px 7px;
		background: rgba(5, 7, 11, 0.46);
		border: 1px solid rgba(194, 139, 255, 0.18);
		border-radius: 8px;
	}
	.custom-audio-controls button {
		min-height: 34px;
		color: var(--muted-strong);
		background: rgba(255, 255, 255, 0.045);
		border: 1px solid var(--line);
		border-radius: 6px;
	}
	.custom-audio-controls button:hover {
		color: #fff;
		background: var(--purple-soft);
		border-color: rgba(194, 139, 255, 0.32);
	}
	.custom-audio-controls .radio-play {
		width: 38px;
		padding: 0;
		color: #fff;
		background: var(--purple);
		border-color: var(--purple);
		font-size: var(--text-small);
	}
	.custom-audio-controls time {
		min-width: 72px;
		color: var(--muted-strong);
		font:
			var(--text-meta) Consolas,
			monospace;
		white-space: nowrap;
	}
	.radio-progress {
		width: 100%;
		min-width: 0;
		accent-color: var(--purple);
		cursor: pointer;
	}
	.radio-progress:disabled {
		cursor: wait;
		opacity: 0.5;
	}
	.custom-audio-controls .radio-volume {
		padding: 0 9px;
		font-size: var(--text-caption);
		font-weight: 750;
		letter-spacing: 0.06em;
	}
	.radio-engine {
		display: none;
	}
	.radio-close {
		width: 36px;
		height: 36px;
		color: var(--muted);
		background: none;
		border: 0;
		border-radius: 6px;
		font-size: 18px;
	}
	.radio-close:hover {
		color: #fff;
		background: rgba(255, 255, 255, 0.06);
	}
	footer {
		display: flex;
		justify-content: space-between;
		padding: 11px 2px 0;
		color: var(--muted);
		font-size: var(--text-caption);
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
		transition:
			color 0.16s ease,
			background 0.16s ease,
			border-color 0.16s ease,
			box-shadow 0.16s ease;
	}
	.playback button,
	.lap-controls button,
	.filters button,
	.track-actions button,
	.custom-audio-controls button,
	.race-picker select {
		border-radius: var(--ui-control-radius);
		min-height: var(--ui-control-height);
	}
	button:focus-visible,
	a:focus-visible,
	select:focus-visible,
	input:focus-visible {
		outline: 2px solid var(--ui-focus);
		outline-offset: 2px;
	}
	@media (max-width: 1120px) {
		.session-bar {
			grid-template-columns: minmax(240px, 1fr) auto;
			gap: 10px 20px;
			padding-block: 10px;
		}
		.session-facts {
			grid-column: 1 / -1;
			justify-content: flex-start;
		}
		.replay-grid {
			grid-template-areas:
				'weather weather'
				'timing center'
				'driver driver';
			grid-template-columns: 240px minmax(0, 1fr);
			grid-template-rows: auto 1fr auto;
		}
		.driver-panel {
			grid-column: auto;
		}
		.driver-empty {
			min-height: 190px;
		}
		.session-facts div:nth-child(3) {
			display: none;
		}
	}
	@media (max-width: 800px) {
		.playback button,
		.lap-controls button,
		.filters button,
		.track-actions button,
		.custom-audio-controls button,
		.timing-toggle,
		.race-picker select {
			min-height: 44px;
		}
		.topbar {
			padding: 0 14px;
		}
		.snapshot {
			font-size: var(--text-caption);
		}
		main {
			padding: 10px;
		}
		.session-bar {
			display: grid;
			grid-template-columns: minmax(0, 1fr) auto;
			align-items: flex-start;
			gap: 10px;
		}
		.event-title {
			min-width: 0;
		}
		.session-facts {
			grid-column: 1 / -1;
			grid-row: 2;
			width: 100%;
			margin: 0;
			justify-content: space-between;
		}
		.race-picker {
			margin-left: 0;
		}
		.replay-grid {
			display: flex;
			flex-direction: column;
		}
		.center-stage {
			order: 2;
			grid-template-rows: auto auto;
		}
		.timing-panel {
			order: 3;
		}
		.driver-panel {
			order: 4;
		}
		.weather-panel {
			order: 1;
		}
		.weather-metrics {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
		.weather-metrics > div:nth-child(4) {
			border-left: 0;
			border-top: 1px solid var(--line);
		}
		.weather-metrics > div:nth-child(5),
		.weather-metrics > div:nth-child(6) {
			border-top: 1px solid var(--line);
		}
		.circuit {
			min-height: 430px;
		}
		.timing-panel ol {
			display: none;
			grid-template-columns: 1fr 1fr;
			max-height: none;
		}
		.timing-panel.expanded ol {
			display: grid;
		}
		.timing-panel:not(.expanded) .tower-footer {
			display: none;
		}
		.timing-toggle {
			display: block;
		}
		.panel-head-actions > b {
			display: none;
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
		.custom-audio-controls {
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
			font-size: 20px;
		}
		.race-picker {
			grid-column: 1 / -1;
			grid-row: 2;
			width: 100%;
			margin: 0;
		}
		.session-facts {
			grid-row: 3;
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
		.weather-metrics {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.weather-metrics > div {
			border-left: 1px solid var(--line);
		}
		.weather-metrics > div:nth-child(odd) {
			border-left: 0;
		}
		.weather-metrics > div:nth-child(n + 3) {
			border-top: 1px solid var(--line);
		}
		footer.weather-source {
			align-items: flex-start;
			flex-direction: column;
			gap: 5px;
		}
		.control-deck {
			grid-template-columns: 1fr auto;
			padding: 9px;
		}
		.playback {
			grid-column: 1 / -1;
		}
		.scrubber {
			grid-row: auto;
		}
		.lap-controls {
			grid-column: 1;
		}
		.speed-control {
			grid-column: 2;
		}
		.event-list {
			grid-template-columns: 1fr;
		}
		.custom-audio-controls {
			grid-template-columns: 38px 1fr auto;
		}
		.radio-progress {
			grid-column: 1 / -1;
			grid-row: 2;
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
