/** Shared primitive/API-envelope types used across all feature modules. */

/** RFC 7807 problem+json error shape returned by the Django backend (SPEC 6). */
export interface ApiProblem {
  type: string
  title: string
  status: number
  detail?: string
  instance?: string
  /** Field-level validation errors, when `status === 422 | 400`. */
  errors?: Record<string, string[]>
}

/** Cursor-based pagination envelope (SPEC 6: "kursor-based pagination"). */
export interface CursorPage<T> {
  results: T[]
  next?: string | null
  previous?: string | null
  next_cursor: string | null
  previous_cursor: string | null
  count?: number
}

export type { Locale } from '@/i18n/registry'

export type StaffRoleCode = 'moderator' | 'support' | 'finance' | 'admin'
export type RoleCode = 'creator' | StaffRoleCode

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'
