// The crowd surfaces: the public feed, communities, reposts and badges.
// They are only worth something with many people on the network, so they start
// paused. Your page, your search, your messages and your shares keep working.
// One switch in Settings brings them back on this device; the network code and
// your data are untouched either way.
const CLE = 'rh-foule'

export const FOULE_VUES = ['fil', 'commus']

export function foule() {
  try { return localStorage.getItem(CLE) === '1' } catch { return false }
}

export function reglerFoule(on) {
  try { on ? localStorage.setItem(CLE, '1') : localStorage.removeItem(CLE) } catch {}
}

// A view of the crowd while it is paused falls back to your own page.
export function vueVisible(v) {
  return !foule() && FOULE_VUES.includes(v) ? 'profil' : v
}
