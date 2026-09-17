import { apiClient } from './client'
import type { CursorPage } from '@/types/common'

/** Follow DRF cursors without trusting a response-provided host for authenticated requests. */
export async function collectPages<T>(path: string, params?: object): Promise<T[]> {
  const result: T[] = []
  const cursors = new Set<string>()
  let cursor: string | undefined
  do {
    const { data } = await apiClient.get<CursorPage<T>>(path, {
      params: { ...params, ...(cursor ? { cursor } : {}) },
    })
    result.push(...data.results)
    const next = data.next
      ? new URL(data.next, window.location.origin).searchParams.get('cursor')
      : null
    if (!next) return result
    if (cursors.has(next) || cursors.size >= 100)
      throw new Error('Pagination did not complete. Narrow your filters.')
    cursors.add(next)
    cursor = next
  } while (cursor)
  return result
}
