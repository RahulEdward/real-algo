import { apiClient } from './client'

interface UnderlyingsResponse {
  status: string
  underlyings?: string[]
  message?: string
}

interface ExpiriesResponse {
  status: string
  expiries?: string[]
  message?: string
}

export const searchApi = {
  async getUnderlyings(exchange: string): Promise<UnderlyingsResponse> {
    const response = await apiClient.get<UnderlyingsResponse>(
      `/search/api/underlyings?exchange=${encodeURIComponent(exchange)}`
    )
    return response.data
  },

  async getExpiries(exchange: string, underlying: string): Promise<ExpiriesResponse> {
    const response = await apiClient.get<ExpiriesResponse>(
      `/search/api/expiries?exchange=${encodeURIComponent(exchange)}&underlying=${encodeURIComponent(underlying)}`
    )
    return response.data
  },
}
