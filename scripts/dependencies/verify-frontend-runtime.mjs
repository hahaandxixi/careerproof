// Refuse stale dependencies or a stale source copy before an E2E service starts.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const args = process.argv.slice(2);
function argument(name) {
  const index = args.indexOf(name);
  if (index < 0 || !args[index + 1]) throw new Error(`Missing ${name}`);
  return path.resolve(args[index + 1]);
}
const root = argument("--project-root");
const expected = argument("--expected-root");
const readJson = (file) => JSON.parse(fs.readFileSync(file, "utf8"));
const lock = readJson(path.join(root, "package-lock.json"));
const jsonDigest = (value) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
assert.equal(
  jsonDigest(lock), jsonDigest(readJson(path.join(expected, "package-lock.json"))),
  "Stale frontend lock",
);
assert.deepEqual(
  readJson(path.join(root, "package.json")), readJson(path.join(expected, "package.json")),
  "Stale frontend manifest",
);
const require = createRequire(path.join(root, "package.json"));
function installed(name, from = root) {
  let directory = path.dirname(require.resolve(name, { paths: [from] }));
  while (directory !== path.dirname(directory)) {
    const file = path.join(directory, "package.json");
    if (fs.existsSync(file)) {
      const metadata = readJson(file);
      if (metadata.name === name) {
        const relative = path.relative(root, directory).split(path.sep).join("/");
        assert(!relative.startsWith("../"), "Runtime dependencies must belong to this frontend");
        assert.equal(metadata.version, lock.packages[relative]?.version, `Stale ${name} runtime`);
        return { version: metadata.version, directory };
      }
    }
    directory = path.dirname(directory);
  }
  throw new Error(`Cannot verify ${name} runtime`);
}
const next = installed("next");
const postcss = installed("postcss", next.directory);
const sharp = installed("sharp", next.directory);
const sourceMap = installed("source-map-js", postcss.directory);
function sourceFiles(base) {
  const result = new Map();
  function collect(directory) {
    for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
      const file = path.join(directory, item.name);
      assert(!item.isSymbolicLink(), "Frontend source symlinks are not accepted");
      if (item.isDirectory()) collect(file);
      else if (item.isFile()) {
        const relative = path.relative(base, file).split(path.sep).join("/");
        const text = fs.readFileSync(file, "utf8").replace(/\r\n/g, "\n");
        result.set(relative, createHash("sha256").update(text).digest("hex"));
      }
    }
  }
  collect(path.join(base, "src"));
  for (const name of ["next.config.mjs", "postcss.config.mjs", "tailwind.config.ts"]) {
    const text = fs.readFileSync(path.join(base, name), "utf8").replace(/\r\n/g, "\n");
    result.set(name, createHash("sha256").update(text).digest("hex"));
  }
  return Object.fromEntries([...result].sort(([a], [b]) => a.localeCompare(b)));
}
const source = sourceFiles(root);
const expectedSource = sourceFiles(expected);
const changed = [...new Set([...Object.keys(source), ...Object.keys(expectedSource)])]
  .filter((name) => source[name] !== expectedSource[name]);
if (changed.length) throw new Error(`Stale frontend source copy: ${changed.slice(0, 8).join(", ")}`);
console.log(JSON.stringify({
  next: next.version, nextPostcss: postcss.version, sharp: sharp.version,
  sourceMap: sourceMap.version, sourceFileCount: Object.keys(source).length,
  sourceDigest: createHash("sha256").update(JSON.stringify(source)).digest("hex"),
}));
