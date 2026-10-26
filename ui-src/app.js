// root-harness: the one interface, the same on the computer and on the phone.
// It only talks to a "host" (host-computer.js or host-phone.js) that knows how
// to reach the agents, the conversations, the friends and GitHub from there.
import { tete, cligner } from './root.js'

let H = null                                  // the host
const $ = (s, r = document) => r.querySelector(s)
const $$ = (s, r = document) => [...r.querySelectorAll(s)]
export const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
const quand = (ms) => { const d = (Date.now() - ms) / 1000
  return d < 60 ? 'now' : d < 3600 ? Math.floor(d / 60) + ' min' : d < 86400 ? Math.floor(d / 3600) + ' h' : d < 604800 ? Math.floor(d / 86400) + ' d' : new Date(ms).toLocaleDateString() }

// -- icons (thin, like Lanterns) ------------------------------------------------
const I = {
  chat: '<path d="M20 12a8 8 0 01-11.6 7.1L4 20l1-4.2A8 8 0 1120 12z"/>',
  dossiers: '<path d="M3.5 7.5a2 2 0 012-2h4l2 2h7a2 2 0 012 2v8a2 2 0 01-2 2h-13a2 2 0 01-2-2z"/>',
  amis: '<circle cx="9" cy="9" r="3.2"/><path d="M3.5 19c.6-3 2.9-4.6 5.5-4.6s4.9 1.6 5.5 4.6"/><circle cx="17" cy="8" r="2.4"/><path d="M15.5 13.6c2.6.1 4.4 1.6 5 4.4"/>',
  vibe: '<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5.5l-3 13"/>',
  reglages: '<circle cx="12" cy="12" r="3"/><path d="M19.4 13.5l1.6 1.2-2 3.4-1.9-.8a7.6 7.6 0 01-2 1.2L14.8 21h-4l-.3-2.5a7.6 7.6 0 01-2-1.2l-1.9.8-2-3.4 1.6-1.2a7.7 7.7 0 010-2.4L4.6 9.9l2-3.4 1.9.8a7.6 7.6 0 012-1.2L10.8 3h4l.3 2.5a7.6 7.6 0 012 1.2l1.9-.8 2 3.4-1.6 1.2a7.7 7.7 0 010 2.4z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>', partage: '<path d="M12 15V4M8 8l4-4 4 4M5 13v5a2 2 0 002 2h10a2 2 0 002-2v-5"/>',
  image: '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="M5 17l4.5-4.5 3 3 2.5-2.5 4 4"/>',
  fleche: '<path d="M12 19V5M5 12l7-7 7 7"/>', retour: '<path d="M15 5l-7 7 7 7"/>', copie: '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 15V6a1 1 0 011-1h9"/>',
}
const ico = (n, w = 1.7) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${I[n]}</svg>`

// -- the shell ----------------------------------------------------------------------
const ONGLETS = [['chat', 'Your agents'], ['discussions', 'Conversations'], ['amis', 'Friends & groups'], ['vibe', 'Vibe code'], ['reglages', 'Settings']]
const ICONE = { chat: 'chat', discussions: 'dossiers', amis: 'amis', vibe: 'vibe', reglages: 'reglages' }

function coquille() {
  document.body.innerHTML = `<div id="fond"></div>
  <div id="app">
    <nav id="rail"><div class="marque">${tete()}</div>
      ${ONGLETS.map(([k, t]) => `<button class="onglet" data-v="${k}" title="${t}">${ico(ICONE[k])}</button>`).join('')}
    </nav>
    <main>
      <section class="vue" id="v-chat"></section><section class="vue" id="v-discussions"></section>
      <section class="vue" id="v-amis"></section><section class="vue" id="v-vibe"></section><section class="vue" id="v-reglages"></section>
    </main>
  </div>
  <div id="voile"></div><div class="feuille" id="feuille"></div><div class="toast" id="toast"></div>
  <div id="porte"><div class="carte-porte verre" id="carte-porte"></div></div>`
  $$('.onglet').forEach((b) => b.onclick = () => aller(b.dataset.v))
  $('#voile').onclick = fermerFeuille
  addEventListener('mousemove', (e) => { const r = document.documentElement.style
    r.setProperty('--mx', (e.clientX / innerWidth - .5).toFixed(3)); r.setProperty('--my', (e.clientY / innerHeight - .5).toFixed(3)) })
  cligner()
}

let VUE = 'chat'
export function aller(v) {
  VUE = v
  $$('.onglet').forEach((b) => b.classList.toggle('on', b.dataset.v === v))
  $$('.vue').forEach((s) => s.classList.toggle('on', s.id === 'v-' + v))
  ;({ chat: vueChat, discussions: vueDiscussions, amis: vueAmis, vibe: vueVibe, reglages: vueReglages })[v]()
}

export function toast(t) { const e = $('#toast'); e.textContent = t; e.classList.add('on'); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove('on'), 2600) }
function feuille(html) { const f = $('#feuille'); f.innerHTML = '<div class="poignee"></div>' + html; f.classList.add('on'); $('#voile').classList.add('on'); return f }
function fermerFeuille() { $('#feuille').classList.remove('on'); $('#voile').classList.remove('on') }
async function fond() {
  const url = await H.background(); const f = $('#fond')
  f.style.backgroundImage = url ? `url("${url}")` : ''
}

// -- markdown, as everywhere in root-harness -----------------------------------------
export function riche(texte) {
  const blocs = []
  texte = (texte || '').replace(/```[\w-]*\n?([\s\S]*?)```/g, (_, c) => `\u0000${blocs.push(c) - 1}\u0000`)
  const ligne = (x) => esc(x).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/(^|\s)(https:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>')
  return texte.split(/\n{2,}/).map((par) => {
    const m = par.match(/^\u0000(\d+)\u0000$/); if (m) return `<pre>${esc(blocs[+m[1]])}</pre>`
    const L = par.split('\n')
    if (L.length > 1 && L.every((l) => /^\s*\|.*\|\s*$/.test(l))) {
      const rows = L.filter((l) => !/^\s*\|[\s:|-]+\|\s*$/.test(l)).map((l) => l.trim().slice(1, -1).split('|').map((c) => ligne(c.trim())))
      return '<table>' + rows.map((r, i) => '<tr>' + r.map((c) => i ? `<td>${c}</td>` : `<th>${c}</th>`).join('') + '</tr>').join('') + '</table>'
    }
    return '<p>' + L.map((l) => { const h = l.match(/^#{1,6}\s+(.*)$/); if (h) return `<h4>${ligne(h[1])}</h4>`
      return /^\s*[-•*]\s+/.test(l) ? '• ' + ligne(l.replace(/^\s*[-•*]\s+/, '')) : ligne(l) }).join('<br>').replace(/<br><h4>/g, '<h4>') + '</p>'
  }).join('')
}

// =====================================================================================
// the account: pseudo + password, on your devices only
// =====================================================================================
async function porte() {
  const st = await H.account.state()
  if (st.exists && st.unlocked) { $('#porte').classList.remove('on'); return true }
  const c = $('#carte-porte'), o = $('#porte'); o.classList.add('on')
  const val = (id) => $('#' + id).value
  const erreur = (t) => { $('#p-err').textContent = t; c.classList.remove('secoue'); void c.offsetWidth; c.classList.add('secoue') }
  const entree = (ids, go) => ids.forEach((i) => $('#' + i).onkeydown = (e) => { if (e.key === 'Enter') go() })
  const occupe = (t) => { const b = $('#p-go'); b.dataset.t = b.dataset.t || b.textContent; b.textContent = t; b.disabled = true; $('#p-barre')?.classList.add('on') }
  const libre = () => { const b = $('#p-go'); if (b.dataset.t) b.textContent = b.dataset.t; b.disabled = false; $('#p-barre')?.classList.remove('on') }
  const fini = async () => { o.classList.remove('on'); await demarrer() }

  const creer = () => {
    c.innerHTML = `<div class="grande-tete">${tete()}</div><h2>root-harness</h2><p>Your agents, your friends, your projects. Pick a pseudo and a password: everything stays yours, on your devices.</p>
      <input class="champ" id="p-pseudo" placeholder="pseudo" autocomplete="username" autocapitalize="off">
      <input class="champ" id="p-mdp" type="password" placeholder="password (10+ characters)">
      <input class="champ" id="p-mdp2" type="password" placeholder="same password again">
      <div class="err" id="p-err"></div><button class="bouton plein" id="p-go">Create my account</button>
      <span class="lien" id="p-deja">I already have an account</span>`
    const go = async () => { const r = await H.account.create(val('p-pseudo'), val('p-mdp'), val('p-mdp2')); if (r.error) return erreur(r.error); fini() }
    $('#p-go').onclick = go; entree(['p-pseudo', 'p-mdp', 'p-mdp2'], go); $('#p-deja').onclick = connecter; $('#p-pseudo').focus()
  }
  const connecter = () => {
    c.innerHTML = `<div class="grande-tete">${tete()}</div><h2>welcome back</h2><p>Your pseudo and password. Your memory comes with them.</p>
      <input class="champ" id="p-pseudo" placeholder="pseudo" autocomplete="username" autocapitalize="off">
      <input class="champ" id="p-mdp" type="password" placeholder="password" autocomplete="current-password">
      <div class="err" id="p-err"></div><div class="barre" id="p-barre"><i></i></div><button class="bouton plein" id="p-go">Sign in</button>
      ${st.exists ? '' : '<span class="lien" id="p-nouveau">Create a new account</span>'}`
    const go = async () => { occupe('Finding your account...'); const r = await H.account.restore(val('p-pseudo'), val('p-mdp'), (p) => { const i = $('#p-barre i'); if (i) i.style.width = Math.round(p * 100) + '%' })
      libre(); if (r.error) return erreur(r.error); fini() }
    $('#p-go').onclick = go; entree(['p-pseudo', 'p-mdp'], go); $('#p-nouveau') && ($('#p-nouveau').onclick = creer); $('#p-pseudo').focus()
  }
  const deverrouiller = () => {
    c.innerHTML = `<div class="grande-tete">${tete()}</div><h2>hi ${esc(st.pseudo)}</h2><p>Type your password.</p>
      <input class="champ" id="p-mdp" type="password" placeholder="password" autocomplete="current-password">
      <div class="err" id="p-err"></div><button class="bouton plein" id="p-go">Unlock</button>
      <span class="lien" id="p-oubli">${H.kind === 'phone' ? 'Sign out of this phone' : 'Forgot your password?'}</span>`
    const go = async () => { occupe('Unlocking...'); const r = await H.account.unlock(val('p-mdp')); libre(); if (r.error) return erreur(r.error)
      if (r.weak) setTimeout(() => toast('Your password is short: change it to 10+ characters in Settings.'), 800); fini() }
    $('#p-go').onclick = go; entree(['p-mdp'], go); $('#p-oubli').onclick = H.kind === 'phone' ? async () => { await H.account.signOut(); porte() } : oubli; $('#p-mdp').focus()
  }
  const oubli = () => {
    c.innerHTML = `<div class="grande-tete">${tete()}</div><h2>start over?</h2><p>A password cannot be recovered. A new account gets a new ID; your channels go away, your agent conversations stay.</p>
      <input class="champ" id="p-reset" placeholder="type RESET to confirm"><div class="err" id="p-err"></div>
      <button class="bouton plein" id="p-go">Start over</button><span class="lien" id="p-ret">Back</span>`
    $('#p-go').onclick = async () => { if (!(await H.account.reset(val('p-reset')))) return erreur('Type RESET in capitals.'); porte() }
    $('#p-ret').onclick = deverrouiller
  }
  st.exists ? deverrouiller() : (H.kind === 'phone' ? connecter() : creer())
  return false
}

// =====================================================================================
// your agents: the chat
// =====================================================================================
let CERVEAU = {}, PIECES = [], OUTILS = {}, dernierOutil = null, EN_COURS = false, COMMANDES = null, CONV_TITRE = ''

function vueChat() {
  const v = $('#v-chat')
  if (!v.dataset.fait) {
    v.dataset.fait = 1
    v.innerHTML = `<div class="tete-chat"><button class="pilule-cerveau verre" id="c-cerveau">${tete()}<span id="c-nom">...</span><span class="modele" id="c-modele"></span></button>
      <span class="etat" id="c-etat"><span class="point" id="c-point"></span><span id="c-etat-t"></span></span>
      <button class="rond-btn" id="c-partager" title="Share with a friend">${ico('partage')}</button><button class="rond-btn" id="c-nouveau" title="New chat">${ico('plus')}</button></div>
      <div class="defile" id="c-defile"><div class="colonne fil" id="c-fil"></div></div>
      <div class="composer"><div class="pieces" id="c-pieces"></div><div class="menu" id="c-menu"></div>
        <div class="boite"><button class="rond-btn" id="c-img" title="Add an image">${ico('image')}</button><input type="file" accept="image/*" id="c-fichier" hidden multiple>
        <textarea id="c-entree" rows="1" placeholder="Ask your agent, or / for commands"></textarea>
        <button class="rond-btn envoyer" id="c-envoyer"><svg class="fleche" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${I.fleche}</svg><svg class="stop" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor"/></svg></button></div></div>`
    $('#c-cerveau').onclick = feuilleCerveau
    $('#c-nouveau').onclick = async () => { const r = await H.agent.newChat(); if (r) { viderFil(); badge(r) } }
    $('#c-partager').onclick = () => feuillePartage()
    $('#c-envoyer').onclick = () => EN_COURS ? H.agent.stop() : envoyer()
    $('#c-img').onclick = () => $('#c-fichier').click()
    $('#c-fichier').onchange = (e) => { [...e.target.files].forEach(ajouterImage); e.target.value = '' }
    const ta = $('#c-entree')
    ta.addEventListener('input', () => { ajuster(ta); menuSlash() })
    ta.addEventListener('keydown', clavier)
    document.addEventListener('paste', (e) => { if (VUE !== 'chat') return
      const f = [...(e.clipboardData?.items || [])].filter((i) => i.type.startsWith('image/')).map((i) => i.getAsFile()); if (f.length) { e.preventDefault(); f.forEach(ajouterImage) } })
    document.addEventListener('dragover', (e) => e.preventDefault())
    document.addEventListener('drop', (e) => { if (VUE === 'chat' && e.dataTransfer?.files?.length) { e.preventDefault(); [...e.dataTransfer.files].forEach(ajouterImage) } })
    accueil()
    H.agent.history().then((h) => { if (h && h.events && h.events.length) { viderFil(); h.events.forEach((e) => montrer(e, true)); $$('.outil').forEach((o) => o.classList.add('fait')) } }).catch(() => {})
  }
  rafraichirCerveau()
}

function accueil() {
  $('#c-fil').innerHTML = `<div class="bienvenue"><div class="grande-tete">${tete()}</div><div class="titre">what are we making?</div>
    <div class="sous-titre" style="margin:8px auto 0">Ask your agent, vibe code on GitHub, or share what you did with a friend.</div></div>`
}
function viderFil() { $('#c-fil').innerHTML = ''; OUTILS = {}; dernierOutil = null }
function ajouter(html, fil = '#c-fil') {
  const f = $(fil); $('.bienvenue', f)?.remove()
  const w = document.createElement('div'); w.innerHTML = html; const n = w.firstElementChild; f.appendChild(n)
  const d = f.closest('.defile'); d && d.scrollTo({ top: d.scrollHeight, behavior: 'smooth' }); return n
}
function ajuster(ta) { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 150) + 'px' }

async function rafraichirCerveau() { try { badge(await H.agent.active()) } catch { badge({ name: 'your computer', label: 'offline', offline: true }) } }
function badge(b) {
  CERVEAU = b || {}
  $('#c-nom') && ($('#c-nom').textContent = b.name || '...')
  $('#c-modele') && ($('#c-modele').textContent = [b.label, b.effort && 'effort ' + b.effort].filter(Boolean).join(' · '))
  etat(b.offline ? (H.kind === 'phone' ? 'your computer is off' : 'offline') : 'ready', b.offline ? 'off' : 'ok')
}
function etat(t, k) {
  $('#c-etat-t') && ($('#c-etat-t').textContent = t); const p = $('#c-point'); if (p) p.className = 'point ' + (k || 'ok')
  EN_COURS = k === 'travail' || k === 'attente'; document.body.classList.toggle('travail', EN_COURS)
}
function attente(on) { $('#c-ecrit')?.remove(); if (on) ajouter('<div class="ecrit" id="c-ecrit"><i></i><i></i><i></i></div>') }

function bulleMoi(text, thumbs, fil = '#c-fil') {
  const v = (thumbs || []).length ? `<div class="vignettes">${thumbs.map((t) => `<img src="${t}">`).join('')}</div>` : ''
  ajouter(`<div class="msg moi">${v}${esc(text)}</div>`, fil)
}
function bulleAgent(text, fil = '#c-fil') { return ajouter(`<div class="msg agent">${tete()}<div class="corps">${riche(text)}</div></div>`, fil) }

async function envoyer() {
  const ta = $('#c-entree'), t = ta.value.trim()
  if (!t && !PIECES.length) return
  if (t.startsWith('/') && !PIECES.length && (await commande(t))) { ta.value = ''; ajuster(ta); fermerMenu(); return }
  ta.value = ''; ajuster(ta); fermerMenu()
  const imgs = PIECES.splice(0); rendrePieces()
  bulleMoi(t, imgs.map((i) => i.thumb)); etat('thinking', 'travail'); attente(true)
  const r = await H.agent.send(t, imgs)
  if (r && r.error) { attente(false); ajouter(`<div class="sys">${esc(r.error)}</div>`); etat('ready', 'ok') }
}

// what the agent does, live
export function montrer(e, histoire) {
  const t = e.type
  if (t === 'user') bulleMoi(e.text, e.thumbs)
  else if (t === 'remote_user') { bulleMoi((e.from === 'phone' ? '📱 ' : '') + e.text); etat('thinking', 'travail'); attente(true) }
  else if (t === 'text') { attente(false); bulleAgent(e.text); if (!histoire) attente(EN_COURS) }
  else if (t === 'tool') {
    attente(false)
    dernierOutil = ajouter(`<div class="outil${histoire ? ' fait' : ''}"><div class="tt"><span class="rond"></span><span class="n">${esc(e.name)}</span><span class="a">${esc(JSON.stringify(e.args || {}))}</span></div><div class="det"></div></div>`)
    dernierOutil.onclick = function () { this.classList.toggle('ouvert') }
    if (e.id) OUTILS[e.id] = dernierOutil
    if (!histoire) etat('using ' + e.name, 'travail')
  } else if (t === 'result') {
    const o = (e.id && OUTILS[e.id]) || dernierOutil
    if (o) { o.classList.add('fait'); $('.det', o).textContent = (e.text || '').slice(0, 3000) }
  } else if (t === 'permission') { attente(false); if (!histoire) carteAutorisation(e) }
  else if (t === 'question') { attente(false); if (!histoire) carteQuestion(e) }
  else if (t === 'status') etat(e.text, 'travail')
  else if (t === 'error') { attente(false); ajouter(`<div class="sys" style="color:#fca5a5">${esc(e.text)}</div>`) }
  else if (t === 'done') { attente(false); etat('ready', 'ok'); $$('.outil').forEach((o) => o.classList.add('fait')); rafraichirCerveau() }
}

function carteAutorisation(e) {
  etat('waiting for you', 'attente')
  const n = ajouter(`<div class="demande"><div class="q">Your agent wants to: <b>${esc(e.title)}</b></div>
    <pre class="code">${esc(JSON.stringify(e.args, null, 1)).slice(0, 700)}</pre><div class="boutons"><button class="bouton vert oui">Allow</button><button class="bouton danger non">Deny</button></div></div>`)
  const fin = (ok) => { H.agent.answer(e.id, ok); $('.boutons', n).outerHTML = `<div class="verdict ${ok ? 'oui' : 'non'}">${ok ? 'Allowed' : 'Denied'}</div>`; etat('thinking', 'travail') }
  $('.oui', n).onclick = () => fin(true); $('.non', n).onclick = () => fin(false)
}
function carteQuestion(e) {
  etat('waiting for you', 'attente'); const choix = {}
  const n = ajouter(`<div class="demande">${e.questions.map((q, i) => `<div data-q="${i}"><div class="q">${esc(q.question)}</div>
    ${(q.options || []).map((o, j) => `<button class="opt" data-j="${j}">${esc(o.label)}${o.description ? `<small>${esc(o.description)}</small>` : ''}</button>`).join('')}</div>`).join('')}
    <div class="boutons"><button class="bouton vert oui">Send</button><button class="bouton non">Skip</button></div></div>`)
  $$('[data-q]', n).forEach((b) => { const q = e.questions[+b.dataset.q]; choix[q.question] = new Set()
    $$('.opt', b).forEach((o) => o.onclick = () => { const lab = q.options[+o.dataset.j].label, S = choix[q.question]
      if (q.multiSelect) { S.has(lab) ? S.delete(lab) : S.add(lab); o.classList.toggle('on') } else { S.clear(); S.add(lab); $$('.opt', b).forEach((x) => x.classList.toggle('on', x === o)) } }) })
  $('.oui', n).onclick = () => { const a = {}; for (const [k, S] of Object.entries(choix)) { if (!S.size) return; a[k] = [...S].join(', ') }
    H.agent.answerQuestion(e.id, a); $('.boutons', n).outerHTML = `<div class="verdict oui">${esc(Object.values(a).join(' · '))}</div>` }
  $('.non', n).onclick = () => { H.agent.answerQuestion(e.id, null); $('.boutons', n).outerHTML = '<div class="verdict non">Skipped</div>' }
}

// images: paste, drop, or pick
function ajouterImage(file) {
  if (!file || !file.type.startsWith('image/')) return
  const r = new FileReader()
  r.onload = () => { const img = new Image(); img.onload = () => {
    const red = (max, type, q) => { const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight)); const c = document.createElement('canvas')
      c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); return c.toDataURL(type, q) }
    // from the phone, a picture travels inside one sealed message (about 60 KB at most)
    const max = H.kind === 'phone' ? 560 : 1568, type = H.kind === 'phone' ? 'image/jpeg' : (file.type === 'image/png' ? 'image/png' : 'image/jpeg')
    PIECES.push({ media_type: type, data: red(max, type, H.kind === 'phone' ? .55 : .9).split(',')[1], thumb: red(H.kind === 'phone' ? 96 : 200, 'image/jpeg', .7) }); rendrePieces() }
    img.src = r.result }
  r.readAsDataURL(file)
}
function rendrePieces() { $('#c-pieces').innerHTML = PIECES.map((p, i) => `<div class="piece"><img src="${p.thumb}"><button data-i="${i}">✕</button></div>`).join('')
  $$('#c-pieces button').forEach((b) => b.onclick = () => { PIECES.splice(+b.dataset.i, 1); rendrePieces() }) }

// -- slash commands -------------------------------------------------------------------
const LOCALES = [['/model', 'Change the model'], ['/effort', 'How hard it thinks'], ['/brain', 'Change the agent'], ['/mode', 'Ask, accept edits, plan or auto'],
  ['/new', 'Start a new conversation'], ['/share', 'Share this conversation with a friend']]
const MENU = { items: [], sel: 0, on: false }
function fermerMenu() { MENU.on = false; $('#c-menu')?.classList.remove('on') }
async function menuSlash() {
  const v = $('#c-entree').value
  if (!v.startsWith('/') || v.includes(' ') || v.includes('\n')) return fermerMenu()
  if (COMMANDES === null) { try { COMMANDES = await H.agent.commands() } catch { COMMANDES = [] } }
  const q = v.toLowerCase(), locales = new Set(LOCALES.map((x) => x[0]))
  MENU.items = [...LOCALES.map(([c, d]) => ({ c, d })), ...COMMANDES.filter((x) => !locales.has(x.name)).map((x) => ({ c: x.name, d: (x.hint ? x.hint + ' · ' : '') + x.desc }))].filter((x) => x.c.startsWith(q))
  MENU.sel = 0; MENU.on = MENU.items.length > 0
  const m = $('#c-menu'); m.classList.toggle('on', MENU.on)
  m.innerHTML = '<div class="titre-menu">commands</div>' + MENU.items.map((x, i) => `<div class="it${i ? '' : ' sel'}" data-i="${i}"><span class="c">${esc(x.c)}</span><span class="d">${esc(x.d)}</span></div>`).join('')
  $$('.it', m).forEach((el) => el.onmousedown = (e) => { e.preventDefault(); choisirCommande(+el.dataset.i) })
}
function choisirCommande(i) { const x = MENU.items[i]; if (!x) return; const ta = $('#c-entree'); ta.value = x.c + ' '; fermerMenu(); ta.focus()
  if (['/model', '/effort', '/brain', '/mode', '/new', '/share'].includes(x.c)) envoyer() }
function clavier(e) {
  if (MENU.on && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) { e.preventDefault(); MENU.sel = (MENU.sel + (e.key === 'ArrowDown' ? 1 : -1) + MENU.items.length) % MENU.items.length
    $$('#c-menu .it').forEach((el, i) => el.classList.toggle('sel', i === MENU.sel)); return }
  if (MENU.on && (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey))) { e.preventDefault(); return choisirCommande(MENU.sel) }
  if (e.key === 'Escape') { if (MENU.on) return fermerMenu(); if (EN_COURS) H.agent.stop() }
  if (e.key === 'Tab' && e.shiftKey) { e.preventDefault(); cycleMode() }
  if (e.key === 'Enter' && !e.shiftKey && !(H.kind === 'phone' && !e.metaKey && !e.ctrlKey && matchMedia('(pointer:coarse)').matches)) { e.preventDefault(); envoyer() }
}
async function commande(t) {
  const [c, ...rest] = t.split(/\s+/), arg = rest.join(' ')
  if (c === '/model' || c === '/effort' || c === '/brain' || c === '/mode') { feuilleCerveau(); return true }
  if (c === '/new' || c === '/clear') { const r = await H.agent.newChat(); if (r) { viderFil(); badge(r) } return true }
  if (c === '/share') { feuillePartage(); return true }
  return false                                         // the agent's own commands go to the agent
}
async function cycleMode() { const L = CERVEAU.modes || []; if (!L.length) return
  const r = await H.agent.setMode(L[(L.indexOf(CERVEAU.mode) + 1) % L.length]); if (r) { badge(r); toast({ default: 'ask mode', acceptEdits: 'accept edits on', plan: 'plan mode on', auto: 'auto mode on' }[r.mode] || r.mode) } }

// -- the agent sheet: who thinks, which model, how hard ---------------------------------
async function feuilleCerveau() {
  const f = feuille('<h3>your agent</h3><div class="sous-titre">Loading...</div>')
  let L, M, E
  try { [L, M, E] = await Promise.all([H.agent.brains(), H.agent.models(), H.agent.efforts()]) } catch (e) {
    f.innerHTML = `<div class="poignee"></div><h3>your agent</h3><div class="sous-titre">${H.kind === 'phone' ? 'Your computer is off or not answering. On the go, use <b>Vibe code</b>: Claude works on GitHub.' : esc(e.message || e)}</div>`; return }
  const modes = CERVEAU.modes || []
  f.innerHTML = `<div class="poignee"></div><h3>your agent</h3><div class="sous-titre">Same tools, same permission cards, whoever thinks.</div>
    <div class="section">agent<span class="ligne"></span></div><div class="liste">${L.brains.map((b, i) => `<div class="item${b.id === L.active ? ' on' : ''}" data-b="${esc(b.id)}" style="--i:${i}"><div class="tx"><div class="t">${esc(b.name)}</div><div class="m">${esc(b.ready ? b.note : b.why)}</div></div>${b.ready ? '' : '<span class="badge">not ready</span>'}</div>`).join('')}</div>
    ${M.models.length ? `<div class="section">model<span class="ligne"></span></div><div class="liste">${M.models.map((m, i) => `<div class="item${m.id === M.current ? ' on' : ''}" data-m="${esc(m.id)}" style="--i:${i}"><div class="tx"><div class="t">${esc(m.label)}</div>${m.desc ? `<div class="m">${esc(m.desc)}</div>` : ''}</div></div>`).join('')}</div>` : ''}
    ${E.efforts.length ? `<div class="section">effort<span class="ligne"></span></div><div class="boutons">${E.efforts.map((x) => `<button class="bouton${x === E.current ? ' vert' : ''}" data-e="${esc(x)}">${esc(x)}</button>`).join('')}</div>` : ''}
    ${modes.length ? `<div class="section">permissions<span class="ligne"></span></div><div class="boutons">${modes.map((x) => `<button class="bouton${x === CERVEAU.mode ? ' vert' : ''}" data-o="${esc(x)}">${esc({ default: 'ask first', acceptEdits: 'accept edits', plan: 'plan', auto: 'auto' }[x] || x)}</button>`).join('')}</div>` : ''}`
  $$('[data-b]', f).forEach((el) => el.onclick = async () => { const r = await H.agent.chooseBrain(el.dataset.b); if (r) { badge(r); COMMANDES = null; viderFil(); accueil(); feuilleCerveau() } })
  $$('[data-m]', f).forEach((el) => el.onclick = async () => { const r = await H.agent.setModel(el.dataset.m); if (r) { badge(r); feuilleCerveau() } })
  $$('[data-e]', f).forEach((el) => el.onclick = async () => { const r = await H.agent.setEffort(el.dataset.e); if (r) { badge(r); if (r.note) toast(r.note.slice(0, 90)); feuilleCerveau() } })
  $$('[data-o]', f).forEach((el) => el.onclick = async () => { const r = await H.agent.setMode(el.dataset.o); if (r) { badge(r); feuilleCerveau() } })
}

// -- share a conversation with a friend or a group ---------------------------------------
async function feuillePartage(source) {
  const f = feuille('<h3>share</h3><div class="sous-titre">Loading your friends...</div>')
  const ov = await H.friends.overview().catch(() => null)
  if (!ov) { f.innerHTML = '<div class="poignee"></div><h3>share</h3><div class="sous-titre">Unlock your account first.</div>'; return }
  const chans = ov.channels.filter((c) => !c.request)
  f.innerHTML = `<div class="poignee"></div><h3>share this conversation</h3><div class="sous-titre">It goes sealed: only the people in the channel can read it. Tool outputs stay with you.</div>
    <div class="liste">${chans.map((c, i) => `<div class="item" data-c="${esc(c.id)}" style="--i:${i}"><div class="tx"><div class="t">${esc(c.name)}</div><div class="m">${esc(c.members.map((m) => m.name).join(', '))}</div></div></div>`).join('') || '<div class="vide">No friend or group yet: add one in Friends & groups.</div>'}</div>`
  $$('[data-c]', f).forEach((el) => el.onclick = async () => {
    const conv = source || await H.agent.history()
    if (!conv || !conv.events || !conv.events.length) { toast('Nothing to share yet.'); return }
    const events = conv.events.filter((e) => e.type === 'user' || e.type === 'text').map((e) => ({ type: e.type, text: (e.text || '').slice(0, 6000) })).slice(-40)
    const r = await H.friends.share(el.dataset.c, { title: conv.title || CONV_TITRE || 'A conversation', agent: CERVEAU.name || conv.agent || '', events })
    fermerFeuille(); toast(r ? 'Shared, sealed.' : 'Not sent: are you online?')
  })
}

// =====================================================================================
// conversations: by agent, and your folders
// =====================================================================================
let FERMES = new Set()
async function vueDiscussions() {
  const v = $('#v-discussions')
  v.innerHTML = `<div class="defile"><div class="colonne"><div class="titre">conversations</div><div class="sous-titre">Everything you did with your agents, by agent and in your folders.</div>
    <input class="champ" id="d-cherche" placeholder="search"><div class="boutons"><button class="bouton" id="d-dossier">${'+'} folder</button></div><div id="d-liste"><div class="vide">Loading...</div></div></div></div>`
  let D
  try { D = await H.convs.list() } catch { $('#d-liste').innerHTML = `<div class="vide">${H.kind === 'phone' ? 'Your conversations show here once your computer has synced them.' : 'Unavailable.'}</div>`; return }
  const rendre = () => {
    const q = $('#d-cherche').value.toLowerCase(), L = D.conversations.filter((c) => !q || c.title.toLowerCase().includes(q))
    const ligne = (c, i) => `<div class="item${c.current ? ' on' : ''}" data-id="${esc(c.id)}" style="--i:${i}"><div class="tx"><div class="t">${esc(c.title)}</div><div class="m">${esc(c.brain_name)} · ${quand(c.updated)}</div></div>${c.terminal ? '<span class="badge">terminal</span>' : ''}</div>`
    let h = '', i = 0
    for (const f of D.folders) { const L2 = L.filter((c) => c.folder === f.id); h += `<div class="section" data-f="${esc(f.id)}">▸ ${esc(f.name)} · ${L2.length}<span class="ligne"></span></div><div class="liste">${L2.map((c) => ligne(c, i++)).join('')}</div>` }
    const par = {}; L.filter((c) => !c.folder).forEach((c) => (par[c.brain_name] = par[c.brain_name] || []).push(c))
    for (const [n, L2] of Object.entries(par)) h += `<div class="section">${esc(n)} · ${L2.length}<span class="ligne"></span></div><div class="liste">${L2.map((c) => ligne(c, i++)).join('')}</div>`
    $('#d-liste').innerHTML = h || '<div class="vide">No conversation yet.</div>'
    $$('#d-liste .item').forEach((el) => el.onclick = () => ouvrirDiscussion(el.dataset.id, D))
  }
  $('#d-cherche').oninput = rendre; rendre()
  $('#d-dossier').onclick = () => { const f = feuille(`<h3>new folder</h3><input class="champ" id="f-nom" placeholder="name"><div class="boutons"><button class="bouton plein" id="f-ok">Create</button></div>`)
    $('#f-ok', f).onclick = async () => { if ($('#f-nom', f).value.trim()) { await H.convs.createFolder($('#f-nom', f).value); fermerFeuille(); vueDiscussions() } } }
}
async function ouvrirDiscussion(id, D) {
  const c = D.conversations.find((x) => x.id === id)
  const f = feuille(`<h3>${esc(c.title)}</h3><div class="sous-titre">${esc(c.brain_name)} · ${quand(c.updated)}</div>
    <div class="boutons"><button class="bouton plein" id="o-ouvrir">Open and continue</button><button class="bouton" id="o-partager">${ico('partage')} share</button></div>
    <div class="section">move to<span class="ligne"></span></div><div class="boutons">${D.folders.map((x) => `<button class="bouton" data-f="${esc(x.id)}">${esc(x.name)}</button>`).join('')}${c.folder ? '<button class="bouton" data-f="">out of the folder</button>' : ''}</div>
    <div class="boutons" style="margin-top:20px"><button class="bouton danger" id="o-suppr">${c.terminal ? 'hide' : 'delete'}</button></div>`)
  $('#o-ouvrir', f).onclick = async () => { fermerFeuille(); const r = await H.convs.open(id); if (!r) return toast("Can't open it right now.")
    aller('chat'); viderFil(); CONV_TITRE = r.title; r.events.forEach((e) => montrer(e, true)); $$('.outil').forEach((o) => o.classList.add('fait')); (r.notes || []).forEach((n) => ajouter(`<div class="sys">${esc(n)}</div>`)); badge(r.brain) }
  $('#o-partager', f).onclick = async () => { const r = await H.convs.read(id); feuillePartage({ title: c.title, agent: c.brain_name, events: r.events }) }
  $$('[data-f]', f).forEach((b) => b.onclick = async () => { await H.convs.move(id, b.dataset.f || null); fermerFeuille(); vueDiscussions() })
  $('#o-suppr', f).onclick = async () => { await H.convs.remove(id); fermerFeuille(); vueDiscussions() }
}

// =====================================================================================
// friends & groups: sealed channels between root-harness users
// =====================================================================================
let CANAL = null
async function vueAmis() {
  const v = $('#v-amis')
  if (CANAL) return vueCanal()
  v.innerHTML = `<div class="defile"><div class="colonne"><div class="titre">friends & groups</div><div class="sous-titre">Sealed end to end. Relays carry sealed blobs: not the text, not who talks to whom.</div>
    <div class="verre carte" id="a-moi"><div class="m" style="color:var(--encre-3);font-size:12.5px">your ID, to give to friends</div><div style="font:12.5px var(--mono);word-break:break-all;margin:6px 0" id="a-npub">...</div>
    <div class="boutons"><button class="bouton" id="a-copier">${ico('copie')} copy</button><button class="bouton" id="a-contact">+ friend</button><button class="bouton vert" id="a-groupe">+ group</button></div></div>
    <div id="a-liste"><div class="vide">Connecting...</div></div></div></div>`
  const id = await H.friends.identity().catch(() => ({}))
  $('#a-npub').textContent = id.npub || 'unlock your account first'
  $('#a-copier').onclick = async () => { await H.copy(id.npub); toast('Copied') }
  $('#a-contact').onclick = () => feuilleContact()
  $('#a-groupe').onclick = feuilleGroupe
  const ov = await H.friends.overview().catch(() => ({ channels: [], contacts: [] }))
  const dem = ov.channels.filter((c) => c.request), ok = ov.channels.filter((c) => !c.request)
  const ligne = (c, i) => `<div class="item" data-c="${esc(c.id)}" style="--i:${i}">${tete()}<div class="tx"><div class="t">${esc(c.name)}</div><div class="m">${esc(c.preview || 'no message yet')}</div></div>${c.unread ? `<span class="nb">${c.unread}</span>` : ''}</div>`
  $('#a-liste').innerHTML = (dem.length ? `<div class="section">requests from people you have not added<span class="ligne"></span></div><div class="liste">${dem.map(ligne).join('')}</div>` : '')
    + `<div class="section">your channels<span class="ligne"></span></div><div class="liste">${ok.map(ligne).join('') || '<div class="vide">Add a friend with their ID, then talk or make a group.</div>'}</div>`
  $$('#a-liste .item').forEach((el) => { $('.tete', el).style.cssText = 'width:30px;height:30px;flex:none'
    el.onclick = () => { const c = ov.channels.find((x) => x.id === el.dataset.c); if (c.request) return feuilleContact(c.members[0]?.npub, c.members[0]?.pseudo); CANAL = c; vueCanal() } })
  pastille(ov.channels.some((c) => c.unread))
}
function pastille(on) { const b = $('.onglet[data-v="amis"]'); let p = $('.pastille', b); if (on && !p) { p = document.createElement('span'); p.className = 'pastille'; b.appendChild(p) } else if (!on && p) p.remove() }
function feuilleContact(npub, pseudo) {
  const f = feuille(`<h3>add a friend</h3><div class="sous-titre">Ask them for their ID (in their Friends tab).</div>
    <input class="champ" id="k-npub" placeholder="npub1..." value="${esc(npub || '')}"><input class="champ" id="k-nom" placeholder="the name you give them" value="${esc(pseudo || '')}">
    <div class="err" id="k-err"></div><div class="boutons"><button class="bouton plein" id="k-ok">Add</button></div>`)
  $('#k-ok', f).onclick = async () => { const r = await H.friends.addContact($('#k-npub', f).value, $('#k-nom', f).value)
    if (!r) return ($('#k-err', f).textContent = 'Check the ID and give a name.'); fermerFeuille(); toast('Added'); vueAmis() }
}
async function feuilleGroupe() {
  const ov = await H.friends.overview()
  if (!ov.contacts.length) return feuilleContact()
  const f = feuille(`<h3>new group</h3><input class="champ" id="g-nom" placeholder="group name (sent sealed)">
    <div class="liste" style="margin-top:8px">${ov.contacts.map((c, i) => `<label class="item" style="--i:${i}"><input type="checkbox" value="${esc(c.hex)}"> <div class="tx"><div class="t">${esc(c.name)}</div></div></label>`).join('')}</div>
    <div class="err" id="g-err"></div><div class="boutons"><button class="bouton plein" id="g-ok">Create</button></div>`)
  $('#g-ok', f).onclick = async () => { const m = $$('input[type=checkbox]:checked', f).map((x) => x.value); if (!m.length) return ($('#g-err', f).textContent = 'Pick at least one friend.')
    const meme = ov.channels.find((c) => c.members.length === m.length && c.members.every((x) => m.includes(x.hex)))
    if (meme) { fermerFeuille(); toast('You already talk with these people here.'); CANAL = meme; return vueCanal() }
    const cid = await H.friends.createGroup($('#g-nom', f).value || ov.contacts.filter((c) => m.includes(c.hex)).map((c) => c.name).join(', '), m)
    fermerFeuille(); if (!cid) return toast('Could not create it.'); const o2 = await H.friends.overview(); CANAL = o2.channels.find((c) => c.id === cid); vueCanal() }
}
async function vueCanal() {
  const v = $('#v-amis'), c = CANAL
  v.innerHTML = `<div class="tete-chat"><button class="rond-btn" id="k-retour">${ico('retour')}</button><span class="pilule-cerveau verre">${tete()}<span>${esc(c.name)}</span><span class="modele">🔒 ${esc(c.members.map((m) => m.name).join(', '))}</span></span></div>
    <div class="defile"><div class="colonne fil" id="k-fil"></div></div>
    <div class="composer"><div class="boite"><textarea id="k-entree" rows="1" placeholder="Message ${esc(c.name)}, sealed"></textarea>
    <button class="rond-btn envoyer" id="k-envoyer"><svg class="fleche" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${I.fleche}</svg></button></div></div>`
  $('#k-retour').onclick = () => { CANAL = null; vueAmis() }
  const msgs = await H.friends.messages(c.id)
  msgs.forEach(bulleCanal)
  if (!msgs.length) ajouter('<div class="sys">Only the people in this channel can read it.</div>', '#k-fil')
  const ta = $('#k-entree'), go = async () => { const t = ta.value.trim(); if (!t) return; ta.value = ''; ajuster(ta)
    const m = await H.friends.send(c.id, t); if (m) bulleCanal(m); else ajouter('<div class="sys">Not sent: are you online?</div>', '#k-fil') }
  $('#k-envoyer').onclick = go; ta.oninput = () => ajuster(ta)
  ta.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey && !matchMedia('(pointer:coarse)').matches) { e.preventDefault(); go() } }
}
function bulleCanal(m) {
  if (m.share) {
    const s = m.share, n = ajouter(`<div class="partage-carte"><div class="t">${m.mine ? 'You shared' : esc(m.name) + ' shared'}: ${esc(s.title)}</div>
      <div class="m">${esc(s.agent || 'an agent')} · ${s.events.length} messages</div><div class="boutons"><button class="bouton">Read</button>${m.mine ? '' : '<button class="bouton vert">Continue with my agent</button>'}</div></div>`, '#k-fil')
    $$('.bouton', n)[0].onclick = () => { const f = feuille(`<h3>${esc(s.title)}</h3><div class="sous-titre">${esc(s.agent || '')}</div><div class="fil" id="lire"></div>`)
      s.events.forEach((e) => e.type === 'user' ? bulleMoi(e.text, null, '#lire') : bulleAgent(e.text, '#lire')) }
    const c = $$('.bouton', n)[1]; if (c) c.onclick = async () => { const r = await H.agent.continueFrom(s); if (r && r.error) return toast(r.error)
      aller('chat'); viderFil(); s.events.forEach((e) => montrer(e, true)); ajouter(`<div class="sys">From ${esc(m.name)}: your agent continues with this as context.</div>`) }
    return
  }
  ajouter(m.mine ? `<div class="msg moi">${esc(m.text)}</div>` : `<div class="msg agent" style="max-width:88%"><div class="corps"><div style="font-size:12px;color:var(--vert-clair);font-weight:600">${esc(m.name)}</div>${riche(m.text)}</div></div>`, '#k-fil')
}

// =====================================================================================
// vibe code: Claude works in any of your GitHub repositories, computer off
// =====================================================================================
let PROJET = null
async function vueVibe() {
  const v = $('#v-vibe')
  if (PROJET) return vueProjet()
  v.innerHTML = `<div class="defile"><div class="colonne"><div class="titre">vibe code</div><div class="sous-titre">Have an idea? Claude Agent builds it in any of your GitHub repositories, on GitHub's machines, with your plan. Your computer can stay off.</div>
    <div id="g-corps"><div class="vide">Looking at GitHub...</div></div></div></div>`
  const st = await H.vibe.status().catch((e) => ({ ready: false, why: String(e.message || e) }))
  if (!st.ready) { $('#g-corps').innerHTML = `<div class="verre carte"><div style="margin-bottom:6px">${esc(st.why || 'Not set up yet.')}</div>${H.kind === 'computer' ? '<button class="bouton vert" id="g-reglages">Set it up in Settings</button>' : '<div class="m" style="color:var(--encre-3);font-size:13px">Set it up once from root-harness on your computer: Settings, Vibe code.</div>'}</div>`
    $('#g-reglages') && ($('#g-reglages').onclick = () => aller('reglages')); return }
  const L = await H.vibe.projects()
  $('#g-corps').innerHTML = `<div class="boutons"><button class="bouton plein" id="g-nouveau">${'+'} new idea</button></div>
    <div class="section">your vibes<span class="ligne"></span></div><div class="liste">${L.map((p, i) => `<div class="item" data-n="${p.number}" style="--i:${i}"><div class="tx"><div class="t">${esc(p.title)}</div><div class="m">${esc(p.repo)} · ${quand(p.updated)}</div></div><span class="badge">${esc(p.state)}</span></div>`).join('') || '<div class="vide">Nothing yet. Start with an idea.</div>'}</div>`
  $('#g-nouveau').onclick = feuilleIdee
  $$('#g-corps .item').forEach((el) => el.onclick = () => { PROJET = L.find((p) => p.number === +el.dataset.n); vueProjet() })
}
async function feuilleIdee() {
  const f = feuille('<h3>a new idea</h3><div class="sous-titre">Loading your repositories...</div>')
  const repos = await H.vibe.repos().catch(() => [])
  f.innerHTML = `<div class="poignee"></div><h3>a new idea</h3><div class="sous-titre">Where should Claude work?</div>
    <input class="champ" id="i-cherche" placeholder="search a repository, or type a name for a new one">
    <div class="liste" id="i-liste" style="max-height:38vh;overflow:auto;margin-top:8px"></div>`
  const rendre = () => { const q = $('#i-cherche', f).value.trim().toLowerCase(), L = repos.filter((r) => r.toLowerCase().includes(q)).slice(0, 40)
    const nouveau = q && /^[a-z0-9._-]+$/i.test(q) && !repos.some((r) => r.split('/')[1].toLowerCase() === q)
    $('#i-liste', f).innerHTML = (nouveau ? `<div class="item" data-new="${esc(q)}"><div class="tx"><div class="t">+ new repository: ${esc(q)}</div><div class="m">private, created by Claude</div></div></div>` : '')
      + L.map((r, i) => `<div class="item" data-r="${esc(r)}" style="--i:${i}"><div class="tx"><div class="t">${esc(r)}</div></div></div>`).join('')
    $$('#i-liste .item', f).forEach((el) => el.onclick = () => { fermerFeuille(); PROJET = { number: 0, repo: el.dataset.r || ('new:' + el.dataset.new), title: '' }; vueProjet() }) }
  $('#i-cherche', f).oninput = rendre; rendre(); $('#i-cherche', f).focus()
}
let SUIVI = null
async function vueProjet() {
  const v = $('#v-vibe'), p = PROJET
  const nom = p.repo.startsWith('new:') ? 'new: ' + p.repo.slice(4) : p.repo
  v.innerHTML = `<div class="tete-chat"><button class="rond-btn" id="p-retour">${ico('retour')}</button><span class="pilule-cerveau verre">${tete()}<span>Claude Agent</span><span class="modele">${esc(nom)}</span></span>
    <span class="etat"><span class="point" id="p-point"></span><span id="p-etat"></span></span></div>
    <div class="defile"><div class="colonne fil" id="p-fil"></div></div>
    <div class="composer"><div class="boite"><textarea id="p-entree" rows="1" placeholder="${p.number ? 'Ask for changes...' : 'Describe your idea...'}"></textarea>
    <button class="rond-btn envoyer" id="p-envoyer"><svg class="fleche" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${I.fleche}</svg></button></div></div>`
  $('#p-retour').onclick = () => { clearInterval(SUIVI); PROJET = null; vueVibe() }
  const etatP = (t, k) => { $('#p-etat') && ($('#p-etat').textContent = t); const e = $('#p-point'); if (e) e.className = 'point ' + k }
  const vus = new Map()
  const rafraichir = async () => {
    if (!PROJET || !PROJET.number) return
    const r = await H.vibe.thread(PROJET.number).catch(() => null); if (!r) return
    for (const m of r.messages) { if (vus.get(m.id) === m.updated) continue
      const html = m.bot ? `<div class="msg agent" data-m="${m.id}">${tete()}<div class="corps">${riche(m.text)}</div></div>` : `<div class="msg moi" data-m="${m.id}">${esc(m.text)}</div>`
      const old = $(`[data-m="${m.id}"]`, $('#p-fil')); if (old) { const w = document.createElement('div'); w.innerHTML = html; old.replaceWith(w.firstElementChild) } else ajouter(html, '#p-fil')
      vus.set(m.id, m.updated) }
    etatP(r.working ? 'Claude is working on GitHub...' : 'done: review the pull request', r.working ? 'travail' : 'ok')
  }
  if (p.number) { etatP('loading...', 'travail'); await rafraichir() }
  else { ajouter(`<div class="bienvenue" style="padding-top:8vh"><div class="grande-tete">${tete()}</div><div class="titre" style="font-size:28px">your idea, built on GitHub</div><div class="sous-titre" style="margin:8px auto 0">Claude makes a branch and a pull request in <b>${esc(nom)}</b>. You review before anything is merged.</div></div>`, '#p-fil'); etatP('ready', 'ok') }
  clearInterval(SUIVI); SUIVI = setInterval(() => { if (VUE === 'vibe' && PROJET) rafraichir() }, 6000)
  const ta = $('#p-entree'), go = async () => { const t = ta.value.trim(); if (!t) return; ta.value = ''; ajuster(ta)
    $('.bienvenue', $('#p-fil'))?.remove(); etatP('sending to GitHub...', 'travail')
    const r = await H.vibe.send(PROJET.repo, t, PROJET.number); if (!r || r.error) return etatP((r && r.error) || 'not sent', 'off')
    if (!PROJET.number) PROJET = { ...PROJET, number: r.number }
    etatP('Claude is starting on GitHub (about a minute)...', 'travail'); rafraichir() }
  $('#p-envoyer').onclick = go; ta.oninput = () => ajuster(ta)
  ta.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey && !matchMedia('(pointer:coarse)').matches) { e.preventDefault(); go() } }
}

// =====================================================================================
// settings
// =====================================================================================
async function vueReglages() {
  const v = $('#v-reglages'), st = await H.account.state()
  v.innerHTML = `<div class="defile"><div class="colonne"><div class="titre">settings</div><div class="sous-titre">Your account lives on your devices. Nothing here goes to a server of ours: there is none.</div>
    <div class="section">account<span class="ligne"></span></div><div class="verre carte">
      <div class="reglage">${tete()}<div class="l"><div>${esc(st.pseudo || '')}</div><div class="d" style="font-family:var(--mono);word-break:break-all">${esc(st.npub || '')}</div></div></div>
      ${H.kind === 'computer' ? `<div class="reglage"><div class="l">Stay signed in<div class="d">No password when root-harness opens</div></div><span class="inter${st.stay ? ' on' : ''}" id="r-stay"></span></div>
      <div class="reglage"><div class="l">Sync between my devices<div class="d">Your whole memory, sealed, on relays</div></div><span class="inter${st.sync ? ' on' : ''}" id="r-sync"></span></div>` : ''}
      <div class="boutons"><button class="bouton" id="r-lock">Lock</button>${H.kind === 'computer' ? '<button class="bouton" id="r-mdp">Change password</button>' : '<button class="bouton danger" id="r-sortir">Sign out of this phone</button>'}</div></div>
    <div class="section">background<span class="ligne"></span></div><div class="verre carte"><div class="boutons">${H.kind === 'computer' ? '<button class="bouton vert" id="r-image">Choose a picture</button>' : ''}<button class="bouton" id="r-sans">Plain night</button></div>
      <div class="d" style="color:var(--encre-3);font-size:12.5px;margin-top:8px">${H.kind === 'phone' ? 'Your phone uses the picture of your computer.' : 'Your picture goes to your phone too, never to anyone else.'}</div></div>
    <div id="r-plus"></div></div></div>`
  $('#r-stay') && ($('#r-stay').onclick = async () => { await H.account.setStay(!st.stay); vueReglages() })
  $('#r-sync') && ($('#r-sync').onclick = async () => { await H.account.setSync(!st.sync); vueReglages() })
  $('#r-lock').onclick = async () => { await H.account.lock(); location.reload() }
  $('#r-sortir') && ($('#r-sortir').onclick = async () => { await H.account.signOut(); location.reload() })
  $('#r-mdp') && ($('#r-mdp').onclick = () => { const f = feuille(`<h3>change password</h3><input class="champ" id="m-a" type="password" placeholder="current password"><input class="champ" id="m-n" type="password" placeholder="new password (10+)"><input class="champ" id="m-n2" type="password" placeholder="again"><div class="err" id="m-err"></div><div class="boutons"><button class="bouton plein" id="m-ok">Change</button></div>`)
    $('#m-ok', f).onclick = async () => { const r = await H.account.changePassword($('#m-a', f).value, $('#m-n', f).value, $('#m-n2', f).value); if (r.error) return ($('#m-err', f).textContent = r.error); fermerFeuille(); toast('Password changed') } })
  $('#r-image') && ($('#r-image').onclick = async () => { await H.chooseBackground(); fond() })
  $('#r-sans').onclick = async () => { await H.plainBackground(); fond() }
  if (H.reglagesEnPlus) H.reglagesEnPlus($('#r-plus'), { feuille, fermerFeuille, toast, esc, ico })
}

// =====================================================================================
// start
// =====================================================================================
async function demarrer() {
  fond(); aller(VUE)
  setTimeout(rafraichirCerveau, 5000); setTimeout(rafraichirCerveau, 15000)     // the agent finishes starting
  H.friends.overview().then((ov) => pastille(ov.channels.some((c) => c.unread))).catch(() => {})
}

export async function lancer(host) {
  H = host
  coquille()
  H.on((e) => {
    if (e.type === 'channel_message') {
      if (CANAL && e.channel === CANAL.id) { bulleCanal(e.message); H.friends.messages(CANAL.id) }
      else { pastille(true); if (VUE === 'amis' && !CANAL) vueAmis() }
    } else if (e.type === 'channels_changed') { if (VUE === 'amis' && !CANAL) vueAmis() }
    else if (e.type === 'synced') { if (e.changed) { fond(); if (VUE === 'discussions') vueDiscussions() } }
    else if (e.type === 'computer') { if (VUE === 'chat') rafraichirCerveau() }
    else montrer(e, false)
  })
  if (await porte()) await demarrer()
}
