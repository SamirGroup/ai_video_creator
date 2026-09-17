import { apiClient } from './client'
import type {
  ContractVersion,
  SignContractPayload,
  SignedContract,
} from '@/types/contract'

export interface CurrentContractState {
  version: ContractVersion | null
  signed: boolean
  has_payment_method: boolean
  requires_signature: boolean
  requires_resign: boolean
  generation_allowed: boolean
  generation_block_code: string | null
}
interface ContractResponse {
  id: string
  contract_version: string
  version: string
  signed_at: string
  status: SignedContract['status']
  has_pdf: boolean
}
function normalizeContract(data: ContractResponse): SignedContract {
  return {
    id: data.id,
    contract_version_id: data.contract_version,
    version: data.version,
    signed_at: data.signed_at,
    status: data.status,
    pdf_url: data.has_pdf ? `/api/v1/contracts/${data.id}/pdf` : null,
  }
}
export const contractsApi = {
  current: () =>
    apiClient.get<CurrentContractState>('/contracts/current').then((r) => r.data),
  history: () =>
    apiClient
      .get<ContractResponse[]>('/contracts/history')
      .then((r) => r.data.map(normalizeContract)),
  sign: (payload: SignContractPayload) =>
    apiClient
      .post<{ contract: ContractResponse }>('/contracts/sign', payload)
      .then((r) => normalizeContract(r.data.contract)),
  downloadPdf: (id: string) =>
    apiClient
      .get<Blob>(`/contracts/${id}/pdf`, { responseType: 'blob' })
      .then((r) => r.data),
}
