// Offline candidate identity: capture inputs before build, seal only unchanged inputs.
// This does not select a runtime profile, start services, or claim browser acceptance.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const front = path.join(root, 'jianli');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const read = p => fs.readFileSync(p);
const json = p => JSON.parse(read(p));
function walk(base, relative = '') {
  return fs.readdirSync(path.join(base, relative), { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name, 'en'))
    .flatMap(entry => {
      const name = relative ? `${relative}/${entry.name}` : entry.name;
      if (entry.isSymbolicLink()) throw new Error(`Link not permitted: ${name}`);
      return entry.isDirectory() ? walk(base, name) : [name];
    });
}
function inputs() {
  const names = [...walk(path.join(front, 'src')).map(p => `src/${p}`),
    ...fs.readdirSync(front).filter(p => /^(package(?:-lock)?\.json|next\.config\..+|tsconfig\.json|next-env\.d\.ts|(?:postcss|tailwind)\.config\..+)$/.test(p)),
    ...(fs.existsSync(path.join(front, 'public')) ? walk(path.join(front, 'public')).map(p => `public/${p}`) : [])].sort();
  return Object.fromEntries(names.map(p => [p, sha(read(path.join(front, p)))]));
}
function equal(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error(`${label} changed`);
}
function artifacts(distDir) {
  const base = path.join(front, distDir);
  const files = walk(base).filter(p => !p.startsWith('cache/') && p !== 'trace');
  return Object.fromEntries(files.map(p => [p, sha(read(path.join(base, p)))]));
}
const [mode, distDir = '.next-candidate-20261104'] = process.argv.slice(2);
if (!/^\.next-candidate-[a-z0-9-]+$/.test(distDir)) throw new Error('Dedicated candidate directory required');
const dir = path.join(root, 'output', 'builds', distDir);
fs.mkdirSync(dir, { recursive: true });
const inputPath = path.join(dir, 'build-input.json');
const manifestPath = path.join(dir, 'artifact-manifest.json');
if (mode === 'capture') {
  if (fs.existsSync(inputPath) || fs.existsSync(path.join(front, distDir))) throw new Error('Existing capture/build must not be overwritten');
  const trackedDiff = execFileSync('git', ['diff', '--binary', '--', 'jianli'], { cwd: root });
  fs.writeFileSync(path.join(dir, 'frontend-input.diff'), trackedDiff);
  fs.writeFileSync(inputPath, JSON.stringify({ schema: 1, capturedAt: new Date().toISOString(),
    distDir, sourceBase: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    dirtyDiffSha256: sha(trackedDiff), inputFiles: inputs(), node: process.version,
    next: json(path.join(front, 'node_modules/next/package.json')).version,
    expectedProxy: 'http://127.0.0.1:8140/:path*' }, null, 2));
  console.log('Captured current source/config/lock/public hashes; no build acceptance yet.');
} else if (mode === 'seal' || mode === 'verify') {
  const captured = json(inputPath);
  equal(distDir, captured.distDir, 'Build directory');
  equal(inputs(), captured.inputFiles, 'Build inputs');
  equal(sha(read(path.join(dir, 'frontend-input.diff'))), captured.dirtyDiffSha256, 'Input diff');
  const base = path.join(front, distDir);
  const buildId = read(path.join(base, 'BUILD_ID')).toString().trim();
  const rewrites = json(path.join(base, 'routes-manifest.json')).rewrites;
  const proxy = (Array.isArray(rewrites) ? rewrites : Object.values(rewrites).flat())
    .filter(p => p.source === '/backend/:path*');
  if (proxy.length !== 1 || proxy[0].destination !== captured.expectedProxy) throw new Error('Compiled proxy differs from candidate contract');
  const actual = { buildId, distDir, inputFiles: captured.inputFiles, artifactFiles: artifacts(distDir) };
  if (mode === 'seal') {
    if (fs.existsSync(manifestPath)) throw new Error('Manifest already sealed');
    fs.writeFileSync(manifestPath, JSON.stringify({ ...captured, sealedAt: new Date().toISOString(), ...actual }, null, 2));
  } else {
    const expected = json(manifestPath);
    for (const key of Object.keys(actual)) equal(actual[key], expected[key], key);
  }
  console.log(`${mode}: ${buildId}; ${Object.keys(actual.inputFiles).length} inputs; ${Object.keys(actual.artifactFiles).length} artifacts`);
} else throw new Error('Usage: candidate-artifact.mjs capture|seal|verify [distDir]');
