// Top-down badminton court at true proportions (13.4 m × 6.1 m, 100 units/m):
// doubles + singles sidelines, short service lines 1.98 m from the net,
// doubles long service lines 0.76 m from the back, centre lines and the net.
export default function CourtLines({ className = 'court-lines' }) {
  return (
    <svg className={className} viewBox="-10 -10 1360 630" aria-hidden="true">
      <rect x="0" y="0" width="1340" height="610" />
      <line x1="0" y1="46" x2="1340" y2="46" />
      <line x1="0" y1="564" x2="1340" y2="564" />
      <line x1="670" y1="-10" x2="670" y2="620" style={{ strokeWidth: 9 }} />
      <line x1="472" y1="0" x2="472" y2="610" />
      <line x1="868" y1="0" x2="868" y2="610" />
      <line x1="76" y1="0" x2="76" y2="610" />
      <line x1="1264" y1="0" x2="1264" y2="610" />
      <line x1="0" y1="305" x2="472" y2="305" />
      <line x1="868" y1="305" x2="1340" y2="305" />
    </svg>
  )
}
