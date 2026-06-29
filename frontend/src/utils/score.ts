// Single source of truth for opportunity score bands (spec doc04 §14).
// Thresholds: >=80 High, 50-79 Medium, <50 Low. Mirrors backend app/core/scoring.py.
export const SCORE_HIGH_MIN = 80;
export const SCORE_MEDIUM_MIN = 50;

export type ScoreBand = 'high' | 'medium' | 'low';

export const scoreBand = (score?: number | null): ScoreBand => {
  const value = score ?? 0;
  if (value >= SCORE_HIGH_MIN) return 'high';
  if (value >= SCORE_MEDIUM_MIN) return 'medium';
  return 'low';
};
