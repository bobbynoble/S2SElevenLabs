# Ollo — Brand & UI Spec

Ollo is a multilingual AI reception assistant for NHS hospital front desks.
Name story: built from the near-universal greeting (hello / hallo / allô / hola) — "the first word everyone understands".

Use this file as the source of truth when building the Ollo app UI.

## Assets
| File | Use |
|---|---|
| `ollo-mascot.svg` | Mascot / app icon / kiosk hero. Speech-bubble face, clearly a friendly machine, not a person. |
| `ollo-lockup.svg` | Primary logo: mascot + "ollo" wordmark (final "o" in coral). Wordmark uses Fredoka 600 — outline the text before production use. |
| `ollo-mark-conversation.svg` | Secondary mark: two speech bubbles facing across the "ll". For splash screens, favicons, marketing. |
| `ollo-kiosk-reference.html` | Static reference for the kiosk welcome screen layout. |

## Colour tokens
```css
:root {
  --ollo-teal:        #0F766E; /* primary brand, buttons, mascot body */
  --ollo-teal-light:  #2BA597; /* mascot on dark backgrounds */
  --ollo-mint:        #7FD4C9; /* soft accent, chips on dark */
  --ollo-coral:       #E8604C; /* secondary accent, wordmark final "o" */
  --ollo-coral-soft:  #F28B7A; /* mascot cheeks, light accents */
  --ollo-ink:         #13302F; /* primary text, dark backgrounds */
  --ollo-ink-muted:   #3D5452; /* secondary text */
  --ollo-ground:      #F4F7F6; /* page background */
  --ollo-surface:     #FFFFFF; /* cards, panels */
}
```
- White text on `--ollo-teal` passes WCAG AA for large and body text.
- Do not put white text on coral; use `--ollo-ink` on coral.
- Deliberately NOT NHS blue — avoid implying official NHS branding. Do not put "NHS" in the product name or use the NHS logo without trust permission.

## Typography
- Display / wordmark: **Fredoka** 500–600 (Google Fonts)
- Body / UI: **Atkinson Hyperlegible** 400/700 (Google Fonts) — designed for low-vision readability.
- Kiosk minimums: body 20px+, buttons 28–32px, headings 64px+.

## Shape & spacing
- Corner radius: 24px cards and buttons, 999px for chips.
- Touch targets: minimum 96px tall on kiosk, 44px elsewhere.
- Generous spacing: 20–40px gaps, 64px page padding on kiosk.

## Voice
- Warm, short, plain English. Greets with "Ollo!" then switches to the patient's language.
- Always transparent that it's AI: "I'm Ollo, a computer assistant — not a person."
- Always point to humans: "A member of staff is always nearby. If you feel very unwell, tell the reception team straight away."
- Never jokey about symptoms or clinical matters.

## Kiosk welcome screen (see reference HTML)
1. Hospital name + location (placeholder `[HOSPITAL NAME]`)
2. Mascot hero
3. "Ollo!" headline + one-line purpose
4. Two-column grid of language buttons, each label in its own language/script with correct `lang` and `dir` (RTL for Arabic and Urdu)
5. Persistent AI-disclosure + safety panel pinned to the bottom

## Accessibility requirements
- Real `<button>` elements; visible focus states.
- Set `lang`/`dir` on every non-English string.
- Text contrast ≥ 4.5:1 (3:1 for 24px+).
- Support screen readers and audio-first use; every visual prompt also spoken.
