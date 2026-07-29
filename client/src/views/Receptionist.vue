<template>
  <div class="receptionist">
    <h1>Reception Console</h1>

    <template v-if="!languageConfirmed">
      <LanguagePicker v-model="selectedLanguage" :languages="languages" />
      <button type="button" class="continue" :disabled="!selectedLanguage" @click="confirmLanguage">
        Start
      </button>
    </template>

    <template v-else>
      <ConnectionStatus :state="status.state" />
      <p v-if="status.detail" class="patient-lang">Patient language: {{ status.detail }}</p>
      <CaptionPanel :captions="captions" />
      <MicButton @start="onMicStart" @end="onMicEnd" />
      <button type="button" class="end-session" @click="onEndSession">End Session</button>
    </template>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api.js'
import { useSession } from '../composables/useSession.js'
import { useMicCapture } from '../composables/useMicCapture.js'
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
.receptionist {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  max-width: 640px;
  margin: 0 auto;
}
.continue {
  padding: 1rem;
  border-radius: 0.75rem;
  border: none;
  background: var(--color-accent);
  color: white;
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
}
.continue:disabled {
  background: var(--color-border);
  color: var(--color-muted);
  cursor: not-allowed;
}
.patient-lang {
  color: var(--color-muted);
  font-size: 0.9rem;
}
.end-session {
  padding: 0.5rem 1.25rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-muted);
  cursor: pointer;
  align-self: center;
}
</style>
