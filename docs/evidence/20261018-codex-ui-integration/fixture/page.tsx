"use client";
import { useEffect, useState } from 'react';
import MaterialPreview from '@/components/MaterialPreview';
import TaskView from '@/components/TaskView';
import {api, type AnalysisTask} from '@/lib/api/client';
import type {ProjectFileContent} from '@/lib/api/domain';

let releaseFile: (()=>void)|null = null;
let activeStream: SyntheticStream|null = null;
let mode = 'running';
const task = ():AnalysisTask => ({
  id:'synthetic-task',taskType:'match',status:mode==='running'?'running':mode==='failed'?'failed':'completed',
  progress:mode==='running'?40:mode==='failed'?50:100,currentStep:mode==='running'?'正在读取材料并检索候选证据':'本次处理已结束',
  errorMessage:mode==='failed'?'合成任务失败，不代表真实业务故障':null,
  totalCostRmb:'0',createdAt:'2026-10-18T06:00:00Z',startedAt:'2026-10-18T06:00:01Z',
  completedAt:mode==='running'?null:'2026-10-18T06:00:12Z',reportId:null,
  steps:mode==='failed'?[{step:1,eventType:'verification.unavailable',name:'核验不可用',detail:'合成不可用样例',payload:{}}]:[
    {step:1,eventType:'tool.completed',name:'读取材料',detail:'仅为模拟交互数据，未调用后端或模型。',payload:{}},
    {step:2,eventType:'tool.completed',name:'模型证据分析',detail:'根据保存的处理方式显示',payload:mode==='fallback'?{provider:'deepseek',fallbackUsed:true}:mode==='ai'?{provider:'deepseek',fallbackUsed:false}:{provider:'rules',skippedReason:'not-consented'}}
  ]
});
class SyntheticStream {
  static CONNECTING=0;static OPEN=1;static CLOSED=2;
  onopen:(()=>void)|null=null;onerror:(()=>void)|null=null;
  private stopped=false;
  constructor(){activeStream=this;setTimeout(()=>{if(!this.stopped)this.onopen?.();},50);}
  addEventListener(){} close(){this.stopped=true;}
}
function prepare(){
  api.listProjectFiles=async(id)=>[{id:id+'-file',relativePath:id+'/source.py',language:'Python',sizeBytes:30,lineCount:2}];
  api.getProjectFile=async(id)=> id.startsWith('A')?new Promise<ProjectFileContent>(resolve=>{releaseFile=()=>resolve({id,relativePath:'A/source.py',content:'OLD-A-CONTENT',projectVersionId:'A'});}):({id,relativePath:'B/source.py',content:'NEW-B-CONTENT',projectVersionId:'B'});
  api.getVisualReview=async()=>null;
  api.getAnalysisTask=async()=>task();
  window.EventSource=SyntheticStream as unknown as typeof EventSource;
}
export default function Check(){
  const [ready,setReady]=useState(false),[material,setMaterial]=useState('A'),[view,setView]=useState('material'),[revision,setRevision]=useState(0);
  useEffect(()=>{prepare();setReady(true);},[]);
  return <div className="space-y-4"><h1 className="text-xl font-bold">Codex合成组件验证台（不连接业务服务）</h1>
    <div className="flex flex-wrap gap-2">
      <button className="btn-secondary" onClick={()=>setView('material')}>材料预览</button>
      <button className="btn-secondary" onClick={()=>setMaterial('B')}>切换到材料B</button>
      <button className="btn-secondary" onClick={()=>releaseFile?.()}>返回旧A响应</button>
      {['running','fallback','rules','ai','failed'].map(value=><button className="btn-secondary" key={value} onClick={()=>{mode=value;setView('task');setRevision(n=>n+1);}}>{value}</button>)}
      <button className="btn-secondary" onClick={()=>activeStream?.onerror?.()}>模拟连接中断</button>
    </div>
    {ready&&(view==='material'?<MaterialPreview id={material} kind="project"/>:<TaskView key={revision} id="synthetic-task"/>)}
  </div>;
}
