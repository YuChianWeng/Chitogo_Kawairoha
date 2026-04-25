import { ref } from 'vue'
import type { CandidateCard } from '../types/trip'

// Module-level singleton: all callers share the same reactive instance
const spotCandidates = ref<CandidateCard[]>([])

export function useMapState() {
  function setSpotCandidates(candidates: CandidateCard[]) {
    spotCandidates.value = candidates
  }

  function clearSpotCandidates() {
    spotCandidates.value = []
  }

  return { spotCandidates, setSpotCandidates, clearSpotCandidates }
}
