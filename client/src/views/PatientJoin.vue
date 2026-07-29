<template>
  <div class="patient-join">
    <template v-if="phase === 'picking_language'">
      <h1>Choose your language</h1>
      <LanguagePicker v-if="languages.length" v-model="selectedLanguage" :languages="languages" />
      <button type="button" class="continue" :disabled="!selectedLanguage" @click="confirmLanguage">
        Continue
      </button>
    </template>

    <template v-else>
      <ConnectionStatus :state="status.state" />
      <CaptionPanel :captions="captions" />
      <MicButton @start="onMicStart" @end="onMicEnd" />
    </template>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api.js'
import { useSession } from '../composables/useSession.js'
import { useMicCapture } from '../composables/useMicCapture.js'
import LanguagePicker from '../components/LanguagePicker.vue'
import ConnectionStatus from '../components/ConnectionStatus.vue'
import CaptionPanel from '../components/CaptionPanel.vue'
import MicButton from '../components/MicButton.vue'

const props = defineProps({
  token: { type: String, required: true },
})

const languages = ref([])
const selectedLanguage = ref(sessionStorage.getItem(`lang:${props.token}`) || null)
const phase = ref('picking_language')

const { status, captions, connectAsPatient, join, startTurn, endTurn, sendAudioChunk, disconnect } =
  useSession()

const mic = useMicCapture({
  onChunk: sendAudioChunk,
  onSilenceTimeout: () => onMicEnd(),
})

onMounted(async () => {
  languages.value = await api.getLanguages()
  connectAsPatient(props.token)
  if (selectedLanguage.value) {
    confirmLanguage()
  }
})

function confirmLanguage() {
  if (!selectedLanguage.value) return
  sessionStorage.setItem(`lang:${props.token}`, selectedLanguage.value)
  join(selectedLanguage.value)
  phase.value = 'in_call'
}

async function onMicStart() {
  startTurn()
  await mic.start()
}

function onMicEnd() {
  mic.stop()
  endTurn()
}

onBeforeUnmount(() => {
  mic.stop()
  disconnect()
})
</script>

<style scoped>
.patient-join {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding: 1.5rem;
  max-width: 480px;
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
</style>
