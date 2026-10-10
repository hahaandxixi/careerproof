import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

export function buildFingerprint(root) {
  const hash = createHash('sha256');
  function visit(relative) {
    const file = path.join(root, relative);
    if (!fs.existsSync(file)) { hash.update(`absent:${relative}\0`); return; }
    const stat = fs.lstatSync(file);
    if (stat.isSymbolicLink()) throw new Error('Build inputs must not be symlinks');
    if (stat.isDirectory()) for (const name of fs.readdirSync(file).sort()) visit(path.join(relative, name));
    else hash.update(relative.split(path.sep).join('/') + '\0').update(fs.readFileSync(file)).update('\0');
  }
  for (const name of ['src', 'public', 'package.json', 'package-lock.json', 'next.config.mjs', 'postcss.config.mjs', 'tailwind.config.ts', 'tsconfig.json', 'next-env.d.ts']) visit(name);
  // All next.config inputs that affect our production build are explicit.
  hash.update('BACKEND_ORIGIN=http://127.0.0.1:8000\0NEXT_DIST_DIR=.next\0');
  return hash.digest('hex');
}

export function inspectBuild(root, stampPath) {
  const fingerprint = buildFingerprint(root);
  const buildFile = path.join(root, '.next', 'BUILD_ID');
  let buildId = null, stamp = null;
  if (fs.existsSync(buildFile)) buildId = fs.readFileSync(buildFile, 'utf8').trim();
  try { stamp = JSON.parse(fs.readFileSync(stampPath, 'utf8')); } catch { /* no trusted cache */ }
  const complete = ['routes-manifest.json', 'required-server-files.json', 'server'].every(name => fs.existsSync(path.join(root, '.next', name)));
  return { fingerprint, buildId, reusable: Boolean(complete && buildId && stamp?.root === path.resolve(root) && stamp?.fingerprint === fingerprint && stamp?.buildId === buildId) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [mode, root, stamp] = process.argv.slice(2);
  if (!['inspect', 'record'].includes(mode) || !root || !stamp || process.argv.length !== 5) throw new Error('Usage: local-build-cache.mjs inspect|record root stamp');
  const result = inspectBuild(path.resolve(root), stamp);
  if (mode === 'record') {
    if (!result.buildId || !['routes-manifest.json', 'required-server-files.json', 'server'].every(name => fs.existsSync(path.join(root, '.next', name)))) throw new Error('A complete successful production build is required');
    fs.mkdirSync(path.dirname(stamp), { recursive: true });
    const temporary = stamp + '.tmp';
    fs.writeFileSync(temporary, JSON.stringify({ ...result, root: path.resolve(root) }));
    fs.renameSync(temporary, stamp);
  }
  console.log(JSON.stringify(result));
}
