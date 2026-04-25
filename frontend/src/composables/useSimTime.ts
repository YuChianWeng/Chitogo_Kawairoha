import { computed, ref } from 'vue'

const SIM_TIME_KEY = 'chitogo_demo_sim_time'

function loadStored(): string | null {
  try { return sessionStorage.getItem(SIM_TIME_KEY) } catch { return null }
}

const _simTimeHHMM = ref<string | null>(loadStored())

export function useSimTime() {
  const isSimulating = computed(() => _simTimeHHMM.value !== null)

  const effectiveDate = computed<Date>(() => {
    if (!_simTimeHHMM.value) return new Date()
    const [hh, mm] = _simTimeHHMM.value.split(':').map(Number)
    const d = new Date()
    d.setHours(hh, mm, 0, 0)
    return d
  })

  const simTimeHHMM = computed(() => _simTimeHHMM.value)

  function setSimTime(hhmm: string) {
    _simTimeHHMM.value = hhmm
    try { sessionStorage.setItem(SIM_TIME_KEY, hhmm) } catch { /* ignore */ }
  }

  function clearSimTime() {
    _simTimeHHMM.value = null
    try { sessionStorage.removeItem(SIM_TIME_KEY) } catch { /* ignore */ }
  }

  function formatTime(date: Date): string {
    const days = ['日', '一', '二', '三', '四', '五', '六']
    const day = days[date.getDay()]
    const hh = String(date.getHours()).padStart(2, '0')
    const mm = String(date.getMinutes()).padStart(2, '0')
    return `星期${day} ${hh}:${mm}`
  }

  return {
    isSimulating,
    effectiveDate,
    simTimeHHMM,
    setSimTime,
    clearSimTime,
    formatTime,
  }
}
