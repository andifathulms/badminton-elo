import { Link, useNavigate } from 'react-router-dom'
import Entity, { fmtScore } from './Entity.jsx'

// The biggest-upsets table, shared by the dashboard and the Insights page so
// both read identically. Columns: gained · winner · opponent · score ·
// tournament · round · category. Clicking a row opens that match; the winner,
// opponent and tournament cells keep their own links.
export default function UpsetsTable({ rows }) {
  const navigate = useNavigate()
  const stop = (e) => e.stopPropagation()
  return (
    <div className="table-scroll">
      <table className="board upset-table">
        <thead>
          <tr>
            <th className="num" title="Elo gained from this win">Gained</th>
            <th>Winner</th>
            <th>Opponent</th>
            <th>Score</th>
            <th>Tournament</th>
            <th className="rnd">Round</th>
            <th className="cat">Cat</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const winners = [row.player, row.partner].filter(Boolean)
            const abnormal =
              row.best_score_status && row.best_score_status !== 'Normal'
            const rkey = `${row.player.player_id}-${row.tournament.tournament_id}-${row.event}`
            const openMatch = row.best_match
              ? () => navigate(`/matches/${row.best_match}`)
              : undefined
            return (
              <tr key={rkey} className={openMatch ? 'row-link' : undefined}
                onClick={openMatch}>
                <td className="num">
                  <span className="up-delta pos">+{row.best_delta.toFixed(0)}</span>
                </td>
                <td onClick={stop}>
                  <Entity players={winners} event={row.event}
                    rating={row.winner_rating_before} />
                </td>
                <td onClick={stop}>
                  <Entity players={row.beat} event={row.event}
                    rating={row.opponent_rating_before} />
                </td>
                <td className="score-cell">
                  {abnormal
                    ? <span className="pill warn tiny">{row.best_score_status}</span>
                    : <span className="score-mono">{fmtScore(row.best_score)}</span>}
                </td>
                <td className="tour-cell" onClick={stop}>
                  <Link to={`/tournaments/${row.tournament.tournament_id}`}
                    className="tour-link">{row.tournament.name}</Link>
                </td>
                <td className="rnd muted">{row.best_round || '—'}</td>
                <td className="cat"><span className="pill ghost">{row.event}</span></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
