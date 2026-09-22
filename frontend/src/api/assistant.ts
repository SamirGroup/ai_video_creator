import { apiClient } from './client'
export interface Profile {
  goal: string
  audience_region: string
  language: string
  timezone: string
  onboarding_completed: boolean
}
export interface Turn {
  id: string
  question: string
  answer: string
  status: string
  error_code: string
  cost_usd: string
}
export interface AssistantState {
  profile: Profile
  available: boolean
  daily_message_limit: number
  turns: Turn[]
  channels: { id: string; channel_title: string; status: string }[]
  preferences: unknown[]
  jobs: { status: string; count: number }[]
  plans: { id: string; status: string; horizon: string }[]
}
export interface Policy {
  enabled: boolean
  daily_message_limit: number
  guidance: string
}
export interface Operations {
  users: number
  connected_channels: number
  ai_cost_30d: string
  assistant_failed: number
  assistant_completed: number
  jobs: { status: string; count: number }[]
  integrations: {
    service: string
    provider: string
    model: string
    active: boolean
    configured: boolean
  }[]
  policy: Policy
  recent_plans: { id: string; status: string; horizon: string; created_at: string }[]
}
export const assistantApi = {
  state: () => apiClient.get<AssistantState>('/me/assistant').then((r) => r.data),
  profile: (data: Profile) => apiClient.patch('/me/assistant', data),
  send: (message: string, request_key: string) =>
    apiClient.post<Turn>('/me/assistant', { message, request_key }).then((r) => r.data),
  overview: () => apiClient.get<Operations>('/admin/assistant').then((r) => r.data),
  policy: (data: Policy) => apiClient.patch('/admin/assistant', data),
}
