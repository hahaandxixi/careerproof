import {test} from "node:test";
import assert from "node:assert/strict";
import {trackReadRetryFocus} from "../src/lib/read-retry-focus.ts";

function bus(){
  const listeners=new Map();
  return {addEventListener(name,fn){if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn);},
    removeEventListener(name,fn){listeners.get(name)?.delete(fn);},
    emit(name,event={}){for(const fn of listeners.get(name)??[])fn(event);},
    size(){return [...listeners.values()].reduce((n,s)=>n+s.size,0);}};
}
function setup(){
  const frames=[],calls=[],win={...bus(),requestAnimationFrame:fn=>frames.push(fn)};
  const doc={...bus(),body:{},visibilityState:"visible",defaultView:win};
  const element=name=>({ownerDocument:doc,isConnected:true,visible:true,getClientRects(){return this.visible?[{}]:[];},hasAttribute:()=>false,
    focus(options){calls.push({name,options});doc.activeElement=this;doc.emit("focusin",{target:this});}});
  const source=element("retry"),target=element("result"),other=element("other input");
  doc.activeElement=source;let current=true;
  const finish=trackReadRetryFocus(source,()=>target,()=>current);
  const flush=()=>{for(const fn of frames.splice(0))fn();assert.equal(doc.size()+win.size(),0,"listeners must be cleaned after settling");};
  return {source,target,other,doc,win,calls,finish,flush,invalidate(){current=false;}};
}

test("repeated failure keeps the enabled retry focused without scrolling",()=>{
  const h=setup();h.finish();h.flush();assert.deepEqual(h.calls,[{name:"retry",options:{preventScroll:true}}]);
});
test("successful recovery replaces an unmounted button with the related result",()=>{
  const h=setup();h.source.isConnected=false;h.doc.activeElement=h.doc.body;
  h.finish();assert.equal(h.calls.length,0,"wait for the result to commit");h.flush();
  assert.equal(h.doc.activeElement,h.target);assert.equal(h.calls[0].options.preventScroll,true);
});
test("native disabling may already have moved focus to body; use the related result",()=>{
  const h=setup();h.source.hasAttribute=name=>name==="disabled";h.doc.activeElement=h.doc.body;
  h.finish();h.flush();assert.equal(h.doc.activeElement,h.target);
});
for(const moved of ["focus","pointer","Tab","Escape","blur","hidden","generation"]){
  test(`user movement or invalidated context (${moved}) prevents focus stealing`,()=>{
    const h=setup();h.source.isConnected=false;h.doc.activeElement=h.doc.body;
    if(moved==="focus"){h.doc.activeElement=h.other;h.doc.emit("focusin",{target:h.other});}
    if(moved==="pointer")h.doc.emit("pointerdown",{target:h.doc.body});
    if(moved==="Tab"||moved==="Escape")h.doc.emit("keydown",{key:moved});
    if(moved==="blur")h.win.emit("blur");
    if(moved==="hidden")h.doc.visibilityState="hidden";
    if(moved==="generation")h.invalidate();
    h.finish();h.flush();assert.deepEqual(h.calls,[]);
  });
}
test("focus moved during the scheduled React commit is also respected",()=>{
  const h=setup();h.source.isConnected=false;h.doc.activeElement=h.doc.body;h.finish();
  h.doc.emit("pointerdown",{target:h.other});h.flush();assert.deepEqual(h.calls,[]);
});
test("an empty or hidden result is never a focus target",()=>{
  const h=setup();h.source.isConnected=false;h.target.visible=false;h.doc.activeElement=h.doc.body;
  h.finish();h.flush();assert.deepEqual(h.calls,[]);
});
