import { useEffect, useRef, useState } from 'react'

// Animates a number up to `value` (easeOutCubic) the first time it appears and
// whenever it changes. Respects prefers-reduced-motion (renders the final value
// instantly). `format` maps the in-flight number to display text.
export default function CountUp({
  value,
  duration = 900,
  format = (n) => Math.round(n).toLocaleString(),
  className,
}) {
  const [display, setDisplay] = useState(value ?? 0)
  const fromRef = useRef(0)

  useEffect(() => {
    if (value == null) return
    const reduced =
      window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) { setDisplay(value); fromRef.current = value; return }

    const from = fromRef.current
    const start = performance.now()
    let raf
    const tick = (t) => {
      const p = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setDisplay(from + (value - from) * eased)
      if (p < 1) raf = requestAnimationFrame(tick)
      else fromRef.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, duration])

  return <span className={className}>{format(display)}</span>
}
