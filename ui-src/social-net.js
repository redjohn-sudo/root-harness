// The network from the phone: the same public events as rootharness/network.py
// (profile, posts, replies, reposts, reactions, badges, communities), signed with
// your key here, sent to the same relays. Nothing in this file is private.
import { finalizeEvent, verifyEvent } from 'nostr-tools/pure'
import * as nip19 from 'nostr-tools/nip19'
import { getToken } from 'nostr-tools/nip98'
import { handle } from './ident.js'

export const TAG = 'root-harness', EXTRAS = 'rh-profile', MEDIA_HOST = 'https://nostr.build/api/v2/nip96/upload', MEDIA_MAX = 20 * 1024 * 1024
const K = { profil: 0, post: 1, suivis: 3, suppr: 5, repost: 6, reaction: 7, award: 8, epingles: 30008, badge: 30009, commu: 34550, extras: 30078, auth: 27235 }
const ETATS = ['etudie', 'travaille', 'cherche'], MONTRER = ['pseudo', 'name', 'both']
const now = () => Math.floor(Date.now() / 1000)
export const slug = (t) => (t || '').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40)
// a work line from somebody's extras: only web links are kept
const travailPropre = (w) => ({ kind: ['project', 'hackathon', 'progress'].includes(w.kind) ? w.kind : 'project', title: String(w.title).slice(0, 60), text: String(w.text || '').slice(0, 200),
  when: String(w.when || '').slice(0, 24), live: !!w.live, url: /^https?:\/\//.test(String(w.url || '')) ? String(w.url).slice(0, 200) : '' })
export const niveauLabel = (n) => ({ 3: 'actively active', 2: 'very active', 1: 'active' })[n] || ''
const first = (tags, name, d = '') => { const t = tags.find((x) => x[0] === name); return t && t[1] !== undefined ? t[1] : d }
const hexOk = (h) => /^[0-9a-f]{64}$/.test(h || '')

// the automatic badges, certified by your own root-harness (shown as self-certified)
export const AUTO = {
  'first-post': ['First post', 'Posted for the first time.'],
  'night-shift': ['Night shift', 'A post between two and five in the morning.'],
  shipped: ['Shipped', 'A project finished and shown.'],
  hackathon: ['Hackathon', 'Took part in a hackathon.'],
}

// extras you keep on this phone (the same shape as network.py's profile.json)
export function extrasVides() {
  return { name: '', show: 'pseudo', about: '', picture: '', banner: '', school: '', role: '', state: 'etudie', work: [], pinned: [], communities: [] }
}
export function extrasPropres(p, fields) {
  for (const k of ['name', 'about', 'picture', 'banner', 'school', 'role']) if (k in fields) p[k] = String(fields[k] || '').slice(0, k === 'picture' || k === 'banner' ? 2000 : 160)
  if (MONTRER.includes(fields.show)) p.show = fields.show
  if (ETATS.includes(fields.state)) p.state = fields.state
  if (Array.isArray(fields.work)) p.work = fields.work.filter((w) => w && w.title).slice(0, 12).map((w) => ({
    id: String(w.id || Math.random().toString(36).slice(2, 10)), kind: ['project', 'hackathon', 'progress'].includes(w.kind) ? w.kind : 'project',
    title: String(w.title).slice(0, 60), text: String(w.text || '').slice(0, 200), when: String(w.when || '').slice(0, 24), live: !!w.live, url: String(w.url || '').slice(0, 200) }))
  if (Array.isArray(fields.pinned)) p.pinned = fields.pinned.filter((a) => typeof a === 'string' && a.startsWith(K.badge + ':')).slice(0, 8)
  if (Array.isArray(fields.communities)) p.communities = [...new Set(fields.communities.map(slug).filter(Boolean))].sort().slice(0, 30)
  return p
}

/** pool: a SimplePool; store: { get(key, fallback), set(key, value) }; activite: () => ({ level, days }) or null. */
export function reseau({ pool, relays, sk, me, pseudo, store, activite, expire = 0 }) {
  const profils = new Map()                                  // hex -> profile view
  const extras = () => extrasPropres(extrasVides(), store.get('rh-net-profile', {}) || {})
  const mine = () => store.get('rh-net-mine', { reactions: {}, reposts: {} }) || { reactions: {}, reposts: {} }

  // expire (seconds) is for tests only: the events vanish from the relays (NIP-40)
  const signer = (kind, content, tags) => finalizeEvent({ kind, created_at: now(), content, tags: [...tags, ['client', TAG], ...(expire ? [['expiration', String(now() + expire)]] : [])] }, sk)
  async function envoyer(ev) {
    const r = await Promise.allSettled(pool.publish(relays, ev))
    return { id: ev.id, at: ev.created_at, relays: r.filter((x) => x.status === 'fulfilled').length }
  }
  async function lire(filters, maxWait = 8000) {
    const L = await Promise.all(filters.map((f) => pool.querySync(relays, f, { maxWait }).catch(() => [])))
    const seen = new Set(), out = []
    for (const ev of L.flat()) if (!seen.has(ev.id)) { seen.add(ev.id); out.push(ev) }
    return out
  }

  // -- profiles --------------------------------------------------------------------------
  function vue(hex, meta, ex) {
    const ps = String(ex.pseudo || meta.name || '').slice(0, 32)
    const v = { hex, npub: nip19.npubEncode(hex), pseudo: ps, id: ps ? handle(ps, hex) : '',
      name: String(ex.name || '').slice(0, 60), show: MONTRER.includes(ex.show) ? ex.show : 'pseudo',
      display: String(meta.display_name || meta.name || ps).slice(0, 80), about: String(ex.about || meta.about || '').slice(0, 300),
      picture: String(ex.picture || meta.picture || '').slice(0, 120000), banner: String(ex.banner || meta.banner || '').slice(0, 160000),
      school: String(ex.school || '').slice(0, 60), role: String(ex.role || '').slice(0, 80), state: ETATS.includes(ex.state) ? ex.state : '',
      level: Math.min(3, Math.max(0, parseInt(ex.level, 10) || 0)), work: (ex.work || []).filter((w) => w && w.title).slice(0, 12).map(travailPropre),
      communities: (ex.communities || []).map(slug).filter(Boolean).slice(0, 30), mine: hex === me }
    v.level_label = niveauLabel(v.level)
    profils.set(hex, v)
    return v
  }
  async function profilsDe(hexes) {
    const manque = [...hexes].filter((h) => !profils.has(h))
    if (manque.length) {
      const evs = await lire([{ kinds: [K.profil], authors: manque }, { kinds: [K.extras], authors: manque, '#d': [EXTRAS] }])
      const metas = {}, exs = {}
      for (const ev of evs.sort((a, b) => a.created_at - b.created_at)) {
        let d; try { d = JSON.parse(ev.content || '{}') } catch { continue }
        ;(ev.kind === K.profil ? metas : exs)[ev.pubkey] = d
      }
      manque.forEach((h) => { const v = vue(h, metas[h] || {}, exs[h] || {}); if (!metas[h] && !exs[h]) profils.delete(h) })   // an empty answer is not kept
    }
    const out = Object.fromEntries([...hexes].map((h) => [h, profils.get(h) || vue(h, {}, {})]))
    for (const h of hexes) if (profils.get(h) && !profils.get(h).pseudo && !profils.get(h).about) profils.delete(h)
    return out
  }
  async function publierProfil() {
    // no activity counter on this device (the phone): keep the level last published from the computer
    if (!activite && !profils.has(me)) await profilsDe(new Set([me]))
    const p = extras(), act = activite ? activite() : { level: (profils.get(me) || {}).level || 0, days: (profils.get(me) || {}).days || 0 }
    const shown = { pseudo, name: p.name || pseudo, both: p.name ? `${p.name} (${pseudo})` : pseudo }[p.show]
    const meta = { name: slug(pseudo).replace(/-/g, '.'), display_name: shown, about: p.about, picture: p.picture.startsWith('https://') ? p.picture : '', banner: p.banner.startsWith('https://') ? p.banner : '' }
    const ex = { v: 1, id: handle(pseudo, me), pseudo, name: p.name, show: p.show, school: p.school, role: p.role, state: p.state, level: act.level, days: act.days,
      work: p.work, communities: p.communities, picture: p.picture.slice(0, 48000), banner: p.banner.slice(0, 48000) }   // relays cap events near 100 KB
    const a = await envoyer(signer(K.profil, JSON.stringify(Object.fromEntries(Object.entries(meta).filter(([, v]) => v))), []))
    const b = await envoyer(signer(K.extras, JSON.stringify(ex), [['d', EXTRAS]]))
    profils.delete(me)
    return { profile: a, extras: b }
  }

  // -- posts -----------------------------------------------------------------------------------
  function postDe(ev) {
    let reposted_by = null
    if (ev.kind === K.repost) {
      let inner; try { inner = JSON.parse(ev.content); if (!verifyEvent(inner)) return null } catch { return null }
      reposted_by = { hex: ev.pubkey, at: ev.created_at }; ev = inner
    } else if (ev.kind !== K.post) return null
    const media = []
    for (const t of ev.tags) if (t[0] === 'imeta') {
      const parts = Object.fromEntries(t.slice(1).filter((x) => x.includes(' ')).map((x) => x.split(/ (.*)/s).slice(0, 2)))
      if (String(parts.url || '').startsWith('https://')) media.push({ url: parts.url, mime: parts.m || '', dim: parts.dim || '' })
    }
    let text = ev.content
    media.forEach((m) => { text = text.replace(m.url, '').trimEnd() })
    const commus = ev.tags.filter((t) => t[0] === 't' && t[1] !== TAG).map((t) => t[1])
    return { id: ev.id, at: ev.created_at, author: { hex: ev.pubkey }, text: text.slice(0, 4000), media, community: commus[0] || '',
      agent: first(ev.tags, 'rh-agent'), reply_to: first(ev.tags, 'e'), from_root_harness: ev.tags.some((t) => t[0] === 't' && t[1] === TAG),
      counts: { replies: 0, reposts: 0, reactions: 0 }, mine: { reaction: false, repost: false, reply: false }, reposted_by, raw: JSON.stringify(ev) }
  }
  async function hydrater(evs, limit) {
    const parId = new Map(), posts = []
    for (const ev of evs) { const p = postDe(ev); if (p && !parId.has(p.id)) { parId.set(p.id, p); posts.push(p) } }
    posts.sort((a, b) => b.at - a.at); posts.splice(limit)
    const ids = posts.map((p) => p.id)
    if (ids.length) for (const ev of await lire([{ kinds: [K.post, K.repost, K.reaction], '#e': ids, limit: 2000 }], 6000)) {
      const t = ev.tags.find((x) => x[0] === 'e' && parId.has(x[1])); if (!t) continue
      const p = parId.get(t[1]), key = ev.kind === K.post ? 'replies' : ev.kind === K.repost ? 'reposts' : 'reactions'
      p.counts[key]++
      if (ev.pubkey === me) p.mine[ev.kind === K.repost ? 'repost' : ev.kind === K.reaction ? 'reaction' : 'reply'] = true
    }
    const auteurs = await profilsDe(new Set([...posts.map((p) => p.author.hex), ...posts.filter((p) => p.reposted_by).map((p) => p.reposted_by.hex)]))
    for (const p of posts) { p.author = auteurs[p.author.hex] || p.author; if (p.reposted_by) p.reposted_by = auteurs[p.reposted_by.hex] || p.reposted_by }
    return posts
  }

  // -- following (kind 3, the list every Nostr app shares) -------------------------------
  async function listeDe(hex) { const L = await lire([{ kinds: [K.suivis], authors: [hex], limit: 1 }]); return L.sort((a, b) => b.created_at - a.created_at)[0] || null }
  async function suivisDe(hex) { const ev = await listeDe(hex); return ev ? [...new Set(ev.tags.filter((t) => t[0] === 'p' && hexOk(t[1]) && t[1] !== hex).map((t) => t[1]))] : [] }
  async function abonnesDe(hex) {
    const latest = new Map()
    for (const ev of await lire([{ kinds: [K.suivis], '#p': [hex], limit: 500 }])) if (ev.pubkey !== hex && (!latest.has(ev.pubkey) || ev.created_at > latest.get(ev.pubkey).created_at)) latest.set(ev.pubkey, ev)
    return [...latest.values()].filter((ev) => ev.tags.some((t) => t[0] === 'p' && t[1] === hex)).map((ev) => ev.pubkey)
  }
  const NOTIFS = 'rh-net-notifs', etat = () => store.get(NOTIFS, null) || { seen_at: 0, followers: {} }

  return {
    extras, me,
    suivis: (hex = me) => suivisDe(hex), abonnes: (hex = me) => abonnesDe(hex),
    async suivre(hex, on = true) {
      if (!hexOk(hex) || hex === me) return { error: 'Nobody to follow.' }
      const ev = await listeDe(me)
      let tags = ev ? ev.tags.map((t) => [...t]) : []
      const has = tags.some((t) => t[0] === 'p' && t[1] === hex)
      if (on && !has) tags.push(['p', hex])
      if (!on) tags = tags.filter((t) => !(t[0] === 'p' && t[1] === hex))
      // never with an expiration: this list replaces the one other apps see
      const sent = await envoyer(finalizeEvent({ kind: K.suivis, created_at: now(), content: ev ? ev.content : '', tags }, sk))
      return { ...sent, following: on, count: tags.filter((t) => t[0] === 'p').length }
    },
    async gens(hexes) { hexes = hexes.filter(hexOk).slice(0, 300); if (!hexes.length) return []; const P = await profilsDe(new Set(hexes)); return hexes.map((h) => P[h]).filter(Boolean) },

    // notifications: what people did with you
    async notifications(days = 30, limit = 120) {
      const since = now() - days * 86400, st = etat(), items = [], cibles = new Set(), t0 = now()
      const evs = await lire([{ kinds: [K.post, K.repost, K.reaction, K.award], '#p': [me], since, limit: limit * 2 }, { kinds: [K.suivis], '#p': [me], limit: 500 }])
      const connus = Object.keys(st.followers).length > 0
      for (const ev of evs) {
        if (ev.pubkey === me) continue
        const cible = first(ev.tags, 'e')
        if (ev.kind === K.suivis) { if (!ev.tags.some((t) => t[0] === 'p' && t[1] === me)) continue
          if (!(ev.pubkey in st.followers)) st.followers[ev.pubkey] = connus ? t0 : ev.created_at   // a follow counts once, when first seen
          items.push({ id: 'f' + ev.pubkey, type: 'follow', at: st.followers[ev.pubkey], who: ev.pubkey }); continue }
        if (ev.kind === K.reaction) items.push({ id: ev.id, type: 'like', at: ev.created_at, who: ev.pubkey, post: cible })
        else if (ev.kind === K.repost) items.push({ id: ev.id, type: 'repost', at: ev.created_at, who: ev.pubkey, post: cible })
        else if (ev.kind === K.post) items.push({ id: ev.id, type: cible ? 'reply' : 'mention', at: ev.created_at, who: ev.pubkey, post: cible, text: ev.content.slice(0, 280) })
        else if (ev.kind === K.award) { const a = first(ev.tags, 'a'); items.push({ id: ev.id, type: 'badge', at: ev.created_at, who: ev.pubkey, badge: a, badge_name: (a.split(':')[2] || 'a badge').replace(/-/g, ' ') }) }
        if (cible) cibles.add(cible)
      }
      const actuels = new Set(items.filter((i) => i.type === 'follow').map((i) => i.who))
      st.followers = Object.fromEntries(Object.entries(st.followers).filter(([h]) => actuels.has(h))); store.set(NOTIFS, st)
      const textes = {}
      if (cibles.size) for (const ev of await lire([{ ids: [...cibles].slice(0, 300) }])) textes[ev.id] = ev.content.slice(0, 140)
      const P = await profilsDe(new Set(items.map((i) => i.who)))
      items.sort((a, b) => b.at - a.at); items.splice(limit)
      for (const i of items) { i.person = P[i.who] || { hex: i.who }; if (i.post) i.post_text = textes[i.post] || ''; i.new = i.at > st.seen_at }
      return { items, unread: items.filter((i) => i.new).length, seen_at: st.seen_at }
    },
    notifsVues() { const st = etat(); st.seen_at = now(); store.set(NOTIFS, st); return st.seen_at },
    async notifsNouvelles() { const r = await this.notifications(7, 60); return { unread: r.unread, fresh: [] } },
    // your profile
    profilLocal() { const p = extras(), act = activite ? activite() : { level: 0 }; return vue(me, { name: slug(pseudo) }, { ...p, pseudo, level: act.level }) },
    async majProfil(fields) { store.set('rh-net-profile', extrasPropres(extras(), fields)); const sent = await publierProfil(); if ('pinned' in fields) await this.epingler(extras().pinned); return { profile: this.profilLocal(), sent } },
    publierProfil,
    async profilDe(hex) { profils.delete(hex); return (await profilsDe(new Set([hex])))[hex] },

    // posting
    async poster(text, { media = [], community = '', agent = '', replyTo = null } = {}) {
      text = String(text || '').trim().slice(0, 4000); media = media.filter((m) => m && String(m.url).startsWith('https://')).slice(0, 4)
      if (!text && !media.length) return { error: 'Nothing to post.' }
      const tags = [['t', TAG]]
      if (slug(community)) tags.push(['t', slug(community)])
      if (agent) tags.push(['rh-agent', String(agent).slice(0, 40)])
      media.forEach((m) => tags.push(['imeta', 'url ' + m.url, 'm ' + (m.mime || 'image/jpeg'), ...(m.dim ? ['dim ' + m.dim] : [])]))
      if (replyTo && replyTo.id) tags.push(['e', replyTo.id, relays[0], 'root'], ['p', replyTo.author || me])
      return envoyer(signer(K.post, text + (media.length ? '\n' + media.map((m) => m.url).join('\n') : ''), tags))
    },
    async republier(post) {
      if (!post || !post.raw) return { error: 'Nothing to repost.' }
      const sent = await envoyer(signer(K.repost, post.raw, [['e', post.id, relays[0]], ['p', post.author.hex || post.author]]))
      const m = mine(); m.reposts[post.id] = sent.id; store.set('rh-net-mine', m); return sent
    },
    async reagir(postId, author, on = true) {
      const m = mine()
      if (on) {
        if (m.reactions[postId]) return { id: m.reactions[postId], already: true }
        const sent = await envoyer(signer(K.reaction, '+', [['e', postId, relays[0]], ['p', author], ['k', String(K.post)]]))
        m.reactions[postId] = sent.id; store.set('rh-net-mine', m); return sent
      }
      const rid = m.reactions[postId]; if (!rid) return { removed: false }
      delete m.reactions[postId]; store.set('rh-net-mine', m)
      return { ...(await envoyer(signer(K.suppr, '', [['e', rid], ['k', String(K.reaction)]]))), removed: true }
    },
    async derepublier(postId) {
      const m = mine(), rid = m.reposts[postId]; if (!rid) return { removed: false }
      delete m.reposts[postId]; store.set('rh-net-mine', m)
      return { ...(await envoyer(signer(K.suppr, '', [['e', rid], ['k', String(K.repost)]]))), removed: true }
    },
    supprimer: (postId) => envoyer(signer(K.suppr, '', [['e', postId], ['k', String(K.post)]])),

    // reading
    async fil(scope = 'for-you', { community = '', friends = [], days = 7, limit = 60 } = {}) {
      const since = now() - days * 86400, kinds = [K.post, K.repost], F = []
      if (scope === 'for-you') { F.push({ kinds, '#t': [TAG], since, limit }); if (friends.length) F.push({ kinds, authors: friends.slice(0, 200), since, limit }) }
      else if (scope === 'friends') { if (!friends.length) return []; F.push({ kinds, authors: [...friends.slice(0, 200), me], since, limit }) }
      else if (scope === 'community') { if (!slug(community)) return []; F.push({ kinds, '#t': [slug(community)], since, limit: limit * 3 }) }
      else if (scope === 'me') F.push({ kinds, authors: [me], limit })
      let evs = await lire(F)
      if (scope === 'community') evs = evs.filter((e) => e.tags.some((t) => t[0] === 't' && t[1] === TAG))   // posted from root-harness, not all of Nostr
      return hydrater(evs, limit)
    },
    async thread(postId) {
      const posts = await hydrater(await lire([{ ids: [postId] }, { kinds: [K.post], '#e': [postId], limit: 200 }]), 201)
      return { post: posts.find((p) => p.id === postId) || null, replies: posts.filter((p) => p.id !== postId).sort((a, b) => a.at - b.at) }
    },
    async mur(hex = me, limit = 60) {
      const posts = await hydrater(await lire([{ kinds: [K.post, K.repost], authors: [hex], limit }]), limit)
      const [profile, badges, following, followers, miens] = await Promise.all([profilsDe(new Set([hex])).then((p) => p[hex]), this.badgesDe(hex),
        suivisDe(hex), abonnesDe(hex), hex === me ? null : suivisDe(me)])
      return { profile, badges, following, followers, i_follow: (miens || following).includes(hex), follows_me: following.includes(me), posts: posts.filter((p) => !p.reply_to && !p.reposted_by), replies: posts.filter((p) => p.reply_to && !p.reposted_by),
        reposts: posts.filter((p) => p.reposted_by), media: posts.filter((p) => p.media.length && !p.reposted_by) }
    },

    // pictures and videos: a public media host, signed with your key (NIP-96 + NIP-98)
    async envoyerMedia(file) {
      if (!file || file.size > MEDIA_MAX) return { error: 'Too big: 20 MB at most.' }
      if (!/^(image|video|audio)\//.test(file.type)) return { error: 'Only pictures, videos and audio.' }
      const body = new FormData(); body.append('file', file, file.name || 'file'); body.append('no_transform', 'false')
      const token = await getToken(MEDIA_HOST, 'POST', (e) => finalizeEvent(e, sk), true)
      let out
      try { const r = await fetch(MEDIA_HOST, { method: 'POST', headers: { Authorization: token }, body }); out = await r.json() } catch (e) { return { error: 'Upload failed: ' + e.message } }
      const tags = (out.nip94_event && out.nip94_event.tags) || [], url = first(tags, 'url')
      if (!url.startsWith('https://')) return { error: 'Upload failed: ' + String(out.message || '').slice(0, 120) }
      return { url, mime: first(tags, 'm', file.type), dim: first(tags, 'dim') }
    },

    // badges (NIP-58)
    async badgeDefinir(ident, name, description, image = '') {
      ident = slug(ident); if (!ident || !name.trim()) return { error: 'A badge needs an id and a name.' }
      const tags = [['d', ident], ['name', name.trim().slice(0, 60)], ['description', description.trim().slice(0, 300)]]
      if (image) tags.push(['image', image.slice(0, 120000), '64x64'])
      return { ...(await envoyer(signer(K.badge, '', tags))), a: `${K.badge}:${me}:${ident}` }
    },
    async badgeDonner(a, recipients) {
      if (!a.startsWith(`${K.badge}:${me}:`)) return { error: 'You can only award badges you created.' }
      recipients = recipients.filter(hexOk); if (!recipients.length) return { error: 'Nobody to award.' }
      return envoyer(signer(K.award, '', [['a', a], ...recipients.slice(0, 200).map((r) => ['p', r, relays[0]])]))
    },
    mesBadges() { return this.badgesDe(me) },
    async badgesDe(hex) {
      const evs = await lire([{ kinds: [K.award], '#p': [hex], limit: 200 }, { kinds: [K.epingles], authors: [hex], '#d': ['profile_badges'], limit: 1 }])
      const awards = new Map(); let pinned = []
      for (const ev of evs) {
        if (ev.kind === K.award) { const a = first(ev.tags, 'a'); if (a.startsWith(K.badge + ':') && a.split(':')[1] === ev.pubkey && !awards.has(a)) awards.set(a, { a, award: ev.id, issuer: ev.pubkey, at: ev.created_at }) }
        else pinned = ev.tags.filter((t) => t[0] === 'a').map((t) => t[1])
      }
      if (!awards.size) return []
      const coords = [...awards.keys()].map((a) => a.split(':'))
      const defs = {}
      for (const ev of await lire([{ kinds: [K.badge], authors: [...new Set(coords.map((c) => c[1]))], '#d': coords.map((c) => c.slice(2).join(':')) }]))
        defs[`${K.badge}:${ev.pubkey}:${first(ev.tags, 'd')}`] = { name: first(ev.tags, 'name'), description: first(ev.tags, 'description'), image: first(ev.tags, 'image') }
      const issuers = await profilsDe(new Set([...awards.values()].map((v) => v.issuer)))
      return [...awards.values()].filter((v) => defs[v.a]).map((v) => ({ ...v, ...defs[v.a], pinned: pinned.includes(v.a), self: v.issuer === hex,
        issuer_name: (issuers[v.issuer] && (issuers[v.issuer].id || issuers[v.issuer].display)) || '' })).sort((x, y) => (x.pinned === y.pinned ? y.at - x.at : x.pinned ? -1 : 1))
    },
    async epingler(coords) {
      const miens = Object.fromEntries((await this.mesBadges()).map((b) => [b.a, b])), tags = [['d', 'profile_badges']], kept = []
      for (const a of coords) if (miens[a]) { tags.push(['a', a], ['e', miens[a].award, relays[0]]); kept.push(a) }
      store.set('rh-net-profile', extrasPropres(extras(), { pinned: kept }))
      return { ...(await envoyer(signer(K.epingles, '', tags))), pinned: kept }
    },
    async verifierBadges() {
      const posts = (await this.fil('me', { limit: 200 })).filter((p) => !p.reposted_by), earned = new Set()
      if (posts.length) earned.add('first-post')
      if (posts.some((p) => { const h = new Date(p.at * 1000).getHours(); return h >= 2 && h < 5 })) earned.add('night-shift')
      const work = extras().work
      if (work.some((w) => w.kind === 'project' && !w.live)) earned.add('shipped')
      if (work.some((w) => w.kind === 'hackathon')) earned.add('hackathon')
      const have = new Set((await this.mesBadges()).map((b) => b.a)), nouveaux = []
      for (const ident of [...earned].sort()) {
        const a = `${K.badge}:${me}:${ident}`; if (have.has(a)) continue
        await this.badgeDefinir(ident, AUTO[ident][0], AUTO[ident][1]); await this.badgeDonner(a, [me]); nouveaux.push(ident)
      }
      return nouveaux
    },

    // communities
    async creerCommunaute(name, description = '') {
      const d = slug(name); if (!d) return { error: 'Give the community a name.' }
      const sent = await envoyer(signer(K.commu, '', [['d', d], ['name', name.trim().slice(0, 60)], ['description', description.trim().slice(0, 300)], ['p', me, relays[0], 'moderator'], ['t', TAG]]))
      this.rejoindre(d, true)
      return { ...sent, slug: d, a: `${K.commu}:${me}:${d}` }
    },
    async communautes(limit = 60) {
      const mienne = new Set(extras().communities), seen = new Set(), out = []
      for (const ev of (await lire([{ kinds: [K.commu], '#t': [TAG], limit }])).sort((a, b) => b.created_at - a.created_at)) {
        const d = first(ev.tags, 'd'); if (!d || seen.has(d)) continue; seen.add(d)
        out.push({ slug: d, name: first(ev.tags, 'name', d), description: first(ev.tags, 'description'), by: ev.pubkey, joined: mienne.has(d), a: `${K.commu}:${ev.pubkey}:${d}` })
      }
      return out
    },
    rejoindre(d, on = true) {
      const cs = new Set(extras().communities); on ? cs.add(slug(d)) : cs.delete(slug(d))
      return extrasPropres(extras(), { communities: [...cs] }).communities && (store.set('rh-net-profile', extrasPropres(extras(), { communities: [...cs] })), [...cs].sort())
    },
  }
}
