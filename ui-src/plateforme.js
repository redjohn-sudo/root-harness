// Which computer or phone runs the interface, and what follows from it: the key
// that holds shortcuts (Cmd on a Mac, Ctrl elsewhere), how a shortcut is written,
// the scrollbars and the glass. One answer for the whole interface.
import { t } from './langue.js'

let P = null
export function plateforme() {               // 'mac' | 'windows' | 'linux' | 'ios' | 'android'
  if (P) return P
  const n = navigator, ua = n.userAgent || ''
  const s = ((n.userAgentData && n.userAgentData.platform) || n.platform || ua).toLowerCase()
  P = /android/.test(s) || /Android/.test(ua) ? 'android'
    : /iphone|ipad|ipod|^ios/.test(s) || /iPhone|iPad|iPod/.test(ua) ? 'ios'
    : /mac/.test(s) ? (n.maxTouchPoints > 1 ? 'ios' : 'mac')      // an iPad says it is a Mac, but it has a touch screen
    : /win/.test(s) ? 'windows' : 'linux'                         // Linux, ChromeOS, the BSDs
  return P
}
export const apple = () => ['mac', 'ios'].includes(plateforme())

// the shortcut key: Cmd on Apple, Ctrl elsewhere (on a Mac, Ctrl+K stays the text field's own)
export const mod = (e) => apple() ? e.metaKey && !e.ctrlKey : e.ctrlKey && !e.metaKey
// Enter that confirms a word being composed (Japanese, Chinese...) is not Enter that sends
export const entree = (e) => e.key === 'Enter' && !e.isComposing && e.keyCode !== 229

// how a shortcut is written: ⌘K and ⇧↩ on Apple, Ctrl+K and Shift+Enter elsewhere
const SIGNES = { mod: '⌘', ctrl: '⌃', alt: '⌥', shift: '⇧', Enter: '↩', Tab: '⇥', Esc: 'esc' }
const NOMS = { mod: 'Ctrl', ctrl: 'Ctrl', alt: 'Alt', shift: 'Shift' }
export function touches(...k) {
  if (apple()) return k.map((x) => SIGNES[x] || x).join('')
  return k.map((x) => t(NOMS[x] || x)).join('+')
}
// the same, for aria-keyshortcuts
export const ariaTouches = (...k) => k.map((x) => ({ mod: apple() ? 'Meta' : 'Control', ctrl: 'Control', alt: 'Alt', shift: 'Shift', Esc: 'Escape' }[x] || x)).join('+')

// the page knows where it runs: thin dark scrollbars outside Apple, opaque glass where blur is missing
export function marquer() {
  const h = document.documentElement
  h.classList.add('pf-' + plateforme())
  const flou = window.CSS && CSS.supports && (CSS.supports('backdrop-filter', 'blur(1px)') || CSS.supports('-webkit-backdrop-filter', 'blur(1px)'))
  const moins = matchMedia('(prefers-reduced-transparency: reduce)')
  const opaque = () => h.classList.toggle('opaque', !flou || moins.matches)
  opaque(); moins.addEventListener && moins.addEventListener('change', opaque)
}

// -- zoom: Cmd or Ctrl with + - 0 and with the wheel, the same in every window --------
const CLE = 'rh-zoom', PAS = [0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2]
let Z = 1
export const zoomActuel = () => Z
export function zoomer(z) {
  Z = Math.min(2, Math.max(0.67, Math.round(z * 100) / 100))
  const h = document.documentElement
  h.style.zoom = Z === 1 ? '' : String(Z); h.style.setProperty('--zoom', Z)
  try { Z === 1 ? localStorage.removeItem(CLE) : localStorage.setItem(CLE, String(Z)) } catch {}
  return Z
}
const pas = (sens) => zoomer(sens > 0 ? PAS.find((x) => x > Z + 0.001) || 2 : [...PAS].reverse().find((x) => x < Z - 0.001) || 0.67)
export function installerZoom() {
  try { const z = parseFloat(localStorage.getItem(CLE)); if (z) zoomer(z) } catch {}
  document.addEventListener('keydown', (e) => {
    if (!mod(e) || e.altKey) return
    const k = e.key, c = e.code
    if (k === '+' || k === '=' || c === 'NumpadAdd') { e.preventDefault(); pas(1) }
    else if (k === '-' || k === '_' || c === 'NumpadSubtract') { e.preventDefault(); pas(-1) }
    else if (k === '0' || c === 'Digit0' || c === 'Numpad0') { e.preventDefault(); zoomer(1) }
  })
  let cumul = 0
  document.addEventListener('wheel', (e) => {
    if (!(e.ctrlKey || mod(e)) || (e.target.closest && e.target.closest('.rc-cadre'))) return
    e.preventDefault()                       // the window's own zoom stays out of it
    cumul += e.deltaY * (e.deltaMode === 1 ? 33 : 1)
    if (Math.abs(cumul) >= 60) { pas(cumul < 0 ? 1 : -1); cumul = 0 }
  }, { passive: false })
}
