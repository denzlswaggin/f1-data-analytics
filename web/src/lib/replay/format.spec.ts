import { describe, expect, it } from 'vitest';
import {
	compassDirection,
	compoundCode,
	formatClock,
	formatDate,
	formatGap,
	formatWeather
} from './format';

describe('replay formatting', () => {
	it('formats race clocks and gaps', () => {
		expect(formatClock(65.9)).toBe('1:05');
		expect(formatClock(3665)).toBe('1:01:05');
		expect(formatGap(1.23456)).toBe('+1.235');
		expect(formatGap(0, true)).toBe('LEADER');
	});

	it('formats compact replay labels', () => {
		expect(compoundCode('MEDIUM')).toBe('M');
		expect(compassDirection(359)).toBe('N');
		expect(formatWeather(22.345, '°C')).toBe('22.3°C');
		expect(formatDate('2026-08-23T23:00:00-02:00')).toBe('24 Aug 2026');
	});
});
