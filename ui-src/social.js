// The network: your page, open to everyone, and the feed of what people build with
// their agents. Everything goes through the host's network (rootharness/network.py
// on the computer, social-net.js on the phone): public events signed with your key,
// kept by the relays. Nothing here is private. When the network cannot be reached
// (locked, offline), examples show what it looks like and nothing is sent.
import { tete } from './root.js'
import { esc, riche, feuille, fermerFeuille, toast, aller } from './app.js'

const $ = (s, r = document) => r.querySelector(s)
const $$ = (s, r = document) => [...r.querySelectorAll(s)]
const quand = (s) => { const d = Date.now() / 1000 - s
  return d < 60 ? 'now' : d < 3600 ? Math.floor(d / 60) + ' min' : d < 86400 ? Math.floor(d / 3600) + ' h' : d < 604800 ? Math.floor(d / 86400) + ' d' : new Date(s * 1000).toLocaleDateString() }

// -- thin icons ---------------------------------------------------------------------
const I = {
  repondre: '<path d="M20 12a8 8 0 01-11.6 7.1L4 20l1-4.2A8 8 0 1120 12z"/>',
  republier: '<path d="M7 7h10l-2.5-2.5M17 17H7l2.5 2.5M17 7v4M7 17v-4"/>',
  coeur: '<path d="M12 20s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.6-7 10-7 10z"/>',
  partage: '<path d="M12 15V4M8 8l4-4 4 4M5 13v5a2 2 0 002 2h10a2 2 0 002-2v-5"/>',
  etincelle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
  image: '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.6"/><path d="M5 17l4.5-4.5 3 3 2.5-2.5 4 4"/>',
  loupe: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
  retour: '<path d="M15 5l-7 7 7 7"/>', fleche: '<path d="M12 19V5M5 12l7-7 7 7"/>',
}
const ico = (n, w = 1.7) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round">${I[n]}</svg>`

// -- badges, in pixels like Root ------------------------------------------------------
// each one: 8x8, "#" = colour, "o" = light
const PIX = {
  premier: ['..####..', '.#oooo#.', '#oo##oo#', '#o#oo#o#', '#o#oo#o#', '#oo##oo#', '.#oooo#.', '..####..'],
  fini: ['........', '......##', '.....##.', '#...##..', '##.##...', '.###....', '..#.....', '........'],
  hack: ['..####..', '.######.', '##.##.##', '########', '.##..##.', '..####..', '.#.##.#.', '#......#'],
  oeil: ['........', '..####..', '.#oooo#.', '#oo##oo#', '#oo##oo#', '.#oooo#.', '..####..', '........'],
  flamme: ['...#....', '...##...', '..#o#...', '..#oo#..', '.#oooo#.', '.#o##o#.', '.#o##o#.', '..####..'],
  livre: ['.######.', '#oooooo#', '#o####o#', '#oooooo#', '#o###oo#', '#oooooo#', '#oooooo#', '.######.'],
  lune: ['..####..', '.##oo...', '##oo....', '##o.....', '##o.....', '##oo....', '.##oo...', '..####..'],
  lanterne: ['...##...', '..####..', '.#oooo#.', '.#o##o#.', '.#o##o#.', '.#oooo#.', '..####..', '...##...'],
  secret: ['..####..', '.##..##.', '.....##.', '....##..', '...##...', '...##...', '........', '...##...'],
}
const pixels = (p, c, l) => `<svg viewBox="0 0 8 8" shape-rendering="crispEdges">${p.flatMap((r, y) => [...r].map((ch, x) =>
  ch === '#' ? `<rect x="${x}" y="${y}" width="1" height="1" fill="${c}"/>` : ch === 'o' ? `<rect x="${x}" y="${y}" width="1" height="1" fill="${l}"/>` : '')).join('')}</svg>`
// the badges your own root-harness certifies, and how to earn them (ids as in network.py)
const CATALOGUE = [
  { id: 'first-post', nom: 'First post', comment: 'Post for the first time.', pix: 'premier', c: '#6fd4b6', l: '#1f4d42' },
  { id: 'shipped', nom: 'Shipped', comment: 'Finish a project and show it on your page.', pix: 'fini', c: '#6fd4b6', l: '#1f4d42' },
  { id: 'hackathon', nom: 'Hackathon', comment: 'Add a hackathon to your work.', pix: 'hack', c: '#f0b35a', l: '#5a3d12' },
  { id: 'seven-days', nom: '7 days in a row', comment: 'Work with your agents seven days in a row.', pix: 'flamme', c: '#f87171', l: '#5a1f1f' },
  { id: 'encyclopedist', nom: 'Encyclopedist', comment: 'Learn fifty words in the encyclopedia.', pix: 'livre', c: '#c4b5fd', l: '#3b2f63' },
  { id: 'night-shift', nom: 'Night shift', comment: 'Secret.', pix: 'lune', c: '#c4b5fd', l: '#3b2f63', secret: true },
]
// how a badge from the network looks: a catalogue one, or an event badge somebody made
const look = (b) => {
  const ident = b.a.split(':').slice(2).join(':'), cat = CATALOGUE.find((c) => c.id === ident)
  if (cat && b.self) return { ...cat, nom: b.name || cat.nom, comment: b.description || cat.comment }
  return { id: ident, nom: b.name || ident, comment: b.description || '', pix: b.self ? 'oeil' : 'lanterne', c: '#f0b35a', l: '#5a3d12', unique: !b.self, par: b.issuer_name }
}
const badge = (lk, gagne = true, t = 34) => `<span class="pix${gagne ? '' : ' verrou'}" style="width:${t}px;height:${t}px" title="${esc(gagne || !lk.secret ? lk.nom : 'secret badge')}">${pixels(gagne || !lk.secret ? PIX[lk.pix] || PIX.secret : PIX.secret, lk.c, lk.l)}</span>`

// -- people -------------------------------------------------------------------------------
const ETATS = { etudie: 'student', travaille: 'working', cherche: 'looking for a job' }
const niveau = (n, label) => n ? `<span class="niveau n${n}" title="from the days spent working with agents"><i></i><i></i><i></i>${esc(label || ['', 'active', 'very active', 'actively active'][n])}</span>` : ''
const hue = (hex) => Math.round(parseInt((hex || '7f').slice(0, 2), 16) * 360 / 255)
const nom = (p) => (p.show === 'name' || p.show === 'both') && p.name ? p.name : p.pseudo || p.display || 'someone'
const sousNom = (p) => '@' + (p.id || (p.npub ? p.npub.slice(0, 14) + '...' : 'unknown')) + (p.show === 'both' && p.name && p.pseudo ? ' · ' + p.pseudo : '')
const avatar = (p, t = 44) => p.picture ? `<span class="av" style="width:${t}px;height:${t}px;background-image:url('${esc(p.picture)}')"></span>`
  : p.mine ? `<span class="av racine" style="width:${t}px;height:${t}px">${tete()}</span>`
  : `<span class="av lettre" style="width:${t}px;height:${t}px;--h:${p.hue ?? hue(p.hex)}">${esc((nom(p)[0] || '?').toUpperCase())}</span>`
const COMMUS_BASE = [['agents', 'Agents'], ['security-ctf', 'Security & CTF'], ['42-paris', '42 Paris'], ['hackathons', 'Hackathons'], ['local-llms', 'Local LLMs'], ['design', 'Design']]
const nomCommu = (slug) => (COMMUS_BASE.find((c) => c[0] === slug) || [slug, slug.replace(/-/g, ' ')])[1]

let MOI = null
async function moi(H) { try { MOI = await H.network.profile() } catch { MOI = null } return MOI }

// -- examples, shown only when the network cannot be reached -----------------------------
const H_ = 3600, T0 = Math.floor(Date.now() / 1000)
const ex = (hue, display, id, level, state, at, text, extra) => ({ id: 'ex-' + at, at, exemple: true, text, media: [], reply_to: '', counts: { replies: 4, reposts: 2, reactions: 31 }, mine: {},
  author: { hex: '', hue, display, pseudo: id.split('#')[0], id, level, level_label: ['', 'active', 'very active', 'actively active'][level], state }, ...extra })
const EXEMPLES = [
  ex(168, 'Nora', 'nora#q8m2hx4c', 3, 'etudie', T0 - 2 * H_, 'My agent now reads the error before rerunning the tests, instead of trying three fixes at random. Fewer runs, and I finally understand why my build broke.', { community: 'agents', agent: 'Claude Agent', scene: 'code' }),
  ex(210, 'Malik', 'malik#7tkz3pd2', 2, 'cherche', T0 - 5 * H_, 'Spent the night on a web challenge: the filter blocked "script" but not "ScRiPt". Lesson: never filter with a list, escape the output.', { community: 'security-ctf', counts: { replies: 9, reposts: 5, reactions: 58 } }),
  ex(32, 'Sam', 'sam#c4vw9rn1', 1, 'travaille', T0 - 9 * H_, 'A 27B model on one consumer GPU answers in 2 seconds once it is warm. The trick was the context size, not the model.', { community: 'local-llms', agent: 'Codex', counts: { replies: 2, reposts: 1, reactions: 17 } }),
  ex(290, 'Léa', 'lea#m2x8fa7q', 2, 'etudie', T0 - 26 * H_, 'First week of piscine done. My agent explains, but I write every line myself: that was the deal.', { community: '42-paris', scene: 'tete', counts: { replies: 12, reposts: 3, reactions: 74 } }),
]
const SCENES = {
  code: `<div class="media code"><div class="m-l"><b>-</b> run_tests()  # again</div><div class="m-l plus"><b>+</b> read(error); fix(cause); run_tests()</div><div class="m-l gris">3 runs instead of 11</div></div>`,
  tete: `<div class="media scene"><div class="scene-tete">${tete()}</div></div>`,
}

// -- a post ------------------------------------------------------------------------------------
const medias = (p) => p.scene ? SCENES[p.scene] : (p.media || []).map((m) => `<div class="media">${(m.mime || '').startsWith('video') ? `<video src="${esc(m.url)}" controls playsinline preload="metadata"></video>` : `<img src="${esc(m.url)}" alt="" loading="lazy">`}</div>`).join('')
function carte(p, i) {
  const a = p.author, rb = p.reposted_by, mine = p.mine || {}
  return `<article class="post" data-id="${esc(p.id)}" style="--i:${Math.min(i, 12)}">${avatar(a)}
    <div class="pc">${rb ? `<div class="pagent" style="margin:0 0 6px">${ico('republier')}reposted by ${esc(nom(rb))}</div>` : ''}
      <div class="ph"><b class="qui" data-hex="${esc(a.hex || '')}">${esc(nom(a))}</b>${niveau(a.level, a.level_label)}<span class="m">${esc(sousNom(a))} · ${quand(p.at)}${p.community ? ' · ' + esc(nomCommu(p.community)) : ''}${p.reply_to ? ' · reply' : ''}</span></div>
      <div class="ptx">${riche(p.text)}</div>${medias(p)}
      ${p.agent ? `<div class="pagent">${ico('etincelle')}written with ${esc(p.agent)}</div>` : ''}
      ${p.exemple ? '<div class="pagent" style="color:var(--ambre)">an example</div>' : ''}
      <div class="pact"><button data-a="rep" title="answer">${ico('repondre')}<span>${p.counts.replies || ''}</span></button>
        <button data-a="rt" class="${mine.repost ? 'on rt' : ''}" title="repost">${ico('republier')}<span>${p.counts.reposts || ''}</span></button>
        <button data-a="coeur" class="${mine.reaction ? 'on coeur' : ''}" title="like">${ico('coeur')}<span>${p.counts.reactions || ''}</span></button>
        <button data-a="part" title="share">${ico('partage')}</button></div></div></article>`
}
function brancher(el, posts, H, apres) {
  $$('.post', el).forEach((a) => {
    const p = posts.find((x) => x.id === a.dataset.id); if (!p) return
    $('.qui', a).onclick = (e) => { e.stopPropagation(); if (p.author.hex) ouvrirPage(H, p.author.hex) }
    $('.ptx', a).onclick = () => { if (!p.exemple) ouvrirFil(p, H) }
    $$('[data-a]', a).forEach((b) => b.onclick = async (e) => {
      e.stopPropagation()
      if (p.exemple) return toast('An example: nothing is sent.')
      const k = b.dataset.a
      if (k === 'coeur' || k === 'rt') {
        const key = k === 'coeur' ? 'reaction' : 'repost', count = k === 'coeur' ? 'reactions' : 'reposts', on = !p.mine[key]
        p.mine[key] = on; p.counts[count] = Math.max(0, (p.counts[count] || 0) + (on ? 1 : -1))     // shown at once, sent after
        b.classList.toggle('on', on); b.classList.toggle(k === 'coeur' ? 'coeur' : 'rt', on); b.classList.remove('saute'); void b.offsetWidth; b.classList.add('saute')
        $('span', b).textContent = p.counts[count] || ''
        try {
          const r = k === 'coeur' ? await H.network.react(p.id, p.author.hex, on) : on ? await H.network.repost(p) : await H.network.unrepost(p.id)
          if (r && r.error) throw new Error(r.error)
          if (k === 'rt') toast(on ? 'Reposted on your page.' : 'Repost removed.')
        } catch (err) {
          p.mine[key] = !on; p.counts[count] = Math.max(0, (p.counts[count] || 0) + (on ? -1 : 1))
          b.classList.toggle('on', !on); b.classList.toggle(k === 'coeur' ? 'coeur' : 'rt', !on); $('span', b).textContent = p.counts[count] || ''
          toast(err.message || 'Not sent.')
        }
        apres && apres()
      } else if (k === 'rep') ouvrirFil(p, H, true)
      else if (k === 'part') partager(p, H)
    })
  })
}

// the thread: the post and its answers, and yours
async function ouvrirFil(p, H, repondre = false) {
  const f = feuille(`<h3>the thread</h3><div id="t-fil"><div class="vide">Loading...</div></div>
    <div class="boite-btw"><input class="champ" id="t-q" placeholder="a real answer: what works, what you would try" autocomplete="off"><button class="rond-btn envoyer" id="t-go"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${I.fleche}</svg></button></div>
    <div class="d" style="color:var(--encre-4);font-size:12px;margin-top:8px">Real answers to other people's work are what this network is for.</div>`)
  const charger = async () => {
    try { const th = await H.network.thread(p.id); const L = [th.post || p, ...th.replies]
      $('#t-fil', f).innerHTML = L.map((x, i) => carte(x, i)).join(''); brancher($('#t-fil', f), L, H, null)
    } catch (e) { $('#t-fil', f).innerHTML = `<div class="vide">${esc(e.message || 'Unavailable.')}</div>` }
  }
  charger()
  const go = async () => {
    const q = $('#t-q', f).value.trim(); if (!q) return
    $('#t-go', f).disabled = true
    try { const r = await H.network.post(q, { replyTo: { id: p.id, author: p.author.hex } }); if (r.error) throw new Error(r.error)
      $('#t-q', f).value = ''; toast('Answered.'); setTimeout(charger, 900)
    } catch (e) { toast(e.message || 'Not sent.') }
    $('#t-go', f).disabled = false
  }
  $('#t-go', f).onclick = go; $('#t-q', f).onkeydown = (e) => { if (e.key === 'Enter') go() }
  if (repondre) setTimeout(() => $('#t-q', f).focus(), 300)
}

// share: to a friend or a group (sealed), or the id to paste anywhere
async function partager(p, H) {
  let canaux = []
  try { canaux = ((await (H.friends.overview())).channels || []).filter((c) => !c.request) } catch {}
  const f = feuille(`<h3>share this post</h3><div class="sous-titre" style="margin-bottom:10px">${esc(p.text.slice(0, 120))}${p.text.length > 120 ? '...' : ''}</div>
    <div class="section">to a friend or a group<span class="ligne"></span></div><div class="liste" id="s-canaux">${canaux.map((c, i) => `<div class="item" data-c="${esc(c.id)}" style="--i:${i}"><div class="tx"><div class="t">${esc(c.name)}</div></div></div>`).join('') || '<div class="vide">No friend or group yet: add them in Friends & groups.</div>'}</div>
    <div class="boutons"><button class="bouton" id="s-id">Copy the post id</button></div>`)
  $$('#s-canaux [data-c]', f).forEach((el) => el.onclick = async () => {
    const partage = (H.friends && H.friends.share) || (H.account && H.account.share)
    const r = await partage(el.dataset.c, { title: 'post by ' + nom(p.author), agent: p.agent || '', events: [{ type: 'text', text: p.text + (p.media || []).map((m) => '\n' + m.url).join('') }] }).catch(() => null)
    fermerFeuille(); toast(r ? 'Shared.' : 'Not shared.')
  })
  $('#s-id', f).onclick = () => { H.copy(p.id); toast('Post id copied.') }
}

// =====================================================================================
// the feed
// =====================================================================================
let FIL = 'for-you', COMMU = '', FICHIER = null
export async function vueFil(H) {
  const v = $('#v-fil'), m = MOI || await moi(H) || { mine: true, communities: [] }
  const commus = [...new Set([...(m.communities || []), ...COMMUS_BASE.map((c) => c[0])])]
  v.innerHTML = `<div class="defile"><div class="colonne">
    <div class="titre">the feed</div><div class="sous-titre">What people build with their agents. Yours too: your agent can write the post.</div>
    <div class="pagent" id="f-travail" style="display:none;margin:-10px 0 14px;cursor:pointer">${ico('etincelle')}your agent is working: scroll here, it tells you when it is done. Back to it</div>
    <div class="verre carte ecrire">${avatar(m, 40)}<div class="ec"><textarea class="champ" id="f-t" rows="2" placeholder="what did you build today?"></textarea>
      <div class="ec-bas"><button class="bouton" id="f-agent">${ico('etincelle')} my agent writes it</button><label class="rond-btn" title="a photo or a video">${ico('image')}<input type="file" id="f-img" accept="image/*,video/*" hidden></label>
      <select class="champ petit" id="f-commu"><option value="">no community</option>${commus.map((c) => `<option value="${esc(c)}">${esc(nomCommu(c))}</option>`).join('')}</select>
      <button class="bouton plein" id="f-ok">Post</button></div><div id="f-apercu"></div></div></div>
    <div class="boutons" id="f-onglets">${[['for-you', 'for you'], ['friends', 'friends'], ['communities', 'communities']].map(([k, t]) => `<button class="bouton${k === FIL ? ' vert' : ''}" data-f="${k}">${t}</button>`).join('')}</div>
    <div class="boutons" id="f-commus" style="${FIL === 'communities' ? '' : 'display:none'}">${commus.map((c) => `<button class="bouton${c === COMMU ? ' vert' : ''}" data-c="${esc(c)}">${esc(nomCommu(c))}</button>`).join('')}<button class="bouton" id="f-commu-plus">+ new</button></div>
    <div class="boite-btw" style="margin-top:10px"><input class="champ" id="f-cherche" placeholder="find someone: pseudo#code or npub" autocomplete="off"><button class="rond-btn" id="f-go" title="find">${ico('loupe')}</button></div>
    <div id="f-liste"><div class="vide">Loading...</div></div></div></div>`
  $('#f-img').onchange = (e) => { FICHIER = e.target.files[0] || null; const u = FICHIER && URL.createObjectURL(FICHIER)
    $('#f-apercu').innerHTML = FICHIER ? `<div class="media">${FICHIER.type.startsWith('video') ? `<video src="${u}" controls playsinline></video>` : `<img src="${u}" alt="">`}</div>` : '' }
  $('#f-agent').onclick = async () => {
    const b = $('#f-agent'); b.innerHTML = `${ico('etincelle')} writing...`; b.disabled = true
    const r = H.social ? await H.social.draft($('#f-t').value.trim()).catch((e) => ({ error: e.message })) : { error: 'Not available here.' }
    b.innerHTML = `${ico('etincelle')} my agent writes it`; b.disabled = false
    if (r.error) return toast(r.error)
    $('#f-t').value = r.text; $('#f-t').dataset.agent = r.agent || ''; $('#f-t').rows = 4
  }
  $('#f-ok').onclick = async () => {
    const ta = $('#f-t'), t = ta.value.trim(), b = $('#f-ok'); if (!t && !FICHIER) return
    b.disabled = true; b.textContent = FICHIER ? 'Uploading...' : 'Posting...'
    try {
      const media = []
      if (FICHIER) { const u = await H.network.upload(FICHIER); if (!u || u.error) throw new Error((u && u.error) || 'Upload failed.'); media.push(u) }
      b.textContent = 'Posting...'
      const r = await H.network.post(t, { media, community: $('#f-commu').value, agent: ta.dataset.agent || '' })
      if (r.error) throw new Error(r.error)
      toast(r.relays ? 'Posted.' : 'Posted, no relay has confirmed yet.')
      ta.value = ''; ta.dataset.agent = ''; ta.rows = 2; FICHIER = null; $('#f-apercu').innerHTML = ''; $('#f-img').value = ''
      setTimeout(() => chargerFil(H), 800)
      H.network.checkBadges().then((n) => { if (Array.isArray(n) && n.length) toast('New badge: ' + n.map((id) => (CATALOGUE.find((c) => c.id === id) || { nom: id }).nom).join(', ')) }).catch(() => {})
    } catch (e) { toast(e.message || 'Not posted.') }
    b.disabled = false; b.textContent = 'Post'
  }
  $$('#f-onglets [data-f]').forEach((b) => b.onclick = () => { FIL = b.dataset.f; if (FIL !== 'communities') COMMU = ''; vueFil(H) })
  $$('#f-commus [data-c]').forEach((b) => b.onclick = () => { COMMU = COMMU === b.dataset.c ? '' : b.dataset.c; vueFil(H) })
  $('#f-commu-plus').onclick = () => nouvelleCommunaute(H)
  const trouver = async () => {
    const t = $('#f-cherche').value.trim(); if (!t) return
    try { const p = await H.network.lookup(t); if (!p) return toast('Nobody found with that.'); ouvrirPage(H, p.hex) } catch (e) { toast(e.message || 'Not found.') }
  }
  $('#f-go').onclick = trouver; $('#f-cherche').onkeydown = (e) => { if (e.key === 'Enter') trouver() }
  $('#f-travail').onclick = () => aller('chat')
  travailEnCours()
  chargerFil(H)
}
// while your agent works (body.travail, set by the chat), the feed says so
let SUIVI = 0
function travailEnCours() {
  clearInterval(SUIVI)
  const voir = () => { const el = $('#f-travail'); if (!el) return clearInterval(SUIVI); el.style.display = document.body.classList.contains('travail') ? 'flex' : 'none' }
  voir(); SUIVI = setInterval(voir, 1500)
}
async function chargerFil(H) {
  const el = $('#f-liste'); if (!el) return
  const scope = FIL === 'communities' ? (COMMU ? 'community' : 'for-you') : FIL
  let posts, why = ''
  try { posts = await H.network.feed(scope, { community: COMMU }); if (!Array.isArray(posts)) throw new Error('No answer from the network.') }
  catch (e) { why = e.message || String(e); posts = EXEMPLES }
  if (FIL === 'communities' && !COMMU) posts = posts.filter((p) => p.community)
  if (!$('#f-liste')) return
  $('#f-liste').innerHTML = (why ? `<div class="vide">Examples only. ${esc(why)}</div>` : '')
    + (posts.map((p, i) => carte(p, i)).join('') || `<div class="vide">${FIL === 'friends' ? 'Your friends have not posted yet.' : 'Nobody has posted here yet. Be the first: your agent can write it.'}</div>`)
  brancher($('#f-liste'), posts, H, null)
}
function nouvelleCommunaute(H) {
  const f = feuille(`<h3>a new community</h3><div class="sous-titre" style="margin-bottom:10px">A place to go deeper into one field. Anyone on root-harness can post in it.</div>
    <input class="champ" id="c-nom" placeholder="its name"><textarea class="champ" id="c-d" rows="2" placeholder="what it is about" style="font:15px var(--police);margin-top:8px"></textarea>
    <div class="err" id="c-err"></div><div class="boutons"><button class="bouton plein" id="c-ok">Create</button></div>`)
  $('#c-ok', f).onclick = async () => {
    try { const r = await H.network.createCommunity($('#c-nom', f).value, $('#c-d', f).value); if (r.error) throw new Error(r.error)
      await moi(H); COMMU = r.slug; FIL = 'communities'; fermerFeuille(); toast('Community created.'); vueFil(H)
    } catch (e) { $('#c-err', f).textContent = e.message || 'Not created.' }
  }
}

// =====================================================================================
// a page: yours, or somebody's
// =====================================================================================
let PAGE = '', ONGLET_P = 'posts'
function ouvrirPage(H, hex) { PAGE = hex; ONGLET_P = 'posts'; aller('profil') }
export async function vueProfil(H, hex) {
  if (hex !== undefined) PAGE = hex
  const v = $('#v-profil'), qui = PAGE
  v.innerHTML = `<div class="defile" style="padding-top:0"><div class="colonne"><div class="couverture"></div><div class="vide" style="margin-top:14px">Loading...</div></div></div>`
  let mur
  try { mur = await H.network.wall(qui); if (!mur || !mur.profile) throw new Error('No answer from the network.') }
  catch (e) {
    if (PAGE !== qui) return
    v.innerHTML = `<div class="defile" style="padding-top:0"><div class="colonne"><div class="couverture"></div><div class="p-haut">${avatar({ mine: !qui }, 104)}</div>
      <div class="p-nom" style="margin-top:16px">${qui ? 'this page' : 'your page'}</div><div class="p-bio">${esc(e.message || 'Unavailable.')}</div>
      <div class="boutons" style="padding:0 4px"><button class="bouton" id="p-retry">Try again</button>${qui ? `<button class="bouton" id="p-retour">${ico('retour')} my page</button>` : ''}</div></div></div>`
    $('#p-retry').onclick = () => vueProfil(H); $('#p-retour') && ($('#p-retour').onclick = () => vueProfil(H, ''))
    return
  }
  if (PAGE !== qui) return
  rendrePage(v, mur, H)
}
const TYPES = { progress: 'in progress', project: 'project', hackathon: 'hackathon' }
const travail = (work) => (work || []).map((t, i) => `<div class="verre tr" style="--i:${i}"><div class="tr-q${t.kind === 'progress' || t.live ? ' vivant' : ''}">${t.kind === 'progress' || t.live ? '<i></i>' : ''}${esc(TYPES[t.kind] || t.kind)}</div>
  <div class="tr-t">${/^https?:\/\//.test(t.url || '') ? `<a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.title)}</a>` : esc(t.title)}</div>${t.text ? `<div class="tr-d">${esc(t.text)}</div>` : ''}${t.when ? `<div class="tr-w">${esc(t.when)}</div>` : ''}</div>`).join('')
function rendrePage(v, mur, H) {
  const p = mur.profile, mine = !!p.mine, badges = mur.badges || [], epingles = badges.filter((b) => b.pinned), montres = epingles.length ? epingles : badges.slice(0, 6)
  v.innerHTML = `<div class="defile" style="padding-top:0"><div class="colonne">
    <div class="couverture"${p.banner ? ` style="background-image:url('${esc(p.banner)}')"` : ''}></div>
    <div class="p-haut">${avatar(p, 104)}<div class="boutons" style="margin:0 0 6px auto">${mine ? `<button class="bouton" id="p-qr">Share my ID</button><button class="bouton plein" id="p-edit">Edit profile</button>`
      : `<button class="bouton" id="p-retour">${ico('retour')} my page</button><button class="bouton vert" id="p-ami">Add as a friend</button>`}</div></div>
    <div class="p-nom">${esc(nom(p))}</div><div class="p-id">${esc(sousNom(p))}</div>
    <div class="p-puces">${p.state === 'cherche' ? '<span class="etat cherche">● looking for a job</span>' : p.state ? `<span class="etat">${esc(ETATS[p.state])}</span>` : ''}
      ${p.school || p.role ? `<span class="etat">${esc([p.school, p.role].filter(Boolean).join(' · '))}</span>` : ''}${niveau(p.level, p.level_label)}</div>
    ${p.about ? `<div class="p-bio">${esc(p.about)}</div>` : ''}
    <div class="p-chiffres">${[[mur.posts.length, 'post'], [mur.replies.length, 'repl', 'y', 'ies'], [(p.communities || []).length, 'communit', 'y', 'ies'], [badges.length, 'badge']].map(([n, w, un = '', pl = 's']) => `<span><b>${n}</b> ${w}${n === 1 ? un : pl}</span>`).join('')}</div>
    <div class="p-badges" id="p-badges">${montres.map((b, i) => `<span style="--i:${i}">${badge(look(b), true, 38)}</span>`).join('')}${mine || badges.length ? `<button class="bouton" id="p-tous">${mine ? 'all badges' : 'badges'}</button>` : ''}</div>
    <div class="section">${mine ? 'my work' : 'work'}${p.state === 'cherche' ? ' · available for work' : ''}<span class="ligne"></span></div>
    <div class="p-travail">${travail(p.work)}</div>${!p.work.length ? `<div class="vide">${mine ? 'Add what you build, your hackathons, what is in progress: Edit profile.' : 'Nothing shown yet.'}</div>` : ''}
    <div class="p-onglets">${[['posts', 'Posts'], ['replies', 'Replies'], ['reposts', 'Reposts'], ['media', 'Photos & videos']].map(([k, t]) => `<button data-o="${k}" class="${k === ONGLET_P ? 'on' : ''}">${t}</button>`).join('')}</div>
    <div id="p-liste"></div></div></div>`
  rendreListe(mur, H)
  // a tab only redraws its list: the page around it stays put
  $$('.p-onglets [data-o]').forEach((b) => b.onclick = () => {
    if (ONGLET_P === b.dataset.o) return
    ONGLET_P = b.dataset.o
    $$('.p-onglets [data-o]').forEach((x) => x.classList.toggle('on', x === b))
    rendreListe(mur, H)
  })
  if (mine) {
    $('#p-edit').onclick = () => editer(H, p)
    $('#p-qr').onclick = () => { if (p.id) { H.copy(p.id); toast('Your ID is copied: ' + p.id) } }
  } else {
    $('#p-retour').onclick = () => vueProfil(H, '')
    $('#p-ami').onclick = async () => {
      const ajouter = (H.friends && H.friends.addContact) || (H.account && H.account.addContact)
      const r = await ajouter(p.npub, nom(p)).catch(() => null); toast(r ? nom(p) + ' is in your friends.' : 'Not added.')
    }
  }
  $('#p-tous') && ($('#p-tous').onclick = () => tousBadges(H, mur))
}

function rendreListe(mur, H) {
  const el = $('#p-liste'), mine = !!mur.profile.mine, L = mur[ONGLET_P] || []
  if (ONGLET_P === 'media' && L.length) el.innerHTML = `<div class="grille-media">${L.map((x) => `<div class="gm" data-id="${esc(x.id)}" style="background-image:url('${esc(x.media[0].url)}')"></div>`).join('')}</div>`
  else el.innerHTML = L.map((x, i) => carte(x, i)).join('') || `<div class="vide">${{ posts: mine ? 'No post yet. In the feed, your agent can write the first one.' : 'No post yet.', replies: 'No reply yet.', reposts: 'Nothing reposted yet.', media: 'Posts with a photo or a video show here.' }[ONGLET_P]}</div>`
  brancher(el, L, H, null)        // hearts and reposts toggle in place: no re-render, the scroll stays
  $$('.gm', el).forEach((g) => g.onclick = () => { const x = L.find((y) => y.id === g.dataset.id); if (x) ouvrirFil(x, H) })
}

function tousBadges(H, mur) {
  const mine = !!mur.profile.mine, earned = mur.badges || [], pinned = earned.filter((b) => b.pinned).map((b) => b.a)
  const items = [...earned.map((b) => ({ b, lk: look(b), gagne: true })),
    ...(mine ? CATALOGUE.filter((c) => !earned.some((b) => b.self && b.a.endsWith(':' + c.id))).map((c) => ({ lk: c, gagne: false })) : [])]
  const f = feuille(`<h3>badges</h3><div class="sous-titre" style="margin-bottom:12px">${mine ? 'Tap one you have to pin it on your page (six at most). Secret badges stay hidden until you find them.' : 'What ' + esc(nom(mur.profile)) + ' has earned.'}</div>
    <div class="grille-badges">${items.map(({ b, lk, gagne }, i) => { const cache = lk.secret && !gagne
      return `<button class="gb${b && b.pinned ? ' epingle' : ''}${gagne ? '' : ' non'}" data-a="${esc(b ? b.a : '')}" style="--i:${i}">${badge(lk, gagne, 46)}<div class="gb-n">${esc(cache ? 'secret badge' : lk.nom)}</div><div class="gb-d">${esc(cache ? 'Nobody says how.' : lk.comment)}</div>${lk.unique ? `<div class="gb-u">${esc(lk.par ? 'from ' + lk.par : 'event')}</div>` : b && b.self ? '<div class="gb-u" style="color:var(--encre-4)">self-certified</div>' : ''}</button>` }).join('')}</div>
    ${mine ? `<div class="section">a badge for an event<span class="ligne"></span></div><div class="d" style="font-size:13px;color:var(--encre-3);margin-bottom:8px">Make one for a hackathon, a team, a night: it is unique, and you give it to the friends you choose.</div>
      <input class="champ" id="b-nom" placeholder="its name, like Lanterns · Oct 2026"><input class="champ" id="b-d" placeholder="one line about it">
      <div class="boutons" id="b-amis"></div><div class="boutons"><button class="bouton plein" id="b-ok">Create and give it</button></div>` : ''}`)
  if (mine) $$('[data-a]', f).forEach((el) => el.onclick = async () => {
    const a = el.dataset.a; if (!a) return toast('Not unlocked yet.')
    const next = pinned.includes(a) ? pinned.filter((x) => x !== a) : [...pinned, a].slice(-6)
    try { const r = await H.network.pin(next); if (r.error) throw new Error(r.error); fermerFeuille(); vueProfil(H) } catch (e) { toast(e.message || 'Not pinned.') }
  })
  if (!mine) return
  const choisis = new Set()
  H.friends.overview().then((o) => { $('#b-amis', f).innerHTML = (o.contacts || []).map((c) => `<button class="bouton" data-hex="${esc(c.hex)}">${esc(c.name)}</button>`).join('') || '<div class="vide">Add friends first, in Friends & groups.</div>'
    $$('#b-amis [data-hex]', f).forEach((b) => b.onclick = () => { const h = b.dataset.hex; choisis.has(h) ? choisis.delete(h) : choisis.add(h); b.classList.toggle('vert', choisis.has(h)) }) }).catch(() => {})
  $('#b-ok', f).onclick = async () => {
    const n = $('#b-nom', f).value.trim(); if (!n) return toast('Give it a name.')
    try { const d = await H.network.defineBadge(n, n, $('#b-d', f).value); if (d.error) throw new Error(d.error)
      const r = await H.network.award(d.a, [mur.profile.hex, ...choisis]); if (r.error) throw new Error(r.error)
      fermerFeuille(); toast('Badge created and given.'); setTimeout(() => vueProfil(H), 900)
    } catch (e) { toast(e.message || 'Not created.') }
  }
}

function editer(H, p) {
  let work = (p.work || []).map((w) => ({ ...w })), photo = p.picture, couv = p.banner, montrer = p.show || 'pseudo', etat = p.state || 'etudie', fPhoto = null, fCouv = null
  const f = feuille(`<h3>edit your profile</h3><div class="sous-titre" style="margin-bottom:10px">Everyone can see it.</div>
    <div class="ed-photo">${avatar(p, 64)}<label class="bouton">photo<input type="file" id="e-photo" accept="image/*" hidden></label><label class="bouton">cover<input type="file" id="e-couv" accept="image/*" hidden></label>${p.picture ? '<button class="bouton" id="e-sansphoto">Root\'s head</button>' : ''}</div>
    <input class="champ" id="e-nom" placeholder="first and last name (optional)" value="${esc(p.name || '')}">
    <div class="d" style="font-size:13px;color:var(--encre-3);margin:12px 0 6px">show</div>
    <div class="boutons" id="e-montrer" style="margin-top:0">${[['pseudo', 'my pseudo'], ['name', 'my name'], ['both', 'both']].map(([k, t]) => `<button class="bouton${montrer === k ? ' vert' : ''}" data-m="${k}">${t}</button>`).join('')}</div>
    <div class="d" style="font-size:13px;color:var(--encre-3);margin:12px 0 6px">right now I am</div>
    <div class="boutons" id="e-etat" style="margin-top:0">${Object.entries(ETATS).map(([k, t]) => `<button class="bouton${etat === k ? ' vert' : ''}" data-e="${k}">${t}</button>`).join('')}</div>
    <input class="champ" id="e-ecole" placeholder="school or company" value="${esc(p.school || '')}" style="margin-top:12px"><input class="champ" id="e-poste" placeholder="role, or the job you are looking for" value="${esc(p.role || '')}">
    <textarea class="champ" id="e-bio" rows="2" placeholder="one line about you" style="font:15px var(--police);margin-top:8px">${esc(p.about || '')}</textarea>
    <div class="section">my work<span class="ligne"></span></div><div id="e-work"></div>
    <div class="boutons"><button class="bouton" id="e-plus">+ a line</button><button class="bouton" id="e-suggere">${ico('etincelle')} from my agents</button></div>
    <div class="section">my agent and my posts<span class="ligne"></span></div>
    <div class="reglage"><div class="l">Proposes a post after a long task<div class="d">It writes it from the work, you decide.</div></div><span class="inter" id="e-suggest"></span></div>
    <div class="reglage"><div class="l">Posts it by itself<div class="d">Without asking. Off unless you turn it on.</div></div><span class="inter" id="e-auto"></span></div>
    <div class="err" id="e-err"></div><div class="boutons"><button class="bouton plein" id="e-ok">Save</button></div>`)
  const lignes = () => { $('#e-work', f).innerHTML = work.map((w, i) => `<div class="rangee" data-i="${i}" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:8px">
      <select class="champ petit" data-k="kind">${Object.entries(TYPES).map(([k, t]) => `<option value="${k}"${w.kind === k ? ' selected' : ''}>${t}</option>`).join('')}</select>
      <input class="champ" data-k="title" placeholder="title" value="${esc(w.title || '')}" style="flex:1;min-width:120px;margin-top:0"><input class="champ" data-k="when" placeholder="when" value="${esc(w.when || '')}" style="width:100px;margin-top:0">
      <input class="champ" data-k="text" placeholder="one line" value="${esc(w.text || '')}" style="flex-basis:100%;margin-top:0"><button class="bouton danger" data-x="${i}">remove</button></div>`).join('') || '<div class="vide">Nothing yet.</div>'
    $$('#e-work [data-k]', f).forEach((el) => el.oninput = () => { work[+el.closest('[data-i]').dataset.i][el.dataset.k] = el.value })
    $$('#e-work [data-x]', f).forEach((b) => b.onclick = () => { work.splice(+b.dataset.x, 1); lignes() }) }
  lignes()
  $('#e-plus', f).onclick = () => { work.push({ kind: 'project', title: '', text: '', when: '' }); lignes() }
  $('#e-suggere', f).onclick = async () => { const s = await H.network.workSuggest().catch(() => []); const add = (s || []).filter((x) => !work.some((w) => (w.title || '').toLowerCase() === x.title.toLowerCase()))
    if (!add.length) return toast('Nothing new to suggest.'); work.push(...add); lignes(); toast(add.length + ' line(s) from your conversations: keep what you want.') }
  const choix = (sel, attr, set) => $$(sel + ' [data-' + attr + ']', f).forEach((b) => b.onclick = () => { set(b.dataset[attr]); $$(sel + ' .bouton', f).forEach((x) => x.classList.toggle('vert', x === b)) })
  choix('#e-montrer', 'm', (x) => montrer = x); choix('#e-etat', 'e', (x) => etat = x)
  $('#e-photo', f).onchange = (e) => { fPhoto = e.target.files[0] || null; toast(fPhoto ? 'Photo ready: it is uploaded when you save.' : '') }
  $('#e-couv', f).onchange = (e) => { fCouv = e.target.files[0] || null; toast(fCouv ? 'Cover ready: it is uploaded when you save.' : '') }
  $('#e-sansphoto', f) && ($('#e-sansphoto', f).onclick = () => { photo = ''; fPhoto = null; toast('Back to Root\'s head.') })
  H.network.posting().then((s) => { $('#e-suggest', f).classList.toggle('on', !!s.suggest); $('#e-auto', f).classList.toggle('on', !!s.auto)
    $('#e-suggest', f).onclick = async () => { const r = await H.network.posting(!s.suggest, null); s.suggest = r.suggest; $('#e-suggest', f).classList.toggle('on', !!r.suggest) }
    $('#e-auto', f).onclick = async () => { const r = await H.network.posting(null, !s.auto); s.auto = r.auto; $('#e-auto', f).classList.toggle('on', !!r.auto); if (r.auto) toast('Your agent will post about long tasks by itself.') } }).catch(() => {})
  $('#e-ok', f).onclick = async () => {
    const b = $('#e-ok', f); b.disabled = true; b.textContent = 'Saving...'
    try {
      if (fPhoto) { const u = await H.network.upload(fPhoto); if (!u || u.error) throw new Error((u && u.error) || 'Photo upload failed.'); photo = u.url }
      if (fCouv) { const u = await H.network.upload(fCouv); if (!u || u.error) throw new Error((u && u.error) || 'Cover upload failed.'); couv = u.url }
      const r = await H.network.update({ name: $('#e-nom', f).value.trim(), show: montrer, state: etat, school: $('#e-ecole', f).value.trim(), role: $('#e-poste', f).value.trim(),
        about: $('#e-bio', f).value.trim(), picture: photo, banner: couv, work: work.filter((w) => (w.title || '').trim()) })
      if (r && r.error) throw new Error(r.error)
      MOI = null; fermerFeuille(); toast('Profile published.'); vueProfil(H)
      H.network.checkBadges().then((n) => { if (Array.isArray(n) && n.length) toast('New badge: ' + n.map((id) => (CATALOGUE.find((c) => c.id === id) || { nom: id }).nom).join(', ')) }).catch(() => {})
    } catch (e) { $('#e-err', f).textContent = e.message || 'Not saved.'; b.disabled = false; b.textContent = 'Save' }
  }
}

// =====================================================================================
// what the computer tells the interface: a post your agent wrote, a badge earned
// =====================================================================================
export function evenementReseau(H, e) {
  if (e.type === 'post_suggestion') suggestionPost(H, e)
  else if (e.type === 'post_published') toast('Your agent posted about your work.')
  else if (e.type === 'badges_new') toast('New badge: ' + (e.badges || []).map((id) => (CATALOGUE.find((c) => c.id === id) || { nom: id }).nom).join(', '))
}
function suggestionPost(H, e) {
  const f = feuille(`<h3>your agent wrote a post</h3><div class="sous-titre" style="margin-bottom:10px">About the work you just did. Change it if you like, then post it, or not.</div>
    <textarea class="champ" id="s-t" rows="5" style="font:15px var(--police)">${esc(e.text || '')}</textarea>
    <div class="boutons"><button class="bouton plein" id="s-ok">Post it</button><button class="bouton" id="s-non">Not now</button></div>`)
  $('#s-non', f).onclick = fermerFeuille
  $('#s-ok', f).onclick = async () => {
    try { const r = await H.network.post($('#s-t', f).value, { agent: e.agent || '' }); if (r.error) throw new Error(r.error); fermerFeuille(); toast('Posted.') }
    catch (err) { toast(err.message || 'Not posted.') }
  }
}
