// root-harness on your phone: a remote for the root-harness running on your
// computer. Everything here runs on the phone: the password never leaves it,
// and the computer is reached only through sealed messages (NIP-59) that the
// relays cannot read. See rootharness/remote.py for the computer's side.
import { scryptAsync } from '@noble/hashes/scrypt.js'
import { getPublicKey, finalizeEvent, generateSecretKey, verifyEvent } from 'nostr-tools/pure'
import * as nip44 from 'nostr-tools/nip44'
import * as nip49 from 'nostr-tools/nip49'
import { SimplePool } from 'nostr-tools/pool'

const RELAYS = ['wss://relay.damus.io', 'wss://nos.lol', 'wss://relay.primal.net']
const LOGIN_LABEL = 'root-harness-login'
const STORE = 'rh-account'
const $ = (s) => document.querySelector(s)
const now = () => Math.floor(Date.now() / 1000)
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
const ck = (sk, pub) => nip44.v2.utils.getConversationKey(sk, pub)

let pool = null, sk = null, me = '', since = 0, lastState = 0
const seen = new Set()

// -- account: sign in with pseudo + password, or unlock with the password -----

function stored() { try { return JSON.parse(localStorage.getItem(STORE)) } catch { return null } }

function screen(html) { $('#ecran').innerHTML = html; $('#ecran').classList.add('on'); $('#appli').classList.remove('on') }

function signIn() {
  screen(`<div class="carte"><div class="logo">R</div><h2>root-harness</h2>
    <p>Sign in with the pseudo and password of your root-harness account.</p>
    <input id="pseudo" placeholder="Pseudo" autocomplete="username" autocapitalize="off">
    <input id="mdp" type="password" placeholder="Password" autocomplete="current-password">
    <div class="err" id="err"></div><div class="barre" id="barre"><i></i></div>
    <button class="go" id="go">Sign in</button>
    <div class="petit">Your phone becomes a remote for root-harness on your computer. Your password stays on this phone.</div></div>`)
  $('#go').onclick = async () => {
    const pseudo = $('#pseudo').value, pw = $('#mdp').value
    if (!pseudo.trim() || !pw) return erreur('Type your pseudo and password.')
    busy('Unlocking your account...')
    try {
      const norm = pseudo.split(/\s+/).filter(Boolean).join(' ').slice(0, 32).toLowerCase()
      const seed = await scryptAsync(new TextEncoder().encode(pw), new TextEncoder().encode('root-harness/login/v1/' + norm),
        { N: 2 ** 18, r: 8, p: 1, dkLen: 32, onProgress: (p) => progres(p * 0.8) })
      const lpub = getPublicKey(seed)
      busy('Looking for your account on the relays...')
      pool = pool || new SimplePool()
      const evs = await pool.querySync(RELAYS, { kinds: [30078], authors: [lpub], '#d': [LOGIN_LABEL] }, { maxWait: 8000 })
      let vault = null
      for (const ev of evs.sort((a, b) => b.created_at - a.created_at)) {
        try { vault = JSON.parse(nip44.v2.decrypt(ev.content, ck(seed, lpub))); if (vault.locked_key) break } catch { vault = null }
      }
      if (!vault || !vault.locked_key) return erreur('No account with this pseudo and password.')
      progres(0.9)
      const key = nip49.decrypt(vault.locked_key, pw)
      localStorage.setItem(STORE, JSON.stringify({ pseudo: vault.pseudo || pseudo, locked: vault.locked_key }))
      progres(1)
      start(key, vault.pseudo || pseudo)
    } catch (e) { erreur('Could not sign in: ' + (e.message || e)) }
  }
  $('#mdp').onkeydown = (e) => { if (e.key === 'Enter') $('#go').click() }
}

function unlock(acc) {
  screen(`<div class="carte"><div class="logo">R</div><h2>Welcome back, ${esc(acc.pseudo)}</h2>
    <p>Type your password.</p><input id="mdp" type="password" placeholder="Password" autocomplete="current-password">
    <div class="err" id="err"></div><button class="go" id="go">Unlock</button>
    <div class="lien" id="sortir">Sign out of this phone</div></div>`)
  $('#go').onclick = () => {
    try { start(nip49.decrypt(acc.locked, $('#mdp').value), acc.pseudo) } catch { erreur('Wrong password.') }
  }
  $('#mdp').onkeydown = (e) => { if (e.key === 'Enter') $('#go').click() }
  $('#sortir').onclick = () => { localStorage.removeItem(STORE); signIn() }
  setTimeout(() => $('#mdp').focus(), 300)
}

function erreur(t) {
  $('#err').textContent = t; const b = $('#go'); if (b) { b.disabled = false; b.textContent = b.dataset.t || b.textContent }
  const c = $('.carte'); c.classList.remove('secoue'); void c.offsetWidth; c.classList.add('secoue'); $('#barre')?.classList.remove('on')
}
function busy(t) { const b = $('#go'); b.dataset.t = b.dataset.t || b.textContent; b.disabled = true; b.textContent = t; $('#err').textContent = ''; $('#barre')?.classList.add('on') }
function progres(p) { const i = $('#barre i'); if (i) i.style.width = Math.round(p * 100) + '%' }

// -- talking to the computer: sealed messages to yourself -----------------------

function wrap(payload) {
  const rumor = { kind: 14, created_at: now(), pubkey: me, tags: [['p', me], ['rh-remote', '1']], content: JSON.stringify(payload) }
  const back = () => now() - Math.floor(Math.random() * 172800)
  const seal = finalizeEvent({ kind: 13, created_at: back(), tags: [], content: nip44.v2.encrypt(JSON.stringify(rumor), ck(sk, me)) }, sk)
  const eph = generateSecretKey()
  return finalizeEvent({ kind: 1059, created_at: back(), tags: [['p', me], ['expiration', String(now() + 86400)]],
    content: nip44.v2.encrypt(JSON.stringify(seal), ck(eph, me)) }, eph)
}

function unwrap(ev) {
  try {
    const seal = JSON.parse(nip44.v2.decrypt(ev.content, ck(sk, ev.pubkey)))
    if (seal.kind !== 13 || seal.pubkey !== me || !verifyEvent(seal)) return null     // sealed by you, or ignored
    const rumor = JSON.parse(nip44.v2.decrypt(seal.content, ck(sk, seal.pubkey)))
    if (rumor.pubkey !== seal.pubkey || !rumor.tags.some((t) => t[0] === 'rh-remote')) return null
    return JSON.parse(rumor.content)
  } catch { return null }
}

async function order(op, extra = {}) {
  // getRandomValues works on any page; randomUUID only on https pages
  const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
  const payload = { v: 1, dir: 'phone', id, ts: now(), op, ...extra }
  try { await Promise.any(pool.publish(RELAYS, wrap(payload))); return true } catch { return false }
}

function start(key, pseudo) {
  sk = key; me = getPublicKey(sk); since = now() - 30
  $('#ecran').classList.remove('on'); $('#appli').classList.add('on')
  $('#qui').textContent = pseudo
  pool = pool || new SimplePool()
  pool.subscribe(RELAYS, { kinds: [1059], '#p': [me], since: now() - 172800 - 300 }, {
    onevent(ev) {
      if (seen.has(ev.id)) return; seen.add(ev.id)
      const m = unwrap(ev)
      if (!m || m.v !== 1 || m.dir !== 'computer' || m.ts < since || seen.has(m.id)) return
      seen.add(m.id); recu(m)
    },
  })
  etat('Calling your computer...', 'attente')
  let tries = 0
  const hello = () => { if (Date.now() - lastState > 20000 && tries++ < 6) { order('hello'); setTimeout(hello, 5000) }
    else if (Date.now() - lastState > 20000) etat('Your computer does not answer: is root-harness open, unlocked, with "Use from my phone" on?', 'off') }
  hello()
  const ask = new URLSearchParams(location.hash.slice(1)).get('ask')     // from a Shortcut: #ask=...
  if (ask) { $('#entree').value = ask; history.replaceState(null, '', location.pathname) }
}

// -- what the computer sends ------------------------------------------------------

function recu(m) {
  if (m.op === 'state') {
    lastState = Date.now()
    const s = m.state
    $('#modele').textContent = [s.brain, s.model, s.effort && 'effort ' + s.effort].filter(Boolean).join(' · ')
    $('#fil').innerHTML = ''; outils = {}
    for (const e of s.events || []) montrer(e, true)
    $$('.outil').forEach((o) => o.classList.add('fait'))
    etat(s.busy ? 'working' : 'connected', s.busy ? 'travail' : 'ok')
  } else if (m.op === 'events') {
    lastState = Date.now()
    for (const e of m.events) montrer(e, false)
  }
}
const $$ = (s) => [...document.querySelectorAll(s)]
let outils = {}, dernierOutil = null

function ajouter(html) {
  const f = $('#fil'), w = document.createElement('div'); w.innerHTML = html
  const n = w.firstElementChild; f.appendChild(n); f.scrollTop = f.scrollHeight; return n
}

function montrer(e, histoire) {
  const t = e.type
  if (t === 'user' || (t === 'remote_user' && e.from !== 'phone' && !enAttente(e.text))) ajouter(`<div class="msg toi">${esc(e.text)}</div>`)
  else if (t === 'text') ajouter(`<div class="msg root">${riche(e.text)}</div>`)
  else if (t === 'tool') {
    dernierOutil = ajouter(`<div class="outil${histoire ? ' fait' : ''}"><span class="rond"></span><b>${esc(e.name)}</b> <span class="args">${esc(JSON.stringify(e.args || {}))}</span></div>`)
    if (e.id) outils[e.id] = dernierOutil
    if (!histoire) etat('using ' + e.name, 'travail')
  } else if (t === 'result') {
    const o = (e.id && outils[e.id]) || dernierOutil
    if (o) { o.classList.add('fait'); const d = document.createElement('div'); d.className = 'detail'; d.textContent = (e.text || '').slice(0, 1200); o.appendChild(d) }
  } else if (t === 'permission' && !histoire) carteAutorisation(e)
  else if (t === 'question' && !histoire) carteQuestion(e)
  else if (t === 'error') ajouter(`<div class="msg erreur">${esc(e.text)}</div>`)
  else if (t === 'status') etat(e.text, 'travail')
  else if (t === 'usage' && e.percent !== undefined) $('#contexte').textContent = `${e.percent}% context`
  else if (t === 'done') { etat('connected', 'ok'); $$('.outil').forEach((o) => o.classList.add('fait')) }
}

let envoyes = []
function enAttente(text) { const i = envoyes.indexOf(text); if (i >= 0) { envoyes.splice(i, 1); return true } return false }

function carteAutorisation(e) {
  etat('waiting for you', 'attente')
  const n = ajouter(`<div class="carte-a"><div class="q">Your agent wants to: <b>${esc(e.title)}</b></div>
    <pre>${esc(JSON.stringify(e.args, null, 1)).slice(0, 600)}</pre><div class="row"><button class="oui">Allow</button><button class="non">Deny</button></div></div>`)
  const fin = (ok) => { order('answer', { pid: e.id, allow: ok }); n.querySelector('.row').outerHTML = `<div class="verdict ${ok ? 'v' : 'r'}">${ok ? 'Allowed' : 'Denied'}</div>`; etat('working', 'travail') }
  n.querySelector('.oui').onclick = () => fin(true); n.querySelector('.non').onclick = () => fin(false)
}

function carteQuestion(e) {
  etat('waiting for you', 'attente')
  const choix = {}
  const n = ajouter(`<div class="carte-a">${e.questions.map((q, i) => `<div data-q="${i}"><div class="q">${esc(q.question)}</div>
    ${(q.options || []).map((o, j) => `<button class="opt" data-j="${j}">${esc(o.label)}${o.description ? `<small>${esc(o.description)}</small>` : ''}</button>`).join('')}</div>`).join('')}
    <div class="row"><button class="oui">Send</button><button class="non">Skip</button></div></div>`)
  n.querySelectorAll('[data-q]').forEach((b) => {
    const q = e.questions[+b.dataset.q]; choix[q.question] = new Set()
    b.querySelectorAll('.opt').forEach((o) => o.onclick = () => {
      const lab = q.options[+o.dataset.j].label, S = choix[q.question]
      if (q.multiSelect) { S.has(lab) ? S.delete(lab) : S.add(lab); o.classList.toggle('on') }
      else { S.clear(); S.add(lab); b.querySelectorAll('.opt').forEach((x) => x.classList.toggle('on', x === o)) }
    })
  })
  n.querySelector('.oui').onclick = () => {
    const answers = {}; for (const [k, S] of Object.entries(choix)) { if (!S.size) return; answers[k] = [...S].join(', ') }
    order('answer', { pid: e.id, answers }); n.querySelector('.row').outerHTML = `<div class="verdict v">${esc(Object.values(answers).join(' · '))}</div>`
  }
  n.querySelector('.non').onclick = () => { order('answer', { pid: e.id, answers: null }); n.querySelector('.row').outerHTML = '<div class="verdict r">Skipped</div>' }
}

function etat(t, kind) {
  $('#etat').textContent = t; $('#point').className = 'point ' + kind
  document.body.classList.toggle('travail', kind === 'travail')
}

// Mini Markdown, as on the computer: code blocks, `code`, **bold**, headings, lists
function riche(texte) {
  const blocs = []
  texte = (texte || '').replace(/```[\w-]*\n?([\s\S]*?)```/g, (_, c) => `\u0000${blocs.push(c) - 1}\u0000`)
  const ligne = (x) => esc(x).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  return texte.split(/\n{2,}/).map((par) => {
    const m = par.match(/^\u0000(\d+)\u0000$/); if (m) return `<pre>${esc(blocs[+m[1]])}</pre>`
    return '<p>' + par.split('\n').map((l) => {
      const h = l.match(/^#{1,6}\s+(.*)$/); if (h) return `<b>${ligne(h[1])}</b>`
      return /^\s*[-•*]\s+/.test(l) ? '• ' + ligne(l.replace(/^\s*[-•*]\s+/, '')) : ligne(l)
    }).join('<br>') + '</p>'
  }).join('')
}

// -- composer ----------------------------------------------------------------------

async function envoyer() {
  const t = $('#entree').value.trim(); if (!t || !sk) return
  $('#entree').value = ''; ajuster()
  envoyes.push(t); ajouter(`<div class="msg toi">${esc(t)}</div>`); etat('sending...', 'travail')
  if (!(await order('send', { text: t }))) etat('Not sent: check your connection.', 'off')
}
function ajuster() { const e = $('#entree'); e.style.height = 'auto'; e.style.height = Math.min(e.scrollHeight, 140) + 'px' }

window.addEventListener('DOMContentLoaded', () => {
  $('#envoyer').onclick = () => document.body.classList.contains('travail') ? order('stop') : envoyer()
  $('#entree').addEventListener('input', ajuster)
  $('#entree').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) envoyer() })
  $('#nouveau').onclick = () => { order('new'); $('#fil').innerHTML = '' }
  $('#verrou').onclick = () => { sk = null; me = ''; location.reload() }
  const acc = stored(); acc ? unlock(acc) : signIn()
})
