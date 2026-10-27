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

test('track actions keep accessible names when their visible labels are hidden', () => {
  const context = {state: {activeJobs: new Map(), library: [], currentlyPlaying: null, isPlaying: false}, track};
  const searchHtml = vm.runInNewContext(functions + '\nrenderTrackRow(track, false)', context);
  assert.match(searchHtml, /aria-label="Download Let It Happen"/);

  context.state.library = [track];
  const savedHtml = vm.runInNewContext(functions + '\nrenderTrackRow(track, true)', context);
  assert.match(savedHtml, /aria-label="Download Let It Happen to this device"/);
  assert.match(savedHtml, /aria-label="Delete Let It Happen from library"/);
});

test('track artwork reserves its rendered dimensions', () => {
  const artworkTrack = {...track, thumbnail: 'https://example.test/cover.jpg'};
  const context = {state: {activeJobs: new Map(), library: [], currentlyPlaying: null, isPlaying: false}, track: artworkTrack};
  const html = vm.runInNewContext(functions + '\nrenderTrackRow(track, false)', context);
  assert.match(html, /class="track-artwork"[^>]*width="56"[^>]*height="56"/);
});

test('download mode is exposed as a pressed-button choice', () => {
  const nodes = new Map([
    ['mode-song', {classList: {toggle() {}}, attrs: {}, setAttribute(name, value) { this.attrs[name] = value; }}],
    ['mode-playlist', {classList: {toggle() {}}, attrs: {}, setAttribute(name, value) { this.attrs[name] = value; }}],
    ['search-input', {placeholder: '', focus() {}}],
    ['input-hint', {textContent: ''}],
  ]);
  const code = source.slice(source.indexOf('  function setInputMode('), source.indexOf('  function renderPlaylistPreview('));
  const context = {state: {}, $: id => nodes.get(id)};
  vm.runInNewContext(code, context);
  context.setInputMode('playlist');
  assert.equal(nodes.get('mode-song').attrs['aria-pressed'], 'false');
  assert.equal(nodes.get('mode-playlist').attrs['aria-pressed'], 'true');
});

test('playlist preview uses a placeholder instead of requesting an empty image URL', () => {
  const nodes = new Map([
    ['playlist-preview', {hidden: true, innerHTML: ''}],
    ['playlist-selection-count', {textContent: ''}],
    ['playlist-save', {disabled: false}],
  ]);
  const helpers = source.slice(source.indexOf('  function safe('), source.indexOf('  function renderAuthStatus('));
  const renderer = source.slice(source.indexOf('  function renderPlaylistPreview('), source.indexOf('  async function startPlaylist('));
  const context = {
    state: {playlist: {entries: [{video_id: 'NMRhx71bGo4', title: 'Song', artist: 'Artist'}]}, playlistSelected: new Set()},
    $: id => nodes.get(id),
  };
  vm.runInNewContext(helpers + renderer, context);
  context.renderPlaylistPreview();
  assert.doesNotMatch(nodes.get('playlist-preview').innerHTML, /<img[^>]*src=""/);
  assert.match(nodes.get('playlist-preview').innerHTML, /artwork-placeholder/);
});

test('library filtering searches artists and sorts without mutating the library', () => {
  const start=source.indexOf('  function filteredLibrary(');
  const context={state:{library:[{id:'b',title:'Zulu',artist:'Band'},{id:'a',title:'Alpha',artist:'Band'},{id:'c',title:'Else',artist:'Other'}],libraryQuery:'band',librarySort:'title'}};
  vm.runInNewContext(start<0?'':source.slice(start,source.indexOf('  // --- Rendering ---')),context);
  assert.equal(typeof context.filteredLibrary,'function');
  assert.deepEqual(Array.from(context.filteredLibrary(),t=>t.id),['a','b']);
  assert.equal(context.state.library[0].id,'b');
});

test('select all chooses every visible library song and can clear the selection', () => {
  const start=source.indexOf('  function filteredLibrary(');
  const end=source.indexOf('  // --- Rendering ---');
  const context={state:{library:[{id:'a',title:'Alpha',artist:'Band'},{id:'b',title:'Beta',artist:'Band'},{id:'c',title:'Else',artist:'Other'}],libraryQuery:'band',librarySort:'newest',selectedTracks:new Set()},render:()=>{}};
  vm.runInNewContext(start<0?'':source.slice(start,end),context);
  assert.equal(typeof context.selectAllVisible,'function');
  context.selectAllVisible();
  assert.deepEqual(Array.from(context.state.selectedTracks),['a','b']);
  context.clearLibrarySelection();
  assert.deepEqual(Array.from(context.state.selectedTracks),[]);
});

test('a fresh browser defaults to compatible M4A but preserves an existing choice', () => {
  const start=source.indexOf('  const state = {');
  const end=source.indexOf('  const $');
  const readDefault=(saved)=>{
    const context={localStorage:{getItem:key=>key==='sonkip-audio-format'?saved:null}};
    vm.runInNewContext(source.slice(start,end)+'\nresult=state.audioFormat;',context);
    return context.result;
  };
  assert.equal(readDefault(null),'m4a');
  assert.equal(readDefault('mp3'),'mp3');
});

test('first-run setup saves format and artwork choices and offers the music folder', () => {
  const code=source.slice(source.indexOf('  function showFirstRunSetup('),source.indexOf('  function renderTrackRow('));
  const nodes=new Map([
    ['setup-dialog',{showModal(){this.open=true;},close(){this.open=false;}}],
    ['setup-format',{value:'opus'}], ['setup-artwork',{checked:false}],
    ['setup-folder',{checked:true}], ['audio-format',{value:'m4a'}],
    ['embed-metadata',{checked:true}], ['music-folder',{click(){this.clicked=true;}}],
  ]);
  const saved={};
  const context={state:{audioFormat:'m4a',embedMetadata:true},$:id=>nodes.get(id),
    localStorage:{getItem:()=>null,setItem:(key,value)=>saved[key]=value}};
  vm.runInNewContext(code,context);
  context.showFirstRunSetup();
  assert.equal(nodes.get('setup-dialog').open,true);
  nodes.get('setup-format').value='opus';
  nodes.get('setup-artwork').checked=false;
  context.finishFirstRunSetup();
  assert.equal(saved['sonkip-audio-format'],'opus');
  assert.equal(saved['sonkip-embed-metadata'],'false');
  assert.equal(saved['sonkip-setup-complete'],'true');
  assert.equal(nodes.get('music-folder').clicked,true);
});

test('opening download history twice never creates duplicate pollers', () => {
  let timers=0;
  const code=source.slice(source.indexOf('  function pollJob('),source.indexOf('  function triggerBrowserDownload('));
  const context={state:{jobPollers:new Map()},setInterval:()=>++timers};
  vm.runInNewContext(code,context);
  context.pollJob('one','video','Song');context.pollJob('one','video','Song');
  assert.equal(timers,1);
});

test('song download sends the selected audio format and metadata preference', async () => {
  let request;
  const code=source.slice(source.indexOf('  async function startDownload('),source.indexOf('  function pollJob('));
  const context={state:{audioFormat:'mp3',embedMetadata:false,activeJobs:new Map()},showToast:()=>{},render:()=>{},
    api:async(path,options)=>{request={path,body:JSON.parse(options.body)};return {job_id:'job'};},pollJob:()=>{}};
  vm.runInNewContext(code,context);
  await context.startDownload('NMRhx71bGo4','Let It Happen','Tame Impala');
  assert.deepEqual(request,{path:'/api/downloads',body:{video_id:'NMRhx71bGo4',audio_format:'mp3',embed_metadata:false}});
});

test('playlist preview selects every track and waits for explicit save', async () => {
  let request, polls=0;
  const code=source.slice(source.indexOf('  async function startPlaylist('),source.indexOf('  function updatePlaylistProgress('));
  const nodes=new Map([
    ['playlist-progress',{hidden:true}],['playlist-title',{textContent:''}],['playlist-count',{textContent:''}],
    ['playlist-meter-fill',{style:{width:''}}],
    ['playlist-preview',{hidden:true}],['playlist-preview-actions',{hidden:true}],
  ]);
  const context={state:{audioFormat:'opus',embedMetadata:true,activeJobs:new Map(),playlistSelected:new Set()},$:id=>nodes.get(id),showToast:()=>{},render:()=>{},renderPlaylistPreview:()=>{},pollJob:()=>polls++,
    api:async(path,options)=>{request={path,body:JSON.parse(options.body)};return {preview_id:'preview',title:'Mix',count:2,entries:[{video_id:'NMRhx71bGo4'},{video_id:'M7lc1UVf-VE'}],unmatched:[],source_count:2,notice:''};}};
  vm.runInNewContext(code,context);
  await context.startPlaylist('https://music.youtube.com/playlist?list=PLroadtrip');
  assert.deepEqual(request,{path:'/api/playlists',body:{url:'https://music.youtube.com/playlist?list=PLroadtrip'}});
  assert.deepEqual(Array.from(context.state.playlistSelected),['NMRhx71bGo4','M7lc1UVf-VE']);
  assert.equal(polls,0);
});
