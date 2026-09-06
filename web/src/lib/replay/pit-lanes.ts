import type { PitLaneProfile } from './types';

/**
 * Pit-entry/pit-exit geometry and median traversal timing measured from the
 * position feed plus FastF1 PitInTime/PitOutTime in every published replay race.
 * Keeping these per circuit matters especially at Monaco, Montreal and Albert
 * Park, where the pit timing line is reached much earlier than on most circuits.
 */
const PIT_LANE_PROFILES: Record<string, PitLaneProfile> = {
	'albert park grand prix circuit': {
		entryProgress: 0.9525,
		exitProgress: 0.01,
		entryLeadSeconds: 16.83,
		exitLagSeconds: 2.3
	},
	'autodromo enzo e dino ferrari': {
		entryProgress: 0.9679,
		exitProgress: 0.0859,
		entryLeadSeconds: 4.39,
		exitLagSeconds: 25.93
	},
	'autodromo nazionale di monza': {
		entryProgress: 0.985,
		exitProgress: 0.0576,
		entryLeadSeconds: 3.71,
		exitLagSeconds: 21.19
	},
	'autodromo hermanos rodriguez': {
		entryProgress: 0.9813,
		exitProgress: 0.076,
		entryLeadSeconds: 2.61,
		exitLagSeconds: 20.04
	},
	'autodromo jose carlos pace': {
		entryProgress: 0.9778,
		exitProgress: 0.0721,
		entryLeadSeconds: 2.83,
		exitLagSeconds: 21.12
	},
	'bahrain international circuit': {
		entryProgress: 0.9821,
		exitProgress: 0.0626,
		entryLeadSeconds: 1.69,
		exitLagSeconds: 23.13
	},
	'baku city circuit': {
		entryProgress: 0.9979,
		exitProgress: 0.0471,
		entryLeadSeconds: 1.24,
		exitLagSeconds: 19.28
	},
	'circuit gilles villeneuve': {
		entryProgress: 0.9059,
		exitProgress: 0.01,
		entryLeadSeconds: 22.35,
		exitLagSeconds: 1.6
	},
	'circuit park zandvoort': {
		entryProgress: 0.985,
		exitProgress: 0.0621,
		entryLeadSeconds: 1.18,
		exitLagSeconds: 16.89
	},
	'circuit de barcelona-catalunya': {
		entryProgress: 0.9812,
		exitProgress: 0.0553,
		entryLeadSeconds: 2.71,
		exitLagSeconds: 19.68
	},
	'circuit de monaco': {
		entryProgress: 0.8892,
		exitProgress: 0.01,
		entryLeadSeconds: 23.43,
		exitLagSeconds: 0.78
	},
	'circuit de spa-francorchamps': {
		entryProgress: 0.9896,
		exitProgress: 0.0412,
		entryLeadSeconds: 3.72,
		exitLagSeconds: 20.05
	},
	'circuit of the americas': {
		entryProgress: 0.9877,
		exitProgress: 0.068,
		entryLeadSeconds: 0.85,
		exitLagSeconds: 23.09
	},
	hungaroring: {
		entryProgress: 0.96,
		exitProgress: 0.08,
		entryLeadSeconds: 1.68,
		exitLagSeconds: 20.14
	},
	'jeddah corniche circuit': {
		entryProgress: 0.9964,
		exitProgress: 0.0446,
		entryLeadSeconds: 0.95,
		exitLagSeconds: 19.74
	},
	'las vegas strip street circuit': {
		entryProgress: 0.9837,
		exitProgress: 0.0447,
		entryLeadSeconds: 2.91,
		exitLagSeconds: 18.72
	},
	'losail international circuit': {
		entryProgress: 0.984,
		exitProgress: 0.0782,
		entryLeadSeconds: 4.04,
		exitLagSeconds: 24.86
	},
	'marina bay street circuit': {
		entryProgress: 0.9716,
		exitProgress: 0.0473,
		entryLeadSeconds: 5.74,
		exitLagSeconds: 18.35
	},
	'miami international autodrome': {
		entryProgress: 0.9689,
		exitProgress: 0.0463,
		entryLeadSeconds: 5.39,
		exitLagSeconds: 17.28
	},
	'red bull ring': {
		entryProgress: 0.9631,
		exitProgress: 0.039,
		entryLeadSeconds: 3.68,
		exitLagSeconds: 17.96
	},
	'shanghai international circuit': {
		entryProgress: 0.9831,
		exitProgress: 0.0576,
		entryLeadSeconds: 1.7,
		exitLagSeconds: 21.26
	},
	'silverstone circuit': {
		entryProgress: 0.94,
		exitProgress: 0.0679,
		entryLeadSeconds: 5.9,
		exitLagSeconds: 23.25
	},
	'suzuka circuit': {
		entryProgress: 0.9867,
		exitProgress: 0.0567,
		entryLeadSeconds: 1.29,
		exitLagSeconds: 22.69
	},
	'yas marina circuit': {
		entryProgress: 0.9881,
		exitProgress: 0.0556,
		entryLeadSeconds: 0.96,
		exitLagSeconds: 20.78
	}
};

export const DEFAULT_PIT_LANE_PROFILE: PitLaneProfile = {
	entryProgress: 0.96,
	exitProgress: 0.18,
	entryLeadSeconds: 4,
	exitLagSeconds: 20
};

const normaliseCircuitName = (name: string) =>
	name
		.normalize('NFD')
		.replace(/\p{Diacritic}/gu, '')
		.toLowerCase()
		.trim();

export function pitLaneProfileFor(circuitName = ''): PitLaneProfile {
	return PIT_LANE_PROFILES[normaliseCircuitName(circuitName)] ?? DEFAULT_PIT_LANE_PROFILE;
}

export const supportedPitLaneCircuits = Object.freeze(Object.keys(PIT_LANE_PROFILES));
