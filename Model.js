.pragma library

function visibleAccounts(accounts) {
  if (!Array.isArray(accounts)) return []
  return accounts.filter(function(account) {
    return account.enabled !== false && messageCount(account) > 0
  })
}

function enabledAccounts(accounts) {
  if (!Array.isArray(accounts)) return []
  return accounts.filter(function(account) { return account.enabled !== false })
}

function accountById(accounts, id) {
  if (!Array.isArray(accounts)) return null
  for (var i = 0; i < accounts.length; i++) {
    if (accounts[i].id === id) return accounts[i]
  }
  return null
}

function messageCount(account) {
  if (!account) return 0
  if (Number.isFinite(Number(account.unread_count))) return Number(account.unread_count)
  if (!Array.isArray(account.messages)) return 0
  return account.messages.length
}

function normalizedInitial(value, email) {
  var candidate = String(value || "").trim()
  if (candidate.length > 0) return candidate.toLocaleUpperCase()
  var local = String(email || "").split("@")[0]
  return local.length > 0 ? local.substring(0, 1).toLocaleUpperCase() : "?"
}


// Shared timestamps keep all monitor instances on the same flash phase.
function isAlertActive(alert, now) {
  return !!alert && !!alert.event_id && alert.acknowledged !== true
    && (Number(alert.expires_at) === 0 || Number(alert.expires_at) > now)
}

function alertPhase(alert, now) {
  return Math.floor((now - Number((alert || {}).started_at || 0)) / 500) % 2 === 0
}
