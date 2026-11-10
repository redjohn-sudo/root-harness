// Group projects: you and your friends put your agents to work on one project.
// A lead plans and gives each task to a member's agent; each task runs on the
// computer of the one who accepts it; this view follows everything.
// Every send is a click: an agent never sends in a group by itself.
import { esc, riche, feuille, fermerFeuille, toast } from './app.js'

const $ = (s, r = document) => r.querySelector(s)
const $$ = (s, r = document) => [...r.querySelectorAll(s)]
const ETAT = { proposed: 'waiting for a yes', accepted: 'in progress', done: 'done', failed: 'not finished', refused: 'refused' }
let DONNEES = null, OUVERT = null, BROUILLONS = {}

const nom = (h) => (DONNEES && DONNEES.names && DONNEES.names[h]) || 'friend'
const erreur = (r) => r && r.error ? (toast(r.error), true) : false

async function charger(H) {
  DONNEES = await H.projects.list().catch((e) => ({ error: e.message || String(e), projects: [], mine: [] }))
  return DONNEES
}

export async function vueProjets(H) {
  const v = $('#v-projets')
  if (!H.projects) {
    v.innerHTML = `<div class="defile"><div class="colonne"><div class="titre">projects</div>
      <div class="vide">Projects run from your computer: open root-harness there to start one, give tasks and run yours.</div></div></div>`
    return
  }
  v.innerHTML = `<div class="defile"><div class="colonne"><div class="titre">projects</div>
    <div class="sous-titre">You and your friends put your agents to work on one project. Each task runs on the computer of the one who accepts it.</div>
    <div class="boutons" style="margin:0 0 6px"><button class="bouton plein" id="pj-nouveau">New project</button></div>
    <div id="pj-corps"><div class="vide">Loading...</div></div></div></div>`
  $('#pj-nouveau').onclick = () => nouveauProjet(H)
  const d = await charger(H)
  if (d.error) { $('#pj-corps').innerHTML = `<div class="vide">${esc(d.error)}</div>`; return }
  const attente = d.mine.map((t, i) => `<div class="item pj-t" data-c="${esc(t.channel)}" data-p="${esc(t.project)}" data-t="${esc(t.id)}" style="--i:${i}">
      <div class="tx"><div class="t">${esc(t.title)}</div><div class="m">${esc(t.project_title)} · ${esc(ETAT[t.status] || t.status)}</div></div>
      <span class="badge pj-${esc(t.status)}">${t.status === 'proposed' ? 'answer' : 'run'}</span></div>`).join('')
  const liste = d.projects.map((p, i) => `<div class="item pj-p" data-c="${esc(p.channel)}" data-p="${esc(p.id)}" style="--i:${i}">
      <div class="tx"><div class="t">${esc(p.title)}</div>
        <div class="m">${esc(p.group || 'group')} · led by ${esc(p.i_lead ? 'you' : nom(p.lead.member))} · ${p.status === 'closed' ? 'closed' : p.progress.percent + '%'}</div>
        <div class="barre on"><i style="width:${Number(p.progress.percent) || 0}%"></i></div></div></div>`).join('')
  $('#pj-corps').innerHTML = (attente ? `<div class="section">waiting for you<span class="ligne"></span></div><div class="liste">${attente}</div>` : '')
    + `<div class="section">projects<span class="ligne"></span></div><div class="liste">${liste || '<div class="vide">No project yet. Start one in a group of friends.</div>'}</div>`
  $$('#pj-corps .pj-t').forEach((el) => el.onclick = () => maTache(H, el.dataset.c, el.dataset.p, el.dataset.t))
  $$('#pj-corps .pj-p').forEach((el) => el.onclick = () => unProjet(H, el.dataset.c, el.dataset.p))
  pastille(d.mine.some((t) => t.status === 'proposed'))
}

function pastille(on) {
  const b = $('.onglet[data-v="projets"]'); if (!b) return
  let p = $('.pastille', b)
  if (on && !p) { p = document.createElement('span'); p.className = 'pastille'; b.appendChild(p) } else if (!on && p) p.remove()
}

// -- a new project: a group, a title, a goal, who leads ---------------------------------
async function nouveauProjet(H) {
  const ov = await H.friends.overview().catch(() => ({ channels: [] }))
  const groupes = ov.channels.filter((c) => !c.request)
  if (!groupes.length) return toast('Start a conversation with friends first, in Messages.')
  const f = feuille(`<h3>new project</h3><div class="sous-titre">In a group of friends. Its lead plans the tasks; everyone runs theirs on their own computer.</div>
    <select class="champ" id="pjn-g">${groupes.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}</select>
    <input class="champ" id="pjn-t" placeholder="Project title" maxlength="120" spellcheck="false">
    <textarea class="champ" id="pjn-b" rows="3" placeholder="The goal, in a few lines" maxlength="2000"></textarea>
    <div class="section">who leads<span class="ligne"></span></div><select class="champ" id="pjn-l"></select>
    <div class="err" id="pjn-err"></div><div class="boutons"><button class="bouton plein" id="pjn-ok">Start the project</button></div>`)
  const leads = () => { const c = groupes.find((x) => x.id === $('#pjn-g', f).value) || groupes[0]
    $('#pjn-l', f).innerHTML = `<option value="">me</option>` + (c.members || []).map((m) => `<option value="${esc(m.hex)}">${esc(m.name || m.pseudo || 'friend')}</option>`).join('') }
  leads(); $('#pjn-g', f).onchange = leads
  $('#pjn-t', f).focus()
  $('#pjn-ok', f).onclick = async () => {
    const t = $('#pjn-t', f).value.trim(); if (!t) return ($('#pjn-err', f).textContent = 'A project needs a title.')
    const b = $('#pjn-ok', f); b.disabled = true
    const r = await H.projects.create($('#pjn-g', f).value, t, $('#pjn-b', f).value.trim(), $('#pjn-l', f).value).catch((e) => ({ error: e.message }))
    b.disabled = false
    if (r && r.error) return ($('#pjn-err', f).textContent = r.error)
    fermerFeuille(); toast('Project started. Ask everyone to share their agents.'); vueProjets(H)
  }
}

// -- one project: goal, tasks, the follow-up, and what you can do -----------------------
async function unProjet(H, cid, pid) {
  OUVERT = { cid, pid }
  const d = DONNEES || await charger(H)
  const p = d.projects.find((x) => x.channel === cid && x.id === pid); if (!p) return
  const moi = d.me, lead = p.i_lead, ouvert = p.status === 'open'
  const taches = Object.values(p.tasks)
  const f = feuille(`<h3>${esc(p.title)}</h3><div class="sous-titre">${esc(p.group || 'group')} · led by ${esc(lead ? 'you' : nom(p.lead.member))} · ${p.status === 'closed' ? 'closed' : p.progress.percent + '% done'}</div>
    ${p.goal ? `<div class="corps pj-but">${riche(p.goal)}</div>` : ''}
    <div class="section">agents<span class="ligne"></span></div>
    <div class="m pj-agents">${p.members.map((m) => `${esc(m === moi ? 'you' : nom(m))}: ${esc(((p.rosters || {})[m] || []).map((a) => a.name).join(', ') || 'not shared yet')}`).join('<br>')}</div>
    <div class="section">tasks<span class="ligne"></span></div>
    <div class="liste">${taches.map((t) => `<div class="item"><div class="tx"><div class="t">${esc(t.title)}</div>
      <div class="m">${esc(t.member === moi ? 'you' : nom(t.member))}${t.agent ? ' · ' + esc(t.agent) : ''} · ${esc(ETAT[t.status] || t.status)}</div></div></div>`).join('') || '<div class="vide">No task yet.</div>'}</div>
    ${p.synthesis ? `<div class="section">synthesis<span class="ligne"></span></div><div class="corps">${riche(p.synthesis)}</div>` : ''}
    <div class="section">follow-up<span class="ligne"></span></div>
    <div class="pj-journal">${p.journal.slice().reverse().map((e) => `<div class="m"><b>${esc(e.who === moi ? 'you' : nom(e.who))}</b> ${esc(e.what)}${e.text ? ': ' + esc(String(e.text).slice(0, 140)) : ''}</div>`).join('')}</div>
    <div class="boutons">${ouvert ? `<button class="bouton" id="pj-agents">Share my agents</button>` : ''}
      ${ouvert && lead ? `<button class="bouton plein" id="pj-plan">Plan with my agent</button><button class="bouton" id="pj-fin">Close</button>` : ''}
      ${!lead ? `<button class="bouton" id="pj-contre">Disagree</button>` : ''}</div>`)
  const b = (id, fn) => { const x = $(id, f); if (x) x.onclick = fn }
  b('#pj-agents', async () => { const r = await H.projects.shareAgents(cid, pid).catch((e) => ({ error: e.message })); if (!erreur(r)) toast('Sharing your agents with the group...') })
  b('#pj-plan', () => plan(H, cid, pid))
  b('#pj-fin', () => ecrire(H, 'close the project', 'The synthesis: what was done, what is left.', (x) => H.projects.close(cid, pid, x)))
  b('#pj-contre', () => ecrire(H, 'disagree', 'Say why, in one line. It does not block anything.', (x) => H.projects.dissent(cid, pid, x)))
}

// the lead's agent drafts the split and who does what; you review, then send it
async function plan(H, cid, pid) {
  const f = feuille(`<h3>plan the project</h3><div class="sous-titre">Your agent proposes the tasks and who does what, from the agents each one shared. Nothing is sent before you click.</div>
    <input class="champ" id="pjp-h" placeholder="A hint for your agent (optional)" spellcheck="false">
    <div class="boutons"><button class="bouton plein" id="pjp-go">Propose a plan</button></div><div id="pjp-liste"></div>`)
  $('#pjp-go', f).onclick = async () => {
    const go = $('#pjp-go', f); go.disabled = true; go.textContent = 'Your agent is thinking...'
    const r = await H.projects.draft(cid, pid, $('#pjp-h', f).value.trim()).catch((e) => ({ error: e.message }))
    go.disabled = false; go.textContent = 'Propose again'
    if (erreur(r)) return
    BROUILLONS[pid] = r.tasks
    $('#pjp-liste', f).innerHTML = `<div class="section">the plan<span class="ligne"></span></div><div class="liste">${r.tasks.map((t, i) => `<div class="item"><div class="tx">
        <input class="champ" data-i="${i}" value="${esc(t.title)}" maxlength="120" style="margin:0 0 4px">
        <div class="m">${esc(nom(t.member))}${t.member === (DONNEES || {}).me ? ' (you)' : ''} · ${esc(t.agent)}</div></div></div>`).join('')}</div>
      <div class="boutons"><button class="bouton plein" id="pjp-send">Send the plan to the group</button></div>`
    $$('#pjp-liste input[data-i]', f).forEach((x) => x.oninput = () => { BROUILLONS[pid][+x.dataset.i].title = x.value })
    $('#pjp-send', f).onclick = async () => {
      const s = await H.projects.sendPlan(cid, pid, BROUILLONS[pid]).catch((e) => ({ error: e.message }))
      if (erreur(s)) return
      fermerFeuille(); toast('Plan sent. Each one answers from their computer.'); rafraichir(H)
    }
  }
}

// a task given to you: say yes or no, then run it here, then send the report (or not)
async function maTache(H, cid, pid, tid) {
  const d = DONNEES || await charger(H)
  const t = d.mine.find((x) => x.channel === cid && x.project === pid && x.id === tid); if (!t) return
  const f = feuille(`<h3>${esc(t.title)}</h3><div class="sous-titre">${esc(t.project_title)} · for ${esc(t.agent || 'your agent')} · ${esc(ETAT[t.status] || t.status)}</div>
    ${t.detail ? `<div class="corps">${riche(t.detail)}</div>` : ''}
    <div class="d" style="color:var(--encre-3);font-size:12.5px;margin-top:8px">It runs on this computer, in its own conversation, and asks you before anything risky. The report comes back to you before anything is sent.</div>
    <div id="pjt-live" class="m" style="margin-top:10px"></div>
    <div class="boutons">${t.status === 'proposed' ? '<button class="bouton plein" id="pjt-oui">Accept</button><button class="bouton" id="pjt-non">Refuse</button>'
      : '<button class="bouton plein" id="pjt-run">Run it with my agent</button>'}</div>`)
  const b = (id, fn) => { const x = $(id, f); if (x) x.onclick = fn }
  b('#pjt-oui', async () => { const r = await H.projects.answer(cid, pid, tid, true).catch((e) => ({ error: e.message })); if (!erreur(r)) { fermerFeuille(); toast('Accepted.'); rafraichir(H) } })
  b('#pjt-non', () => ecrire(H, 'refuse the task', 'A word for the lead (optional).', (x) => H.projects.answer(cid, pid, tid, false, x), true))
  b('#pjt-run', async () => {
    const r = await H.projects.run(cid, pid, tid).catch((e) => ({ error: e.message })); if (erreur(r)) return
    $('#pjt-run', f).disabled = true; $('#pjt-live', f).textContent = 'Your agent is working on it...'
  })
}

function rapport(H, e) {
  const t = (DONNEES ? DONNEES.mine : []).find((x) => x.channel === e.channel && x.project === e.project && x.id === e.task) || {}
  if (e.error) return toast('The task stopped: ' + e.error)
  const f = feuille(`<h3>your agent's report</h3><div class="sous-titre">${esc(t.title || 'task')}. Read it, change it if you like, then send it to the group, or not.</div>
    <textarea class="champ" id="pjr-x" rows="8" maxlength="8000">${esc(e.text || '')}</textarea>
    <div class="boutons"><button class="bouton plein" id="pjr-ok">Send the result</button><button class="bouton" id="pjr-ko">It did not work</button><button class="bouton" id="pjr-plus-tard">Not now</button></div>`)
  const envoyer = async (ok) => { const r = await H.projects.sendResult(e.channel, e.project, e.task, $('#pjr-x', f).value, ok).catch((er) => ({ error: er.message }))
    if (!erreur(r)) { fermerFeuille(); toast('Result sent to the group.'); rafraichir(H) } }
  $('#pjr-ok', f).onclick = () => envoyer(true)
  $('#pjr-ko', f).onclick = () => envoyer(false)
  $('#pjr-plus-tard', f).onclick = fermerFeuille
}

function ecrire(H, titre, aide, faire, optionnel = false) {
  const f = feuille(`<h3>${esc(titre)}</h3><div class="sous-titre">${esc(aide)}</div>
    <textarea class="champ" id="pje-x" rows="4" maxlength="4000"></textarea><div class="boutons"><button class="bouton plein" id="pje-ok">Send</button></div>`)
  $('#pje-x', f).focus()
  $('#pje-ok', f).onclick = async () => {
    const x = $('#pje-x', f).value.trim(); if (!x && !optionnel) return
    const r = await faire(x).catch((e) => ({ error: e.message }))
    if (!erreur(r)) { fermerFeuille(); toast('Sent.'); rafraichir(H) }
  }
}

async function rafraichir(H) {
  await charger(H)
  if ($('#v-projets.on')) vueProjets(H)
}

// events from the computer: a friend's message changed a project, your task moved on, or ended
export function evenementProjet(H, e) {
  if (e.type === 'projects_changed') return rafraichir(H).then(() => pastille((DONNEES ? DONNEES.mine : []).some((t) => t.status === 'proposed')))
  if (e.type === 'project_event') {
    const live = $('#pjt-live'); if (live && e.event && e.event.type === 'text' && e.event.text) live.textContent = String(e.event.text).slice(0, 200)
    return
  }
  if (e.type === 'project_task_done') rapport(H, e)
  if (e.type === 'project_send_failed') toast(e.text || 'Not sent yet.')
}
