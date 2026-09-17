import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { videoKeys } from '@/lib/queryKeys'
import { videosApi } from '@/api/videos'
import type {
  RejectVideoPayload,
  RequestChangesPayload,
  VideoListFilters,
} from '@/types/video'

export function useVideoList(filters: VideoListFilters = {}) {
  return useQuery({
    queryKey: videoKeys.list({ ...filters }),
    queryFn: () => videosApi.listAll(filters),
    refetchInterval: 15000,
  })
}
export function useVideoDetail(id: string | undefined) {
  return useQuery({
    queryKey: videoKeys.detail(id ?? ''),
    queryFn: () => videosApi.get(id!),
    enabled: Boolean(id),
    refetchInterval: 10000,
  })
}
export function useVideoSteps(id: string | undefined) {
  return useQuery({
    queryKey: videoKeys.steps(id ?? ''),
    queryFn: () => videosApi.steps(id!),
    enabled: Boolean(id),
    refetchInterval: 10000,
  })
}
function useRefreshVideo(id: string) {
  const client = useQueryClient()
  return async () => {
    await client.invalidateQueries({ queryKey: ['videos'] })
    await client.invalidateQueries({ queryKey: videoKeys.detail(id) })
  }
}
export function useApproveVideo(id: string) {
  return useMutation({
    mutationFn: () => videosApi.approve(id),
    onSuccess: useRefreshVideo(id),
  })
}
export function useRequestChangesVideo(id: string) {
  return useMutation({
    mutationFn: (payload: RequestChangesPayload) => videosApi.requestChanges(id, payload),
    onSuccess: useRefreshVideo(id),
  })
}
export function useRejectVideo(id: string) {
  return useMutation({
    mutationFn: (payload: RejectVideoPayload) => videosApi.reject(id, payload),
    onSuccess: useRefreshVideo(id),
  })
}
