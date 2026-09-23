// Plays back synthesized speech audio streamed from the backend as it's generated, rather than
// waiting for the whole reply to finish synthesizing first -- the backend forwards each raw PCM
// chunk from ElevenLabs' streaming TTS endpoint as soon as it arrives (see audio_reply_start in
// websocket_handler.py), so playback can start well before the rest of the reply exists.

const SAMPLE_RATE = 16000

export function useAudioPlayback() {
  const audioContext = new (window.AudioContext || window.webkitAudioContext)()
  let nextStartTime = 0

  function startReply() {
    nextStartTime = audioContext.currentTime
  }

  function appendChunk(arrayBuffer) {
    const samples = new Int16Array(arrayBuffer)
    const floatSamples = new Float32Array(samples.length)
    for (let i = 0; i < samples.length; i++) floatSamples[i] = samples[i] / 32768
    const audioBuffer = audioContext.createBuffer(1, floatSamples.length, SAMPLE_RATE)
    audioBuffer.copyToChannel(floatSamples, 0)

    const source = audioContext.createBufferSource()
    source.buffer = audioBuffer
    source.connect(audioContext.destination)

    // Chunks can arrive faster or slower than real-time playback consumes them -- scheduling
    // each one back-to-back off the last (rather than starting it the instant it lands) avoids
    // both overlapping audio and audible gaps between chunks.
    const startAt = Math.max(nextStartTime, audioContext.currentTime)
    source.start(startAt)
    nextStartTime = startAt + audioBuffer.duration
  }

  // Call from a user-gesture handler (button click) so iOS Safari unlocks the context.
  function prime() {
    if (audioContext.state === 'suspended') audioContext.resume()
  }

  return { startReply, appendChunk, prime }
}
