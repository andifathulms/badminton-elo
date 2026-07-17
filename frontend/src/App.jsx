import { Link, Outlet } from 'react-router-dom'

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          🏸 Badminton Ratings
        </Link>
        <span className="tagline">Per-discipline skill ratings from BWF results</span>
      </header>
      <main className="content">
        <Outlet />
      </main>
      <footer className="footer">
        Ratings are Glicko-2-with-pairs over BWF tournament data. Conservative
        score = mu − 2·rd.
      </footer>
    </div>
  )
}
