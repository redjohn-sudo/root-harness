// The phone's host: the same interface, reached from a phone.
//  - your account: pseudo + password find your identity on the relays (the
//    computer published it sealed; see rootharness/account.py and sync.py);
//  - your memory: the sealed pieces your computer keeps on the relays
//    (conversations, friends, background, keys), read here, opened here;
//  - friends & groups: sealed messages, sent and received right here;
//  - vibe code: GitHub's API, with the GitHub sign-in from your sealed memory;
//  - your agents on the computer: sealed orders when it is on.
// The password never leaves the phone.
// Older iPhones (before iOS 15.4) lack Object.hasOwn, used by a library: give it to them.
if (!Object.hasOwn) Object.hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k)
import { scryptAsync } from '@noble/hashes/scrypt.js'
import { sha256 } from '@noble/hashes/sha2.js'
import { hmac } from '@noble/hashes/hmac.js'
import { bytesToHex, hexToBytes, utf8ToBytes } from '@noble/hashes/utils.js'
import { getPublicKey, finalizeEvent, generateSecretKey, verifyEvent } from 'nostr-tools/pure'
import * as nip44 from 'nostr-tools/nip44'
import * as nip49 from 'nostr-tools/nip49'
import * as nip19 from 'nostr-tools/nip19'
import { SimplePool } from 'nostr-tools/pool'
import { lancer } from './app.js'
import { code, parse, handle } from './ident.js'
import { reseau } from './social-net.js'
import BASE from '../rootharness/glossary_base.json'

const RELAYS = ['wss://relay.damus.io', 'wss://nos.lol', 'wss://relay.primal.net']
const STORE = 'rh-account', CACHE = 'rh-cache'
const now = () => Math.floor(Date.now() / 1000)
const ck = (sk, pub) => nip44.v2.utils.getConversationKey(sk, pub)
const rid = () => bytesToHex(crypto.getRandomValues(new Uint8Array(16)))

let pool = new SimplePool(), sk = null, me = '', ecoute = () => {}
let ordinateur = 0                                     // last time the computer answered
const attentes = new Map()                             // order id -> resolve
const vus = new Set()

// -- the account -------------------------------------------------------------------
const compte = () => { try { return JSON.parse(localStorage.getItem(STORE)) } catch { return null } }
const norm = (p) => p.split(/\s+/).filter(Boolean).join(' ').slice(0, 32).toLowerCase()

async function connecter(pseudo, pw, progres) {
  const seed = await scryptAsync(utf8ToBytes(pw), utf8ToBytes('root-harness/login/v1/' + norm(pseudo)),
    { N: 2 ** 18, r: 8, p: 1, dkLen: 32, onProgress: (p) => progres && progres(p * 0.8) })
  const lpub = getPublicKey(seed)
  const evs = await pool.querySync(RELAYS, { kinds: [30078], authors: [lpub], '#d': ['root-harness-login'] }, { maxWait: 8000 })
  for (const ev of evs.sort((a, b) => b.created_at - a.created_at)) {
    try { const v = JSON.parse(nip44.v2.decrypt(ev.content, ck(seed, lpub))); if (v.locked_key) {
      const key = nip49.decrypt(v.locked_key, pw); progres && progres(1)
      localStorage.setItem(STORE, JSON.stringify({ pseudo: v.pseudo || pseudo, locked: v.locked_key, npub: nip19.npubEncode(getPublicKey(key)) }))
      return key } } catch {}
  }
  return null
}

// -- sealed messages (NIP-59), as the computer makes them --------------------------------
function sceller(rumorTags, content, to, expire) {
  const rumor = { kind: 14, created_at: now(), pubkey: me, tags: [['p', to], ...rumorTags], content }
  rumor.id = bytesToHex(sha256(utf8ToBytes(JSON.stringify([0, rumor.pubkey, rumor.created_at, rumor.kind, rumor.tags, rumor.content]))))
  const back = () => now() - Math.floor(Math.random() * 172800)
  const seal = finalizeEvent({ kind: 13, created_at: back(), tags: [], content: nip44.v2.encrypt(JSON.stringify(rumor), ck(sk, to)) }, sk)
  const eph = generateSecretKey(), tags = [['p', to]]
  if (expire) tags.push(['expiration', String(now() + expire)])
  return finalizeEvent({ kind: 1059, created_at: back(), tags, content: nip44.v2.encrypt(JSON.stringify(seal), ck(eph, to)) }, eph)
}
function ouvrir(ev) {
  try {
    const seal = JSON.parse(nip44.v2.decrypt(ev.content, ck(sk, ev.pubkey)))
    if (seal.kind !== 13 || !verifyEvent(seal)) return null
    const rumor = JSON.parse(nip44.v2.decrypt(seal.content, ck(sk, seal.pubkey)))
    if (rumor.pubkey !== seal.pubkey) return null                 // the sender is who sealed it
    return { rumor, sender: seal.pubkey }
  } catch { return null }
}
async function publier(ev) { try { await Promise.any(pool.publish(RELAYS, ev)); return true } catch { return false } }

// -- your memory, as the computer keeps it on the relays (sync.py) -----------------------
let etiquette = null
const piece = (name) => bytesToHex(hmac(sha256, etiquette, utf8ToBytes(name))).slice(0, 40)
let MANIFESTE = null
async function manifeste() {
  if (MANIFESTE) return MANIFESTE
  const evs = await pool.querySync(RELAYS, { kinds: [30078], authors: [me], '#d': [piece('manifest')] }, { maxWait: 7000 })
  const ev = evs.sort((a, b) => b.created_at - a.created_at)[0]
  MANIFESTE = ev ? JSON.parse(nip44.v2.decrypt(ev.content, ck(sk, me))) : { items: {} }
  return MANIFESTE
}
async function lire(name) {
  const m = (await manifeste()).items[name]; if (!m) return null
  const labels = Array.from({ length: m.n }, (_, i) => piece(`${name}#${i}`))
  const evs = await pool.querySync(RELAYS, { kinds: [30078], authors: [me], '#d': labels }, { maxWait: 7000 })
  const par = {}
  for (const e of evs) { const d = (e.tags.find((t) => t[0] === 'd') || [])[1]; if (!par[d] || e.created_at > par[d].created_at) par[d] = e }
  if (labels.some((l) => !par[l])) return null
  const b64 = labels.map((l) => nip44.v2.decrypt(par[l].content, ck(sk, me))).join('')
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))
  const txt = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'))).text()
  return JSON.parse(txt)
}
const cache = { get(k) { try { return JSON.parse(localStorage.getItem(CACHE + ':' + k)) } catch { return null } },
  set(k, v) { try { localStorage.setItem(CACHE + ':' + k, JSON.stringify(v)) } catch {} } }

// -- friends & groups, here on the phone -------------------------------------------------
let AMIS = { contacts: {}, channels: {}, pseudos: {} }, LOGS = {}
const canalId = (membres) => bytesToHex(sha256(utf8ToBytes([...membres].sort().join(',')))).slice(0, 16)
const npubDe = (h) => nip19.npubEncode(h)
const hexDe = (s) => { try { s = s.trim(); return s.startsWith('npub') ? nip19.decode(s).data : (/^[0-9a-f]{64}$/.test(s) ? s : null) } catch { return null } }
const nom = (h) => h === me ? 'You' : (AMIS.contacts[h]?.name || (AMIS.pseudos[h] ? `${AMIS.pseudos[h]} (${npubDe(h).slice(0, 12)}...)` : npubDe(h).slice(0, 14) + '...'))
function garderAmis() { cache.set('amis', AMIS); cache.set('logs', LOGS) }
function vue(m) { return { ...m, mine: m.from === me, name: nom(m.from) } }
function ajouterMessage(cid, m) {
  const L = LOGS[cid] = LOGS[cid] || []
  if (L.some((x) => x.rid === m.rid)) return false
  L.push(m); L.sort((a, b) => a.at - b.at); if (L.length > 500) L.splice(0, L.length - 500)
  const ch = AMIS.channels[cid]; if (ch) ch.last = Math.max(ch.last || 0, m.at)
  return true
}
function appliquer(op) {
  if (op.op === 'contact_add' && hexDe(op.hex)) AMIS.contacts[op.hex] = { name: op.name || 'friend' }
  if (op.op === 'group_create' && op.members?.length) {
    const cid = canalId(new Set([...op.members, me]))
    AMIS.channels[cid] = AMIS.channels[cid] || { name: op.name, members: op.members, unread: 0, last: now(), request: false }
  }
  for (const ch of Object.values(AMIS.channels)) if (ch.members.every((m) => AMIS.contacts[m])) ch.request = false
  garderAmis()
}
async function annoncer(op) { await publier(sceller([['rh-op', '1']], JSON.stringify(op), me, 30 * 86400)); appliquer(op) }

function recevoir(ev) {
  if (vus.has(ev.id)) return; vus.add(ev.id)
  const o = ouvrir(ev); if (!o) return
  const { rumor, sender } = o, tags = rumor.tags || []
  const has = (k) => tags.some((t) => t[0] === k), val = (k) => (tags.find((t) => t[0] === k) || [])[1]
  if (rumor.kind !== 14) return
  if (has('rh-op')) { if (sender === me) try { appliquer(JSON.parse(rumor.content)); ecoute({ type: 'channels_changed' }) } catch {} return }
  if (has('rh-remote')) { if (sender === me) try { duOrdinateur(JSON.parse(rumor.content)) } catch {} return }
  const membres = new Set([...tags.filter((t) => t[0] === 'p').map((t) => t[1]), sender, me])
  const cid = canalId(membres)
  if (val('rh-name') && sender !== me) AMIS.pseudos[sender] = val('rh-name').slice(0, 32)
  if (!AMIS.channels[cid]) {
    const autres = [...membres].filter((m) => m !== me).sort()
    AMIS.channels[cid] = { name: val('subject') || '', members: autres, unread: 0, last: 0, request: sender !== me && !autres.every((m) => AMIS.contacts[m]) }
  }
  let m = { rid: val('rh-id') || ev.id, from: sender, text: rumor.content, at: rumor.created_at }
  if (has('rh-share')) try { const s = JSON.parse(rumor.content); m = { ...m, text: 'shared: ' + s.title, share: s } } catch {}
  if (ajouterMessage(cid, m)) { if (sender !== me) AMIS.channels[cid].unread++; garderAmis(); ecoute({ type: 'channel_message', channel: cid, message: vue(m) }) }
}
async function envoyerCanal(cid, content, extra = []) {
  const ch = AMIS.channels[cid]; if (!ch) return null
  const r = rid(), pseudo = compte()?.pseudo || ''
  let ok = false
  for (const to of [...ch.members, me]) {
    const tags = [['rh-id', r], ['rh-name', pseudo], ...extra, ...(ch.name ? [['subject', ch.name]] : []), ...ch.members.filter((m) => m !== to).map((m) => ['p', m])]
    if ((await publier(sceller(tags, content, to))) && to !== me) ok = true
  }
  return { r, ok }
}

// -- linking this phone with a QR code (rootharness/pairing.py) ---------------------------
// The QR opens this app with #pair=<the computer's one-time key>. The phone makes its own
// one-time key, answers, shows the same 6 digits as the computer, and receives the
// identity sealed for it once you approve on the computer.
const PAIR = (() => { const m = location.hash.match(/pair=(npub1[0-9a-z]+)/); try { return m ? nip19.decode(m[1]).data : null } catch { return null } })()
function codeAppairage(computerHex, phoneHex) {
  const h = sha256(new Uint8Array([...hexToBytes(computerHex), ...hexToBytes(phoneHex)]))
  const n = ((h[0] << 24) >>> 0) + (h[1] << 16) + (h[2] << 8) + h[3]          // first 4 bytes, big-endian
  return String(n % 1000000).padStart(6, '0')
}
function scellerAvec(skX, to, tags, content, expire) {
  const pub = getPublicKey(skX)
  const rumor = { kind: 14, created_at: now(), pubkey: pub, tags: [['p', to], ...tags], content }
  rumor.id = bytesToHex(sha256(utf8ToBytes(JSON.stringify([0, rumor.pubkey, rumor.created_at, rumor.kind, rumor.tags, rumor.content]))))
  const back = () => now() - Math.floor(Math.random() * 3600)
  const seal = finalizeEvent({ kind: 13, created_at: back(), tags: [], content: nip44.v2.encrypt(JSON.stringify(rumor), ck(skX, to)) }, skX)
  const eph = generateSecretKey(), t = [['p', to]]; if (expire) t.push(['expiration', String(now() + expire)])
  return finalizeEvent({ kind: 1059, created_at: back(), tags: t, content: nip44.v2.encrypt(JSON.stringify(seal), ck(eph, to)) }, eph)
}
function appairer(onCode) {
  return new Promise((resolve) => {
    const eph = generateSecretKey(), mine = getPublicKey(eph), t0 = now()
    onCode(codeAppairage(PAIR, mine))
    const sub = pool.subscribe(RELAYS, { kinds: [1059], '#p': [mine], since: t0 - 3 * 3600 }, { onevent(ev) {
      try {
        const seal = JSON.parse(nip44.v2.decrypt(ev.content, ck(eph, ev.pubkey)))
        if (seal.pubkey !== PAIR || !verifyEvent(seal)) return                 // only the computer of the QR code
        const rumor = JSON.parse(nip44.v2.decrypt(seal.content, ck(eph, seal.pubkey))), m = JSON.parse(rumor.content)
        if (m.op === 'pair-key' && m.key) { sub.close(); resolve({ key: nip19.decode(m.key).data, pseudo: m.pseudo || '' }) }
      } catch {}
    } })
    publier(scellerAvec(eph, PAIR, [['rh-pair', '1']], JSON.stringify({ op: 'pair-hello' }), 600))
  })
}

// -- the computer: sealed orders and answers --------------------------------------------
function duOrdinateur(m) {
  if (m.v !== 1 || m.dir !== 'computer' || m.ts < now() - 600 || vus.has('o' + m.id)) return
  vus.add('o' + m.id); ordinateur = Date.now()
  if (m.op === 'result') { const a = attentes.get(m.re); if (a) { attentes.delete(m.re); m.error ? a.reject(new Error(m.error)) : a.resolve(m.value) } }
  else if (m.op === 'events') m.events.forEach((e) => { if (!(e.type === 'remote_user' && e.from === 'phone')) ecoute(e) })
  else if (m.op === 'state') ecoute({ type: 'computer' })
}
async function ordre(op, extra = {}) {
  const id = rid(), payload = JSON.stringify({ v: 1, dir: 'phone', id, ts: now(), op, ...extra })
  if (payload.length > 60000) throw new Error('Too big to send to your computer (an image? try a smaller one).')
  await publier(sceller([['rh-remote', '1']], payload, me, 86400))
  return id
}
const LENTS = new Set(['post_draft', 'glossary_ask'])  // the agent writes the answer: a model call, slow
function appel(method, ...args) {
  return new Promise(async (resolve, reject) => {
    try {
      const id = await ordre('call', { method, args })
      attentes.set(id, { resolve, reject })
      setTimeout(() => { if (attentes.has(id)) { attentes.delete(id); reject(new Error('Your computer is off or not answering.')) } },
        LENTS.has(method) ? 90000 : Date.now() - ordinateur < 90000 ? 45000 : 12000)
    } catch (e) { reject(e) }
  })
}

// -- GitHub, for vibe coding ---------------------------------------------------------------
let GH = null
async function gh(path, opts = {}) {
  if (!GH) { const keys = cache.get('keys') || ''; const l = keys.split('\n').find((x) => x.startsWith('GITHUB_TOKEN=')); GH = l ? l.slice(13).trim() : '' }
  if (!GH || GH === '-') throw new Error('Turn on "GitHub on my phone" in Settings on your computer.')
  const r = await fetch('https://api.github.com' + path, { ...opts, headers: { Authorization: 'Bearer ' + GH, Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28', ...(opts.body ? { 'Content-Type': 'application/json' } : {}) } })
  if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 100)}`)
  return r.status === 204 ? null : r.json()
}
let RUNNER = null
async function runner() { if (!RUNNER) RUNNER = (await gh('/user')).login + '/root-harness-runner'; return RUNNER }
const nettoyer = (t) => (t || '').split('<!-- rh:')[0].trim()

// =====================================================================================
const host = {
  kind: 'phone',
  on(fn) { ecoute = fn },
  async background() {
    const b = cache.get('background'); if (!b) return ''
    return URL.createObjectURL(new Blob([Uint8Array.from(atob(b.data), (c) => c.charCodeAt(0))], { type: 'image/jpeg' }))
  },
  chooseBackground: async () => {}, plainBackground: async () => { localStorage.removeItem(CACHE + ':background') },
  async copy(t) { try { await navigator.clipboard.writeText(t) } catch { const a = document.createElement('textarea'); a.value = t; document.body.appendChild(a); a.select(); document.execCommand('copy'); a.remove() } },

  account: {
    async state() { const a = compte(); return a ? { exists: true, unlocked: !!sk, pseudo: a.pseudo, npub: a.npub, id: me ? handle(a.pseudo, me) : '', at: ((cache.get('rh-net-profile') || {}).at) || '' } : { exists: false } },
    async setFindable() {},
    async create() { return { error: 'Create your account on your computer first, then sign in here.' } },
    pairing: !!PAIR,
    pair: (onCode) => appairer(onCode),
    async finishPair(key, pseudo, code) {
      if ((code || '').length < 6) return { error: 'At least 6 characters.' }
      localStorage.setItem(STORE, JSON.stringify({ pseudo, locked: nip49.encrypt(key, code), npub: nip19.npubEncode(getPublicKey(key)) }))
      history.replaceState(null, '', location.pathname); await ouvert(key); return {}
    },
    async restore(p, pw, progres) { try { const k = await connecter(p, pw, progres); if (!k) return { error: 'No account with this pseudo and password.' }; await ouvert(k); return {} }
      catch (e) { return { error: 'Could not reach the relays: ' + (e.message || e) } } },
    async unlock(pw) { const a = compte(); try { const k = nip49.decrypt(a.locked, pw); await ouvert(k); return {} } catch { return { error: 'Wrong password.' } } },
    async lock() { sk = null }, async signOut() { sk = null; localStorage.clear() },
    async setStay() {}, async setSync() {}, async changePassword() { return { error: 'Change it on your computer.' } }, async reset() { return false },
  },

  agent: {
    async active() { const r = await appel('active_brain'); return r },
    brains: () => appel('brains_list'), chooseBrain: (i) => appel('choose_brain', i), models: () => appel('models'),
    setModel: (m) => appel('set_model', m), efforts: () => appel('efforts'), setEffort: (e) => appel('set_effort', e), setMode: (m) => appel('set_mode', m),
    commands: () => appel('commands'),
    async send(t, imgs) { try { await appel('send', t, imgs && imgs.length ? imgs : null); return {} } catch (e) { return { error: e.message } } },
    stop: () => appel('interrupt').catch(() => {}), answer: (p, a) => appel('permission_answer', p, a), answerQuestion: (p, a) => appel('question_answer', p, a),
    newChat: () => appel('new_conversation').catch(() => null), history: () => appel('current_events'), continueFrom: (s) => appel('continue_from', s).catch((e) => ({ error: e.message })),
  },

  convs: {
    // from the computer when it is on, otherwise from your sealed memory (read-only)
    async list() { try { return await appel('conversations_list') } catch {
      const idx = cache.get('index') || await lire('index'); if (!idx) throw new Error('not synced'); cache.set('index', idx)
      const names = { claude: 'Claude Agent', codex: 'Codex', deepseek: 'DeepSeek', nebius: 'Nebius', 'claude-api': 'Claude API', ollama: 'Ollama' }
      return { folders: idx.folders || [], conversations: Object.values(idx.conversations || {}).map((c) => ({ ...c, brain_name: names[c.brain] || c.brain, model_label: (c.model || '').split('/').pop(), terminal: !!c.terminal })).sort((a, b) => b.updated - a.updated) } } },
    async open(i) { try { return await appel('open_conversation', i) } catch { const r = await host.convs.read(i); return { ...r, brain: { name: 'your computer is off', label: 'read only', offline: true }, notes: ['Read only: your computer is off.'], title: '' } } },
    async read(i) { try { return await appel('read_conversation', i) } catch { const r = await lire('conv:' + i); return { events: (r && r.events) || [] } } },
    move: (i, f) => appel('move_conversation', i, f), remove: (i) => appel('delete_conversation', i), createFolder: (n) => appel('create_folder', n),
  },

  friends: {
    async identity() { const a = compte(); return { npub: a?.npub, id: me ? handle(a?.pseudo || '', me) : '' } },
    // someone's ID: only a card whose key matches the code counts (rootharness/directory.py)
    async lookup(text) {
      text = (text || '').trim()
      if (text.startsWith('npub1')) return hexDe(text) ? { npub: text, pseudo: '', id: '' } : { error: 'Check the key.' }
      const p = parse(text); if (!p) return { error: 'An ID looks like name#k7f2qa9m.' }
      const evs = await pool.querySync(RELAYS, { kinds: [30078], '#d': ['rh-handle:' + p[0] + '#' + p[1]] }, { maxWait: 7000 })
      for (const ev of evs.sort((a, b) => b.created_at - a.created_at)) {
        if (code(ev.pubkey) !== p[1] || !ev.content || !verifyEvent(ev)) continue
        try { const c = JSON.parse(ev.content); return { hex: ev.pubkey, npub: npubDe(ev.pubkey), pseudo: String(c.pseudo || p[0]).slice(0, 32), id: p[0] + '#' + p[1] } } catch {}
      }
      return { error: 'Nobody with this ID (or they are not findable).' }
    },
    async overview() {
      const chans = Object.entries(AMIS.channels).map(([id, ch]) => { const L = LOGS[id] || [], last = L[L.length - 1]
        return { id, name: ch.name || ch.members.map(nom).join(', '), members: ch.members.map((h) => ({ hex: h, name: nom(h), npub: npubDe(h), pseudo: AMIS.pseudos[h] || '' })),
          unread: ch.unread || 0, last: ch.last || 0, request: !!ch.request, preview: last ? `${nom(last.from)}: ${last.text}`.slice(0, 80) : '' } }).sort((a, b) => b.last - a.last)
      return { channels: chans, contacts: Object.entries(AMIS.contacts).map(([hex, c]) => ({ hex, name: c.name, npub: npubDe(hex) })) }
    },
    async messages(cid) { if (AMIS.channels[cid]) { AMIS.channels[cid].unread = 0; garderAmis() } return (LOGS[cid] || []).map(vue) },
    async send(cid, text) { const r = await envoyerCanal(cid, text); if (!r) return null; const m = { rid: r.r, from: me, text, at: now() }; ajouterMessage(cid, m); garderAmis(); return r.ok ? vue(m) : null },
    async share(cid, s) {
      const payload = { rh: 'share', title: (s.title || '').slice(0, 120), agent: (s.agent || '').slice(0, 60), events: (s.events || []).filter((e) => e.type === 'user' || e.type === 'text').map((e) => ({ type: e.type, text: (e.text || '').slice(0, 6000) })) }
      while (JSON.stringify(payload).length > 40000 && payload.events.length) payload.events.shift()
      const r = await envoyerCanal(cid, JSON.stringify(payload), [['rh-share', '1']]); if (!r) return null
      ajouterMessage(cid, { rid: r.r, from: me, text: 'shared: ' + payload.title, share: payload, at: now() }); garderAmis(); return r.ok
    },
    async addContact(npub, name) { const h = hexDe(npub); if (!h || !name.trim() || h === me) return null; await annoncer({ op: 'contact_add', hex: h, name: name.trim().slice(0, 40) }); return { hex: h } },
    async createGroup(name, members) { members = members.filter((m) => AMIS.contacts[m]); if (!members.length) return null
      await annoncer({ op: 'group_create', name: name.trim().slice(0, 60), members: members.sort() }); return canalId(new Set([...members, me])) },
  },

  // the encyclopedia: from the computer when it is on, otherwise the base + your synced words
  glossary: {
    async list() { try { return await appel('glossary_list') } catch {
      const g = cache.get('glossary') || { terms: {}, hidden: [], auto: false }, id = (t) => t.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
      const items = Object.fromEntries(BASE.map((b) => [id(b.term), { ...b, source: 'base', added: 0 }])); Object.assign(items, g.terms); (g.hidden || []).forEach((h) => delete items[h])
      return { auto: g.auto, terms: Object.entries(items).map(([k, v]) => ({ id: k, ...v })).sort((a, b) => a.term.localeCompare(b.term)) } } },
    setAuto: (o) => appel('glossary_set_auto', o), add: (t, d, c) => appel('glossary_add', t, d, c), remove: (i) => appel('glossary_remove', i),
    ask: (i, q, h) => appel('glossary_ask', i, q, h).catch((e) => ({ error: e.message })),
  },
  // the network: your agent on the computer writes the post
  social: { draft: (h) => appel('post_draft', h || '') },
  vibe: {
    async status() {
      let r; try { r = await runner() } catch (e) { return { ready: false, why: e.message } }
      try { await gh(`/repos/${r}/contents/.github/workflows/root-harness-vibe.yml`) } catch { return { ready: false, why: 'Create your workshop from your computer: Settings, Vibe code.' } }
      return { ready: true, runner: r }
    },
    async projects() { const r = await runner(); return (await gh(`/repos/${r}/issues?labels=root-harness-vibe&state=all&sort=updated&per_page=50`)).map((i) => {
      const first = (i.body || '').split('\n')[0]; return { number: i.number, title: i.title, repo: first.includes(':') ? first.split(':').slice(1).join(':').trim() : '?', state: i.state, updated: Date.parse(i.updated_at) } }) },
    async repos() { const L = await gh('/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator'); return L.filter((x) => x.permissions?.push && !x.full_name.endsWith('/root-harness-runner')).map((x) => x.full_name) },
    async thread(n) {
      const r = await runner(), it = await gh(`/repos/${r}/issues/${n}`), cs = await gh(`/repos/${r}/issues/${n}/comments?per_page=100`), moi = it.user.login
      const msgs = [{ id: 'i' + n, bot: false, text: (it.body || '').split('\n').slice(1).join('\n').trim(), updated: it.updated_at }]
      let working = false
      for (const c of cs) { const bot = c.user.login !== moi; msgs.push({ id: String(c.id), bot, text: nettoyer(c.body), updated: c.updated_at }); if (bot) working = (c.body || '').includes('<!-- rh:working -->') }
      if (cs.length && cs[cs.length - 1].user.login === moi) working = true
      return { messages: msgs, working }
    },
    async send(repo, text, n) {
      try { const r = await runner()
        if (!n) { const first = repo.startsWith('new:') ? 'new: ' + repo.slice(4) : 'repo: ' + repo
          const it = await gh(`/repos/${r}/issues`, { method: 'POST', body: JSON.stringify({ title: text.replace(/\s+/g, ' ').slice(0, 70), body: `${first}\n\n${text}`, labels: ['root-harness-vibe'] }) }); return { number: it.number } }
        await gh(`/repos/${r}/issues/${n}/comments`, { method: 'POST', body: JSON.stringify({ body: text }) }); return { number: n }
      } catch (e) { return { error: e.message } }
    },
  },
}

// -- notifications: your computer pushes them when your agent needs you (push.py) --------
const b64u = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - s.length % 4) % 4)), (c) => c.charCodeAt(0))
const appareil = () => /iPhone/.test(navigator.userAgent) ? 'iPhone' : /iPad/.test(navigator.userAgent) ? 'iPad' : /Android/.test(navigator.userAgent) ? 'Android' : 'phone'
const SW = window.isSecureContext && 'serviceWorker' in navigator ? navigator.serviceWorker.register('sw.js').catch(() => null) : Promise.resolve(null)
async function notifEtat() {
  if (!window.isSecureContext) return { why: 'Notifications need root-harness opened over https (its online address or your private link). Here it is opened over plain http on your Wi-Fi.' }
  if (/iPhone|iPad/.test(navigator.userAgent) && !navigator.standalone) return { why: 'On iPhone, add root-harness to your Home Screen first (Share, Add to Home Screen), then open it from there.' }
  const reg = await SW
  if (!reg || !('PushManager' in window) || !('Notification' in window)) return { why: 'This browser cannot receive notifications.' }
  if (Notification.permission === 'denied') return { why: 'Notifications are blocked for root-harness in this phone\'s settings.' }
  return { ok: true, on: Notification.permission === 'granted' && !!(await reg.pushManager.getSubscription()) }
}
async function notifActiver(on) {
  const reg = await SW, old = await reg.pushManager.getSubscription()
  if (!on) { if (old) await old.unsubscribe(); return }          // your computer forgets it at the next send
  if (await Notification.requestPermission() !== 'granted') throw new Error('Notifications were not allowed.')
  const key = b64u(await appel('push_key'))
  if (old) await old.unsubscribe()
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
  if (!await appel('push_register', sub.toJSON(), appareil())) throw new Error('Your computer did not accept this phone.')
}
host.reglagesEnPlus = async function plus(el, outils) {
  const st = await notifEtat()
  el.innerHTML = `<div class="section">this phone<span class="ligne"></span></div><div class="verre carte">
    <div class="reglage" style="border:0"><div class="l">Notifications<div class="d">${outils.esc(st.ok ? 'When your agent needs you or finishes a long task. Your conversation never shows on the lock screen.' : st.why)}</div></div>${st.ok ? `<span class="inter${st.on ? ' on' : ''}" id="r-notif"></span>` : ''}</div></div>`
  const t = el.querySelector('#r-notif')
  if (t) t.onclick = async () => {
    t.style.opacity = .5
    try { await notifActiver(!st.on); outils.toast(st.on ? 'Notifications off on this phone.' : 'Notifications on. Your computer will tell you.') } catch (e) { outils.toast(e.message) }
    plus(el, outils)
  }
}

// -- the network, signed right here on the phone (social-net.js) -----------------------------
let NET = null
const netStore = { get: (k, d) => { const v = cache.get(k); return v === undefined || v === null ? d : v }, set: (k, v) => cache.set(k, v) }
function net() {
  if (!sk) throw new Error('Locked.')
  if (!NET || NET.me !== me) NET = reseau({ pool, relays: RELAYS, sk, me, pseudo: (compte() || {}).pseudo || '', store: netStore })
  return NET
}
host.network = {
  profile: (h) => (h ? net().profilDe(h) : Promise.resolve(net().profilLocal())), update: (f) => net().majProfil(f),
  workSuggest: async () => [], activity: async () => ({ level: net().profilLocal().level, days: 0 }),
  post: (t, o = {}) => net().poster(t, { media: o.media || [], community: o.community || '', agent: o.agent || '', replyTo: o.replyTo || null }),
  repost: (p) => net().republier(p), unrepost: (id) => net().derepublier(id), react: (id, a, on) => net().reagir(id, a, on), remove: (id) => net().supprimer(id),
  async feed(s, o = {}) {
    let friends = Object.keys(AMIS.contacts || {})
    if (s === 'friends' || s === 'for-you') friends = [...new Set([...friends, ...(await net().suivis().catch(() => []))])]   // your friends and the people you follow
    return net().fil(s, { community: o.community || '', friends, days: o.days || 7, limit: o.limit || 60 })
  },
  thread: (id) => net().thread(id), wall: (h) => net().mur(h || me),
  async lookup(t) { if (/^@/.test(t.trim())) { const o = await net().proprioAt(t); return o ? net().profilDe(o) : null }
    const h = hexDe(t); if (h) return net().profilDe(h); const r = await host.friends.lookup(t); return r && r.hex ? net().profilDe(r.hex) : null },
  upload: (file) => net().envoyerMedia(file),
  follow: (h, on) => net().suivre(h, on), people: (L) => net().gens(L), claimAt: (n) => net().reserverAt(n),
  block: (h, on) => net().bloquer(h, on), blocked: () => net().bloques(), report: (id, a, r) => net().signaler(id, a, r),
  notifications: () => net().notifications(), notificationsSeen: async () => net().notifsVues(), notificationsNew: () => net().notifsNouvelles(),
  posting: (s, a) => appel('settings_posting', s === undefined ? null : s, a === undefined ? null : a),
  badges: (h) => net().badgesDe(h || me), pin: (c) => net().epingler(c), defineBadge: (i, n, d, img) => net().badgeDefinir(i, n, d, img || ''), award: (a, r) => net().badgeDonner(a, r), checkBadges: () => net().verifierBadges(),
  communities: () => net().communautes(), createCommunity: (n, d) => net().creerCommunaute(n, d || ''), join: async (s, on) => net().rejoindre(s, on),
}

// unlocked: listen, load the memory, say hello to the computer
async function ouvert(key) {
  sk = key; me = getPublicKey(sk)
  etiquette = sha256(new Uint8Array([...utf8ToBytes('root-harness/sync/labels/v1'), ...sk]))
  AMIS = cache.get('amis') || AMIS; LOGS = cache.get('logs') || {}
  pool.subscribe(RELAYS, { kinds: [1059], '#p': [me], since: now() - 3 * 86400 - 300 }, { onevent: recevoir })
  ordre('hello').catch(() => {})
  memoire()                                          // in the background
}
async function memoire() {
  try {
    MANIFESTE = null
    const [ch, keys, bg, gl] = await Promise.all([lire('channels'), lire('keys'), cache.get('background') ? null : lire('background'), lire('glossary').catch(() => null)])
    if (gl) cache.set('glossary', gl)
    if (ch) { for (const k of ['contacts', 'pseudos']) AMIS[k] = { ...(ch[k] || {}), ...AMIS[k] }
      for (const [id, c] of Object.entries(ch.channels || {})) AMIS.channels[id] = { ...c, ...(AMIS.channels[id] || {}), unread: AMIS.channels[id]?.unread || 0 }
      await Promise.all(Object.keys(ch.channels || {}).map(async (id) => { const L = await lire('chan:' + id).catch(() => null); (L || []).forEach((m) => ajouterMessage(id, m)) }))
      garderAmis() }
    if (keys) { cache.set('keys', keys); GH = null }
    if (bg) cache.set('background', bg)
    ecoute({ type: 'synced', changed: true })
  } catch {}
}

lancer(host)
