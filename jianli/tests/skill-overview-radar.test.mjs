import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { buildSkillPanorama, skillRecordMeasure } from '../src/lib/skill-panorama.ts';
const require=createRequire(import.meta.url), React=require('react'), jsx=require('react/jsx-runtime'), {transform}=require('sucrase');
function fixture(skills, selected='python') {
 let page=0, picked, prevented=false;
 const modules={react:{useState:()=>[page,v=>{page=typeof v==='function'?v(page):v;}],useEffect:()=>{}}, 'react/jsx-runtime':jsx,
  '@/lib/skill-panorama':{skillRecordMeasure}, './SkillPanorama.module.css':{__esModule:true,default:new Proxy({},{get:(_,key)=>key})}};
 const mod={exports:{}}; const source=readFileSync(new URL('../src/components/SkillOverviewRadar.tsx',import.meta.url),'utf8');
 new Function('require','module','exports',transform(source,{transforms:['typescript','jsx','imports'],jsxRuntime:'automatic',production:true}).code)(id=>{assert.ok(id in modules,id);return modules[id];},mod,mod.exports);
 const render=()=>mod.exports.default({skills,selected,onSelect:key=>{picked=key;}});
 const nodes=n=>!n||typeof n!=='object'?[]:[n,...React.Children.toArray(n.props?.children).flatMap(nodes)];
 return {render,nodes,get picked(){return picked},get prevented(){return prevented},key(node,key){node.props.onKeyDown({key,preventDefault(){prevented=true}})}};
}
const report=(id,items)=>({id,jobId:'job-'+id,jobTitle:'岗位',createdAt:'2026-11-01',materials:[],items});
const item=(id,skill,verdict,extra={})=>({requirementId:id,skill,verdict,requirementTitle:id,...extra});
test('circular radar uses full record counts and preserves unknown and review independently',()=>{
 const a=report('a',[item('1','Python','supported',{confirmationStatus:'rejected'}),item('2','SQL','unsupported'),item('3','pytest','gap'),item('5','FastAPI','claimed_only'),item('6','Git','unsupported')]);
 const b=report('b',[item('4','Python','unsupported')]);
 const skills=buildSkillPanorama([a,b,a]).skills, f=fixture(skills); const nodes=f.nodes(f.render());
 assert.deepEqual(nodes.filter(n=>n.type==='circle'&&n.props.className==='radarRing').map(n=>n.props.r),[28,56,84,112]);
 assert.equal(nodes.filter(n=>n.type==='circle'&&n.props.className==='radarPoint').length,1);
 assert.equal(nodes.filter(n=>n.type==='circle'&&n.props.className==='radarZeroPoint').length,2);
 assert.equal(nodes.some(n=>n.type==='polygon'),true);
 const axes=nodes.filter(n=>n.type==='g'&&n.props.role==='button');assert.equal(axes.length,3);
 assert.match(axes[0].props['aria-label'],/Python，有证据支持 1\/2 条，未评估 1 条，需复核 1 条/);
 assert.ok(!axes.some(axis=>/^(SQL|Git)，/.test(axis.props['aria-label'])));
 const fastApi=axes.find(axis=>axis.props['aria-label'].startsWith('FastAPI，'));
 const focusFrame=f.nodes(fastApi).find(node=>node.props.className==='radarAxisFocus');
 assert.equal(focusFrame.type,'rect');assert.equal(focusFrame.props['aria-hidden'],'true');assert.equal(fastApi.props.tabIndex,0);
 fastApi.props.onClick();assert.equal(f.picked,'fastapi');
 f.key(axes.find(axis=>axis.props['aria-label'].startsWith('pytest，')),'Enter');assert.equal(f.picked,'pytest');assert.equal(f.prevented,true);
});
test('more than eight skills have explicit pages, and fewer than three do not invent axes',()=>{
 const skills=buildSkillPanorama([report('a',Array.from({length:10},(_,i)=>item('r'+i,'skill-'+i,'supported')))]).skills;
 const f=fixture(skills,null);let nodes=f.nodes(f.render());assert.equal(nodes.filter(n=>n.type==='g'&&n.props.role==='button').length,8);
 const next=nodes.find(n=>n.type==='button'&&n.props.children==='下一组');assert.ok(next);next.props.onClick();nodes=f.nodes(f.render());
 assert.equal(nodes.filter(n=>n.type==='g'&&n.props.role==='button').length,0);assert.ok(nodes.some(n=>n.type==='p'&&n.props.children==='本组少于 3 个已评估技能，请从列表查看。'));
});

test('complete records shade the real area including a known zero', () => {
 const skills=buildSkillPanorama([report('a',[item('1','Python','supported'),item('2','SQL','claimed_only'),item('3','pytest','supported')])]).skills;
 const f=fixture(skills); const polygon=f.nodes(f.render()).find(node=>node.type==='polygon');
 assert.ok(polygon.props.points.split(' ').includes('250,225'));
 assert.equal(polygon.props.fill, 'var(--radar-data)');
 assert.equal(polygon.props.fillOpacity, 0.16);
});
