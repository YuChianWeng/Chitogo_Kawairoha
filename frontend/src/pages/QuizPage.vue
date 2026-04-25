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
      <button class="start-btn" @click="goToSetup">開始規劃行程</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createSession, submitQuiz } from '../services/api'
import type { QuizAnswers } from '../types/trip'

const router = useRouter()

const QUESTIONS = [
  {
    key: 'Q1',
    text: '你理想中的旅遊環境是？',
    options: [
      { key: 'A', label: '文青咖啡廳、書店、展覽' },
      { key: 'B', label: '戶外公園、山徑、自然景觀' },
      { key: 'C', label: '熱鬧夜市、酒吧、深夜食堂' },
    ],
  },
  {
    key: 'Q2',
    text: '你喜歡的旅遊節奏是？',
    options: [
      { key: 'A', label: '慢慢逛，享受每個細節' },
      { key: 'B', label: '快速打卡，行程塞滿滿' },
    ],
  },
  {
    key: 'Q3',
    text: '對於人潮你的態度是？',
    options: [
      { key: 'A', label: '偏好安靜、小眾的地方' },
      { key: 'B', label: '熱鬧有趣，人多更好玩' },
    ],
  },
  {
    key: 'Q4',
    text: '這次旅遊你的同行對象是？',
    options: [
      { key: 'A', label: '朋友或另一半' },
      { key: 'B', label: '家人、小孩' },
    ],
  },
  {
    key: 'Q5',
    text: '你對飲食的態度是？',
    options: [
      { key: 'A', label: '想嚐當地特色或網路名店' },
      { key: 'B', label: '輕食、咖啡、健康取向' },
    ],
  },
  {
    key: 'Q6',
    text: '你最活躍的時段是？',
    options: [
      { key: 'A', label: '白天（上午到傍晚）' },
      { key: 'B', label: '夜晚（晚上到深夜）' },
    ],
  },
  {
    key: 'Q7',
    text: '你更偏好哪種體驗？',
    options: [
      { key: 'A', label: '文化、藝術、歷史' },
      { key: 'B', label: '運動、自然、冒險' },
    ],
  },
  {
    key: 'Q8',
    text: '你的移動方式偏好？',
    options: [
      { key: 'A', label: '步行探索，慢慢走' },
      { key: 'B', label: '搭捷運或公車，高效率' },
    ],
  },
  {
    key: 'Q9',
    text: '你對台北的熟悉程度？',
    options: [
      { key: 'A', label: '第一次來，想踩點必遊景點' },
      { key: 'B', label: '常來，想找新鮮感' },
    ],
  },
]

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

function goToSetup() {
  router.push('/setup')
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
