import { apiClient } from './client'
import type { CursorPage } from '@/types/common'
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

// Endpoint group: Revenue (SPEC 6, FR-61..FR-69). TODO: real API.
export const revenueApi = {
  summary: (range: RevenueRange) =>
    apiClient.get<RevenueSummary>('/revenue/summary', { params: range }).then((r) => r.data),

  daily: (range: RevenueRange) =>
    apiClient
      .get<RevenueDailyPoint[]>('/revenue/daily', { params: range })
      .then((r) => r.data),

  byVideo: (range: RevenueRange) =>
    apiClient
      .get<RevenueByVideo[]>('/revenue/by-video', { params: range })
      .then((r) => r.data),

  statements: () =>
    apiClient
      .get<CursorPage<RevenueShareStatement>>('/revenue/statements')
      .then((r) => r.data),

  statement: (id: string) =>
    apiClient.get<RevenueShareStatement>(`/revenue/statements/${id}`).then((r) => r.data),

  statementPdfUrl: (id: string) => `/api/v1/revenue/statements/${id}/pdf`,

  dispute: (id: string, payload: DisputeStatementPayload) =>
    apiClient
      .post<RevenueShareStatement>(`/revenue/statements/${id}/dispute`, payload)
      .then((r) => r.data),
}
