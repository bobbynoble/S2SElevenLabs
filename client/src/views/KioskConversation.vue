<template>
  <div class="kiosk-conversation">
    <template v-if="phase === 'picking_languages'">
      <h1>Set up this conversation</h1>
      <p class="helper">Both people pick their language on this screen, then share the tablet to talk.</p>

      <section class="language-block">
        <h2>Patient's language</h2>
        <LanguagePicker v-if="languages.length" v-model="patientLanguage" :languages="languages" />
      </section>

      <section class="language-block">
        <h2>Receptionist's language</h2>
        <LanguagePicker v-if="languages.length" v-model="receptionistLanguage" :languages="languages" />
      </section>

      <button
        type="button"
        class="btn btn-primary start"
        :disabled="!patientLanguage || !receptionistLanguage"
        @click="startConversation"
      >
        Start conversation
      </button>
      <button type="button" class="btn btn-secondary" @click="$emit('end')">Back</button>
      <p class="privacy-note">This conversation is interpreted live and isn't saved once the session ends.</p>
    </template>

    <template v-else-if="!sessionEnded">
      <ConnectionStatus v-if="combinedStatus" :state="combinedStatus.state" :detail="combinedStatus.state === 'error' ? combinedStatus.detail : null" />
      <CaptionPanel :captions="receptionistSession.captions.value" />

      <div class="mic-row">
        <div class="mic-col">
          <span class="mic-label">Receptionist</span>
          <MicButton ref="receptionistMicButton" :disabled="otherSideBusy" @start="onReceptionistMicStart" @end="onReceptionistMicEnd" />
          <p v-if="receptionistMic.actualSampleRate.value" class="mic-diagnostic" :class="{ clipping: receptionistMic.isClipping.value }">
            {{ receptionistMic.actualSampleRate.value }}Hz &middot; level
            <span class="level-meter"><span class="level-fill" :style="{ width: receptionistMic.liveLevelPercent.value + '%' }"></span></span>
            {{ receptionistMic.liveLevelPercent.value }}%
          </p>
          <p v-if="receptionistMic.isClipping.value" class="clip-warning">⚠ Distorted audio &mdash; move away from the speaker</p>
        </div>
        <div class="mic-col">
          <span class="mic-label">Patient</span>
          <MicButton ref="patientMicButton" :disabled="otherSideBusy" @start="onPatientMicStart" @end="onPatientMicEnd" />
          <p v-if="patientMic.actualSampleRate.value" class="mic-diagnostic" :class="{ clipping: patientMic.isClipping.value }">
            {{ patientMic.actualSampleRate.value }}Hz &middot; level
            <span class="level-meter"><span class="level-fill" :style="{ width: patientMic.liveLevelPercent.value + '%' }"></span></span>
            {{ patientMic.liveLevelPercent.value }}%
          </p>
          <p v-if="patientMic.isClipping.value" class="clip-warning">⚠ Distorted audio &mdash; move away from the speaker</p>
        </div>
      </div>

      <button type="button" class="btn btn-secondary end-session" @click="onEndSession">End Session</button>
    </template>

    <template v-else>
      <CaptionPanel :captions="receptionistSession.captions.value" />

      <div v-if="receptionistSession.clinicalCode.value" class="coding-result">
        <h2>Suggested clinical codes</h2>
        <div v-for="(s, i) in receptionistSession.clinicalCode.value.suggestions" :key="i" class="suggestion">
          <p class="code">
            {{ s.code }} <span class="system">({{ s.system }})</span>
            <span v-if="s.confidence" class="confidence" :class="s.confidence">{{ s.confidence }}</span>
          </p>
          <p v-if="s.description" class="description">{{ s.description }}</p>
          <p v-if="s.justification" class="justification">{{ s.justification }}</p>
          <p v-if="s.review_flag" class="review-flag">⚠ {{ s.review_flag }}</p>
        </div>
        <p v-if="receptionistSession.clinicalCode.value.coding_notes" class="coding-notes">
          {{ receptionistSession.clinicalCode.value.coding_notes }}
        </p>
      </div>
      <p v-else-if="receptionistSession.error.value?.code === 'coding_failed'" class="coding-error">
        Couldn't determine a clinical code: {{ receptionistSession.error.value.message }}
      </p>
      <p v-else-if="receptionistSession.status.value.state === 'coding'" class="helper hint">Determining clinical code…</p>

      <div v-if="receptionistSession.usage.value" class="usage-summary">
        ElevenLabs usage: {{ receptionistSession.usage.value.stt_seconds }}s STT,
        {{ receptionistSession.usage.value.tts_characters }} TTS characters
        &mdash; est. ${{ receptionistSession.usage.value.estimated_cost_usd.toFixed(4) }}
      </div>

      <button type="button" class="btn btn-primary" @click="onDone">Back to reception desk</button>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api.js'
import { useSession } from '../composables/useSession.js'
import { useMicCapture } from '../composables/useMicCapture.js'
import LanguagePicker from '../components/LanguagePicker.vue'
import ConnectionStatus from '../components/ConnectionStatus.vue'
import CaptionPanel from '../components/CaptionPanel.vue'
import MicButton from '../components/MicButton.vue'

const props = defineProps({
  session: { type: Object, required: true },
})
const emit = defineEmits(['end'])

const phase = ref('picking_languages')
const languages = ref([])
const patientLanguage = ref(null)
const receptionistLanguage = ref('en')

// The patient join token is embedded as the last path segment of patient_join_url (see
// server/src/qr.py build_join_url) -- reused here to join as "patient" from this same device
// instead of a separate phone, rather than the backend needing a distinct local-join concept.
const patientToken = new URL(props.session.patient_join_url).pathname.split('/').pop()

const receptionistSession = useSession()
const patientSession = useSession()

const receptionistMicButton = ref(null)
const patientMicButton = ref(null)
const sessionEnded = ref(false)

const receptionistMic = useMicCapture({
  onChunk: receptionistSession.sendAudioChunk,
  onSilenceTimeout: () => receptionistMicButton.value?.forceRelease(),
})
const patientMic = useMicCapture({
  onChunk: patientSession.sendAudioChunk,
  onSilenceTimeout: () => patientMicButton.value?.forceRelease(),
})

// Both sockets receive identical status/caption broadcasts for this session (see
// _broadcast_status / _broadcast_caption in websocket_handler.py) -- captions can be read from
// either one; status is merged so a turn in progress on either side is reflected here.
const combinedStatus = computed(() => {
  for (const status of [receptionistSession.status.value, patientSession.status.value]) {
    if (['processing', 'speaking', 'error'].includes(status.state)) return status
  }
  return null
})
const otherSideBusy = computed(() => combinedStatus.value !== null)

onMounted(async () => {
  languages.value = await api.getLanguages()
  receptionistSession.connectAsReceptionist(props.session.session_id, props.session.receptionist_secret)
  patientSession.connectAsPatient(patientToken)
})

function startConversation() {
  receptionistSession.primeAudio()
  patientSession.primeAudio()
  receptionistSession.join(receptionistLanguage.value)
  patientSession.join(patientLanguage.value)
  phase.value = 'in_call'
}

async function onReceptionistMicStart() {
  receptionistSession.startTurn()
  await receptionistMic.start()
}
function onReceptionistMicEnd() {
  receptionistMic.stop()
  receptionistSession.endTurn()
}

async function onPatientMicStart() {
  patientSession.startTurn()
  await patientMic.start()
}
function onPatientMicEnd() {
  patientMic.stop()
  patientSession.endTurn()
}

function onEndSession() {
  sessionEnded.value = true
  receptionistMic.stop()
  patientMic.stop()
  // Sockets stay open here (rather than disconnecting immediately) so the receptionist socket
  // can still receive the usage summary and clinical-code suggestions the backend sends right
  // after "ended" -- see onDone for the actual cleanup once those have been seen.
  receptionistSession.endSession()
}

function onDone() {
  receptionistSession.disconnect()
  patientSession.disconnect()
  emit('end')
}

onBeforeUnmount(() => {
  receptionistMic.stop()
  patientMic.stop()
  receptionistSession.disconnect()
  patientSession.disconnect()
})
</script>

<style scoped>
.kiosk-conversation {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
}
h1 {
  margin: 0;
  font-size: 1.6rem;
}
h2 {
  margin: 0 0 0.6rem;
  font-size: 1.05rem;
}
.helper {
  color: var(--color-muted);
  margin: -0.75rem 0 0;
  font-size: 1rem;
}
.language-block {
  text-align: left;
}
.hint {
  margin: 0;
  text-align: center;
}
.start {
  font-size: 1.1rem;
}
.privacy-note {
  color: var(--color-muted);
  font-size: 0.85rem;
  text-align: center;
  margin: 0;
}
.mic-row {
  display: flex;
  gap: 1.5rem;
  justify-content: center;
  flex-wrap: wrap;
}
.mic-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}
.mic-label {
  font-weight: 700;
  color: var(--color-muted);
  text-transform: uppercase;
  font-size: 0.85rem;
  letter-spacing: 0.03em;
}
.mic-diagnostic {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
  font-size: 0.75rem;
  font-family: monospace;
  color: var(--color-muted);
}
.level-meter {
  display: inline-block;
  width: 60px;
  height: 8px;
  background: var(--color-border);
  border-radius: 4px;
  overflow: hidden;
}
.level-fill {
  display: block;
  height: 100%;
  background: var(--color-accent);
  transition: width 0.05s linear;
}
.mic-diagnostic.clipping .level-fill {
  background: var(--color-error);
}
.clip-warning {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--color-error);
}
.end-session {
  align-self: center;
}
.coding-result {
  align-self: center;
  text-align: center;
  background: #e5f5ea;
  border: 1px solid #b6e3c4;
  border-radius: 6px;
  padding: 1rem 1.5rem;
}
.coding-result h2 {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}
.coding-result .suggestion + .suggestion {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid #b6e3c4;
}
.coding-result .code {
  margin: 0;
  font-size: 1.4rem;
  font-weight: 700;
}
.coding-result .system {
  font-weight: 400;
  color: var(--color-muted);
}
.coding-result .description {
  margin: 0.4rem 0 0;
  color: var(--color-muted);
}
.coding-result .justification {
  margin: 0.3rem 0 0;
  font-size: 0.9rem;
  color: var(--color-muted);
  font-style: italic;
}
.coding-result .review-flag {
  margin: 0.4rem 0 0;
  font-weight: 700;
  color: var(--amber-text, #92400e);
}
.coding-result .coding-notes {
  margin: 1rem 0 0;
  padding-top: 0.75rem;
  border-top: 1px solid #b6e3c4;
  font-size: 0.9rem;
  color: var(--color-muted);
}
.confidence {
  display: inline-block;
  margin-left: 0.4rem;
  padding: 0.05rem 0.5rem;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  vertical-align: middle;
  background: var(--color-border);
  color: var(--color-muted);
}
.confidence.high {
  background: #d1fadf;
  color: #067647;
}
.confidence.medium {
  background: #fef0c7;
  color: #93500f;
}
.confidence.low {
  background: #fee4e2;
  color: #b42318;
}
.coding-error {
  align-self: center;
  color: var(--color-error);
  text-align: center;
}
.usage-summary {
  align-self: center;
  color: var(--color-muted);
  font-size: 0.85rem;
  text-align: center;
}
</style>
