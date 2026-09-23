import { apiClient } from './client'
export interface Partner {
  id: number
  name: string
  image_url: string
  link_url: string
  caption: string
  sort_order: number
  is_active: boolean
  is_affiliate: boolean
}
export interface PartnerBanner {
  enabled: boolean
  title: string
  subtitle: string
  animation_enabled: boolean
  animation_seconds: number
}
export const partnersApi = {
  list: async () => (await apiClient.get<Partner[]>('/admin/partners')).data,
  banner: async () => (await apiClient.get<PartnerBanner>('/admin/partners/banner')).data,
  save: (data: Omit<Partner, 'id'>, id?: number) =>
    id
      ? apiClient.patch(`/admin/partners/${id}`, data)
      : apiClient.post('/admin/partners', data),
  remove: (id: number) => apiClient.delete(`/admin/partners/${id}`),
  saveBanner: (data: PartnerBanner) => apiClient.patch('/admin/partners/banner', data),
}
