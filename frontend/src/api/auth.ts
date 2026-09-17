import { apiClient } from './client'
import type {
  LoginResponse,
  ForgotPasswordPayload,
  GoogleLoginPayload,
  LoginPayload,
  RegisterPayload,
  ResetPasswordPayload,
  User,
  VerifyEmailPayload,
} from '@/types/auth'

// Endpoint group: Auth (SPEC 6). Backend not live yet — calls are wired to
// the documented `/api/v1/auth/*` contract so integration is a no-op once
// `backend-developer` ships the real views. TODO: real API.
export const authApi = {
  register: (payload: RegisterPayload) =>
    apiClient.post<{ message: string }>('/auth/register', payload).then((r) => r.data),

  login: (payload: LoginPayload) =>
    apiClient.post<LoginResponse>('/auth/login', payload).then((r) => r.data),

  loginWithGoogle: (payload: GoogleLoginPayload) =>
    apiClient.post<LoginResponse>('/auth/google', payload).then((r) => r.data),

  logout: () => apiClient.post<void>('/auth/logout').then((r) => r.data),

  refresh: () => apiClient.post<{ access: string }>('/auth/refresh').then((r) => r.data),

  verifyEmail: (payload: VerifyEmailPayload) =>
    apiClient
      .post<{ message: string }>('/auth/verify-email', payload)
      .then((r) => r.data),

  requestPasswordReset: (payload: ForgotPasswordPayload) =>
    apiClient
      .post<{ message: string }>('/auth/password/reset', payload)
      .then((r) => r.data),

  confirmPasswordReset: (payload: ResetPasswordPayload) =>
    apiClient
      .post<{ message: string }>('/auth/password/reset/confirm', payload)
      .then((r) => r.data),

  me: () => apiClient.get<User>('/me').then((r) => r.data),
}
