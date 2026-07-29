import { ref } from 'vue'
import { connectPatientSocket, connectReceptionistSocket } from '../ws.js'
import { useAudioPlayback } from './useAudioPlayback.js'

export function useSession() {
  const status = ref({ state: 'connecting', detail: null })
  const captions = ref([])
  const error = ref(null)

  let socket = null
  const playback = useAudioPlayback()
  let receivingAudio = false

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
        break
      case 'audio_reply_end':
        receivingAudio = false
        playback.playBuffered()
        break
      case 'error':
        error.value = json
        break
    }
  }

  function connectAsPatient(token) {
    socket = connectPatientSocket(token, { onMessage: handleMessage })
  }

  function connectAsReceptionist(sessionId, secret) {
    socket = connectReceptionistSocket(sessionId, secret, { onMessage: handleMessage })
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
    socket?.close()
  }

  function primeAudio() {
    playback.prime()
  }

  return {
    status,
    captions,
    error,
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
