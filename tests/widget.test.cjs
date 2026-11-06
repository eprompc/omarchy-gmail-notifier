const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync('BarWidget.qml', 'utf8');
function widget() {
  const sent = [];
  const ctx = {
    connected: false, stateEpoch: '', stateRevision: -1,
    accounts: [], alerts: {}, actionQueue: [], currentAction: [], requestSequence: 0,
    isActionRunning: false, actionError: '', settingsMode: true, opened: false,
    flashDurationSeconds: 60, flashUntilClicked: false, pollIntervalMinutes: 2,
    fontSizeOffset: 0, panelWidth: 376, language: 'auto', oauthReady: false,
    lastError: '', selectedAccountId: '',
    Commons: {I18n: {language: 'es'}},
    Qt: {callLater: fn => fn()}, clientProcess: {write: line => sent.push(JSON.parse(line))},
    injectPanel() {},
  };
  ctx.root = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync('Model.js', 'utf8').replace(/^\.pragma library\s*/, ''), ctx);
  ctx.Model = ctx;
  for (const name of ['sendPacket', 'receivePacket', 'receiveSnapshot', 'runAction', 'startNextAction']) {
    const start = source.indexOf('  function ' + name + '(');
    let end = source.indexOf('\n  function ', start + 1);
    if (end < 0) end = source.length;
    vm.runInContext(source.slice(start, end), ctx);
  }
  return {ctx, sent};
}
function state(revision, acknowledged = false) {
  return JSON.stringify({type: 'state', epoch: 'epoch1', revision, ok: true,
    accounts: [{id: 'a', unread_count: 1, messages: [], details_ready: false}],
    alerts: {a: {event_id: 'one', expires_at: 0, acknowledged}}});
}
test('late snapshots cannot reactivate acknowledged events', () => {
  const {ctx} = widget();
  ctx.receivePacket(state(2, true)); ctx.receivePacket(state(1, false));
  assert.equal(ctx.alerts.a.acknowledged, true);
  assert.equal(ctx.stateRevision, 2);
});
test('configuration actions are queued and processed without silent loss', () => {
  const {ctx, sent} = widget(); ctx.receivePacket(state(1));
  ctx.runAction(['set-initial', 'a', 'TR']); ctx.runAction(['set-enabled', 'a', 'false']);
  assert.equal(sent.filter(x => x.request_id > 0).length, 1);
  ctx.receivePacket(JSON.stringify({type:'result',request_id:1,ok:true}));
  assert.equal(sent.filter(x => x.request_id > 0).length, 2);
  assert.deepEqual(sent.at(-1).args, ['set-enabled','a','false']);
});
test('incomplete snapshots do not trigger repeated detail queries', () => {
  const {ctx, sent} = widget(); ctx.opened = true; ctx.settingsMode = false; ctx.selectedAccountId = 'a';
  ctx.receivePacket(state(1)); ctx.receivePacket(state(2));
  assert.equal(sent.filter(x => x.args[0] === 'details').length, 0);
});
test('a new service epoch is accepted after reconnecting', () => {
  const {ctx} = widget();ctx.receivePacket(state(10));ctx.connected=false;
  const fresh=JSON.parse(state(1));fresh.epoch='epoch2';ctx.receivePacket(JSON.stringify(fresh));
  assert.equal(ctx.stateEpoch,'epoch2');assert.equal(ctx.stateRevision,1);
});
