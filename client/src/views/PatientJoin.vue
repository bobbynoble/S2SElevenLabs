<template>
  <div class="page">
    <AppHeader />
    <main class="patient-join">
      <template v-if="phase === 'picking_language'">
        <h1>Choose your language</h1>
        <p class="helper">This lets the receptionist see and hear you in your own language.</p>
        <LanguagePicker v-if="languages.length" v-model="selectedLanguage" :languages="languages" />
        <button type="button" class="btn btn-primary continue" :disabled="!selectedLanguage" @click="confirmLanguage">
          Continue
        </button>
      </template>

      <template v-else>
        <ConnectionStatus :state="status.state" :detail="status.detail" />
        <CaptionPanel :captions="captions" />
        <div class="noise-control">
          <label for="noiseLevel">Testing: simulate background noise</label>
          <select id="noiseLevel" v-model="noiseLevel">
            <option v-for="opt in NOISE_LEVELS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <p class="helper hint">Press and hold the button below, speak, then release.</p>
        <MicButton ref="micButton" @start="onMicStart" @end="onMicEnd" />
      </template>
    </main>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api.js'
import { useSession } from '../composables/useSession.js'
import { useMicCapture } from '../composables/useMicCapture.js'
import { NOISE_LEVELS } from '../audio/hospitalNoise.js'
import AppHeader from '../components/AppHeader.vue'
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

const { status, captions, connectAsPatient, join, startTurn, endTurn, sendAudioChunk, primeAudio, disconnect } =
  useSession()

const micButton = ref(null)
const noiseLevel = ref('off')

const mic = useMicCapture({
  onChunk: sendAudioChunk,
  // Goes through the button's own release path (rather than calling onMicEnd directly) so
  // its visual "held" state resets in sync with the turn actually ending -- otherwise it's
  // left showing "Release to send" after an auto-stop with nothing left to release.
  onSilenceTimeout: () => micButton.value?.forceRelease(),
  getNoiseLevel: () => noiseLevel.value,
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
  primeAudio()
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
.page {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}
.patient-join {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.5rem;
  max-width: 480px;
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
.noise-control {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  align-self: center;
  padding: 0.4rem 0.75rem;
  border: 1px dashed var(--color-border);
  border-radius: 4px;
  font-size: 0.85rem;
  color: var(--color-muted);
}
.noise-control select {
  font-family: inherit;
  font-size: 0.85rem;
  padding: 0.2rem 0.4rem;
}
</style>
