export type NullableNumber = number | null;

export type RaceSummary = {
	key: string;
	season: number;
	round: number;
	race_name: string;
	race_date: string;
	circuit_name: string;
	country: string;
	driver_count: number;
	duration_s: number;
	position_rows: number;
	race_control_count: number;
	overtake_count: number;
	radio_count: number;
	pre_race_radio_count: number;
	race_radio_count: number;
	post_race_radio_count: number;
	weather_sample_count: number;
	bundle_url: string;
	positions_url: string;
};

export type ReplayManifest = {
	schema_version: number;
	default_race: string;
	snapshot: { version: string | null; generated_at: string | null; sha256: string | null };
	races: RaceSummary[];
};

export type DriverMeta = {
	driver_code: string;
	driver_name: string;
	team: string | null;
	team_color: string;
	grid_position: NullableNumber;
	finish_position: NullableNumber;
	status: string | null;
	is_classified: boolean | null;
};

export type LapRow = {
	pit_entry_t_s?: NullableNumber;
	pit_exit_t_s?: NullableNumber;
	driver_code: string;
	lap_number: number;
	lap_start_t_s: number;
	lap_time_sec: NullableNumber;
	stint: NullableNumber;
	compound: string | null;
	tyre_life: NullableNumber;
};

export type RaceControlRow = {
	t_s: number;
	category: string | null;
	flag: string | null;
	scope: string | null;
	message: string;
	driver_code: string | null;
};

export type RadioPhase = 'pre-race' | 'race' | 'post-race';

export type RadioRow = {
	t_s: number;
	driver_code: string;
	recording_url: string;
	transcript: string | null;
	phase: RadioPhase;
};

export type WeatherRow = {
	t_s: number;
	air_temperature: NullableNumber;
	track_temperature: NullableNumber;
	humidity: NullableNumber;
	pressure: NullableNumber;
	rainfall: boolean | null;
	wind_direction: NullableNumber;
	wind_speed: NullableNumber;
};

export type OvertakeRow = {
	t_s: number;
	for_position: NullableNumber;
	passer_code: string;
	passed_code: string;
	gap_at_pass_s: NullableNumber;
	confidence: NullableNumber;
	evidence: string | null;
	reason: string | null;
};

export type RaceBundle = {
	race: {
		season: number;
		round: number;
		race_name: string;
		race_date: string;
		circuit_name: string;
		country: string;
		locality: string;
	};
	drivers: DriverMeta[];
	laps: LapRow[];
	race_control: RaceControlRow[];
	radio: RadioRow[];
	weather: WeatherRow[];
	overtakes: OvertakeRow[];
};

export type PositionRow = {
	running_order_source?: string | null;
	gap_source?: string | null;
	driver_code: string;
	t_s: number;
	x: number;
	y: number;
	running_order: NullableNumber;
	gap_to_leader_s: NullableNumber;
	gap_to_ahead_s: NullableNumber;
};

export type ReplaySample = {
	orderSource?: string | null;
	gapSource?: string | null;
	t: number;
	x: number;
	y: number;
	order: NullableNumber;
	gap: NullableNumber;
	ahead: NullableNumber;
	lap: NullableNumber;
	lapProgress: NullableNumber;
	stint: NullableNumber;
	compound: string | null;
	tyreLife: NullableNumber;
};

export type ReplayDriver = {
	code: string;
	name: string;
	team: string;
	color: string;
	startOrder: NullableNumber;
	finishPosition: NullableNumber;
	isClassified: boolean | null;
	resultStatus: string | null;
	tmin: number;
	tmax: number;
	samples: ReplaySample[];
	pitWindows: PitWindow[];
};

export type PitVisit = {
	id: string;
	driver: string;
	lap: number;
	entry: number | null;
	exit: number | null;
	window: PitWindow | null;
	source: 'recorded' | 'estimated' | 'incomplete';
	fromCompound: string | null;
	toCompound: string | null;
	tyreChange: boolean;
	raw: LapRow;
};

export type PitWindow = { start: number; stop: number; end: number };

export type PitLaneProfile = {
	entryProgress: number;
	exitProgress: number;
	entryLeadSeconds: number;
	exitLagSeconds: number;
};

export type TrackPoint = { x: number; y: number };

export type TrackPath = {
	points: TrackPoint[];
	cumulative: number[];
	length: number;
};

export type PitLanePath = TrackPath & {
	box: TrackPoint;
	entryProgress: number;
	exitProgress: number;
};

export type TimingRow = {
	orderSource?: string | null;
	gapSource?: string | null;
	code: string;
	name: string;
	team: string;
	color: string;
	order: NullableNumber;
	gap: NullableNumber;
	ahead: NullableNumber;
	lap: NullableNumber;
	lapProgress: NullableNumber;
	stint: NullableNumber;
	compound: string | null;
	tyreLife: NullableNumber;
	stops: NullableNumber;
	positionChange: NullableNumber;
	status: 'racing' | 'classified' | 'not classified' | 'out';
};

export type ReplayEvent = {
	id: string;
	time: number;
	pitVisit?: PitVisit;
	type: 'control' | 'overtake' | 'pit' | 'radio';
	subtype: string;
	label: string;
	meta: string;
	participants: string[];
	raw: RaceControlRow | RadioRow | OvertakeRow | LapRow;
};

export type LoadedRace = {
	summary: RaceSummary;
	bundle: RaceBundle;
	positions: PositionRow[];
};
