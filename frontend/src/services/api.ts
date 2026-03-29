import axios from 'axios'
import type { ItineraryRequest, ItineraryResponse } from '../types/itinerary'

const client = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 10000,
})

export async function generateItinerary(
  request: ItineraryRequest,
): Promise<ItineraryResponse> {
  const { data } = await client.post<ItineraryResponse>('/itinerary', request)
  return data
}

export async function checkHealth(): Promise<{ status: string; version: string }> {
  const { data } = await client.get('/health')
  return data
}
