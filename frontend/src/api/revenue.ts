import { apiClient } from './client'
import { collectPages } from './pagination'
import type {
  DisputeStatementPayload,
  RevenueByVideo,
  RevenueDailyPoint,
  RevenueShareStatement,
  RevenueSummary,
} from '@/types/revenue'
export interface RevenueRange {
  from: string
  to: string
}
interface SummaryResponse {
  from: string
  to: string
  is_estimated: boolean
  source: RevenueSummary['source']
  platform_generated: {
    views: number
    estimated_minutes_watched: number
    estimated_revenue: string
    estimated_ad_revenue: string
  }
}
interface VideoRevenueResponse {
  job_id: string
  job__title: string
  youtube_video_id: string
  views: number
  estimated_revenue: string
}
export const revenueApi = {
  summary: async (range?: RevenueRange): Promise<RevenueSummary> => {
    const { data } = await apiClient.get<SummaryResponse>('/revenue/summary', {
      params: range,
    })
    return {
      currency: 'USD',
      period_start: data.from,
      period_end: data.to,
      source: data.source,
      is_estimated: data.is_estimated,
      total_views: data.platform_generated.views,
      total_estimated_minutes_watched: data.platform_generated.estimated_minutes_watched,
      total_estimated_revenue: data.platform_generated.estimated_revenue,
      total_estimated_ad_revenue: data.platform_generated.estimated_ad_revenue,
    }
  },
  daily: (range?: RevenueRange) =>
    apiClient
      .get<{ days: RevenueDailyPoint[] }>('/revenue/daily', { params: range })
      .then((r) => r.data.days),
  byVideo: (range?: RevenueRange): Promise<RevenueByVideo[]> =>
    apiClient
      .get<{ videos: VideoRevenueResponse[] }>('/revenue/by-video', { params: range })
      .then((r) => r.data.videos.map((v) => ({ ...v, title: v.job__title, rpm: null }))),
  statements: () => collectPages<RevenueShareStatement>('/revenue/statements'),
  statement: (id: string) =>
    apiClient.get<RevenueShareStatement>(`/revenue/statements/${id}`).then((r) => r.data),
  dispute: (id: string, payload: DisputeStatementPayload) =>
    apiClient
      .post<RevenueShareStatement>(`/revenue/statements/${id}/dispute`, payload)
      .then((r) => r.data),
}
