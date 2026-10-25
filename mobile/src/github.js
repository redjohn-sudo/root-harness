// Claude on GitHub, from the phone: vibe coding with no computer on.
// Each conversation is an issue labelled "root-harness" in your repository;
// your messages are comments starting with "@claude", and the workflow
// installed by root-harness runs Claude Code on GitHub's machines with your
// plan. Claude answers in a progress comment it keeps editing, and links the
// branch it worked on. The GitHub token stays on this phone, sealed with your
// identity (it opens only once you have typed your password).
const API = 'https://api.github.com'
const STORE = 'rh-github'
const WORKFLOW = '.github/workflows/root-harness-claude.yml'
const LABEL = 'root-harness'
const TOKEN_PAGE = 'https://github.com/settings/personal-access-tokens/new'

export function makeGitHub({ $, ajouter, riche, esc, etat, seal, open }) {
  let cfg = null, issue = null, timer = null, shown = new Map(), calm = 0

  function load() {
    try { cfg = JSON.parse(open(localStorage.getItem(STORE))) } catch { cfg = null }
    return cfg
  }
  function save() { localStorage.setItem(STORE, seal(JSON.stringify(cfg))) }

  async function gh(path, opts = {}) {
    const r = await fetch(API + path, { ...opts, headers: {
      Authorization: 'Bearer ' + cfg.token, Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28', ...(opts.body ? { 'Content-Type': 'application/json' } : {}) } })
    if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()).slice(0, 120)}`)
    return r.status === 204 ? null : r.json()
  }

  // -- setting up: a token, then a repository -----------------------------------

  function setupToken(err) {
    stop(); $('#fil').innerHTML = ''
    $('#modele').textContent = 'Claude on GitHub'; $('#contexte').textContent = ''
    const n = ajouter(`<div class="carte-a gh"><div class="q"><b>Claude on GitHub</b></div>
      <p class="aide">Claude Code works in your repository on GitHub's machines, with your plan. Your computer can stay off.</p>
      <p class="aide">1. On your computer, in root-harness: Settings, Claude on GitHub, get a repository ready.<br>
      2. Here, paste a GitHub token: <a href="${TOKEN_PAGE}" target="_blank">create one</a> (fine-grained), for that repository, with <b>Issues: read and write</b>, <b>Contents: read</b>, <b>Actions: read</b>.</p>
      <input id="gh-token" type="password" placeholder="github_pat_..." autocomplete="off">
      <div class="err">${esc(err || '')}</div><div class="row"><button class="oui" id="gh-ok">Continue</button></div></div>`)
    n.querySelector('#gh-ok').onclick = async () => {
      const token = n.querySelector('#gh-token').value.trim(); if (!token) return
      cfg = { token, repo: '' }
      try { await gh('/user'); save(); chooseRepo() } catch (e) { cfg = null; setupToken('This token does not work: ' + e.message) }
    }
  }

  async function chooseRepo(err) {
    stop(); $('#fil').innerHTML = ''; etat('looking at your repositories...', 'travail')
    let repos = []
    try { repos = await gh('/user/repos?per_page=100&sort=updated') } catch (e) { return setupToken(e.message) }
    etat('choose a repository', 'attente')
    const n = ajouter(`<div class="carte-a gh"><div class="q">Which repository?</div><div class="err">${esc(err || '')}</div>
      ${repos.map((r) => `<button class="opt" data-r="${esc(r.full_name)}">${esc(r.full_name)}${r.private ? ' 🔒' : ''}</button>`).join('') || '<p class="aide">This token sees no repository.</p>'}
      <div class="row"><button class="non" id="gh-autre">Use another token</button></div></div>`)
    n.querySelectorAll('.opt').forEach((b) => b.onclick = async () => {
      const repo = b.dataset.r
      try { await gh(`/repos/${repo}/contents/${WORKFLOW}`) } catch {
        return chooseRepo(`${repo} is not ready: on your computer, root-harness, Settings, Claude on GitHub.`)
      }
      cfg.repo = repo; save(); list()
    })
    n.querySelector('#gh-autre').onclick = () => { localStorage.removeItem(STORE); cfg = null; setupToken() }
  }

  // -- conversations = issues ----------------------------------------------------

  async function list() {
    stop(); issue = null; $('#fil').innerHTML = ''
    $('#modele').textContent = cfg.repo; $('#contexte').textContent = ''
    etat('Claude on GitHub', 'ok')
    let issues = []
    try { issues = await gh(`/repos/${cfg.repo}/issues?labels=${LABEL}&state=all&sort=updated&per_page=30`) } catch (e) { return chooseRepo(e.message) }
    const n = ajouter(`<div class="carte-a gh"><div class="q">Vibe coding in <b>${esc(cfg.repo)}</b></div>
      <p class="aide">Write what you want below: Claude codes it on GitHub and gives you a branch to review.</p>
      ${issues.map((i) => `<button class="opt" data-n="${i.number}">${esc(i.title)}<small>#${i.number} · ${i.state} · ${new Date(i.updated_at).toLocaleString()}</small></button>`).join('')}
      <div class="row"><button class="non" id="gh-repo">Change repository</button></div></div>`)
    n.querySelectorAll('.opt').forEach((b) => b.onclick = () => openIssue(+b.dataset.n))
    n.querySelector('#gh-repo').onclick = () => chooseRepo()
  }

  async function openIssue(number) {
    stop(); issue = number; shown = new Map(); $('#fil').innerHTML = ''
    try {
      const it = await gh(`/repos/${cfg.repo}/issues/${number}`)
      $('#modele').textContent = `${cfg.repo} #${number}`
      bubble({ id: 'issue', user: it.user, body: it.body, updated_at: it.updated_at })
      await refresh(); poll()
    } catch (e) { etat(e.message, 'off') }
  }

  // -- talking -------------------------------------------------------------------

  async function send(text) {
    if (!issue) $('#fil').innerHTML = ''          // a new conversation: the list goes away
    ajouter(`<div class="msg toi">${esc(text)}</div>`)
    etat('sending to GitHub...', 'travail')
    try {
      if (!issue) {
        const it = await gh(`/repos/${cfg.repo}/issues`, { method: 'POST', body: JSON.stringify({
          title: text.replace(/\s+/g, ' ').slice(0, 70), body: '@claude ' + text, labels: [LABEL] }) })
        issue = it.number; shown.set('issue', it.updated_at)
        $('#modele').textContent = `${cfg.repo} #${issue}`
      } else {
        const c = await gh(`/repos/${cfg.repo}/issues/${issue}/comments`, { method: 'POST', body: JSON.stringify({ body: '@claude ' + text }) })
        shown.set(c.id, c.updated_at)
      }
      etat('Claude is starting on GitHub (about a minute)...', 'travail'); calm = 0; poll()
    } catch (e) { etat('Not sent: ' + e.message, 'off') }
  }

  function bubble(c) {
    const bot = c.user && (c.user.type === 'Bot' || /\[bot\]$/.test(c.user.login))
    const html = bot ? `<div class="msg root" data-c="${c.id}">${riche(clean(c.body))}</div>`
      : `<div class="msg toi" data-c="${c.id}">${esc((c.body || '').replace(/^\s*@claude\s*/i, ''))}</div>`
    const old = document.querySelector(`[data-c="${c.id}"]`)
    if (old) { const w = document.createElement('div'); w.innerHTML = html; old.replaceWith(w.firstElementChild) }
    else ajouter(html)
    shown.set(c.id, c.updated_at)
    return bot
  }

  // Claude edits one comment as it works: show new comments, update edited ones
  async function refresh() {
    const cs = await gh(`/repos/${cfg.repo}/issues/${issue}/comments?per_page=100`)
    let changed = false, working = false
    for (const c of cs) {
      if (shown.get(c.id) === c.updated_at) continue
      const bot = bubble(c); changed = true
      if (bot && /working|in progress|⏳|Claude Code is working/i.test(c.body) && !/finished|completed|error/i.test(c.body)) working = true
    }
    const last = cs[cs.length - 1]
    const botLast = last && last.user && (last.user.type === 'Bot' || /\[bot\]$/.test(last.user.login))
    if (botLast && /working|in progress/i.test(last.body) && !/finished|completed|error/i.test(last.body)) working = true
    etat(working ? 'Claude is working on GitHub...' : (botLast ? 'done: review the branch' : 'waiting for Claude...'), working || !botLast ? 'travail' : 'ok')
    return changed || working
  }

  function poll() {
    stop()
    timer = setInterval(async () => {
      try { if (!(await refresh())) calm++; else calm = 0 } catch { calm++ }
      if (calm > 100) stop()        // about ten minutes with nothing new
    }, 6000)
  }
  function stop() { if (timer) clearInterval(timer); timer = null }

  // GitHub comments carry some HTML (a spinner image, folded details): keep the words and links
  function clean(body) {
    return (body || '').replace(/<img[^>]*>/gi, '').replace(/<\/?(details|summary|sub|sup|br|p|div|span)[^>]*>/gi, '\n')
      .replace(/<[^>]+>/g, '').replace(/\n{3,}/g, '\n\n').trim()
  }

  return {
    enter() { if (!load()) return setupToken(); if (!cfg.repo) return chooseRepo(); issue ? openIssue(issue) : list() },
    leave: stop,
    send,
    fresh() { stop(); issue = null; if (cfg && cfg.repo) list() },
    ready: () => !!(cfg && cfg.repo),
  }
}
