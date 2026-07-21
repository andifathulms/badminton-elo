import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import Entity, { fmtScore } from './Entity.jsx'

// The biggest-upsets table, shared by the dashboard and the Insights page so
// both read identically. Columns: gained · winner · opponent · score ·
// tournament · round · category. When `expandable` is set, each row toggles a
// detail row rendered by `renderExpand(row)`.
export default function UpsetsTable({ rows, expandable = false, renderExpand }) {
  const [open, setOpen] = useState(null)
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
            const isOpen = expandable && open === rkey
            const stop = (e) => e.stopPropagation()
            return (
              <Fragment key={rkey}>
                <tr
                  className={expandable ? 'expandable' : undefined}
                  onClick={expandable ? () => setOpen(isOpen ? null : rkey) : undefined}
                >
                  <td className="num">
                    {expandable && <span className="caret">{isOpen ? '▾' : '▸'}</span>}{' '}
                    {row.best_match ? (
                      <Link to={`/matches/${row.best_match}`} className="up-delta pos"
                        onClick={stop}>+{row.best_delta.toFixed(0)}</Link>
                    ) : (
                      <span className="up-delta pos">+{row.best_delta.toFixed(0)}</span>
                    )}
                  </td>
                  <td>
                    <Entity players={winners} event={row.event}
                      rating={row.winner_rating_before} />
                  </td>
                  <td>
                    <Entity players={row.beat} event={row.event}
                      rating={row.opponent_rating_before} />
                  </td>
                  <td className="score-cell">
                    {abnormal
                      ? <span className="pill warn tiny">{row.best_score_status}</span>
                      : <span className="score-mono">{fmtScore(row.best_score)}</span>}
                  </td>
                  <td className="tour-cell">
                    <Link to={`/tournaments/${row.tournament.tournament_id}`}
                      className="tour-link" onClick={stop}>{row.tournament.name}</Link>
                  </td>
                  <td className="rnd muted">{row.best_round || '—'}</td>
                  <td className="cat"><span className="pill ghost">{row.event}</span></td>
                </tr>
                {isOpen && renderExpand && (
                  <tr className="expand-row"><td colSpan={7}>{renderExpand(row)}</td></tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
