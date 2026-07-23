import { useEffect, useState } from 'react'

// Tiny async-data hook: returns { data, error, loading, reload }. `deps` re-runs
// it; `reload()` re-runs on demand (for retry buttons).
export function useAsync(fn, deps) {
  const [nonce, setNonce] = useState(0)
  const [state, setState] = useState({ data: null, error: null, loading: true })
  useEffect(() => {
    let alive = true
    setState({ data: null, error: null, loading: true })
    Promise.resolve()
      .then(fn)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])
  return { ...state, reload: () => setNonce((n) => n + 1) }
}
