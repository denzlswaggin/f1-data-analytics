export function sourceLabel(source: string | null | undefined): string {
    if (source === 'openf1_recorded') return 'Recorded OpenF1 sample aligned to the race clock';
    if (source === 'lap_progress_estimate') return 'Estimated from lap-progress timing';
    return 'Source unavailable in this bundle';
}

export function sourceMarker(source: string | null | undefined): string {
    if (source === 'openf1_recorded') return '';
    if (source === 'lap_progress_estimate') return '\u2248';
    return '?';
}
