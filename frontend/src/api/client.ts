import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'

import { useAuthStore } from '@/stores/authStore'
import type { ApiProblem } from '@/types/common'

/**
 * Normalized error shape thrown by the client for TanStack Query/UI to consume.
 * Wraps the backend's RFC 7807 `application/problem+json` body (SPEC 6).
 */
export class ApiError extends Error {
  status: number
  problem: ApiProblem | null
  requestId: string | null

  constructor(status: number, problem: ApiProblem | null, requestId: string | null) {
    super(problem?.detail ?? problem?.title ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.problem = problem
    this.requestId = requestId
  }
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  // Refresh token cookie must travel with cross-origin requests in dev
  // (frontend :5173 -> backend :8000) and same-site in prod.
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

function generateRequestId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

// ---- Request interceptor: attach Bearer token + correlation id ----
apiClient.interceptors.request.use((config) => {
  const { accessToken } = useAuthStore.getState()
  if (accessToken) {
    config.headers.set('Authorization', `Bearer ${accessToken}`)
  }
  config.headers.set('X-Request-ID', generateRequestId())
  return config
})

// ---- 401 refresh-and-retry-once skeleton (FR-4/FR-14) ----
// TODO: real API — backend refresh endpoint not live yet; this wiring is
// ready for `POST /auth/refresh` (httpOnly cookie based, no body needed).
let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post<{ access: string }>(`${BASE_URL}/api/v1/auth/refresh`, {}, { withCredentials: true })
      .then((res) => {
        useAuthStore.getState().setAccessToken(res.data.access)
        return res.data.access
      })
      .catch(() => {
        useAuthStore.getState().clearSession()
        return null
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiProblem>) => {
    const originalRequest = error.config as
      | (InternalAxiosRequestConfig & { _retried?: boolean })
      | undefined

    const status = error.response?.status ?? 0
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/')

    if (status === 401 && originalRequest && !originalRequest._retried && !isAuthEndpoint) {
      originalRequest._retried = true
      const newToken = await refreshAccessToken()
      if (newToken) {
        originalRequest.headers.set('Authorization', `Bearer ${newToken}`)
        return apiClient(originalRequest)
      }
    }

    const requestId = (error.response?.headers?.['x-request-id'] as string) ?? null
    return Promise.reject(new ApiError(status, error.response?.data ?? null, requestId))
  },
)
