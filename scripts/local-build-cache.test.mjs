import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { inspectBuild } from './local-build-cache.mjs';

const root = fs.mkdtempSync(path.resolve('backend/.tmp/local-cache-test-'));
const frontend = path.join(root, 'frontend'), stamp = path.join(root, 'stamp.json');
fs.mkdirSync(path.join(frontend, 'src'), { recursive: true });
fs.mkdirSync(path.join(frontend, 'public'));
fs.writeFileSync(path.join(frontend, 'src', 'page.tsx'), 'v1');
fs.writeFileSync(path.join(frontend, 'package-lock.json'), '{"version":1}');
test.after(() => {
  const workspace = path.resolve('backend/.tmp');
  assert(root.startsWith(workspace + path.sep));
  fs.rmSync(root, { recursive: true });
});
function record() {
  const result = spawnSync(process.execPath, ['scripts/local-build-cache.mjs', 'record', frontend, stamp], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr);
}
test('an absent or partial build cannot receive a trusted stamp', () => {
  fs.mkdirSync(path.join(frontend, '.next'));
  fs.writeFileSync(path.join(frontend, '.next', 'BUILD_ID'), 'build-1');
  const result = spawnSync(process.execPath, ['scripts/local-build-cache.mjs', 'record', frontend, stamp], { encoding: 'utf8' });
  assert.notEqual(result.status, 0);
  assert(!fs.existsSync(stamp));
  assert.equal(inspectBuild(frontend, stamp).reusable, false);
});
test('unchanged complete build is reused, source/public/lock changes invalidate it', () => {
  fs.mkdirSync(path.join(frontend, '.next', 'server'));
  for (const name of ['routes-manifest.json', 'required-server-files.json']) fs.writeFileSync(path.join(frontend, '.next', name), '{}');
  record();
  assert.equal(inspectBuild(frontend, stamp).reusable, true);
  for (const name of ['src/page.tsx', 'public/logo.svg', 'package-lock.json', 'next.config.mjs']) {
    fs.writeFileSync(path.join(frontend, name), 'changed');
    assert.equal(inspectBuild(frontend, stamp).reusable, false, name);
    record();
    assert.equal(inspectBuild(frontend, stamp).reusable, true);
  }
});
test('build identity, deleted artifacts and corrupted stamp invalidate cache', () => {
  fs.writeFileSync(path.join(frontend, '.next', 'BUILD_ID'), 'build-2');
  assert.equal(inspectBuild(frontend, stamp).reusable, false);
  record();
  fs.unlinkSync(path.join(frontend, '.next', 'routes-manifest.json'));
  assert.equal(inspectBuild(frontend, stamp).reusable, false);
  fs.writeFileSync(stamp, '{broken');
  assert.equal(inspectBuild(frontend, stamp).reusable, false);
});
