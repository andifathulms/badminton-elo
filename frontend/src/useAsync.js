import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { withSignal } from './api.js'

// Async-data hook: returns { data, error, loading, fetching, reload }.
//
// Backed by TanStack Query, so every page gets caching across navigation,
// de-duplication of identical in-flight requests, cancellation on unmount, and
// the previous data kept on screen while a filter/page change loads (instead
// of blanking the view). The cache key is the fetcher's source plus `deps`:
// the same contract as before — `deps` must list everything `fn` reads.
// `reload()` refetches on demand (retry buttons).
export function useAsync(fn, deps) {
  const q = useQuery({
    queryKey: ['useAsync', fn.toString(), ...deps],
    // TanStack rejects `undefined` results; old fetchers sometimes return it.
    queryFn: ({ signal }) => Promise.resolve(withSignal(signal, fn)).then((d) => d ?? null),
    placeholderData: keepPreviousData,
  })
  return {
    data: q.data ?? null,
    error: q.error ?? null,
    loading: q.isPending,
    fetching: q.isFetching,
    reload: () => q.refetch(),
  }
}
