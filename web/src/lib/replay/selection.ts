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
