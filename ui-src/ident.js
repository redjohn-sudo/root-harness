// Your ID, as rootharness/directory.py makes it: your pseudo + 8 characters
// computed from your public key (vincent#k7f2qa9m). And its QR code.
import { sha256 } from '@noble/hashes/sha2.js'
import { hexToBytes } from '@noble/hashes/utils.js'
import qrcode from 'qrcode-generator'

const B32 = 'abcdefghijklmnopqrstuvwxyz234567'

export function code(pubHex) {
  const b = sha256(hexToBytes(pubHex)).slice(0, 5)        // 40 bits -> 8 characters
  let bits = 0n
  for (const x of b) bits = (bits << 8n) | BigInt(x)
  let out = ''
  for (let i = 7; i >= 0; i--) out += B32[Number((bits >> BigInt(i * 5)) & 31n)]
  return out
}
export function slug(pseudo) {
  const s = (pseudo || '').normalize('NFKD').replace(/[^\x00-\x7f]/g, '').toLowerCase().split(/\s+/).filter(Boolean).join('.').replace(/[^a-z0-9._-]+/g, '')
  return s.slice(0, 24).replace(/^[._-]+|[._-]+$/g, '') || 'friend'
}
export const handle = (pseudo, pubHex) => `${slug(pseudo)}#${code(pubHex)}`
export function parse(text) {
  const m = (text || '').toLowerCase().match(/^\s*([a-z0-9._-]{1,24})#([a-z2-7]{8})\s*$/)
  return m ? [m[1], m[2]] : null
}

// a QR code as SVG, black on white so any camera reads it
export function qr(text) {
  const q = qrcode(0, 'M'); q.addData(text); q.make()
  const n = q.getModuleCount(), m = 2
  let rects = ''
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (q.isDark(y, x)) rects += `<rect x="${x + m}" y="${y + m}" width="1" height="1"/>`
  return `<svg viewBox="0 0 ${n + 2 * m} ${n + 2 * m}" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="#fff"/><g fill="#11131c">${rects}</g></svg>`
}
