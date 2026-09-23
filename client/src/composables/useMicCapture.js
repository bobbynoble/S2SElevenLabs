// Captures microphone audio and encodes it as 16-bit PCM chunks. This is a mic-capture
// utility only -- it does no speech recognition, translation, or synthesis. The silence
// timer decides *when* to stop sending audio (a UX safety net for push-to-talk), it does
// not interpret what was said.

import { ref } from 'vue'
import { createNoiseGraph } from '../audio/hospitalNoise.js'

const TARGET_SAMPLE_RATE = 16000
const CHUNK_FLUSH_MS = 200
const SILENCE_RMS_THRESHOLD = 0.01
const SILENCE_AUTO_STOP_MS = 1800

function floatTo16BitPCM(floatSamples) {
  const buffer = new ArrayBuffer(floatSamples.length * 2)
  const view = new DataView(buffer)
  for (let i = 0; i < floatSamples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, floatSamples[i]))
    view.setInt16(i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
  }
  return buffer
}

function rms(floatSamples) {
  let sum = 0
  for (let i = 0; i < floatSamples.length; i++) {
    sum += floatSamples[i] * floatSamples[i]
  }
  return Math.sqrt(sum / floatSamples.length)
}

// True digital clipping (samples pinned at the format's +/-1.0 ceiling), not just "loud" --
// the level meter alone saturates at 100% well before this and can't tell the two apart.
const CLIP_THRESHOLD = 0.98
function clipFraction(floatSamples) {
  let clipped = 0
  for (let i = 0; i < floatSamples.length; i++) {
    if (Math.abs(floatSamples[i]) >= CLIP_THRESHOLD) clipped++
  }
  return clipped / floatSamples.length
}

export function useMicCapture({ onChunk, onSilenceTimeout, getNoiseLevel } = {}) {
  let audioContext = null
  let sourceNode = null
  let workletNode = null
  let stream = null
  let noiseGraph = null
  let pendingSamples = []
  let pendingSampleCount = 0
  let flushTimer = null
  let silenceTimer = null
  // A quick tap can call stop() while start()'s async setup (getUserMedia, worklet module
  // load) is still in flight. Without this flag, stop() has nothing to tear down yet --
  // stream/audioContext are still null -- and start() finishes moments later regardless,
  // silently capturing and streaming mic audio the UI already believes has stopped. Checked
  // after every await in start(); a stop requested mid-setup tears down whatever was
  // acquired so far instead of wiring up ongoing capture.
  let stopRequested = false

  // On-screen diagnostics -- exposed so a view can show them directly, since dev-tools console
  // output has repeatedly turned out to be unreliable to read back over a support conversation
  // (filtered views, "nothing" reported when lines were actually there, etc.). No audio content
  // in either: a sample rate number and a 0-100 loudness meter.
  const actualSampleRate = ref(null)
  const liveLevelPercent = ref(0)
  const isClipping = ref(false)
  let clippedChunkStreak = 0

  function flushPending() {
    if (pendingSampleCount === 0) return
    const merged = new Float32Array(pendingSampleCount)
    let offset = 0
    for (const chunk of pendingSamples) {
      merged.set(chunk, offset)
      offset += chunk.length
    }
    pendingSamples = []
    pendingSampleCount = 0
    onChunk?.(floatTo16BitPCM(merged))
  }

  function armSilenceTimer() {
    clearTimeout(silenceTimer)
    silenceTimer = setTimeout(() => onSilenceTimeout?.(), SILENCE_AUTO_STOP_MS)
  }

  function teardown() {
    clearInterval(flushTimer)
    clearTimeout(silenceTimer)
    flushTimer = null
    silenceTimer = null
    pendingSamples = []
    pendingSampleCount = 0
    workletNode?.disconnect()
    sourceNode?.disconnect()
    workletNode = null
    sourceNode = null
    noiseGraph?.stop()
    noiseGraph = null
    stream?.getTracks().forEach((track) => track.stop())
    stream = null
    audioContext?.close()
    audioContext = null
  }

  async function start() {
    stopRequested = false

    // Explicit, not left to browser defaults: echoCancellation in particular directly targets
    // the same-device feedback loop (speaker's own TTS reply leaking back into the mic) that
    // live testing traced as the actual cause of clipped, untranscribable audio -- confirmed by
    // the peak-amplitude diagnostic pegging at 100% specifically on turns that produced nothing.
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    if (stopRequested) {
      stream.getTracks().forEach((track) => track.stop())
      stream = null
      return
    }

    audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE })
    // The constructor's sampleRate option is a request, not a guarantee -- some browser/OS/
    // device combinations silently ignore it and run at their own native rate instead (often
    // 44100 or 48000Hz). The worklet below has no resampling logic and just forwards whatever
    // rate the context actually gives it, while the server always assumes 16000Hz -- a mismatch
    // here means every chunk sent is effectively played back at the wrong speed, which can
    // still measure as loud (real audio energy) while being unrecognizable as speech to STT.
    actualSampleRate.value = audioContext.sampleRate
    const workletUrl = new URL('../worklets/pcm-capture-processor.js', import.meta.url)
    await audioContext.audioWorklet.addModule(workletUrl)
    if (stopRequested) {
      teardown()
      return
    }

    sourceNode = audioContext.createMediaStreamSource(stream)
    workletNode = new AudioWorkletNode(audioContext, 'pcm-capture-processor')

    // Testing aid: optionally mix synthesized hospital-reception noise in with the real mic
    // signal before it reaches the worklet, so noise robustness can be exercised with real
    // speech rather than only offline. With noise enabled, ambient level alone can sit above
    // SILENCE_RMS_THRESHOLD, so the auto-stop timer may not fire -- release the button
    // manually in that case.
    const level = getNoiseLevel?.() ?? 'off'
    const mixNode = audioContext.createGain()
    sourceNode.connect(mixNode)
    if (level !== 'off') {
      noiseGraph = createNoiseGraph(audioContext, level)
      noiseGraph.output.connect(mixNode)
      // Also route to the speakers -- otherwise the noise silently affects only the audio
      // sent for transcription, with nothing audible to confirm it's actually on.
      noiseGraph.output.connect(audioContext.destination)
    }

    workletNode.port.onmessage = (event) => {
      const samples = event.data
      pendingSamples.push(samples)
      pendingSampleCount += samples.length
      const rmsLevel = rms(samples)
      liveLevelPercent.value = Math.min(100, Math.round(rmsLevel * 300))

      // A chunk that's mostly at the digital ceiling, sustained over many consecutive chunks
      // (~150ms+, not just one loud transient), is the signature traced live to same-device
      // feedback -- distorted audio that measures loud but transcribes as nothing.
      if (clipFraction(samples) > 0.5) {
        clippedChunkStreak++
      } else {
        clippedChunkStreak = 0
      }
      isClipping.value = clippedChunkStreak >= 20

      if (rmsLevel >= SILENCE_RMS_THRESHOLD) {
        armSilenceTimer()
      } else if (!silenceTimer) {
        armSilenceTimer()
      }
    }

    mixNode.connect(workletNode)

    if (stopRequested) {
      teardown()
      return
    }

    flushTimer = setInterval(flushPending, CHUNK_FLUSH_MS)
    armSilenceTimer()
  }

  function stop() {
    stopRequested = true
    flushPending()
    teardown()
    actualSampleRate.value = null
    liveLevelPercent.value = 0
    isClipping.value = false
    clippedChunkStreak = 0
  }

  return { start, stop, actualSampleRate, liveLevelPercent, isClipping }
}
