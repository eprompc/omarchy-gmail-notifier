const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const ctx = vm.createContext({});
const source = fs.readFileSync('SetupHelp.js', 'utf8');
vm.runInContext(source.replace(/^\.pragma library\s*/, ''), ctx);
const {render} = require('../scripts/render-setup-docs.cjs');

test('guide follows English/Spanish regional locales and falls back to English', () => {
  assert.equal(ctx.guide('en-GB').title, 'Set up Google sign-in');
  assert.equal(ctx.guide('es-ES').title, 'Configura el acceso con Google');
  assert.equal(ctx.guide('es_MX').title, ctx.guide('es').title);
  assert.equal(ctx.guide('de').title, ctx.guide('en').title);
  assert.equal(ctx.guide(undefined).title, ctx.guide('en').title);
});

test('both languages have complete steps, matching official destinations and recovery advice', () => {
  const en = ctx.guide('en'); const es = ctx.guide('es');
  assert.equal(en.steps.length, 8);assert.equal(es.steps.length, 8);
  assert.equal(en.problems.length, es.problems.length);
  for (let i = 0; i < en.steps.length; i++) {
    assert.notEqual(en.steps[i].title, es.steps[i].title);
    assert.equal(en.steps[i].paragraphs.length, es.steps[i].paragraphs.length);
    assert.equal(en.steps[i].links.length, es.steps[i].links.length);
    for (let j = 0; j < en.steps[i].links.length; j++) {
      assert.equal(new URL(en.steps[i].links[j].url).searchParams.get('hl'), 'en');
      assert.equal(new URL(es.steps[i].links[j].url).searchParams.get('hl'), 'es');
      assert.equal(en.steps[i].links[j].url.replace('?hl=en',''), es.steps[i].links[j].url.replace('?hl=es',''));
    }
  }
  assert.match(en.existing, /ORIGINAL/);assert.match(es.existing, /ORIGINAL/);
  assert.match(en.problems.join(' '), /seven days/);
  assert.match(es.problems.join(' '), /siete días/);
  assert.equal(en.steps[3].code, 'https://www.googleapis.com/auth/gmail.metadata');
  assert.equal(es.steps[3].code, en.steps[3].code);
  assert.equal(en.steps[5].location, '~/.config/omarchy/gmail-notifier/oauth-client.json');
  assert.doesNotMatch(en.steps.map(s=>s.code||'').join('\n'), /rm |cp |client_secret|refresh_token/);
});

test('link opener admits only fixed official Google help URLs in supported locales', () => {
  for (const locale of ['en','es']) {
    const help = ctx.guide(locale);
    for (const link of help.steps.flatMap(s=>s.links).concat(help.supportLinks)) {
      assert.equal(ctx.allowedLink(link.url), true);
      const url = new URL(link.url);
      assert.equal(url.protocol, 'https:');
      assert.ok(['console.cloud.google.com','developers.google.com','support.google.com'].includes(url.hostname));
    }
  }
  for (const url of ['file:///etc/passwd','javascript:alert(1)','https://example.invalid',
      'https://console.cloud.google.com.evil.invalid/auth/clients?hl=en',
      'https://console.cloud.google.com/auth/clients?hl=en&email=private@example.invalid'])
    assert.equal(ctx.allowedLink(url), false);
});

test('published language guides stay in sync with the actual in-app help', () => {
  for (const locale of ['en','es']) assert.equal(fs.readFileSync('docs/OAUTH_SETUP.'+locale+'.md','utf8'), render(locale));
});

test('saved-account recovery never instructs users to create another Google client', () => {
  for (const locale of ['en','es']) {
    const recovery = ctx.guide(locale, true);
    assert.equal(recovery.steps.length, 3);
    assert.equal(recovery.steps.flatMap(s=>s.links).length, 0);
    assert.equal(recovery.steps[1].location, '~/.config/omarchy/gmail-notifier/oauth-client.json');
    assert.match(recovery.existing, /ORIGINAL/);
  }
});

test('help is read-only until explicit check or connect and protects existing users', () => {
  const qml = fs.readFileSync('OAuthSetupHelp.qml','utf8');
  const panel = fs.readFileSync('Panel.qml','utf8');
  assert.match(qml, /language === "auto" \? Commons.I18n.language : language/);
  assert.match(qml, /root.oauthReady && !root.hasAccounts/);
  assert.match(panel, /if \(!root.oauthReady \|\| root.accounts.length > 0\) return/);
  assert.match(panel, /root.settingsMode && !root.oauthReady && !root.helpMode/);
  assert.match(panel, /onCheckRequested: root.runAction\(\["check-setup"\]\)/);
  // Account creation must remain discoverable before setup is complete.
  const start = panel.indexOf('objectName: "addGmailAccountButton"');
  assert.ok(start > 0);
  const add = panel.slice(start, panel.indexOf('onClicked: root.addAccount()', start));
  assert.match(add, /"Add Gmail account"/);
  assert.doesNotMatch(add, /visible: root.oauthReady|enabled: root.oauthReady/);
  assert.doesNotMatch(qml+'\n'+source, /Component.onCompleted|\bProcess\s*\{|XMLHttpRequest|fetch\(/);
  for (const locale of ['en','es']) {
    const catalog=JSON.parse(fs.readFileSync('i18n/'+locale+'.json','utf8'));
    assert.equal(typeof catalog['HELP — Set up Google'], 'string');
  }
});

test('Add account guides a new user until setup is ready and never launches OAuth early', () => {
  const panel = fs.readFileSync('Panel.qml','utf8');
  const start = panel.indexOf('  function addAccount(');
  const end = panel.indexOf('\n  function ', start+1);
  const calls=[];
  const context=vm.createContext({oauthReady:false,lastError:'',
    showSetupHelp:()=>calls.push('help'),runAction:args=>calls.push(Array.from(args))});
  vm.runInContext(panel.slice(start,end),context);
  context.addAccount();
  assert.deepEqual(calls,['help']);
  context.oauthReady=true;context.addAccount();
  assert.deepEqual(calls,['help',['add-account']]);
});
