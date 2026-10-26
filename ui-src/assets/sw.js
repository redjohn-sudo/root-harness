// root-harness on your phone: shows what your computer sends when your agent
// needs you. The content arrives encrypted for this phone only (Web Push).
self.addEventListener('push', (e) => {
  let d = {}
  try { d = e.data.json() } catch {}
  // always show one: phones drop the subscription of a site that pushes silently
  e.waitUntil(self.registration.showNotification(d.title || 'root-harness', {
    body: d.body || '', tag: d.tag || 'root-harness', icon: 'icon-192.png', badge: 'icon-192.png', renotify: true,
  }))
})
self.addEventListener('notificationclick', (e) => {
  e.notification.close()
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((cs) => {
    const c = cs[0]
    return c ? c.focus() : self.clients.openWindow('./')
  }))
})
