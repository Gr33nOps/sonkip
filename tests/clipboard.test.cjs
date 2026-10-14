const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Execute the real registered handler with browser clipboard permission states.
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const handler = source.slice(source.indexOf('  const copyInstallButton ='), source.indexOf('  const authDialog ='));
function setup(clipboard) {
  let click;
  let selected = false;
  const button = { textContent: 'COPY COMMAND', addEventListener: (_, fn) => { click = fn; } };
  const command = { textContent: '  example install command  ' };
  vm.runInNewContext(handler, {
    $: id => id === 'copy-install-command' ? button : command,
    navigator: { clipboard }, setTimeout: () => {}, showToast: () => {},
    document: {
      createElement: () => ({style: {}, select() {}, remove() {}}),
      body: {appendChild() {}},
      // Reproduce an embedded browser reporting success without changing clipboard.
      execCommand: () => true,
      createRange: () => ({selectNodeContents(node) { assert.equal(node, command); }}),
    },
    window: {getSelection: () => ({removeAllRanges() {}, addRange() { selected = true; }})},
  });
  return { click: () => click(), button, selected: () => selected };
}
test('writes the actual command even if legacy copy would report success', async () => {
  let contents = 'stale Android package table';
  const ui = setup({writeText: async text => { contents = text; }});
  await ui.click();
  assert.equal(contents, 'example install command');
  assert.equal(ui.button.textContent, 'COPIED ✓');
});
test('blocked clipboard selects command without falsely claiming copied', async () => {
  const ui = setup({writeText: async () => { throw new Error('Permission denied'); }});
  await ui.click();
  assert.equal(ui.selected(), true);
  assert.match(ui.button.textContent, /COPY MANUALLY/);
});
test('missing clipboard API offers manual selection', async () => {
  const ui = setup(undefined);
  await ui.click();
  assert.equal(ui.selected(), true);
  assert.match(ui.button.textContent, /COPY MANUALLY/);
});
