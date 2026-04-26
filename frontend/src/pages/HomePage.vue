<template>
  <div class="app-container">
    <!-- Sidebar (desktop only) -->
    <aside class="sidebar">
      <div class="logo-container">
        <img src="/images/111_200.svg" alt="Logo" class="logo-icon">
        <h1 class="logo-text">𨑨迌迌<br><span class="logo-sub">Chito-Go</span></h1>
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
      <div class="sidebar-footer">
        <LangToggle />
      </div>
    </aside>

    <!-- Agent tab: chat + map -->
    <div v-if="activeTab === 'agent'" class="main-content" ref="mainContentEl">
      <!-- Chat Area -->
      <main class="chat-area" :style="isMobile ? {} : { width: chatWidth + 'px' }">
        <header class="chat-header">
          <h2 class="chat-title">𨑨迌迌 <span class="chat-title-accent">Chito-Go</span></h2>
          <div class="info-bar">
            <div class="info-item">
              <span>{{ weatherDisplay }}</span>
            </div>
            <div class="info-item">
              <span>{{ currentTime }}</span>
            </div>
            <div class="info-item">
              <span>{{ locationDisplay }}</span>
            </div>
          </div>
        </header>

        <div class="chat-content" :class="{ 'chat-content--map-open': isMobile && isMobileMapOpen }">
          <RouterView v-show="!isMobile || !isMobileMapOpen" />
          <!-- Mobile map view (inline, toggled) -->
          <div v-if="isMobile && isMobileMapOpen" class="mobile-map-view">
            <MapPanel />
          </div>
        </div>
      </main>

      <!-- Resizable Divider (desktop only) -->
      <div
        v-if="!isMobile"
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
            <img src="/images/116_47.svg" alt="" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:20px;height:20px;">
          </div>
        </div>
      </div>

      <!-- Map (desktop only) -->
      <MapPanel v-if="!isMobile" />

      <!-- Mobile map toggle button -->
      <button
        v-if="isMobile"
        class="map-toggle-btn"
        type="button"
        :aria-label="isMobileMapOpen ? locale.nav.mapToggle.closeMapAria : locale.nav.mapToggle.openMapAria"
        @click="isMobileMapOpen = !isMobileMapOpen"
      >
        <span class="map-toggle-icon">{{ isMobileMapOpen ? '💬' : '🗺️' }}</span>
        <span class="map-toggle-label">{{ isMobileMapOpen ? locale.nav.mapToggle.openChat : locale.nav.mapToggle.openMap }}</span>
      </button>
    </div>

    <!-- Placeholder tabs -->
    <div v-else class="main-content placeholder-content">
      <div class="placeholder-view">
        <h2>{{ NAV_TABS.find(t => t.key === activeTab)?.label }}</h2>
        <p>{{ locale.nav.comingSoon }}</p>
      </div>
    </div>

    <!-- Bottom nav (mobile only) -->
    <nav class="mobile-bottom-nav" aria-label="主選單">
      <button
        v-for="tab in NAV_TABS"
        :key="tab.key"
        type="button"
        :class="['mobile-nav-item', activeTab === tab.key ? 'active' : '']"
        @click="activeTab = tab.key"
      >
        <img v-if="tab.icon" :src="tab.icon" :alt="tab.label" class="mobile-nav-icon">
        <span v-else class="mobile-nav-icon-placeholder"></span>
        <span class="mobile-nav-label">{{ tab.label }}</span>
      </button>
    </nav>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted } from 'vue'
import { RouterView } from 'vue-router'
import MapPanel from '../components/MapPanel.vue'
import LangToggle from '../components/LangToggle.vue'
import { useLocale } from '../composables/useLocale'
import { useWeather } from '../composables/useWeather'
import { useMapState } from '../composables/useMapState'

const { locale } = useLocale()
const { weather } = useWeather()
const { currentLocation } = useMapState()

type TabKey = 'home' | 'attractions' | 'agent' | 'profile' | 'settings'

const NAV_TABS = computed<{ key: TabKey; label: string; icon?: string }[]>(() => [
  { key: 'home',        label: locale.value.nav.tabs.home,        icon: '/images/I111_161_1_103_47_149.svg' },
  { key: 'attractions', label: locale.value.nav.tabs.attractions, icon: '/images/I111_160_1_103_47_158.svg' },
  { key: 'agent',       label: locale.value.nav.tabs.agent,       icon: '/images/I111_160_1_103_47_159.svg' },
  { key: 'profile',     label: locale.value.nav.tabs.profile,     icon: '/images/I111_163_1_103_47_152.svg' },
  { key: 'settings',    label: locale.value.nav.tabs.settings,    icon: '/images/I111_163_1_103_47_153.svg' },
])

const CHAT_MIN = 360
const CHAT_MAX = 760
const CHAT_DEFAULT = 520
const MOBILE_BREAKPOINT = 767

// ── Tab state ──
const activeTab = ref<TabKey>('agent')

// ── Mobile state ──
const isMobile = ref(window.innerWidth <= MOBILE_BREAKPOINT)
const isMobileMapOpen = ref(false)

const weatherDisplay = computed(() => {
  if (weather.value.loading) return locale.value.nav.weather.loading
  const cond = weather.value.condition
  const temp = weather.value.temperature
  const prob = weather.value.rainProbability

  if (cond && temp !== null) {
    return `${cond} • ${temp}°C`
  }

  const fallbackCondition = weather.value.isRainingLikely
    ? locale.value.nav.weather.rainy
    : (prob !== null && prob > 20) ? locale.value.nav.weather.cloudy : locale.value.nav.weather.sunny
  
  if (prob === null) return fallbackCondition
  return locale.value.nav.weather.format(fallbackCondition, prob)
})

const directionDisplay = computed(() => {
  return weather.value.windDirection || '微風'
})

const locationDisplay = computed(() => {
  return currentLocation.value?.label || locale.value.nav.location
})

function onResize() {
  isMobile.value = window.innerWidth <= MOBILE_BREAKPOINT
  if (!isMobile.value) isMobileMapOpen.value = false
}

onMounted(() => window.addEventListener('resize', onResize))

// ── Resizable panel state ──
const mainContentEl = ref<HTMLElement | null>(null)
const chatWidth = ref<number>(
  parseInt(localStorage.getItem('chitogo.chatWidth') ?? String(CHAT_DEFAULT)) || CHAT_DEFAULT
)

const currentTime = computed(() => {
  const now = new Date()
  const days = locale.value.nav.time.days
  const day = days[now.getDay()]
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const prefix = locale.value.nav.time.dayPrefix
  return `${prefix}${day} ${hh}:${mm}`
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
  window.removeEventListener('resize', onResize)
})
</script>

<style scoped>
/* ── Outer shell ── */
.app-container {
  display: flex;
  width: full;
  min-height: 100vh;
  padding: 20px 80px;
  gap: 0;
  margin: 0 auto;
  background:
    radial-gradient(circle at 0% 0%, rgba(191, 219, 254, 0.55) 0%, transparent 40%),
    radial-gradient(circle at 100% 100%, rgba(199, 210, 254, 0.45) 0%, transparent 40%),
    linear-gradient(180deg, #eff6ff 0%, #f8fbff 50%, #f8fafc 100%);
}

/* ── Sidebar ── */
.sidebar {
  width: 193px;
  background: linear-gradient(180deg, #f0f6ff 0%, #ffffff 100%);
  border-radius: 20px;
  border: 1px solid rgba(191, 219, 254, 0.6);
  flex-shrink: 0;
  padding: 36px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 8px 32px rgba(37, 99, 235, 0.08), 0 1px 4px rgba(37, 99, 235, 0.06);
}

.sidebar-footer {
  margin-top: auto;
  padding-top: 16px;
}

/* ── Logo ── */
.logo-container {
  text-align: center;
  margin-bottom: 52px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 40px;
  height: 40px;
}

.logo-text {
  font-size: 15px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.35;
  margin: 0;
}

.logo-sub {
  font-size: 13px;
  font-weight: 600;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: 0.02em;
}

/* ── Nav ── */
.nav-menu {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 11px 16px;
  border: none;
  background: transparent;
  color: #64748b;
  border-radius: 14px;
  font-size: 14px;
  font-family: inherit;
  font-weight: 500;
  gap: 12px;
  cursor: pointer;
  text-align: left;
  width: 100%;
  transition: background 0.18s, color 0.18s, box-shadow 0.18s;
}

.nav-item:hover:not(.active) {
  background: rgba(37, 99, 235, 0.07);
  color: #1d4ed8;
}

.nav-item img {
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  opacity: 0.7;
  transition: opacity 0.18s;
}

.nav-item:hover:not(.active) img {
  opacity: 1;
}

.nav-icon-placeholder {
  width: 22px;
  height: 22px;
  display: inline-block;
  flex-shrink: 0;
}

.nav-item.active {
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
  color: #fff;
  box-shadow: 0 6px 20px rgba(37, 99, 235, 0.28), 0 2px 6px rgba(79, 70, 229, 0.18);
  font-weight: 700;
}

.nav-item.active img {
  filter: brightness(0) invert(1);
  opacity: 1;
}

/* ── Main content ── */
.main-content {
  display: flex;
  margin-left: 20px;
  height: calc(100vh - 40px);
  flex: 1;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 8px 40px rgba(15, 23, 42, 0.1), 0 2px 8px rgba(15, 23, 42, 0.06);
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
  padding: 18px 0 0;
  flex-shrink: 0;
  background: white;
}

.chat-title {
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 14px;
  letter-spacing: -0.01em;
}

.chat-title-accent {
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.info-bar {
  background: rgba(239, 246, 255, 0.9);
  border-top: 1px solid rgba(191, 219, 254, 0.7);
  border-bottom: 1px solid rgba(191, 219, 254, 0.7);
  backdrop-filter: blur(8px);
  color: #1d4ed8;
  display: flex;
  justify-content: space-around;
  align-items: center;
  height: 36px;
  font-size: 12px;
  font-weight: 600;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.info-item img {
  width: 15px;
  height: 15px;
  opacity: 0.75;
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
  width: 20px;
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
  outline: 2px solid #2563eb;
}

.divider-line {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 2px;
  height: 100%;
  background: linear-gradient(180deg, transparent 0%, #bfdbfe 15%, #93c5fd 50%, #bfdbfe 85%, transparent 100%);
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
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 12px;
}

.placeholder-view p {
  font-size: 16px;
}

/* ── Mobile map toggle button ── */
.map-toggle-btn {
  display: none;
}

/* ── Mobile bottom nav (hidden on desktop) ── */
.mobile-bottom-nav {
  display: none;
}

/* ── Mobile map view ── */
.mobile-map-view {
  flex: 1;
  height: 100%;
  overflow: hidden;
}

/* ═══════════════════════════════════════════
   MOBILE  ≤ 767 px
═══════════════════════════════════════════ */
@media (max-width: 767px) {
  /*
   * Fixed-height root so flex children can resolve heights against it.
   * padding-bottom carves out the 56 px fixed bottom nav from the layout
   * flow, keeping all scrollable content above the nav.
   */
  .app-container {
    padding: 0;
    padding-bottom: calc(56px + env(safe-area-inset-bottom, 0px));
    flex-direction: column;
    height: 100dvh;
    height: 100vh;
    overflow: hidden;
  }

  /* Hide desktop sidebar */
  .sidebar {
    display: none;
  }

  /*
   * flex: 1 + min-height: 0 fills (100dvh - padding-bottom).
   * No explicit calc needed — the root padding handles the reservation.
   */
  .main-content {
    margin-left: 0;
    border-radius: 0;
    flex: 1;
    min-height: 0;
    flex-direction: column;
    box-shadow: none;
    overflow: hidden;
  }

  /* Chat area fills full width */
  .chat-area {
    width: 100% !important;
    flex: 1;
    min-height: 0;
    min-width: 0;
  }

  /* Shrink the header on mobile */
  .chat-header {
    padding: 10px 0 0;
  }

  .chat-title {
    font-size: 15px;
    margin-bottom: 8px;
  }

  .info-bar {
    font-size: 11px;
    height: 32px;
  }

  /*
   * The scroll container for RouterView pages.
   * padding-bottom ensures content can scroll past the composer/nav area
   * even when there is not enough content to trigger scrolling naturally.
   */
  .chat-content {
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }

  /* Map toggle FAB */
  .map-toggle-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    position: fixed;
    bottom: calc(56px + env(safe-area-inset-bottom, 0px) + 12px);
    right: 16px;
    z-index: 100;
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
    color: white;
    border: none;
    border-radius: 24px;
    padding: 10px 16px;
    font-size: 13px;
    font-family: inherit;
    font-weight: 700;
    box-shadow: 0 4px 16px rgba(37, 99, 235, 0.35);
    cursor: pointer;
    touch-action: manipulation;
  }

  .map-toggle-icon {
    font-size: 16px;
    line-height: 1;
  }

  .map-toggle-label {
    letter-spacing: 0.02em;
  }

  /* Mobile bottom navigation */
  .mobile-bottom-nav {
    display: flex;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 56px;
    background: rgba(255, 255, 255, 0.97);
    backdrop-filter: blur(12px);
    border-top: 1px solid rgba(191, 219, 254, 0.8);
    box-shadow: 0 -2px 12px rgba(15, 23, 42, 0.06);
    z-index: 200;
    padding-bottom: env(safe-area-inset-bottom);
    align-items: stretch;
  }

  .mobile-nav-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    border: none;
    background: transparent;
    color: #94a3b8;
    font-family: inherit;
    font-size: 10px;
    font-weight: 500;
    cursor: pointer;
    padding: 4px 2px;
    touch-action: manipulation;
    transition: color 0.15s;
  }

  .mobile-nav-item.active {
    color: #2563eb;
  }

  .mobile-nav-icon {
    width: 22px;
    height: 22px;
    opacity: 0.55;
    transition: opacity 0.15s;
  }

  .mobile-nav-item.active .mobile-nav-icon {
    opacity: 1;
    filter: none;
  }

  .mobile-nav-icon-placeholder {
    width: 22px;
    height: 22px;
    display: inline-block;
  }

  .mobile-nav-label {
    line-height: 1;
  }

  /* Placeholder tab on mobile */
  .placeholder-content {
    border-radius: 0;
  }
}
</style>

<style>
/* Global: prevent text selection while dragging the divider */
body.is-resizing {
  user-select: none;
  cursor: col-resize;
}
</style>
