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
    isActionRunning: false, networkBusy: false, pendingDetailsId: '', actionError: '', settingsMode: true, opened: false,
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

test('refresh clicks on a busy monitor never enqueue more network requests', () => {
  const {ctx, sent} = widget();
  const busy = JSON.parse(state(1)); busy.network_busy = true;
  ctx.receivePacket(JSON.stringify(busy));
  for (let i = 0; i < 100; i++) ctx.runAction(['update']);
  assert.equal(sent.filter(x => x.args[0] === 'update').length, 0);
  assert.equal(ctx.actionQueue.length, 0);
  assert.equal(ctx.networkBusy, true);
  ctx.receivePacket(state(2));
  ctx.runAction(['update']);
  assert.equal(sent.filter(x => x.args[0] === 'update').length, 1);
});

test('refresh double click is suppressed before busy broadcast arrives', () => {
  const {ctx, sent} = widget();ctx.receivePacket(state(1));
  ctx.runAction(['update']);ctx.runAction(['update']);ctx.runAction(['update']);
  assert.equal(sent.filter(x => x.args[0] === 'update').length, 1);
  assert.equal(ctx.actionQueue.length, 0);
});

test('a cross-monitor race defers details once until the service is idle', () => {
  const {ctx, sent} = widget();ctx.receivePacket(state(1));
  ctx.opened = true;ctx.settingsMode = false;ctx.selectedAccountId = 'a';
  ctx.runAction(['details','a']);
  ctx.receivePacket(JSON.stringify({type:'result',request_id:1,ok:false,code:'busy'}));
  assert.equal(ctx.pendingDetailsId, 'a');
  assert.equal(sent.filter(x => x.args[0] === 'details').length, 1);
  ctx.receivePacket(state(2));
  assert.equal(sent.filter(x => x.args[0] === 'details').length, 2);
  ctx.receivePacket(state(3));
  ctx.receivePacket(JSON.stringify({type:'result',request_id:2,ok:true}));
  ctx.receivePacket(state(4));
  assert.equal(sent.filter(x => x.args[0] === 'details').length, 2);
});

test('settings remain usable during another monitors network query', () => {
  const {ctx, sent} = widget();
  const busy = JSON.parse(state(1));busy.network_busy = true;
  ctx.receivePacket(JSON.stringify(busy));ctx.runAction(['set-initial','a','TR']);
  assert.deepEqual(sent.at(-1).args, ['set-initial','a','TR']);
});

test('failed update releases local state and permits a later retry', () => {
  const {ctx, sent} = widget();ctx.receivePacket(state(1));ctx.runAction(['update']);
  ctx.receivePacket(state(2));
  ctx.receivePacket(JSON.stringify({type:'result',request_id:1,ok:false,error:'temporary failure'}));
  assert.equal(ctx.isActionRunning, false);
  ctx.runAction(['update']);
  assert.equal(sent.filter(x => x.args[0] === 'update').length, 2);
});

test('both refresh buttons and loading more use shared service busy state', () => {
  const panel = fs.readFileSync('Panel.qml','utf8');
  for (const id of ['updateSettingsBtn', 'updateAccountBtn']) {
    const start = panel.indexOf('id: '+id);
    assert.match(panel.slice(start, panel.indexOf('onClicked:',start)), /enabled: !root.isActionRunning && !root.networkBusy/);
  }
  const more = panel.indexOf('onClicked: root.runAction(["more-details"');
  assert.match(panel.slice(more-100,more), /enabled: !root.isActionRunning && !root.networkBusy/);
});
