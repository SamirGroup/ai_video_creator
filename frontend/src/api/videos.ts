import { apiClient } from './client'
import type { CursorPage } from '@/types/common'
import type {
  RejectVideoPayload,
  RequestChangesPayload,
  UpdateVideoMetadataPayload,
  VideoJob,
  VideoJobStep,
  VideoListFilters,
} from '@/types/video'

// Endpoint group: Video jobs (SPEC 6, status model SPEC 7.2). TODO: real API.
export const videosApi = {
  list: (filters: VideoListFilters = {}) =>
    apiClient
      .get<CursorPage<VideoJob>>('/videos', { params: filters })
      .then((r) => r.data),

  get: (id: string) => apiClient.get<VideoJob>(`/videos/${id}`).then((r) => r.data),

  steps: (id: string) =>
    apiClient.get<VideoJobStep[]>(`/videos/${id}/steps`).then((r) => r.data),

  generateNow: () => apiClient.post<VideoJob>('/videos/generate').then((r) => r.data),

  cancel: (id: string) => apiClient.post<VideoJob>(`/videos/${id}/cancel`).then((r) => r.data),

  updateMetadata: (id: string, payload: UpdateVideoMetadataPayload) =>
    apiClient.patch<VideoJob>(`/videos/${id}/metadata`, payload).then((r) => r.data),

  approve: (id: string) =>
    apiClient.post<VideoJob>(`/videos/${id}/approve`).then((r) => r.data),

  requestChanges: (id: string, payload: RequestChangesPayload) =>
    apiClient
      .post<VideoJob>(`/videos/${id}/request-changes`, payload)
      .then((r) => r.data),

  reject: (id: string, payload: RejectVideoPayload) =>
    apiClient.post<VideoJob>(`/videos/${id}/reject`, payload).then((r) => r.data),
}
