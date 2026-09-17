import { apiClient } from './client'
export interface PlanItem {
  id: string
  title: string
  brief: string
  rationale: string
  scheduled_for: string
  selected: boolean
  job: string | null
}
export interface ContentPlan {
  id: string
  channel: string
  horizon: string
  status: string
  summary: string
  error_code: string
  cost_usd: string
  preference_snapshot: { publish_timezone: string }
  analysis: {
    source?: string
    retrieved_at?: string
    videos?: { video_id: string; title: string; views: number; likes: number }[]
  }
  items: PlanItem[]
}
export const planningApi = {
  list: (channel: string) =>
    apiClient
      .get<ContentPlan[]>(`/channels/${channel}/content-plans`)
      .then((r) => r.data),
  propose: (channel: string, horizon: string, count: number, request_key: string) =>
    apiClient
      .post<ContentPlan>(`/channels/${channel}/content-plans`, {
        horizon,
        count,
        request_key,
      })
      .then((r) => r.data),
  update: (plan: string, item: string, input: Partial<PlanItem>) =>
    apiClient
      .patch<PlanItem>(`/content-plans/${plan}/items/${item}`, input)
      .then((r) => r.data),
  approve: (id: string, item_ids: string[]) =>
    apiClient
      .post<ContentPlan>(`/content-plans/${id}/approve`, { item_ids })
      .then((r) => r.data),
}
