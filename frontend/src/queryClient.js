import { QueryClient } from '@tanstack/react-query'

// One cache for every API read. Data only changes when the backend re-rates
// (and the server revalidates with ETags anyway), so results stay fresh for a
// minute and are kept for ten — moving back and forth between pages is
// instant, and identical requests in flight are shared.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      gcTime: 10 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})
