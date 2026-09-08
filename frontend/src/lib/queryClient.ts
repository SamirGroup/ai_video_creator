import { QueryClient } from '@tanstack/react-query'

/**
 * Central QueryClient (TanStack Query = server state, per project profile).
 * Defaults tuned for a dashboard: data is not hyper-real-time, so we avoid
 * refetch storms on window focus, but keep a short staleTime so navigating
 * back to a screen shows fresh-enough data without a duplicate request.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        const status = (error as { status?: number }).status
        // Don't retry on client errors (4xx) — only transient/server errors.
        if (status && status >= 400 && status < 500) return false
        return failureCount < 2
      },
    },
    mutations: {
      retry: false,
    },
  },
})
