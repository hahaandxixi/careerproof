import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {createApplicationSubmitSession} from '../src/lib/application-submit-session.ts';

// Real component/session, controlled hooks and API. Not browser acceptance.
const require=createRequire(import.meta.url), React=require('react'), jsx=require('react/jsx-runtime'), {transform}=require('sucrase');
const nodes=n=>!n||typeof n!=='object'?[]:[n,...React.Children.toArray(n.props?.children).flatMap(nodes)];
const text=n=>typeof n==='string'?n:React.Children.toArray(n?.props?.children).map(text).join('');
function mount(overrides={}) {
  let cursor=0, calls=[], refreshes=0, props={reportId:'r',reviewRevision:3,blocked:false,onRefresh:()=>refreshes++};
  const cells=[], effects=[];
  const changed=(a,b)=>!a||a.length!==b.length||a.some((v,i)=>!Object.is(v,b[i]));
  const hooks={
    useState(initial){const i=cursor++;if(!(i in cells))cells[i]=initial;return[cells[i],v=>cells[i]=typeof v==='function'?v(cells[i]):v];},
    useMemo(fn,deps){const i=cursor++;if(changed(cells[i]?.deps,deps))cells[i]={deps,value:fn()};return cells[i].value;},
    useEffect(fn,deps){const i=cursor++;if(changed(cells[i]?.deps,deps)){cells[i]?.cleanup?.();cells[i]={deps};effects.push(()=>cells[i].cleanup=fn());}},
  };
  const modules={react:hooks,'react/jsx-runtime':jsx,'next/link':{__esModule:true,default:(props)=>React.createElement('a',{href:props.href},props.children)},'@/lib/application-submit-session':{createApplicationSubmitSession},'@/lib/api/client':{api:{createApplication:async(...args)=>{calls.push(args);if(overrides.error)throw overrides.error;return{id:'a'};}},errorMessage:e=>e.message}};
  const source=readFileSync(new URL('../src/components/ApplicationSubmit.tsx',import.meta.url),'utf8');
  const mod={exports:{}};
  new Function('require','module','exports',transform(source,{transforms:['typescript','jsx','imports'],jsxRuntime:'automatic',production:true}).code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
  const render=()=>{cursor=0;return mod.exports.default(props);};
  const settle=async()=>{for(let i=0;i<6;i++){render();while(effects.length)effects.shift()();await Promise.resolve();}return render();};
  return {render,settle,setProps(p){props={...props,...p};},get calls(){return calls;},get refreshes(){return refreshes;},check(tree){nodes(tree).find(n=>n.type==='input').props.onChange({target:{checked:true}});},submit(tree){return nodes(tree).find(n=>n.type==='button'&&text(n)==='确认投递');}};
}

test('missing/null/nonpositive/noninteger revision fails closed even if event is invoked',async()=>{
  for(const revision of [undefined,null,0,-1,1.5,NaN,Infinity]) {
    const h=mount();h.setProps({reviewRevision:revision});let tree=await h.settle();
    assert.equal(nodes(tree).find(n=>n.type==='input').props.disabled,true);
    h.check(tree);tree=h.render();assert.equal(h.submit(tree).props.disabled,true);h.submit(tree).props.onClick();await h.settle();assert.equal(h.calls.length,0);
  }
});
test('a synchronized consent submits the displayed revision exactly once while busy',async()=>{
  const h=mount();h.check(await h.settle());let tree=h.render();assert.equal(h.submit(tree).props.disabled,false);
  h.submit(tree).props.onClick();h.submit(tree).props.onClick();tree=await h.settle();assert.deepEqual(h.calls,[['r',3]]);assert.match(text(tree),/已投递/);
  const progress=nodes(tree).find(n=>n.props?.href&&String(n.props.href).includes('#application-a'));assert.ok(progress,'成功入口必须定位新建投递');
});
test('review synchronization revokes consent; successful reread needs another explicit check',async()=>{
  const h=mount();h.check(await h.settle());h.setProps({blocked:true});let tree=await h.settle();
  assert.equal(h.submit(tree).props.disabled,true);assert.equal(nodes(tree).find(n=>n.type==='input').props.checked,false);
  h.submit(tree).props.onClick();h.setProps({blocked:false,reviewRevision:4});tree=await h.settle();assert.equal(h.submit(tree).props.disabled,true);assert.equal(h.calls.length,0);
  h.check(tree);h.submit(h.render()).props.onClick();await h.settle();assert.deepEqual(h.calls,[['r',4]]);
});
test('a revision change invalidates old consent without automatically submitting',async()=>{
  const h=mount();h.check(await h.settle());h.setProps({reviewRevision:5});const tree=await h.settle();assert.equal(h.submit(tree).props.disabled,true);assert.equal(h.calls.length,0);
});
test('version rejection offers read-only recovery and clears consent without a second POST',async()=>{
  const h=mount({error:Object.assign(new Error('报告核对记录已更新，请重新读取后确认投递。'),{status:409})});h.check(await h.settle());h.submit(h.render()).props.onClick();let tree=await h.settle();
  assert.match(text(tree),/已更新/);assert.equal(nodes(tree).find(n=>n.type==='input').props.checked,false);assert.equal(h.submit(tree).props.disabled,true);nodes(tree).find(n=>n.type==='button'&&text(n)==='重新读取报告后确认').props.onClick();tree=await h.settle();
  assert.equal(h.refreshes,1);assert.equal(h.calls.length,1);assert.equal(h.submit(tree).props.disabled,true);
});
