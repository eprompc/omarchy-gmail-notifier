const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const model = vm.createContext({});
vm.runInContext(fs.readFileSync('Model.js', 'utf8').replace(/^\.pragma library\s*/, ''), model);

test('all monitors share activity, deadline and phase', () => {
  const alert = {event_id: 'one', started_at: 1000, expires_at: 61000, acknowledged: false};
  assert.equal(model.isAlertActive(alert, 60000), true);
  assert.equal(model.isAlertActive(alert, 61000), false);
  assert.equal(model.alertPhase(alert, 1000), true);
  assert.equal(model.alertPhase(alert, 1500), false);
  assert.equal(model.alertPhase(alert, 2000), true);
});
test('acknowledged events remain silent even after widget recreation', () => {
  assert.equal(model.isAlertActive({event_id: 'one', expires_at: 0, acknowledged: true}, 1000), false);
  assert.equal(model.isAlertActive({event_id: 'two', expires_at: 0, acknowledged: false}, 1e12), true);
  assert.equal(model.isAlertActive(undefined, 1000), false);
});
test('paused accounts and empty inboxes are hidden', () => {
  assert.equal(model.visibleAccounts([{enabled: false, unread_count: 5}, {unread_count: 0}]).length, 0);
});
