<template>
  <div class="loc-tweaker-root">
    <!-- Collapsed pill -->
    <button
      v-if="!expanded"
      class="loc-tweaker-pill"
      :class="{ 'loc-tweaker-pill--active': isSimLocating }"
      type="button"
      @click="expanded = true"
    >
      <span class="pill-icon">📍</span>
      <span class="pill-label">{{ isSimLocating ? simLabel : 'DEMO' }}</span>
    </button>

    <!-- Expanded panel -->
    <div v-else class="loc-tweaker-panel">
      <div class="loc-tweaker-header">
        <div class="loc-tweaker-title">
          <span class="loc-tweaker-badge">DEMO</span>
          <span>位置模擬器</span>
        </div>
        <button class="loc-tweaker-close" type="button" @click="expanded = false">✕</button>
      </div>

      <p class="loc-tweaker-desc">
        模擬「目前位置」，讓景點推薦在 Demo 中從指定地點出發。
      </p>

      <div class="loc-tweaker-input-row">
        <label class="loc-tweaker-label" for="sim-loc-select">選擇起點地標</label>
        <select
          id="sim-loc-select"
          v-model="selectedPreset"
          class="loc-tweaker-select"
        >
          <option value="">— 選擇地標 —</option>
          <option
            v-for="preset in PRESETS"
            :key="preset.label"
            :value="preset.label"
          >{{ preset.label }}</option>
        </select>
      </div>

      <div class="loc-tweaker-actions">
        <button
          class="loc-action-btn loc-action-btn--activate"
          type="button"
          :disabled="!selectedPreset"
          @click="activate"
        >
          啟動模擬
        </button>
        <button
          class="loc-action-btn loc-action-btn--reset"
          type="button"
          @click="reset"
        >
          重設真實位置
        </button>
      </div>

      <p v-if="isSimLocating" class="loc-active-indicator">
        📍 模擬中：{{ simLabel }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useSimLocation } from '../composables/useSimLocation'

const { isSimLocating, simLabel, setSimLocation, clearSimLocation } = useSimLocation()

const expanded = ref(false)
const selectedPreset = ref('')

const PRESETS = [
  { label: '台北 101', lat: 25.0338, lng: 121.5645 },
  { label: '西門町', lat: 25.0421, lng: 121.5081 },
  { label: '中正紀念堂', lat: 25.0359, lng: 121.5197 },
  { label: '士林夜市', lat: 25.0878, lng: 121.5241 },
  { label: '饒河夜市', lat: 25.0507, lng: 121.5779 },
  { label: '國立故宮博物院', lat: 25.1023, lng: 121.5484 },
  { label: '大稻埕', lat: 25.0636, lng: 121.5097 },
  { label: '松山文創園區', lat: 25.0444, lng: 121.5606 },
  { label: '象山', lat: 25.0262, lng: 121.5776 },
  { label: '陽明山', lat: 25.1542, lng: 121.5491 },
  { label: '淡水老街', lat: 25.1701, lng: 121.4404 },
]

function activate() {
  const preset = PRESETS.find(p => p.label === selectedPreset.value)
  if (!preset) return
  setSimLocation(preset.lat, preset.lng, preset.label)
}

function reset() {
  clearSimLocation()
  selectedPreset.value = ''
}
</script>

<style scoped>
.loc-tweaker-root {
  position: fixed;
  bottom: 24px;
  left: 24px;
  z-index: 9999;
  font-family: inherit;
}

/* ── Collapsed pill ── */
.loc-tweaker-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1.5px solid #2563eb;
  background: #eff6ff;
  color: #1e3a8a;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.2);
  transition: transform 0.15s, box-shadow 0.15s;
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.loc-tweaker-pill:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(37, 99, 235, 0.3);
}

.loc-tweaker-pill--active {
  background: #2563eb;
  color: white;
  border-color: #1d4ed8;
}

.pill-icon {
  font-size: 15px;
  flex-shrink: 0;
}

.pill-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Expanded panel ── */
.loc-tweaker-panel {
  background: #eff6ff;
  border: 1.5px solid #2563eb;
  border-radius: 20px;
  padding: 18px;
  width: 280px;
  box-shadow: 0 12px 40px rgba(37, 99, 235, 0.2), 0 2px 8px rgba(0,0,0,0.08);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.loc-tweaker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.loc-tweaker-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #1e3a8a;
}

.loc-tweaker-badge {
  background: #2563eb;
  color: white;
  font-size: 10px;
  font-weight: 800;
  padding: 2px 7px;
  border-radius: 999px;
  letter-spacing: 0.06em;
}

.loc-tweaker-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #1d4ed8;
  padding: 4px;
  line-height: 1;
}

.loc-tweaker-desc {
  font-size: 12px;
  color: #1e40af;
  line-height: 1.6;
  margin: 0;
}

.loc-tweaker-input-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.loc-tweaker-label {
  font-size: 12px;
  font-weight: 600;
  color: #1e3a8a;
}

.loc-tweaker-select {
  padding: 10px 12px;
  border: 1.5px solid #2563eb;
  border-radius: 12px;
  font-family: inherit;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  background: white;
  width: 100%;
  box-sizing: border-box;
  cursor: pointer;
}

.loc-tweaker-select:focus {
  outline: 2px solid #2563eb;
  outline-offset: 1px;
}

/* ── Action buttons ── */
.loc-tweaker-actions {
  display: flex;
  gap: 8px;
}

.loc-action-btn {
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

.loc-action-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.05);
}

.loc-action-btn--activate {
  background: #2563eb;
  color: white;
}

.loc-action-btn--activate:disabled {
  background: #93c5fd;
  color: #1e3a8a;
  cursor: not-allowed;
}

.loc-action-btn--reset {
  background: white;
  color: #1d4ed8;
  border: 1.5px solid #2563eb;
}

/* ── Active indicator ── */
.loc-active-indicator {
  font-size: 12px;
  color: #1d4ed8;
  background: #dbeafe;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 0;
  font-weight: 600;
  line-height: 1.5;
}
</style>
