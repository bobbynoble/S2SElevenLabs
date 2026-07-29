<template>
  <div class="page">
    <AppHeader />
    <main class="receptionist">
      <template v-if="!languageConfirmed">
        <h1>Reception Console</h1>
        <p class="helper">Choose the language you'll be speaking as the receptionist.</p>
        <LanguagePicker v-model="selectedLanguage" :languages="languages" />
        <button type="button" class="btn btn-primary continue" :disabled="!selectedLanguage" @click="confirmLanguage">
          Start
        </button>
      </template>

      <template v-else>
        <h1>Reception Console</h1>
        <div class="status-row">
          <ConnectionStatus :state="status.state" :detail="status.state === 'error' ? status.detail : null" />
          <p v-if="status.state !== 'error' && status.detail" class="patient-lang">Patient language: {{ status.detail }}</p>
        </div>
        <CaptionPanel :captions="captions" />
        <p class="helper hint">Press and hold the button below, speak, then release.</p>
        <MicButton @start="onMicStart" @end="onMicEnd" />
        <button type="button" class="btn btn-secondary end-session" @click="onEndSession">End Session</button>
      </template>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { useSession } from '../composables/useSession.js'
import { useMicCapture } from '../composables/useMicCapture.js'
import AppHeader from '../components/AppHeader.vue'
import LanguagePicker from '../components/LanguagePicker.vue'
import ConnectionStatus from '../components/ConnectionStatus.vue'
import CaptionPanel from '../components/CaptionPanel.vue'
import MicButton from '../components/MicButton.vue'

const props = defineProps({
  sessionId: { type: String, required: true },
})

const route = useRoute()
const router = useRouter()

const languages = ref([])
const selectedLanguage = ref('en')
const languageConfirmed = ref(false)

const { status, captions, connectAsReceptionist, join, startTurn, endTurn, endSession, sendAudioChunk, primeAudio, disconnect } =
  useSession()

const mic = useMicCapture({
  onChunk: sendAudioChunk,
  onSilenceTimeout: () => onMicEnd(),
})

onMounted(async () => {
  const storageKey = `secret:${props.sessionId}`
  let secret = route.query.secret
  if (secret) {
    sessionStorage.setItem(storageKey, secret)
  } else {
    secret = sessionStorage.getItem(storageKey)
  }
  if (!secret) {
    router.push('/')
    return
  }

  languages.value = await api.getLanguages()
  connectAsReceptionist(props.sessionId, secret)
})

function confirmLanguage() {
  primeAudio()
  join(selectedLanguage.value)
  languageConfirmed.value = true
}

async function onMicStart() {
  startTurn()
  await mic.start()
}

function onMicEnd() {
  mic.stop()
  endTurn()
}

function onEndSession() {
  endSession()
  router.push('/')
}

onBeforeUnmount(() => {
  mic.stop()
  disconnect()
})
</script>

<style scoped>
.page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.receptionist {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  max-width: 640px;
  margin: 0 auto;
  width: 100%;
}
h1 {
  margin: 0;
  font-size: 1.6rem;
}
.helper {
  color: var(--color-muted);
  margin: -0.75rem 0 0;
  font-size: 1rem;
}
.hint {
  margin: 0;
  text-align: center;
}
.continue {
  font-size: 1.1rem;
}
.status-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.patient-lang {
  color: var(--color-muted);
  font-size: 0.95rem;
  margin: 0;
}
.end-session {
  align-self: center;
}
</style>
