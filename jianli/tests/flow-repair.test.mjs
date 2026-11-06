import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { revealEvidenceAnchor } from '../src/lib/evidence-anchor.ts';
import { flowStepsForLocation, studentFlowLocation, FLOW_STEPS } from '../src/lib/flow-steps.ts';
const require = createRequire(import.meta.url), React = require('react'), { transform } = require('sucrase');
const nodes = node => !node || typeof node !== 'object' ? [] : [node, ...React.Children.toArray(node.props?.children).flatMap(nodes)];
function fixture(hash = '') {
  let selected, effect, tree; const listeners = new Map(), frames = [], targets = new Map(), focus = [];
  const original = { window: globalThis.window, document: globalThis.document, requestAnimationFrame: globalThis.requestAnimationFrame, cancelAnimationFrame: globalThis.cancelAnimationFrame };
  globalThis.window = { location: { hash }, addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name), dispatchEvent: event => { listeners.get(event.type)?.(event); return true; } };
  globalThis.document = { getElementById: id => targets.get(id) ?? null };
  globalThis.requestAnimationFrame = fn => { frames.push(fn); return frames.length; }; globalThis.cancelAnimationFrame = () => {};
  const sections = ['report-matching', 'report-materials', 'report-supplement', 'report-sharing'].map((id, index) => {
    const panel = { id, closest() { return panel; }, parentElement: null, scrollIntoView() {}, focus() { focus.push(id); } }; targets.set(id, panel);
    return { id, label: ['岗位对照', '材料来源', '补充证据', '投递授权'][index], content: React.createElement('input', { defaultValue: 'draft-' + id }) };
  });
  const details = { tagName: 'DETAILS', open: false, parentElement: null };
  targets.set('citation-x', { closest: () => targets.get('report-matching'), parentElement: details, scrollIntoView() {}, focus() { focus.push('citation-x'); } });
  targets.set('application-submit', { closest: () => targets.get('report-sharing'), parentElement: null, scrollIntoView() {}, focus() { focus.push('application-submit'); } });
  const modules = { react: { useState: initial => [selected ?? initial, value => { selected = value; }], useRef: () => ({ current: { contains: () => true } }), useEffect: fn => { effect = fn; } }, 'react/jsx-runtime': require('react/jsx-runtime'), 'react-dom': { flushSync: fn => fn() }, '@/lib/evidence-anchor': { revealEvidenceAnchor } };
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', transform(readFileSync(new URL('../src/components/ReportSections.tsx', import.meta.url), 'utf8'), { transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true }).code)(id => modules[id], mod, mod.exports);
  const render = () => { tree = mod.exports.default({ sections, versions: '项目 V2 · 固定编号' }); return tree; };
  render(); const cleanup = effect(); frames.splice(0).forEach(fn => fn()); render();
  return { render, sections, details, focus, get panels() { return nodes(tree).filter(node => node.props?.['data-report-section'] !== undefined); }, get active() { return nodes(tree).find(node => node.type === 'a' && node.props['aria-current'] === 'location').props.href; }, click(id) { nodes(tree).find(node => node.type === 'a' && node.props.href === '#' + id).props.onClick({}); render(); }, hash(hash) { window.location.hash = hash; listeners.get('hashchange')(); render(); }, cleanup() { cleanup(); assert.equal(listeners.size, 0); Object.assign(globalThis, original); } };
}
test('report directory switches distinct content, keeps every panel mounted and retains child identities', () => {
  const h = fixture(); try {
    assert.equal(h.active, '#report-matching'); assert.equal(h.panels.filter(panel => !panel.props.hidden).length, 1);
    h.click('report-materials'); assert.equal(h.active, '#report-materials'); assert.equal(h.panels.find(panel => !panel.props.hidden).props.id, 'report-materials');
    for (let i = 0; i < h.panels.length; i++) assert.equal(h.panels[i].props.children, h.sections[i].content);
    h.click('report-sharing'); h.click('report-supplement'); assert.equal(h.panels.length, 4); assert.equal(h.active, '#report-supplement');
  } finally { h.cleanup(); }
});
test('source bookmark, disclosure opening, sharing bookmark, back to no hash and focus remain coherent', () => {
  const h = fixture('#application-submit'); try {
    assert.equal(h.active, '#report-sharing'); assert.equal(h.focus.at(-1), 'application-submit');
    h.hash('#citation-x'); assert.equal(h.active, '#report-matching'); assert.equal(h.details.open, true); assert.equal(h.focus.at(-1), 'citation-x');
    h.hash('#report-materials'); assert.equal(h.active, '#report-materials'); h.hash(''); assert.equal(h.active, '#report-matching');
    revealEvidenceAnchor('application-submit'); h.render(); assert.equal(h.active, '#report-sharing');
  } finally { h.cleanup(); }
});
test('journey labels are shared, context is location-only, source report and requirement survive material return', () => {
  assert.deepEqual(FLOW_STEPS.map(step => step.label), ['准备材料', '选择岗位', '查看匹配', '补充材料', '确认投递']);
  assert.equal(studentFlowLocation('/portfolio', 'student', '?sourceReport=r1&sourceRequirement=q1'), 'growth');
  assert.equal(studentFlowLocation('/reports/r1', 'student', '', '#report-sharing'), 'application');
  const steps = flowStepsForLocation('/portfolio', '?sourceReport=r1&sourceRequirement=q1');
  assert.equal(steps.find(step => step.key === 'matching').href, '/reports/r1');
  assert.equal(steps.at(-1).href, '/reports/r1#application-submit');
  assert.match(steps.find(step => step.key === 'growth').href, /sourceRequirement=q1/);
  assert.match(flowStepsForLocation('/jobs').at(-1).unavailableReason, /请先打开/);
});
