// Plays back synthesized audio received from the backend. Buffer-then-play: the backend
// wraps a turn's audio in audio_reply_start/audio_reply_end, so we accumulate the binary
// frames in between and decode+play once the reply is complete. No AI/translation logic here.

function mergeArrayBuffers(buffers) {
  const total = buffers.reduce((sum, buf) => sum + buf.byteLength, 0)
  const merged = new Uint8Array(total)
  let offset = 0
  for (const buffer of buffers) {
    merged.set(new Uint8Array(buffer), offset)
    offset += buffer.byteLength
  }
  return merged.buffer
}

export function useAudioPlayback() {
  const audioContext = new (window.AudioContext || window.webkitAudioContext)()
  let chunks = []

  function appendChunk(arrayBuffer) {
    chunks.push(arrayBuffer)
  }

  async function playBuffered() {
    if (chunks.length === 0) return
    const merged = mergeArrayBuffers(chunks)
    chunks = []
    const audioBuffer = await audioContext.decodeAudioData(merged)
    const source = audioContext.createBufferSource()
    source.buffer = audioBuffer
    source.connect(audioContext.destination)
    source.start()
  }

  return { appendChunk, playBuffered }
}
