<template>
  <button
    type="button"
    class="lang-toggle"
    :aria-label="lang === 'zh' ? 'Switch to English' : '切換中文'"
    @click="toggle"
  >
    <span :class="{ active: lang === 'zh' }">中</span>
    <span class="divider">/</span>
    <span :class="{ active: lang === 'en' }">EN</span>
  </button>
</template>

<script setup lang="ts">
import { useLocale } from '../composables/useLocale'

const { lang, setLang } = useLocale()

function toggle() {
  setLang(lang.value === 'zh' ? 'en' : 'zh')
}
</script>

<style scoped>
.lang-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 4px 10px;
  border: 1.5px solid #dbeafe;
  border-radius: 999px;
  background: white;
  font-size: 13px;
  font-weight: 600;
  color: #94a3b8;
  cursor: pointer;
  transition: border-color 0.18s;
  font-family: inherit;
  white-space: nowrap;
}

.lang-toggle:hover {
  border-color: #4d68bf;
}

.lang-toggle span.active {
  color: #4d68bf;
}

.divider {
  color: #cbd5e1;
}
</style>
