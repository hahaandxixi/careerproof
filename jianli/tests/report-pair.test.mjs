import test from 'node:test';
import assert from 'node:assert/strict';
import { createReportPairSession, reportPairLabel } from '../src/lib/report-pair.ts';
const report = (id, extra = {}) => ({ id, jobId: 'job', candidateId: 'owner', createdAt: '2026-11-05T00:00:00Z', analysisMode: 'rules', materials: [{ id: 'fixed-version', kind: 'project', versionNumber: 2 }], ...extra });
const page = items => ({ items, page: 1, pageSize: 50, total: items.length });
const deferred = () => { let resolve, reject; const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; }); return { promise, resolve, reject }; };
function fixture(overrides = {}, initialBaseId = '') {
  let state, listCalls = 0, compareCalls = 0;
  const reports = ['a', 'b', 'c'].map(id => report(id));
  const api = { listReports: async (p, s, filters) => { listCalls++; assert.deepEqual(filters, { jobId: 'job', candidateId: 'owner', scope: 'all' }); return page(reports); }, getReport: async id => reports.find(r => r.id === id), compareReports: async (baseId, targetId) => { compareCalls++; return { baseId, targetId }; }, errorMessage: e => e.message, ...overrides };
  const session = createReportPairSession(reports[1], api, value => { state = value; }, initialBaseId);
  session.activate();
  return { session, get state() { return state; }, get listCalls() { return listCalls; }, get compareCalls() { return compareCalls; } };
}
test('A/B selects any distinct saved reports in the same candidate/job and shows fixed metadata', async () => {
  const h = fixture(); await h.session.loadMore();
  assert.equal(h.state.baseId, 'a'); assert.equal(h.state.targetId, 'b');
  h.session.select('targetId', 'c'); await h.session.compare();
  assert.equal(h.state.value.comparison.targetId, 'c'); assert.equal(h.compareCalls, 1);
  assert.match(reportPairLabel(report('abcd1234-more')), /项目 v2/);
  assert.doesNotMatch(reportPairLabel(report('abcd1234-more')), /abcd1234|fixed-ve|规则分析/);
  h.session.select('baseId', 'c'); await h.session.compare(); assert.equal(h.compareCalls, 1); assert.equal(h.state.value, null); assert.match(h.state.error, /不同/);
});
test('original report is preselected as A while the new report stays B', async () => {
  const h = fixture({}, 'a');
  assert.equal(h.state.baseId, 'a'); assert.equal(h.state.targetId, 'b');
  await h.session.loadMore(); assert.equal(h.state.baseId, 'a'); assert.equal(h.state.targetId, 'b');
  h.session.select('baseId', 'c'); assert.equal(h.state.baseId, 'c');
});
test('same-job candidate scope is checked in listing and again after authorization reads', async () => {
  const h = fixture({ listReports: async () => page([report('a'), report('other-job', { jobId: 'different' }), report('other-owner', { candidateId: 'different' })]), getReport: async id => report(id, { jobId: 'changed' }) });
  await h.session.loadMore(); assert.deepEqual(h.state.reports.map(r => r.id), ['b', 'a']);
  await h.session.compare(); assert.equal(h.state.value, null); assert.match(h.state.error, /不一致/);
});
test('late comparison after a changed selector cannot display the previous pair', async () => {
  const response = deferred();
  const h = fixture({ compareReports: () => response.promise }); await h.session.loadMore();
  const old = h.session.compare(); h.session.select('targetId', 'c'); response.resolve({ baseId: 'a', targetId: 'b' }); await old;
  assert.equal(h.state.value, null); assert.equal(h.state.targetId, 'c'); assert.equal(h.state.busy, false);
});
test('StrictMode setup -> pending load -> cleanup -> setup restarts and rejects late old load', async () => {
  const first = deferred(), second = deferred(); let calls = 0;
  const h = fixture({ listReports: () => (++calls === 1 ? first.promise : second.promise) });
  const old = h.session.loadMore(); assert.equal(h.state.listing, true);
  h.session.dispose(); h.session.activate(); const replay = h.session.loadMore(); assert.equal(calls, 2);
  first.resolve(page([report('stale')])); await old; assert.equal(h.state.listing, true); assert(!h.state.reports.some(r => r.id === 'stale'));
  second.resolve(page([report('a'), report('b')])); await replay; assert.equal(h.state.listing, false); assert.equal(h.state.baseId, 'a');
});
test('disposal rejects old failures and pagination merges authorized rows without duplicate IDs', async () => {
  const old = deferred(); const h = fixture({ listReports: () => old.promise }); const request = h.session.loadMore(); h.session.dispose(); const frozen = h.state;
  old.reject(new Error('old account')); await request; assert.equal(h.state, frozen);
  const pages = fixture({ listReports: async p => ({ items: p === 1 ? [report('a'), report('b')] : [report('a'), report('c')], page: p, pageSize: 2, total: 4 }) });
  await pages.session.loadMore(); await pages.session.loadMore(); assert.deepEqual(pages.state.reports.map(r => r.id), ['b', 'a', 'c']); assert.equal(pages.state.hasMore, false);
});
