import { ref } from 'vue'
import { connectPatientSocket, connectReceptionistSocket } from '../ws.js'
import { useAudioPlayback } from './useAudioPlayback.js'

export function useSession() {
  const status = ref({ state: 'connecting', detail: null })
  const captions = ref([])
  const error = ref(null)
  const clinicalCode = ref(null)
  const usage = ref(null)

  let socket = null
  const playback = useAudioPlayback()
  let receivingAudio = false
  // disconnect() closes the socket deliberately (navigating away, ending the session) and
  // triggers the same browser 'close' event as an unexpected drop -- this flag is the only way
  // to tell the two apart, so a normal navigation away doesn't flash a scary "connection lost"
  // error in the instant before the page actually leaves.
  let intentionalDisconnect = false

  function handleClose() {
    if (intentionalDisconnect) return
    status.value = { state: 'error', detail: 'Connection lost. Check your network and try again.' }
  }

  function handleMessage(json, binary) {
    if (binary) {
      if (receivingAudio) playback.appendChunk(binary)
      return
    }
    switch (json.type) {
      case 'status':
        status.value = { state: json.state, detail: json.detail }
        break
      case 'caption':
        captions.value.push(json)
        break
      case 'audio_reply_start':
        receivingAudio = true
        playback.startReply()
        break
      case 'audio_reply_end':
        receivingAudio = false
        break
      case 'error':
        error.value = json
        status.value = { state: 'error', detail: json.message }
        break
      case 'clinical_code':
        clinicalCode.value = json
        break
      case 'usage':
        usage.value = json
        break
    }
  }

  function connectAsPatient(token) {
    intentionalDisconnect = false
    socket = connectPatientSocket(token, { onMessage: handleMessage, onClose: handleClose })
  }

  function connectAsReceptionist(sessionId, secret) {
    intentionalDisconnect = false
    socket = connectReceptionistSocket(sessionId, secret, { onMessage: handleMessage, onClose: handleClose })
  }

  function join(language) {
    socket?.sendJson({ type: 'join', language })
  }

  function startTurn() {
    socket?.sendJson({ type: 'start_turn' })
  }

  function endTurn() {
    socket?.sendJson({ type: 'end_turn' })
  }

  function endSession() {
    socket?.sendJson({ type: 'end_session' })
  }

  function sendAudioChunk(buffer) {
    socket?.sendBinary(buffer)
  }

  function disconnect() {
    intentionalDisconnect = true
    socket?.close()
  }

  function primeAudio() {
    playback.prime()
  }

  return {
    status,
    captions,
    error,
    clinicalCode,
    usage,
    connectAsPatient,
    connectAsReceptionist,
    join,
    startTurn,
    endTurn,
    endSession,
    sendAudioChunk,
    primeAudio,
    disconnect,
  }
}
