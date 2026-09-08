import type { Locale, RoleCode } from './common'

/** Mirrors `users` table (SPEC 5.1) — never includes tokens/secrets. */
export interface User {
  id: string
  email: string
  full_name: string
  is_email_verified: boolean
  locale: Locale
  timezone: string
  status: 'active' | 'suspended' | 'pending_deletion' | 'deleted'
  roles: RoleCode[]
  is_totp_enabled: boolean
  created_at: string
}

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  email: string
  password: string
  full_name: string
  marketing_opt_in?: boolean
}

/** `POST /auth/login` response — refresh token lives in an httpOnly cookie,
 * only the short-lived access token is ever readable by JS (NFR-2, C-5).
 * Matches the backend's actual response key (`access`, not `access_token` —
 * see accounts/views.py and accounts/tests/test_auth.py). */
export interface AuthSession {
  access: string
  user: User
}

export interface ForgotPasswordPayload {
  email: string
}

export interface ResetPasswordPayload {
  token: string
  new_password: string
}

export interface VerifyEmailPayload {
  token: string
}

export interface GoogleLoginPayload {
  id_token: string
}
