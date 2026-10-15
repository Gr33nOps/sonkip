const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function load(wpc) {
  const context = {window: {top: {'havuokmhhs-0': {bevasrs: {wpc}}}},
    setTimeout: (fn) => fn()};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('android/app/src/main/assets/mint-token.js', 'utf8'), context);
  return context;
}

test('returns a per-video token after the provider becomes ready', async () => {
  let attempts = 0;
  const context = load(async () => ({mws: async ({c}) => {
    if (++attempts < 3) throw Error('SDF:notready');
    return c === 'NMRhx71bGo4' ? 'public-video-token' : null;
  }}));
  assert.equal(await context.sonkipMint('NMRhx71bGo4'), 'public-video-token');
});

test('reports unavailable provider rather than returning an invalid token', async () => {
  await assert.rejects(load(undefined).sonkipMint('NMRhx71bGo4'), /unavailable/);
});

test('rejects empty tokens and does not swallow unexpected provider errors', async () => {
  await assert.rejects(load(async () => ({mws: async () => ''})).sonkipMint('NMRhx71bGo4'), /empty/);
  await assert.rejects(load(async () => {throw Error('Network failed');}).sonkipMint('NMRhx71bGo4'), /Network failed/);
});
