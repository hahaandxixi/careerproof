import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { revealEvidenceAnchor } from '../src/lib/evidence-anchor.ts';
import { flowStepsForLocation, studentFlowLocation, FLOW_STEPS } from '../src/lib/flow-steps.ts';
const require = createRequire(import.meta.url), React = require('react'), { transform } = require('sucrase');
const nodes = node => !node || typeof node !== 'object' ? [] : [node, ...React.Children.toArray(node.props?.children).flatMap(nodes)];
function fixture(hash = '') {
  let selected, tree, scrollY = 0;
  const listeners = new Map(), frames = [], targets = new Map(), focus = [], scrolls = [], effects = [];
  const paper = { getBoundingClientRect: () => ({ top: 120 - scrollY }) };
  const siteHeader = { getBoundingClientRect: () => ({ height: 64 }) };
  const original = {
    window: globalThis.window, document: globalThis.document, requestAnimationFrame: globalThis.requestAnimationFrame,
    cancelAnimationFrame: globalThis.cancelAnimationFrame, getComputedStyle: globalThis.getComputedStyle,
  };
  const windowObject = {
    location: { hash },
    get scrollY() { return scrollY; },
    scrollTo: ({ top }) => { scrollY = top; scrolls.push(top); },
    addEventListener: (name, fn) => listeners.set(name, fn),
    removeEventListener: name => listeners.delete(name),
    dispatchEvent: event => { listeners.get(event.type)?.(event); return true; },
  };
  globalThis.window = windowObject;
  globalThis.document = {
    getElementById: id => targets.get(id) ?? null,
    querySelector: selector => selector === '.site-header' ? siteHeader : null,
  };
  globalThis.requestAnimationFrame = fn => { frames.push(fn); return frames.length; };
  globalThis.cancelAnimationFrame = () => {};
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => '80px' });
  const sections = ['report-matching', 'report-materials', 'report-supplement', 'report-sharing'].map((id, index) => {
    const panel = { id, closest() { return panel; }, parentElement: null, scrollIntoView() {}, focus() { focus.push(id); } }; targets.set(id, panel);
    return { id, label: ['岗位对照', '材料来源', '补充证据', '投递授权'][index], content: React.createElement('input', { defaultValue: 'draft-' + id }) };
  });
  const details = { tagName: 'DETAILS', open: false, parentElement: null };
  targets.set('citation-x', { id: 'citation-x', closest: () => targets.get('report-matching'), parentElement: details, getBoundingClientRect: () => ({ top: 220 }), scrollIntoView() {}, focus() { focus.push('citation-x'); } });
  targets.set('application-submit', { id: 'application-submit', closest: () => targets.get('report-sharing'), parentElement: null, getBoundingClientRect: () => ({ top: 240 }), scrollIntoView() {}, focus() { focus.push('application-submit'); } });
  const modules = {
    react: {
      useState: initial => [selected ?? initial, value => { selected = typeof value === 'function' ? value(selected) : value; }],
      useRef: () => ({ current: { contains: () => true, querySelector: () => paper, style: { setProperty() {} } } }),
      useEffect: fn => { effects.push(fn); },
    },
    'react/jsx-runtime': require('react/jsx-runtime'),
    'react-dom': { flushSync: fn => fn() },
    '@/lib/evidence-anchor': {
      revealEvidenceAnchor,
      navigateEvidenceFragment: next => {
        if (windowObject.location.hash === next) return;
        windowObject.location.hash = next;
        listeners.get('hashchange')?.();
      },
    },
  };
  const mod = { exports: {} };
  new Function('require', 'module', 'exports', transform(readFileSync(new URL('../src/components/ReportSections.tsx', import.meta.url), 'utf8'), { transforms: ['typescript', 'jsx', 'imports'], jsxRuntime: 'automatic', production: true }).code)(id => modules[id], mod, mod.exports);
  const render = () => {
    tree = mod.exports.default({
      sections, versions: '项目 V2 · 固定编号',
      header: React.createElement('header', { id: 'report-title' }, '共享报告身份'),
    });
    return tree;
  };
  render();
  const cleanups = effects.map(fn => fn());
  while (frames.length) frames.splice(0).forEach(fn => fn());
  tree = render();
  const flush = () => { while (frames.length) frames.splice(0).forEach(fn => fn()); };
  return {
    render, sections, details, focus, scrolls, flush,
    get scrollY() { return scrollY; },
    get panels() { return nodes(tree).filter(node => node.props?.['data-report-section'] !== undefined); },
    get header() { return nodes(tree).find(node => node.props?.id === 'report-title'); },
    get active() { return nodes(tree).find(node => node.type === 'a' && node.props['aria-current'] === 'location').props.href; },
    click(id) { nodes(tree).find(node => node.type === 'a' && node.props.href === '#' + id).props.onClick({ preventDefault() {} }); flush(); render(); },
    hash(next) { windowObject.location.hash = next; listeners.get('hashchange')(); flush(); render(); },
    cleanup() {
      cleanups.forEach(fn => fn?.());
      assert.equal(listeners.size, 0);
      Object.assign(globalThis, original);
    },
    scrollTo(value) { scrollY = value; },
  };
}
test('report directory switches distinct content, keeps every panel mounted and retains child identities', () => {
  const h = fixture(); try {
    assert.equal(h.active, '#report-matching'); assert.equal(h.panels.filter(panel => !panel.props.hidden).length, 1);
    assert.equal(h.header.props.children, '共享报告身份');
    h.click('report-materials'); assert.equal(h.active, '#report-materials'); assert.equal(h.panels.find(panel => !panel.props.hidden).props.id, 'report-materials');
    for (let i = 0; i < h.panels.length; i++) assert.equal(h.panels[i].props.children, h.sections[i].content);
    h.click('report-sharing'); h.click('report-supplement'); assert.equal(h.panels.length, 4); assert.equal(h.active, '#report-supplement');
  } finally { h.cleanup(); }
});
test('directory switching near the top does not scroll, but deep switching restores the shared reading start', () => {
  const h = fixture(); try {
    h.click('report-materials');
    assert.deepEqual(h.scrolls, []);
    h.scrollTo(600);
    h.click('report-supplement');
    assert.deepEqual(h.scrolls, [40]);
    assert.equal(h.active, '#report-supplement');
    assert.equal(h.focus.length, 0, 'directory switching must not steal focus from the active link');
  } finally { h.cleanup(); }
});
test('source bookmark, disclosure opening, sharing bookmark, back to no hash and focus remain coherent', () => {
  const h = fixture('#application-submit'); try {
    assert.equal(h.active, '#report-sharing');
    assert.equal(h.focus.at(-1), 'application-submit');
    h.hash('#citation-x'); assert.equal(h.active, '#report-matching'); assert.equal(h.details.open, true); assert.equal(h.focus.at(-1), 'citation-x');
    h.hash('#report-materials'); assert.equal(h.active, '#report-materials'); h.hash(''); assert.equal(h.active, '#report-matching');
    revealEvidenceAnchor('application-submit'); h.render(); assert.equal(h.active, '#report-sharing');
  } finally { h.cleanup(); }
});
test('journey labels are shared, context is location-only, source report and requirement survive material return', () => {
  assert.deepEqual(FLOW_STEPS.map(step => step.label), ['准备材料', '选择岗位', '查看匹配', '按需补证', '确认投递']);
  assert.equal(studentFlowLocation('/portfolio', 'student', '?sourceReport=r1&sourceRequirement=q1'), 'growth');
  assert.equal(studentFlowLocation('/reports/r1', 'student', '', '#report-sharing'), 'application');
  const steps = flowStepsForLocation('/portfolio', '?sourceReport=r1&sourceRequirement=q1');
  assert.equal(steps.find(step => step.key === 'matching').href, '/reports/r1');
  assert.equal(steps.find(step => step.key === 'growth').href, '/reports/r1#report-supplement');
  assert.equal(steps.at(-1).href, '/reports/r1#application-submit');
  assert.equal(steps.find(step => step.key === 'growth').href, '/reports/r1#report-supplement');
  assert.match(flowStepsForLocation('/jobs').at(-1).unavailableReason, /请先打开/);
});


