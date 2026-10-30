from pathlib import Path
import subprocess,json,hashlib
root=Path('D:/jbcode/web ai/jianli'); stage=root/'backend/.tmp/layout-closeout-20261023'
files=subprocess.check_output(['git','diff','--name-only'],cwd=stage).decode().splitlines()+['jianli/src/lib/growth-next-action.ts']
backup=root/'backend/.tmp/layout-closeout-integration-20261023'; backup.mkdir(exist_ok=True)
def git(*args, data=None):return subprocess.run(['git',*args],cwd=root,input=data,capture_output=True,check=True).stdout
assert not git('diff','--cached','--name-only').strip(),'Index is not empty'
base=git('rev-parse','HEAD').decode().strip(); assert base=='4f5ad6ff1cb84c06f3ea5ff97f5ee7e25fb28070'
plans=[]; conflicts=[]
for i,f in enumerate(files):
    accepted=(stage/f).read_bytes().replace(b'\r\n',b'\n')
    target=root/f; current=target.read_bytes() if target.exists() else None
    old=subprocess.run(['git','show',f'{base}:{f}'],cwd=root,capture_output=True)
    if old.returncode and current is not None:raise RuntimeError('Untracked collision '+f)
    if current is None or current.replace(b'\r\n',b'\n')==old.stdout:merged=accepted
    else:
        d=backup/str(i);d.mkdir(exist_ok=True)
        (d/'original').write_bytes(current);(d/'current').write_bytes(current.replace(b'\r\n',b'\n'));(d/'base').write_bytes(old.stdout);(d/'accepted').write_bytes(accepted)
        m=subprocess.run(['git','merge-file','-p',str(d/'current'),str(d/'base'),str(d/'accepted')],cwd=root,capture_output=True)
        (d/'merged').write_bytes(m.stdout)
        if m.returncode:
            if f.endswith('/ApplicationBoard.tsx'):
                text=current.decode('utf-8').replace('className="btn" disabled={busy} onClick={()=>void download()}', 'className="btn-secondary" disabled={busy} onClick={()=>void download()}')
                text=text.replace('materials={selected.report.materials}/>', 'materials={selected.report.materials} aiFallbackUsed={selected.report.aiFallbackUsed}/>')
                merged=text.encode('utf-8').replace(b'\r\n',b'\n')
            elif f.endswith('/ReportDetail.tsx'):
                text=accepted.decode('utf-8')
                for field in ['evidenceLevelReason','evidenceLevelGap','aiExplanation','aiInformationGap','aiSuggestion']:
                    text=text.replace('{item.'+field+'}', '{item.'+field+' ?? ""}')
                text=text.replace('版本：{material.id}<br />内容摘要：', '本报告已保存该材料版本。<br />内容摘要：')
                merged=text.encode('utf-8')
            else:
                conflicts.append(f); merged=m.stdout
        else: merged=m.stdout
    plans.append((f,current,accepted,merged))
(backup/'plan.json').write_text(json.dumps({'baseline':base,'files':files,'conflicts':conflicts},indent=2),encoding='utf-8')
if conflicts:print(json.dumps({'conflicts':conflicts}));raise SystemExit(2)
for f,current,accepted,merged in plans:
    target=root/f
    assert (target.read_bytes() if target.exists() else None)==current,'Concurrent modification '+f
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(merged)
    oid=git('hash-object','-w','--stdin',data=accepted).decode().strip()
    git('update-index','--add','--cacheinfo',f'100644,{oid},{f}')
print(json.dumps({'stagedFiles':len(files),'preservedUnrelatedHunks':sum(c is not None and c.replace(b'\r\n',b'\n')!=subprocess.run(['git','show',f'{base}:{f}'],cwd=root,capture_output=True).stdout for f,c,a,m in plans)}))
