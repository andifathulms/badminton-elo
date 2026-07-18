import React from 'react'
import ReactDOM from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import App from './App.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Leaderboard from './pages/Leaderboard.jsx'
import Player from './pages/Player.jsx'
import Match from './pages/Match.jsx'
import Tournaments from './pages/Tournaments.jsx'
import Tournament from './pages/Tournament.jsx'
import Insights from './pages/Insights.jsx'
import PairDetail from './pages/PairDetail.jsx'
import './styles.css'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'rankings', element: <Leaderboard /> },
      { path: 'players/:id', element: <Player /> },
      { path: 'matches/:id', element: <Match /> },
      { path: 'tournaments', element: <Tournaments /> },
      { path: 'tournaments/:id', element: <Tournament /> },
      { path: 'insights', element: <Insights /> },
      { path: 'pairs/:event/:p1/:p2', element: <PairDetail /> },
    ],
  },
])

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
)
