import { computed, ref } from 'vue'
import { en } from '../i18n/en'
import { zh } from '../i18n/zh'

const lang = ref<'zh' | 'en'>(
  (localStorage.getItem('chitogo_lang') as 'zh' | 'en') ?? 'zh'
)

export function useLocale() {
  const locale = computed(() => lang.value === 'en' ? en : zh)

  function setLang(l: 'zh' | 'en') {
    lang.value = l
    localStorage.setItem('chitogo_lang', l)
  }

  return { lang, locale, setLang }
}
