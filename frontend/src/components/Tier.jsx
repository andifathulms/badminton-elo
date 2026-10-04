// Tournament tier chip. World Tour levels get strength bars (1–5) so a Super 300
// can't be mistaken for a Super 1000; majors (Worlds/Olympics) are gold.
export function tierOf(category = '') {
  const t = category || ''
  if (/Grade 1|Olympic|World Championships/i.test(t)) return { label: 'Major', bars: 5, major: true }
  if (/Super 1000/.test(t)) return { label: 'Super 1000', bars: 5 }
  if (/Super 750/.test(t)) return { label: 'Super 750', bars: 4 }
  if (/Super 500/.test(t)) return { label: 'Super 500', bars: 3 }
  if (/Super 300/.test(t)) return { label: 'Super 300', bars: 2 }
  if (/Super 100/.test(t)) return { label: 'Super 100', bars: 1 }
  if (/World Tour Finals/i.test(t)) return { label: 'Finals', bars: 5, major: true }
  if (/Team/i.test(t)) return { label: 'Team event', bars: 0 }
  if (/Challenge/i.test(t)) return { label: 'Challenge', bars: 0 }
  if (/International Series/i.test(t)) return { label: 'Series', bars: 0 }
  if (/Future/i.test(t)) return { label: 'Future', bars: 0 }
  if (/Junior|U\d\d/i.test(t)) return { label: 'Junior', bars: 0 }
  return { label: t.replace(/^HSBC BWF World Tour /, '').replace(/^BWF /, '') || 'Other', bars: 0 }
}

export default function Tier({ category, title }) {
  const t = tierOf(category)
  return (
    <span className={`tier${t.major ? ' major' : ''}`} title={title || category || undefined}>
      {t.bars > 0 && (
        <span className="tier-bars" aria-hidden="true">
          {[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= t.bars ? 'f' : ''} />)}
        </span>
      )}
      {t.label}
    </span>
  )
}
