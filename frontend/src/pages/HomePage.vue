<template>
  <div class="app-container">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="logo-container">
        <img src="/images/111_200.svg" alt="Logo" class="logo-icon">
        <h1 class="logo-text">𨑨迌迌<br>Chito-Go</h1>
      </div>
      <nav class="nav-menu">
        <button
          v-for="tab in NAV_TABS"
          :key="tab.key"
          type="button"
          :class="['nav-item', activeTab === tab.key ? 'active' : '']"
          @click="activeTab = tab.key"
        >
          <img v-if="tab.icon" :src="tab.icon" :alt="tab.label">
          <span v-else class="nav-icon-placeholder"></span>
          <span>{{ tab.label }}</span>
        </button>
      </nav>
    </aside>

    <!-- Agent tab: chat + map -->
    <div v-if="activeTab === 'agent'" class="main-content" ref="mainContentEl">
      <!-- Chat Area -->
      <main class="chat-area" :style="{ width: chatWidth + 'px' }">
        <header class="chat-header">
          <h2>𨑨迌迌 Chito-Go</h2>
          <div class="info-bar">
            <div class="info-item">
              <img src="/images/111_361.svg" alt="Weather">
              <span>多雲•降雨機率 30%</span>
            </div>
            <div class="info-item">
              <img src="/images/111_363.svg" alt="Time">
              <span>{{ currentTime }}</span>
            </div>
            <div class="info-item">
              <img src="/images/111_362.svg" alt="Location">
              <span>台北市•信義區</span>
            </div>
          </div>
        </header>

        <div class="chat-content">
          <RouterView />
        </div>
      </main>

      <!-- Resizable Divider -->
      <div
        class="divider"
        role="separator"
        aria-orientation="vertical"
        :aria-valuenow="chatWidth"
        :aria-valuemin="CHAT_MIN"
        :aria-valuemax="CHAT_MAX"
        tabindex="0"
        @pointerdown.prevent="onDividerPointerDown"
        @keydown="onDividerKeyDown"
      >
        <div class="divider-line"></div>
        <div class="divider-handle">
          <div style="position: relative; width: 32px; height: 32px;">
            <img src="/images/116_56.svg" alt="" style="position:absolute;top:0;left:0;width:100%;height:100%;">
            <img src="/images/116_47.svg" alt="" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:24px;height:24px;">
          </div>
        </div>
      </div>

      <!-- Map -->
      <MapPanel :itinerary="null" :candidates="[]" :loading="false" />
    </div>

    <!-- Placeholder tabs -->
    <div v-else class="main-content placeholder-content">
      <div class="placeholder-view">
        <h2>{{ NAV_TABS.find(t => t.key === activeTab)?.label }}</h2>
        <p>即將推出</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { RouterView } from 'vue-router'
import MapPanel from '../components/MapPanel.vue'

type TabKey = 'home' | 'attractions' | 'agent' | 'profile' | 'settings'

const NAV_TABS: { key: TabKey; label: string; icon?: string }[] = [
  { key: 'home',        label: '首頁',     icon: '/images/I111_161_1_103_47_149.svg' },
  { key: 'attractions', label: '景點',     icon: '/images/I111_160_1_103_47_158.svg' },
  { key: 'agent',       label: 'Agent',    icon: '/images/I111_160_1_103_47_159.svg' },
  { key: 'profile',     label: '個人資料', icon: '/images/I111_163_1_103_47_152.svg' },
  { key: 'settings',    label: '設定',     icon: '/images/I111_163_1_103_47_153.svg' },
]

const CHAT_MIN = 360
const CHAT_MAX = 760
const CHAT_DEFAULT = 520

// ── Tab state ──
const activeTab = ref<TabKey>('agent')

// ── Resizable panel state ──
const mainContentEl = ref<HTMLElement | null>(null)
const chatWidth = ref<number>(
  parseInt(localStorage.getItem('chitogo.chatWidth') ?? String(CHAT_DEFAULT)) || CHAT_DEFAULT
)

const currentTime = computed(() => {
  const now = new Date()
  const days = ['日', '一', '二', '三', '四', '五', '六']
  const day = days[now.getDay()]
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  return `星期${day} ${hh}:${mm}`
})

function clampWidth(w: number): number {
  return Math.min(CHAT_MAX, Math.max(CHAT_MIN, w))
}

function onDividerPointerDown(e: PointerEvent) {
  const container = mainContentEl.value
  if (!container) return

  document.body.classList.add('is-resizing')
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)

  function onMove(ev: PointerEvent) {
    const rect = container.getBoundingClientRect()
    chatWidth.value = clampWidth(ev.clientX - rect.left)
  }

  function onUp() {
    document.body.classList.remove('is-resizing')
    localStorage.setItem('chitogo.chatWidth', String(chatWidth.value))
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }

  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

function onDividerKeyDown(e: KeyboardEvent) {
  const step = 16
  if (e.key === 'ArrowLeft')  { chatWidth.value = clampWidth(chatWidth.value - step); e.preventDefault() }
  if (e.key === 'ArrowRight') { chatWidth.value = clampWidth(chatWidth.value + step); e.preventDefault() }
  if (e.key === 'Home')       { chatWidth.value = CHAT_MIN; e.preventDefault() }
  if (e.key === 'End')        { chatWidth.value = CHAT_MAX; e.preventDefault() }
  if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) {
    localStorage.setItem('chitogo.chatWidth', String(chatWidth.value))
  }
}

onBeforeUnmount(() => {
  document.body.classList.remove('is-resizing')
})
</script>

<style scoped>
/* ── Outer shell ── */
.app-container {
  display: flex;
  width: 1440px;
  min-height: 100vh;
  padding: 20px 80px;
  gap: 0;
  margin: 0 auto;
}

/* ── Sidebar ── */
.sidebar {
  width: 193px;
  background: white;
  border-radius: 15px;
  flex-shrink: 0;
  padding: 40px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo-container {
  text-align: center;
  margin-bottom: 60px;
}

.logo-icon {
  width: 40px;
  height: 40px;
  margin-bottom: 10px;
}

.logo-text {
  font-size: 16px;
  font-weight: bold;
  color: #000;
  line-height: 1.4;
}

.nav-menu {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 12px 20px;
  border: none;
  background: transparent;
  color: #6c7072;
  border-radius: 15px;
  font-size: 16px;
  font-family: inherit;
  gap: 15px;
  cursor: pointer;
  text-align: left;
  width: 100%;
}

.nav-item img {
  width: 24px;
  height: 24px;
}

.nav-icon-placeholder {
  width: 24px;
  height: 24px;
  display: inline-block;
  flex-shrink: 0;
}

.nav-item.active {
  background-color: #4d68bf;
  color: #fff;
  box-shadow: 0 4px 4px rgba(0,0,0,0.1);
}

.nav-item.active img {
  filter: brightness(0) invert(1);
}

/* ── Main content ── */
.main-content {
  display: flex;
  margin-left: 24px;
  height: calc(100vh - 40px);
  flex: 1;
  border-radius: 15px;
  overflow: hidden;
  box-shadow: 0 0 20px rgba(0,0,0,0.05);
  min-width: 0;
}

/* ── Chat area ── */
.chat-area {
  background: white;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

.chat-header {
  text-align: center;
  padding-top: 20px;
  flex-shrink: 0;
}

.chat-header h2 {
  font-size: 18px;
  margin-bottom: 15px;
  color: #000;
}

.info-bar {
  background-color: #4d68bf;
  color: white;
  display: flex;
  justify-content: space-around;
  align-items: center;
  height: 33px;
  font-size: 12px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.info-item img {
  width: 16px;
  height: 16px;
}

/* ── Chat content (wizard host) ── */
.chat-content {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

/* Override full-viewport height on embedded wizard pages */
.chat-content :deep(.quiz-container),
.chat-content :deep(.setup-container),
.chat-content :deep(.trip-container),
.chat-content :deep(.summary-container) {
  min-height: unset;
  flex: 1;
}

/* ── Divider ── */
.divider {
  width: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  flex-shrink: 0;
  cursor: col-resize;
  position: relative;
  z-index: 10;
  background: transparent;
  border: none;
  padding: 0;
  outline-offset: -2px;
}

.divider:focus-visible {
  outline: 2px solid #4d68bf;
}

.divider-line {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 3px;
  height: 100%;
  background-color: #4d68bf;
  pointer-events: none;
}

.divider-handle {
  width: 32px;
  height: 32px;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
  z-index: 1;
}

/* ── Placeholder tabs ── */
.placeholder-content {
  justify-content: center;
  align-items: center;
  background: white;
}

.placeholder-view {
  text-align: center;
  color: #94a3b8;
}

.placeholder-view h2 {
  font-size: 24px;
  color: #4d68bf;
  margin-bottom: 12px;
}

.placeholder-view p {
  font-size: 16px;
}
</style>

<style>
/* Global: prevent text selection while dragging the divider */
body.is-resizing {
  user-select: none;
  cursor: col-resize;
}
</style>
