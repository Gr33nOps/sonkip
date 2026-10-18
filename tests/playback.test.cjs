const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const functions = source.slice(source.indexOf('  function safe('), source.indexOf('  function formatTime('))
  + source.slice(source.indexOf('  function renderTrackRow('), source.indexOf('  // --- Search ---'));
const track = {id: '0123456789abcdef0123456789abcdef', video_id: 'NMRhx71bGo4', title: 'Let It Happen', artist: 'Tame Impala', extension: 'webm'};
test('completed downloads do not also save to browser Downloads when a music folder is configured', async () => {
  let tick, exports=0;
  const code=source.slice(source.indexOf('  function pollJob('),source.indexOf('  function triggerBrowserDownload('));
  const context={state:{jobPollers:new Map(),activeJobs:new Map(),musicFolder:'D:/Music'},setInterval:fn=>{tick=fn;return 1;},clearInterval:()=>{},
    api:async()=>({status:'complete',track_id:'song',percent:100}),loadLibrary:async()=>{},render:()=>{},showToast:()=>{},triggerBrowserDownload:()=>exports++};
  vm.runInNewContext(code,context);context.pollJob('job','video','Song');await tick();
  assert.equal(exports,0);
});
for (const [local, expected] of [[true, track.id], [false, track.video_id]]) {
  test(`${local ? 'saved' : 'search'} play button targets the correct identifier`, () => {
    const context = {state: {activeJobs: new Map(), library: [track], currentlyPlaying: null, isPlaying: false}, track, local};
    const html = vm.runInNewContext(functions + '\nrenderTrackRow(track, local)', context);
    assert.equal(html.match(/data-play-track="([^"]+)"/)[1], expected);
    assert.equal(html.match(/data-is-local="([^"]+)"/)[1], local ? '1' : '0');
  });
}

test('active downloads expose cancellation for the actual job', () => {
  const context = {state: {activeJobs: new Map([[track.video_id, {id:'job123',status:'downloading',percent:42}]]), library: [], currentlyPlaying:null},track};
  const html=vm.runInNewContext(functions+'\nrenderTrackRow(track,false)',context);
  assert.match(html,/data-cancel-job="job123"/);
});

test('library filtering searches artists and sorts without mutating the library', () => {
  const start=source.indexOf('  function filteredLibrary(');
  const context={state:{library:[{id:'b',title:'Zulu',artist:'Band'},{id:'a',title:'Alpha',artist:'Band'},{id:'c',title:'Else',artist:'Other'}],libraryQuery:'band',librarySort:'title'}};
  vm.runInNewContext(start<0?'':source.slice(start,source.indexOf('  // --- Rendering ---')),context);
  assert.equal(typeof context.filteredLibrary,'function');
  assert.deepEqual(Array.from(context.filteredLibrary(),t=>t.id),['a','b']);
  assert.equal(context.state.library[0].id,'b');
});

test('opening download history twice never creates duplicate pollers', () => {
  let timers=0;
  const code=source.slice(source.indexOf('  function pollJob('),source.indexOf('  function triggerBrowserDownload('));
  const context={state:{jobPollers:new Map()},setInterval:()=>++timers};
  vm.runInNewContext(code,context);
  context.pollJob('one','video','Song');context.pollJob('one','video','Song');
  assert.equal(timers,1);
});

test('song download sends the selected audio format', async () => {
  let request;
  const code=source.slice(source.indexOf('  async function startDownload('),source.indexOf('  function pollJob('));
  const context={state:{audioFormat:'mp3',activeJobs:new Map()},showToast:()=>{},render:()=>{},
    api:async(path,options)=>{request={path,body:JSON.parse(options.body)};return {job_id:'job'};},pollJob:()=>{}};
  vm.runInNewContext(code,context);
  await context.startDownload('NMRhx71bGo4','Let It Happen','Tame Impala');
  assert.deepEqual(request,{path:'/api/downloads',body:{video_id:'NMRhx71bGo4',audio_format:'mp3'}});
});

test('playlist download sends the selected audio format', async () => {
  let request;
  const code=source.slice(source.indexOf('  async function startPlaylist('),source.indexOf('  function updatePlaylistProgress('));
  const nodes=new Map([
    ['playlist-progress',{hidden:true}],['playlist-title',{textContent:''}],['playlist-count',{textContent:''}],
    ['playlist-meter-fill',{style:{width:''}}],
  ]);
  const context={state:{audioFormat:'opus',activeJobs:new Map()},$:id=>nodes.get(id),showToast:()=>{},render:()=>{},pollJob:()=>{},
    api:async(path,options)=>{request={path,body:JSON.parse(options.body)};return {title:'Mix',count:0,jobs:[],review:[],unmatched:[],source_count:0,notice:''};}};
  vm.runInNewContext(code,context);
  await context.startPlaylist('https://music.youtube.com/playlist?list=PLroadtrip');
  assert.deepEqual(request,{path:'/api/playlists',body:{url:'https://music.youtube.com/playlist?list=PLroadtrip',audio_format:'opus'}});
});
