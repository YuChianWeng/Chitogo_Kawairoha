<template>
  <div class="tweaker-root">
    <!-- Collapsed pill -->
    <button
      v-if="!expanded"
      class="tweaker-pill"
      :class="{ 'tweaker-pill--active': isSimulating }"
      type="button"
      @click="expanded = true"
    >
      <span class="pill-icon">⏱</span>
      <span class="pill-label">{{ isSimulating ? simTimeHHMM : 'DEMO' }}</span>
    </button>

    <!-- Expanded panel -->
    <div v-else class="tweaker-panel">
      <div class="tweaker-header">
        <div class="tweaker-title">
          <span class="tweaker-badge">DEMO</span>
          <span>時間模擬器</span>
        </div>
        <button class="tweaker-close" type="button" @click="expanded = false">✕</button>
      </div>

      <p class="tweaker-desc">
        模擬「現在時間」，讓回家提醒功能在 Demo 中即時觸發。
      </p>

      <div class="tweaker-input-row">
        <label class="tweaker-label" for="sim-time-input">模擬時間（HH:MM）</label>
        <input
          id="sim-time-input"
          v-model="inputVal"
          type="time"
          class="tweaker-input"
        />
      </div>

      <div class="quick-btns">
        <button
          v-for="offset in QUICK_OFFSETS"
          :key="offset.label"
          type="button"
          class="quick-btn"
          @click="applyOffset(offset.mins)"
        >{{ offset.label }}</button>
      </div>

      <div class="tweaker-actions">
        <button
          class="action-btn action-btn--activate"
          type="button"
          :disabled="!inputVal"
          @click="activate"
        >
          啟動模擬
        </button>
        <button
          class="action-btn action-btn--reset"
          type="button"
          @click="reset"
        >
          重設真實時間
        </button>
      </div>

      <p v-if="isSimulating" class="active-indicator">
        ⏱ 模擬中：{{ simTimeHHMM }}（真實：{{ realTimeStr }}）
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useSimTime } from '../composables/useSimTime'

const { isSimulating, simTimeHHMM, setSimTime, clearSimTime } = useSimTime()

const expanded = ref(false)
const inputVal = ref('')

const QUICK_OFFSETS = [
  { label: '回程時間 −30 分', mins: -30 },
  { label: '回程時間 −5 分', mins: -5 },
  { label: '回程時間準時', mins: 0 },
]

const realTimeStr = computed(() => {
  const now = new Date()
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
})

function returnTimeFromStorage(): string | null {
  try {
    const sessionId = localStorage.getItem('chitogo_session_id')
    if (!sessionId) return null
    return localStorage.getItem(`chitogo_return_time_${sessionId}`)
  } catch { return null }
}

function applyOffset(offsetMins: number) {
  const stored = returnTimeFromStorage()
  let base: Date
  if (stored) {
    const [hh, mm] = stored.split(':').map(Number)
    base = new Date()
    base.setHours(hh, mm, 0, 0)
  } else {
    // No return time stored — offset from now
    base = new Date()
  }
  base.setMinutes(base.getMinutes() + offsetMins)
  const hh = String(base.getHours()).padStart(2, '0')
  const mm = String(base.getMinutes()).padStart(2, '0')
  inputVal.value = `${hh}:${mm}`
}

function activate() {
  if (!inputVal.value) return
  setSimTime(inputVal.value)
}

function reset() {
  clearSimTime()
  inputVal.value = ''
}
</script>

<style scoped>
.tweaker-root {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  font-family: inherit;
}

/* ── Collapsed pill ── */
.tweaker-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1.5px solid #d97706;
  background: #fffbeb;
  color: #92400e;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(217, 119, 6, 0.2);
  transition: transform 0.15s, box-shadow 0.15s;
}

.tweaker-pill:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(217, 119, 6, 0.3);
}

.tweaker-pill--active {
  background: #d97706;
  color: white;
  border-color: #b45309;
}

.pill-icon {
  font-size: 15px;
}

/* ── Expanded panel ── */
.tweaker-panel {
  background: #fffbeb;
  border: 1.5px solid #d97706;
  border-radius: 20px;
  padding: 18px;
  width: 280px;
  box-shadow: 0 12px 40px rgba(217, 119, 6, 0.2), 0 2px 8px rgba(0,0,0,0.08);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.tweaker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tweaker-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #92400e;
}

.tweaker-badge {
  background: #d97706;
  color: white;
  font-size: 10px;
  font-weight: 800;
  padding: 2px 7px;
  border-radius: 999px;
  letter-spacing: 0.06em;
}

.tweaker-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #b45309;
  padding: 4px;
  line-height: 1;
}

.tweaker-desc {
  font-size: 12px;
  color: #78350f;
  line-height: 1.6;
  margin: 0;
}

.tweaker-input-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tweaker-label {
  font-size: 12px;
  font-weight: 600;
  color: #92400e;
}

.tweaker-input {
  padding: 10px 12px;
  border: 1.5px solid #d97706;
  border-radius: 12px;
  font-family: inherit;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  background: white;
  width: 100%;
  box-sizing: border-box;
}

.tweaker-input:focus {
  outline: 2px solid #d97706;
  outline-offset: 1px;
}

/* ── Quick offset buttons ── */
.quick-btns {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quick-btn {
  padding: 8px 12px;
  border: 1.5px solid #fcd34d;
  border-radius: 10px;
  background: white;
  color: #92400e;
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s;
}

.quick-btn:hover {
  background: #fef3c7;
}

/* ── Action buttons ── */
.tweaker-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  flex: 1;
  padding: 10px 8px;
  border-radius: 12px;
  font-family: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: none;
  transition: filter 0.15s, transform 0.15s;
}

.action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.05);
}

.action-btn--activate {
  background: #d97706;
  color: white;
}

.action-btn--activate:disabled {
  background: #fcd34d;
  color: #78350f;
  cursor: not-allowed;
}

.action-btn--reset {
  background: white;
  color: #b45309;
  border: 1.5px solid #d97706;
}

/* ── Active indicator ── */
.active-indicator {
  font-size: 12px;
  color: #b45309;
  background: #fef3c7;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 0;
  font-weight: 600;
  line-height: 1.5;
}
</style>
