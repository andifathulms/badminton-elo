// Date helpers for ISO "YYYY-MM-DD" strings (tournament dates are dates, not
// instants, so compare as strings and format without timezone shifts).
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function today() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

// "17 Aug", "17 Aug 2026"
export function fmtDay(s, withYear = false) {
  if (!s) return ''
  const [y, m, d] = s.slice(0, 10).split('-')
  return `${+d} ${MON[+m - 1]}${withYear ? ` ${y}` : ''}`
}

// "17–23 Aug", "28 Jul – 2 Aug", optionally with the year.
export function fmtRange(s, e, withYear = false) {
  if (!s) return ''
  if (!e || e === s) return fmtDay(s, withYear)
  const [y1, m1, d1] = s.split('-')
  const [y2, m2, d2] = e.split('-')
  const yr = withYear ? ` ${y2}` : ''
  if (y1 === y2 && m1 === m2) return `${+d1}–${+d2} ${MON[+m2 - 1]}${yr}`
  return `${fmtDay(s, y1 !== y2 && withYear)} – ${fmtDay(e)}${yr}`
}

export const isLive = (t) => !!t?.start_date && t.start_date <= today() && (t.end_date || t.start_date) >= today()

// "Aug 2026" from an ISO date/datetime.
export function fmtMonth(s) {
  if (!s) return ''
  const [y, m] = s.slice(0, 7).split('-')
  return `${MON[+m - 1]} ${y}`
}
