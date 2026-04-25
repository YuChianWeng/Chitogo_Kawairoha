<template>
  <div class="quiz-container">
    <div class="quiz-card" v-if="phase === 'quiz'">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: `${(currentQ / 9) * 100}%` }"></div>
      </div>
      <p class="progress-label">第 {{ currentQ }} / 9 題</p>

      <h2 class="question-text">{{ currentQuestion.text }}</h2>

      <div class="options">
        <button
          v-for="opt in currentQuestion.options"
          :key="opt.key"
          class="option-btn"
          :class="{ selected: selectedAnswer === opt.key }"
          @click="selectAnswer(opt.key)"
        >
          {{ opt.label }}
        </button>
      </div>

      <button
        class="next-btn"
        :disabled="!selectedAnswer || loading"
        @click="nextQuestion"
      >
        {{ currentQ < 9 ? '下一題' : '查看結果' }}
      </button>

      <div v-if="errorText" class="error">{{ errorText }}</div>
    </div>

    <div class="result-card" v-else-if="phase === 'result'">
      <div class="mascot-img">
        <img :src="`/images/mascot_${mascot}.svg`" :alt="gene" @error="onMascotImgError">
      </div>
      <h2 class="gene-title">你的旅遊基因：{{ gene }}</h2>
      <p class="gene-desc">{{ geneDescription }}</p>
      <button class="start-btn" @click="goToAccommodation">開始規劃行程</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createSession, submitQuiz } from '../services/api'
import type { QuizAnswers } from '../types/trip'
import { clearAccommodationState } from '../utils/accommodation'

const router = useRouter()

const QUESTIONS = [
  {
    key: 'Q1',
    text: '台北對你來說，更像是一場什麼樣的邂逅？',
    options: [
      { key: 'A', label: '初次見面的神祕網友，充滿新鮮感。' },
      { key: 'B', label: '見過幾次面，還在探索彼此的共同話題。' },
      { key: 'C', label: '熟到不能再熟的老友，閉著眼都能走到目的地。' },
    ],
  },
  {
    key: 'Q2',
    text: '當你打開導航地圖，你的手指通常會滑向哪裡？',
    options: [
      { key: 'A', label: '經典必去！沒在標誌性景點前打卡就不算來過。' },
      { key: 'B', label: '拒絕人潮！哪裡沒人往哪鑽，越神祕的小徑我越愛。' },
    ],
  },
  {
    key: 'Q3',
    text: '如果給你一個靜止的午後，縮在城市角落的咖啡廳聞著豆香，你的電力值會？',
    options: [
      { key: 'A', label: '直衝 100%！這種孤獨的浪漫是我最頂級的充電方式。' },
      { key: 'B', label: '降到 20%... 靜止太久我會開始焦慮，我需要點熱鬧的聲音。' },
    ],
  },
  {
    key: 'Q4',
    text: '暫時放下手機，親手完成一件手工藝品（如陶藝、皮革），你覺得那是？',
    options: [
      { key: 'A', label: '靈魂的冥想。沉浸在「慢工出細活」裡是極致的紓壓。' },
      { key: 'B', label: '意志力的考驗。我更傾向於直接購買成品來享受生活。' },
    ],
  },
  {
    key: 'Q5',
    text: '路過一家風格奇特、充滿個人色彩的文創選物店，你的反應是？',
    options: [
      { key: 'A', label: '像磁鐵一樣被吸進去！我就愛這些奇奇怪怪的小驚喜。' },
      { key: 'B', label: '保持社交距離。除非真的有需求，否則我很少駐足。' },
    ],
  },
  {
    key: 'Q6',
    text: '當太陽下山、霓虹燈亮起，你體內的細胞通常會？',
    options: [
      { key: 'A', label: '全面甦醒！夜晚才是我的主場，越夜越有活力。' },
      { key: 'B', label: '準備休眠。太陽下山後，我的靈魂也想跟著床鋪合體。' },
    ],
  },
  {
    key: 'Q7',
    text: '比起在摩天大樓間穿梭，你更渴望讓雙腳踩在什麼樣的土地上？',
    options: [
      { key: 'A', label: '濕潤的泥土或森林草地，大自然才是我的救贖。' },
      { key: 'B', label: '乾淨平整的大理石地板，吹著冷氣逛街才是正經事。' },
    ],
  },
  {
    key: 'Q8',
    text: '今天的你，是要進行一場「限時 24 小時」的忙裡偷閒大作戰嗎？',
    options: [
      { key: 'A', label: '沒錯！戰鬥力已滿，我準備好要在今天內征服這座城市的所有美好。' },
      { key: 'B', label: '沒這回事！我想要的是慢節奏，打算在這裡多賴幾天，慢慢感受。' },
    ],
  },
  {
    key: 'Q9',
    text: '這次有帶著家裡的「小跟班」一起冒險嗎？',
    options: [
      { key: 'A', label: '有，帶孩子一起同行！' },
      { key: 'B', label: '沒有，這次是我的 Me Time～' },
    ],
  },
];

const phase = ref<'quiz' | 'result'>('quiz')
const currentQ = ref(1)
const selectedAnswer = ref<string>('')
const answers = ref<Record<string, string>>({})
const loading = ref(false)
const errorText = ref('')
const gene = ref('')
const mascot = ref('')
const geneDescription = ref('')
const sessionId = ref('')

const currentQuestion = computed(() => QUESTIONS[currentQ.value - 1])

onMounted(async () => {
  try {
    const session = await createSession()
    sessionId.value = session.session_id
    localStorage.setItem('chitogo_session_id', session.session_id)
    localStorage.removeItem('chitogo_gene')
    localStorage.removeItem('chitogo_mascot')
    clearAccommodationState()
  } catch {
    errorText.value = '無法建立對話，請重新整理頁面。'
  }
})

function selectAnswer(key: string) {
  selectedAnswer.value = key
}

async function nextQuestion() {
  if (!selectedAnswer.value) return
  answers.value[`Q${currentQ.value}`] = selectedAnswer.value
  selectedAnswer.value = ''

  if (currentQ.value < 9) {
    currentQ.value++
    return
  }

  loading.value = true
  errorText.value = ''
  try {
    const result = await submitQuiz(sessionId.value, answers.value as QuizAnswers)
    gene.value = result.travel_gene
    mascot.value = result.mascot
    geneDescription.value = result.gene_description
    localStorage.setItem('chitogo_gene', result.travel_gene)
    localStorage.setItem('chitogo_mascot', result.mascot)
    phase.value = 'result'
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorText.value = e?.response?.data?.detail ?? '提交失敗，請重試。'
  } finally {
    loading.value = false
  }
}

function onMascotImgError(e: Event) {
  (e.target as HTMLImageElement).style.display = 'none'
}

function goToAccommodation() {
  router.push('/accommodation')
}
</script>

<style scoped>
.quiz-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f0f4ff;
  padding: 20px;
}

.quiz-card, .result-card {
  background: white;
  border-radius: 20px;
  padding: 40px 32px;
  max-width: 480px;
  width: 100%;
  box-shadow: 0 8px 32px rgba(77, 104, 191, 0.12);
}

.progress-bar {
  height: 6px;
  background: #e2e8f0;
  border-radius: 3px;
  margin-bottom: 8px;
}

.progress-fill {
  height: 100%;
  background: #4d68bf;
  border-radius: 3px;
  transition: width 0.3s;
}

.progress-label {
  text-align: right;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 24px;
}

.question-text {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 24px;
  line-height: 1.5;
}

.options {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 28px;
}

.option-btn {
  padding: 14px 20px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  background: white;
  color: #334155;
  font-size: 15px;
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
}

.option-btn:hover {
  border-color: #4d68bf;
  background: #f0f4ff;
}

.option-btn.selected {
  border-color: #4d68bf;
  background: #4d68bf;
  color: white;
}

.next-btn {
  width: 100%;
  padding: 14px;
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.next-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.next-btn:not(:disabled):hover {
  background: #3d55a0;
}

.error {
  margin-top: 12px;
  color: #ef4444;
  font-size: 14px;
  text-align: center;
}

/* Result card */
.mascot-img {
  text-align: center;
  margin-bottom: 20px;
}

.mascot-img img {
  width: 120px;
  height: 120px;
  object-fit: contain;
}

.gene-title {
  text-align: center;
  font-size: 24px;
  font-weight: 700;
  color: #4d68bf;
  margin-bottom: 12px;
}

.gene-desc {
  text-align: center;
  color: #64748b;
  font-size: 15px;
  line-height: 1.7;
  margin-bottom: 28px;
}

.start-btn {
  width: 100%;
  padding: 14px;
  background: #4d68bf;
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 16px;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}

.start-btn:hover {
  background: #3d55a0;
}
</style>
