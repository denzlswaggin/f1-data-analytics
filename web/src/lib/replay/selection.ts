export function latestRaceForSeason<T extends { season: number; round: number }>(
	races: readonly T[],
	season: number
): T | undefined {
	return races.reduce<T | undefined>(
		(latest, race) =>
			race.season === season && (!latest || race.round > latest.round) ? race : latest,
		undefined
	);
}

export function initialRace<T extends { key: string; season: number; round: number }>(
	races: readonly T[],
	defaultKey: string,
	params: URLSearchParams
): T {
	const seasonParam = params.get('season');
	const roundParam = params.get('race') ?? params.get('round');
	let selected: T | undefined;
	if (seasonParam !== null || roundParam !== null) {
		const season = Number(seasonParam);
		const round = Number(roundParam);
		selected =
			roundParam === null
				? latestRaceForSeason(races, season)
				: races.find((race) => race.season === season && race.round === round);
		if (!selected)
			throw new Error(
				'Replay data is unavailable for the requested race. Open the race overview to choose another race.'
			);
	} else {
		selected = races.find((race) => race.key === defaultKey) ?? races[0];
	}
	if (!selected) throw new Error('No replay races are available in this snapshot.');
	return selected;
}
