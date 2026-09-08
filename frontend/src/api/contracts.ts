import { apiClient } from './client'
import type { ContractVersion, SignContractPayload, SignedContract } from '@/types/contract'

// Endpoint group: Contracts (SPEC 6, FR-28..FR-32, FR-70a). TODO: real API.
export const contractsApi = {
  current: () => apiClient.get<ContractVersion>('/contracts/current').then((r) => r.data),

  history: () => apiClient.get<SignedContract[]>('/contracts/history').then((r) => r.data),

  sign: (payload: SignContractPayload) =>
    apiClient.post<SignedContract>('/contracts/sign', payload).then((r) => r.data),

  pdfUrl: (id: string) => `/api/v1/contracts/${id}/pdf`,
}
