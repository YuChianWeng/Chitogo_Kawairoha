import type { ChatCandidate } from './itinerary'
import type { CandidatesResult, SelectResult } from './trip'

export type ChatRole = 'user' | 'assistant'

export type ChatWidget =
  | { kind: 'navigation'; data: SelectResult }
  | { kind: 'rating'; data: SelectResult }
  | { kind: 'transport_prompt'; submitted?: boolean }
  | { kind: 'selecting'; data: CandidatesResult; submitted?: boolean }

export interface ChatMessage {
  id: string
  role: ChatRole
  text: string
  pending?: boolean
  candidates?: ChatCandidate[]
  widget?: ChatWidget
}
