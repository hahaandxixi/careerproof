// Offline compatibility probe over the actual Next-resolved PostCSS and Sharp.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const args = process.argv.slice(2);
function argument(name, required = true) {
  const index = args.indexOf(name);
  if (index >= 0 && args[index + 1]) return args[index + 1];
  if (required) throw new Error(`Missing ${name}`);
  return null;
}
const projectRoot = path.resolve(argument("--project-root"));
const output = path.resolve(argument("--output"));
if (fs.existsSync(output)) throw new Error("Refusing to overwrite prior evidence");
const require = createRequire(path.join(projectRoot, "package.json"));
const nextRoot = path.dirname(require.resolve("next/package.json"));
const postcss = require(require.resolve("postcss", { paths: [nextRoot] }));
const cases = [
  "a{color:red;--gap:2px;margin:calc(2 * var(--gap))}",
  "@media (min-width:390px){.card:is(.active,.focus){display:grid}}",
  '.中文{content:"合成内容";font-family:"Arial"}',
  '/* synthetic */ .a:hover::before{content:"x"}',
  "@supports(display:grid){a{display:grid}}",
];
const results = [];
for (const css of cases) {
  const result = await postcss([require("autoprefixer")]).process(css, {
    from: "synthetic.css", map: { inline: false, annotation: false },
  });
  results.push({ css: result.css, map: JSON.parse(result.map.toString()) });
}
const baseline = argument("--baseline", false);
if (baseline) {
  assert.deepEqual(results, JSON.parse(fs.readFileSync(baseline, "utf8")).results);
}
const sharp = require("sharp");
const svg = '<svg width="2" height="2" xmlns="http://www.w3.org/2000/svg">'
  + '<rect width="2" height="2" fill="red"/></svg>';
const png = await sharp(Buffer.from(svg)).png().toBuffer();
const metadata = await sharp(png).metadata();
assert.equal(metadata.width, 2);
assert.equal(metadata.height, 2);
assert.equal(metadata.format, "png");
const report = {
  next: require("next/package.json").version,
  postcssVersion: postcss().version,
  sourceMap: require("source-map-js/package.json").version,
  results,
  comparedWithBaseline: Boolean(baseline),
  sharpVersions: sharp.versions,
  syntheticSvg: { width: metadata.width, height: metadata.height, format: metadata.format },
};
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
console.log(JSON.stringify({ next: report.next, postcss: report.postcssVersion, cases: cases.length }));
