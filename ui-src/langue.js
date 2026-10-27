// The language of the interface. The English text stays the source: every text
// on screen, placeholder and title is looked up in i18n.json and shown in your
// language; new content is translated as it appears. What people write (posts,
// names, conversations, words of the encyclopedia) is never touched.
import TABLE from './i18n.json'

export const LANGUES = TABLE.langs                       // [code, name], in alphabetical order (French names)
const CLE = 'rh-langue'
const PERSO = '.ptx,.n-cite,.n-post,.p-bio,.p-nom,.p-id,.tr-t,.tr-d,.qui,.item .tx,.msg,.bulle,.corps,.mots,code,pre,textarea,input,[data-brut]'
const MOTIFS = TABLE.patterns.map((p) => ({ re: new RegExp(p.en), p }))
let L = 'en', obs = null
const orig = new WeakMap()                                 // node -> its English text

export function langue() {
  try { const l = localStorage.getItem(CLE); if (l && LANGUES.some(([c]) => c === l)) return l } catch {}
  const n = (navigator.language || 'en').slice(0, 2)
  return LANGUES.some(([c]) => c === n) ? n : 'en'
}
function traduire(en) {
  if (L === 'en') return en
  const t = en.trim(); if (!t) return en
  const s = TABLE.strings[t]
  let r = s && s[L]
  if (!r) for (const { re, p } of MOTIFS) { if (re.test(t) && p[L]) { r = t.replace(re, p[L]); break } }
  return r ? en.replace(t, r) : en
}
function texte(n) {
  if (!orig.has(n)) orig.set(n, n.nodeValue)
  const v = traduire(orig.get(n)); if (n.nodeValue !== v) n.nodeValue = v
}
function attrs(el) {
  for (const a of ['placeholder', 'title']) {
    if (!el.hasAttribute || !el.hasAttribute(a)) continue
    const k = 'data-en-' + a
    if (!el.hasAttribute(k)) el.setAttribute(k, el.getAttribute(a))
    const v = traduire(el.getAttribute(k)); if (el.getAttribute(a) !== v) el.setAttribute(a, v)
  }
}
function parcourir(root) {
  if (root.nodeType === 3) { if (!root.parentElement || !root.parentElement.closest(PERSO)) texte(root); return }
  if (root.nodeType !== 1) return
  if (root.matches && root.matches('input,textarea')) { attrs(root); return }
  if (root.closest && root.closest(PERSO) && !root.matches('input,textarea')) return
  attrs(root)
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
    acceptNode: (n) => n.nodeType === 1 ? (n.matches(PERSO) && !n.matches('input,textarea') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT) : NodeFilter.FILTER_ACCEPT })
  for (let n = w.nextNode(); n; n = w.nextNode()) n.nodeType === 3 ? texte(n) : attrs(n)
}

export function appliquer(l) {
  L = l || langue()
  try { localStorage.setItem(CLE, L) } catch {}
  document.documentElement.lang = L
  if (obs) obs.disconnect()
  parcourir(document.body)
  obs = new MutationObserver((ms) => {
    obs.disconnect()                                       // our own changes must not wake us again
    for (const m of ms) {
      if (m.type === 'characterData') { const n = m.target; if (!n.parentElement || !n.parentElement.closest(PERSO)) { orig.set(n, n.nodeValue); texte(n) } }
      else m.addedNodes.forEach(parcourir)
    }
    obs.observe(document.body, { childList: true, subtree: true, characterData: true })
  })
  obs.observe(document.body, { childList: true, subtree: true, characterData: true })
}
export const t = (en) => traduire(en)
