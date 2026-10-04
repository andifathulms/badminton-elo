// Rating confidence from the Glicko-2 rating deviation (rd). A low rd means the
// engine has seen enough of a player for a settled estimate; a high rd (a debut
// or long-inactive player) means the rating is still provisional. The public
// rating is already conservative (mu − 2·rd), so 2·rd is the ± uncertainty on it.
export function confidence(rd) {
  if (rd == null) return { level: 'unknown', label: 'Unknown', bars: 0 }
  if (rd < 80) return { level: 'high', label: 'Settled', bars: 3 }
  if (rd < 130) return { level: 'medium', label: 'Firming up', bars: 2 }
  return { level: 'low', label: 'Provisional', bars: 1 }
}

// ± points of uncertainty on the conservative rating.
export const uncertainty = (rd) => (rd == null ? null : Math.round(2 * rd))
