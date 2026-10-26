// The computer's host: the interface talks to root-harness in Python
// (window.pywebview.api), which runs the agents, keeps the memory and syncs it.
import { lancer, aller } from './app.js'

const api = () => window.pywebview.api

const host = {
  kind: 'computer',
  on(fn) { window.onEvent = fn },
  async background() { const s = await api().settings_get(); return s.image ? s.image + '?t=' + Date.now() : '' },
  chooseBackground: () => api().choose_background(),
  plainBackground: () => api().set_background('vert'),
  copy: (t) => api().copy_text(t),
  account: {
    state: () => api().account_state(), create: (p, a, b) => api().account_create(p, a, b), restore: (p, a) => api().account_restore(p, a),
    unlock: (a) => api().account_unlock(a), lock: () => api().account_lock(), setStay: (o) => api().account_set_stay(o),
    setSync: (o) => api().account_set_sync(o), changePassword: (a, b, c) => api().account_change_password(a, b, c),
    reset: (c) => api().account_reset(c), signOut: async () => true,
    recoveryWords: (p) => api().account_recovery_words(p), setFindable: (o) => api().account_set_findable(o), restoreWords: (w, p, a, b) => api().account_restore_words(w, p, a, b),
  },
  // sign-up: what is already here, the keys you add, the extras you turn on
  setup: {
    detect: () => api().setup_detect(), key: (n, v) => api().setup_key(n, v),
    phone: (on) => api().remote_set(on), githubPhone: (on) => api().vibe_phone_token(on), workshop: () => api().vibe_create(),
  },
  agent: {
    active: () => api().active_brain(), brains: () => api().brains_list(), chooseBrain: (i) => api().choose_brain(i),
    models: () => api().models(), setModel: (m) => api().set_model(m), efforts: () => api().efforts(), setEffort: (e) => api().set_effort(e),
    setMode: (m) => api().set_mode(m), commands: () => api().commands(), send: (t, i) => api().send(t, i), stop: () => api().interrupt(),
    answer: (p, a) => api().permission_answer(p, a), answerQuestion: (p, a) => api().question_answer(p, a),
    newChat: () => api().new_conversation(), history: () => api().current_events(), continueFrom: (s) => api().continue_from(s),
  },
  convs: {
    list: () => api().conversations_list(), open: (i) => api().open_conversation(i), read: (i) => api().read_conversation(i),
    move: (i, f) => api().move_conversation(i, f), remove: (i) => api().delete_conversation(i), createFolder: (n) => api().create_folder(n),
  },
  friends: {
    identity: async () => ({ ...(await api().channels_start()), id: (await api().account_state()).id }), lookup: (t) => api().friend_lookup(t), overview: () => api().channels_overview(), messages: (c) => api().channel_messages(c),
    send: (c, t) => api().channel_send(c, t), share: (c, p) => api().channel_share(c, p),
    addContact: (n, m) => api().channel_add_contact(n, m), createGroup: (n, m) => api().channel_create(n, m),
  },
  vibe: {
    status: () => api().vibe_status(), projects: () => api().vibe_projects(), repos: () => api().vibe_repos(),
    thread: (n) => api().vibe_thread(n), send: (r, t, n) => api().vibe_send(r, t, n || 0),
  },

  // what only the computer can set: your phone, and the vibe-code workshop
  async reglagesEnPlus(el, { feuille, fermerFeuille, toast, esc }) {
    const r = await api().remote_state(), v = await api().vibe_status(), t = await api().vibe_phone_token_state()
    el.innerHTML = `<div class="section">your phone<span class="ligne"></span></div><div class="verre carte">
      <div class="reglage"><div class="l">Use from my phone<div class="d">Your phone becomes this computer's remote, through sealed messages</div></div><span class="inter${r.on ? ' on' : ''}" id="r-tel"></span></div>
      ${r.on ? `<div class="reglage"><div class="l">On your phone (same Wi-Fi), open in Safari<div class="d" style="font-family:var(--mono)">${esc((r.url || '').replace('https://', 'http://'))}</div><div class="d">then Share, Add to Home Screen. Type http:// in full.</div></div></div>` : ''}
      <div class="reglage"><div class="l">GitHub on my phone<div class="d">Vibe code from the phone with your GitHub sign-in, kept in your sealed memory</div></div><span class="inter${t.on ? ' on' : ''}" id="r-ghtel"></span></div></div>
      <div class="section">vibe code<span class="ligne"></span></div><div class="verre carte" id="r-vibe">${vibeEtat(v, esc)}</div>`
    el.querySelector('#r-tel').onclick = async () => { await api().remote_set(!r.on); host.reglagesEnPlus(el, { feuille, fermerFeuille, toast, esc }) }
    el.querySelector('#r-ghtel').onclick = async () => { const x = await api().vibe_phone_token(!t.on); if (x && x.error) toast(x.error); host.reglagesEnPlus(el, { feuille, fermerFeuille, toast, esc }) }
    const c = el.querySelector('#r-creer'); if (c) c.onclick = async () => { c.textContent = 'Creating...'; const x = await api().vibe_create(); if (x.error) toast(x.error); host.reglagesEnPlus(el, { feuille, fermerFeuille, toast, esc }) }
    const re = el.querySelector('#r-revoir'); if (re) re.onclick = () => host.reglagesEnPlus(el, { feuille, fermerFeuille, toast, esc })
    const go = el.querySelector('#r-go'); if (go) go.onclick = () => aller('vibe')
  },
}

function vibeEtat(v, esc) {
  if (v.ready) return `<div class="reglage"><div class="l">Ready<div class="d">Your workshop: ${esc(v.runner)}. Claude can work in any of your repositories.</div></div></div><div class="boutons"><button class="bouton vert" id="r-go">Vibe code</button></div>`
  if (v.step === 'create') return `<div class="reglage"><div class="l">${esc(v.why)}<div class="d">A private repository, ${esc(v.runner)}, where your ideas wait for Claude.</div></div></div><div class="boutons"><button class="bouton vert" id="r-creer">Create my workshop</button></div>`
  if (v.step === 'secrets') return `<div class="l">${esc(v.why)} In a terminal (root-harness never sees them):</div>
    ${v.missing.map((m) => `<pre class="code">${esc(v.commands[m])}</pre>`).join('')}<div class="boutons"><button class="bouton" id="r-revoir">Check again</button></div>`
  return `<div class="l">${esc(v.why || v.error || 'Unavailable')}</div><div class="boutons"><button class="bouton" id="r-revoir">Check again</button></div>`
}

window.addEventListener('pywebviewready', () => lancer(host))
