/**
 * TODO: real API — every page currently reads from `src/mocks/fixtures.ts`
 * through this helper instead of the modules in `src/api/*`. The backend
 * (`backend/`) is still being scaffolded in parallel; swapping a page over
 * once its endpoint is live is a one-line change: replace
 * `mockFetch(fixture)` with the matching `xyzApi.method(...)` call — the
 * TanStack Query hook, loading/error/empty rendering, and types don't change.
 */
export function mockFetch<T>(data: T, delayMs = 350): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(data), delayMs))
}
