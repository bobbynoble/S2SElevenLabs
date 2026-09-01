// Synthesizes a hospital-reception-style background ambience entirely in the browser --
// HVAC rumble, occasional footsteps, a double-beep monitor, and two band-passed "murmur"
// voices with speech-like on/off rhythm standing in for distant overlapping conversation --
// so background-noise testing doesn't depend on any external audio asset. This is a testing
// aid, not a patient-facing feature -- see the noise-level control in Receptionist.vue /
// PatientJoin.vue.
//
// Deliberately has no flat broadband hiss layer -- that's what reads as generic "static" --
// everything here is either tonal, band-limited, or gated into short bursts.

const LEVELS = {
  quiet: { rumble: 0.03, murmur: 0, footstepEveryS: 0, beepEveryS: 0 },
  busy: { rumble: 0.05, murmur: 0.09, footstepEveryS: 3.5, beepEveryS: 2.4 },
  loud: { rumble: 0.07, murmur: 0.16, footstepEveryS: 1.8, beepEveryS: 1.6 },
}

function noiseBuffer(ctx, seconds) {
  const buffer = ctx.createBuffer(1, Math.round(ctx.sampleRate * seconds), ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  return buffer
}

// One "voice" in the background murmur: band-passed noise around a formant-like centre
// frequency, gated into irregular syllable-length bursts rather than a smooth tone -- a
// continuous filtered drone reads as machinery, not people talking.
function makeMurmurVoice(ctx, master, peakGain, centerFreq, q) {
  const src = ctx.createBufferSource()
  src.buffer = noiseBuffer(ctx, 4)
  src.loop = true
  const filter = ctx.createBiquadFilter()
  filter.type = 'bandpass'
  filter.frequency.value = centerFreq
  filter.Q.value = q
  const gain = ctx.createGain()
  gain.gain.value = 0
  src.connect(filter).connect(gain).connect(master)
  src.start()

  let timer = null
  let stopped = false
  function scheduleSyllable() {
    if (stopped) return
    const now = ctx.currentTime
    const burst = 0.06 + Math.random() * 0.18
    const gap = 0.05 + Math.random() * 0.35
    const peak = peakGain * (0.55 + Math.random() * 0.45)
    gain.gain.cancelScheduledValues(now)
    gain.gain.setValueAtTime(gain.gain.value, now)
    gain.gain.linearRampToValueAtTime(peak, now + 0.02)
    gain.gain.linearRampToValueAtTime(0, now + burst)
    timer = setTimeout(scheduleSyllable, (burst + gap) * 1000)
  }
  scheduleSyllable()

  return {
    stop() {
      stopped = true
      clearTimeout(timer)
      src.stop()
    },
  }
}

function makeFootsteps(ctx, master, everyS) {
  let timer = null
  let stopped = false
  function step() {
    if (stopped) return
    const now = ctx.currentTime
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = 90 + Math.random() * 20
    const gain = ctx.createGain()
    gain.gain.setValueAtTime(0.22, now)
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12)
    osc.connect(gain).connect(master)
    osc.start(now)
    osc.stop(now + 0.13)
    timer = setTimeout(step, everyS * (0.6 + Math.random() * 0.8) * 1000)
  }
  timer = setTimeout(step, Math.random() * everyS * 1000)
  return {
    stop() {
      stopped = true
      clearTimeout(timer)
    },
  }
}

function makeMonitorBeep(ctx, master, everyS) {
  let timer = null
  let stopped = false
  function beepPair() {
    if (stopped) return
    for (const offset of [0, 0.18]) {
      const now = ctx.currentTime + offset
      const osc = ctx.createOscillator()
      osc.type = 'sine'
      osc.frequency.value = 1050
      const gain = ctx.createGain()
      gain.gain.setValueAtTime(0, now)
      gain.gain.linearRampToValueAtTime(0.1, now + 0.01)
      gain.gain.linearRampToValueAtTime(0, now + 0.09)
      osc.connect(gain).connect(master)
      osc.start(now)
      osc.stop(now + 0.1)
    }
    timer = setTimeout(beepPair, everyS * 1000)
  }
  beepPair()
  return {
    stop() {
      stopped = true
      clearTimeout(timer)
    },
  }
}

export function createNoiseGraph(ctx, level) {
  const cfg = LEVELS[level]
  const master = ctx.createGain()
  master.gain.value = 1
  const stopFns = []

  if (cfg.rumble > 0) {
    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = 70
    const gain = ctx.createGain()
    gain.gain.value = cfg.rumble
    osc.connect(gain).connect(master)
    osc.start()
    stopFns.push(() => osc.stop())
  }

  if (cfg.murmur > 0) {
    const low = makeMurmurVoice(ctx, master, cfg.murmur, 450, 1.2)
    const high = makeMurmurVoice(ctx, master, cfg.murmur * 0.8, 1400, 1.0)
    stopFns.push(() => {
      low.stop()
      high.stop()
    })
  }

  if (cfg.footstepEveryS > 0) {
    const footsteps = makeFootsteps(ctx, master, cfg.footstepEveryS)
    stopFns.push(() => footsteps.stop())
  }

  if (cfg.beepEveryS > 0) {
    const beep = makeMonitorBeep(ctx, master, cfg.beepEveryS)
    stopFns.push(() => beep.stop())
  }

  return {
    output: master,
    stop() {
      stopFns.forEach((fn) => fn())
    },
  }
}

export const NOISE_LEVELS = [
  { value: 'off', label: 'Off' },
  { value: 'quiet', label: 'Quiet corridor' },
  { value: 'busy', label: 'Busy reception' },
  { value: 'loud', label: 'Tannoy + trolley' },
]
