const assert = require('node:assert/strict');
const test = require('node:test');

const { detectPlatform, getPlatformDownload } = require('../static/platform.js');

test('detects Android before Linux from its user agent', () => {
  assert.equal(
    detectPlatform({
      userAgent: 'Mozilla/5.0 (Linux; Android 15; Pixel 9)',
      platform: 'Linux armv8l',
    }),
    'android',
  );
});

test('detects Windows, macOS, and desktop Linux', () => {
  assert.equal(detectPlatform({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }), 'windows');
  assert.equal(detectPlatform({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' }), 'macos');
  assert.equal(detectPlatform({ userAgent: 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64)' }), 'linux');
});

test('returns the matching download and setup command', () => {
  assert.deepEqual(getPlatformDownload('android'), {
    label: 'ANDROID',
    button: 'DOWNLOAD FOR ANDROID (.APK)',
    href: 'https://github.com/Gr33nOps/sonkip/releases/download/v2.4.1/Sonkip-2.4.1.apk',
    commandLabel: '',
    command: '',
  });
  assert.equal(getPlatformDownload('windows').command.startsWith('irm https://'), true);
  assert.equal(getPlatformDownload('macos').button, 'DOWNLOAD FOR MAC (.ZIP)');
  assert.equal(getPlatformDownload('linux').button, 'DOWNLOAD FOR LINUX (.TAR.GZ)');
});
