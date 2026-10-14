const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const functions = source.slice(source.indexOf('  function safe('), source.indexOf('  function formatTime('))
  + source.slice(source.indexOf('  function renderTrackRow('), source.indexOf('  // --- Search ---'));
const track = {id: '0123456789abcdef0123456789abcdef', video_id: 'NMRhx71bGo4', title: 'Let It Happen', artist: 'Tame Impala', extension: 'webm'};
for (const [local, expected] of [[true, track.id], [false, track.video_id]]) {
  test(`${local ? 'saved' : 'search'} play button targets the correct identifier`, () => {
    const context = {state: {activeJobs: new Map(), library: [track], currentlyPlaying: null, isPlaying: false}, track, local};
    const html = vm.runInNewContext(functions + '\nrenderTrackRow(track, local)', context);
    assert.equal(html.match(/data-play-track="([^"]+)"/)[1], expected);
    assert.equal(html.match(/data-is-local="([^"]+)"/)[1], local ? '1' : '0');
  });
}
