import { apiClient } from './client'
export interface AuthLogo {
  id: number
  name: string
  image_url: string
  link_url: string
  sort_order: number
  is_active: boolean
}
export const authLogosApi = {
  publicList: () => apiClient.get<AuthLogo[]>('/public/auth-logos').then((r) => r.data),
  list: () => apiClient.get<AuthLogo[]>('/admin/auth-logos').then((r) => r.data),
  save: (data: Omit<AuthLogo, 'id'>, id?: number) =>
    id
      ? apiClient.patch(`/admin/auth-logos/${id}`, data)
      : apiClient.post('/admin/auth-logos', data),
  remove: (id: number) => apiClient.delete(`/admin/auth-logos/${id}`),
}
