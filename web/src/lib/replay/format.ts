/** Pure presentation helpers shared by replay surfaces. */

export function formatClock(seconds: number) {
	const value = Math.max(0, Math.floor(seconds || 0));
	const hours = Math.floor(value / 3600);
	const minutes = Math.floor((value % 3600) / 60);
	const secs = value % 60;
	return hours
		? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
		: `${minutes}:${String(secs).padStart(2, '0')}`;
}

export function formatGap(value: number | null, leader = false) {
	if (value == null) return '—';
	if (value <= 0) return leader ? 'LEADER' : '—';
	return `+${value.toFixed(3)}`;
}

export function compoundCode(value: string | null) {
	return value ? value[0].toUpperCase() : '—';
}

export function formatDate(value: string | null | undefined) {
	if (!value) return 'unknown';
	return new Intl.DateTimeFormat('en-GB', {
		day: '2-digit',
		month: 'short',
		year: 'numeric',
		timeZone: 'UTC'
	}).format(new Date(value));
}

export function formatWeather(value: number | null, unit: string, digits = 1) {
	return value == null ? '—' : `${value.toFixed(digits)}${unit}`;
}

export function compassDirection(value: number | null) {
	if (value == null) return '—';
	const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
	return directions[Math.round((((value % 360) + 360) % 360) / 45) % directions.length];
}
