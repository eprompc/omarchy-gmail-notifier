const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const root = process.cwd();
const manifest = JSON.parse(fs.readFileSync(root + '/manifest.json', 'utf8'));

test('manifest matches the Omarchy 4.5 community bar-widget contract', () => {
  assert.equal(manifest.schemaVersion, 1);
  for (const field of ['id', 'name', 'version', 'author', 'description']) {
    assert.equal(typeof manifest[field], 'string');
    assert.ok(manifest[field].trim().length > 0);
  }
  assert.match(manifest.id, /^[a-z0-9][a-z0-9._-]*$/);
  assert.doesNotMatch(manifest.id, /\.\./);
  assert.ok(!manifest.id.startsWith('omarchy.'));
  assert.deepEqual(manifest.kinds, ['bar-widget']);
  assert.equal(manifest.entryPoints.barWidget, 'BarWidget.qml');
  assert.equal(manifest.barWidget.displayName, 'Gmail Notifier');
  assert.equal(typeof manifest.barWidget.description, 'string');
  assert.ok(manifest.barWidget.description.length > 0);
  assert.equal(manifest.barWidget.category, 'Productivity');
  assert.equal(manifest.barWidget.allowMultiple, false);
  assert.ok(['left', 'center', 'right'].includes(manifest.barWidget.defaultSection));
  assert.ok(fs.existsSync(root + '/' + manifest.entryPoints.barWidget));
});
