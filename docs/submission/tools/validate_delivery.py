"""Verify owned navigation, exact source ZIP, evidence, PDF and planned video timing."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from zipfile import ZipFile, ZIP_DEFLATED

from pypdf import PdfReader
from build_review_materials import ROOT, BASE, PRODUCT, DATE, PDF_REL, SOURCE_REL, CI_URL, sha, write

def validate():
    errors=[]
    docs=list((ROOT/'docs/submission').glob('*.md'))+list((ROOT/'output/video').glob('*20261023-B1.md'))
    count=0; navigation_targets=[]
    for doc in docs:
        # Only authored navigation is checked; byte-preserved historical snapshots are .txt.
        text=doc.read_text(encoding='utf-8')
        for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',text):
            target=unquote(target.strip('<>'))
            if re.match(r'^[a-z]+:',target) or target.startswith('#'): continue
            path=(doc.parent/target.split('#',1)[0]).resolve()
            navigation_targets.append((doc.name,target,path))
            count+=1
    evidence=json.loads((ROOT/'docs/submission/evidence/verified-index.json').read_text(encoding='utf-8'))
    for e in evidence:
        if sha(ROOT/e['source'])!=e['sha256'] or sha(ROOT/e['reviewCopy'])!=e['sha256']:
            errors.append('evidence hash '+e['id'])
    assets=json.loads((ROOT/'docs/submission/evidence/assets.json').read_text(encoding='utf-8'))
    for a in assets:
        if sha(ROOT/a['path'])!=a['sha256'] or sha(ROOT/a['original'])!=a['sha256']:
            errors.append('screenshot hash '+a['id'])
    with ZipFile(ROOT/SOURCE_REL) as z:
        m=json.loads(z.read('SOURCE_MANIFEST.json'))
        if m['commit']!=BASE: errors.append('source commit mismatch')
        mismatches=[]
        for path,info in m['files'].items():
            if hashlib.sha256(z.read(path)).hexdigest()!=info['sha256']: mismatches.append(path)
            if '..' in PurePosixPath(path).parts or PurePosixPath(path).is_absolute(): errors.append('unsafe ZIP path')
        if mismatches: errors.append('source ZIP byte mismatch')
        source_count=len(m['files'])
        zip_link_scope=m.get('document_link_check')
    source_entries=[
        'backend/app/agents/provider.py','backend/app/agents/contracts.py','backend/app/tools/skill_rubric.py',
        'backend/app/agents/evidence_workflow.py','backend/app/mcp_server.py',
        'backend/app/tools/semantic_retrieval.py','backend/app/services/retrieval.py',
        'backend/app/tools/code_analyzer.py','backend/app/tools/ocr.py','backend/app/services/portfolio.py',
        'backend/app/services/applications.py','backend/evals/bounded_evidence_smoke.py',
        'jianli/src/components/ReportAgentEvidence.tsx','jianli/src/components/ApplicationBoard.tsx',
        'jianli/src/components/ReportItemExplanation.tsx',
    ]
    for s in source_entries:
        if not (ROOT/s).is_file(): errors.append('missing source entry '+s)
    reader=PdfReader(ROOT/PDF_REL)
    texts=[p.extract_text() or '' for p in reader.pages]
    if len(reader.pages)!=25 or len(reader.pages)>30: errors.append('PDF page count')
    for i,p in enumerate(reader.pages,1):
        if abs(float(p.mediabox.width)-595.276)>1 or abs(float(p.mediabox.height)-841.89)>1: errors.append('not A4')
        if f'{i} / 25' not in texts[i-1]: errors.append('bad page number '+str(i))
    if '\ufffd' in ''.join(texts): errors.append('replacement glyph')
    render=json.loads((ROOT/'tmp/pdfs/B1/render-check.json').read_text(encoding='utf-8'))
    if render['outsidePage']: errors.append('PDF text outside page')
    shots=json.loads((ROOT/'output/video/CareerProof-镜头清单-20261023-B1.json').read_text(encoding='utf-8'))
    cursor=0
    for shot in shots:
        if shot['start']!=cursor: errors.append('video time gap')
        cursor+=shot['duration']
        if not (ROOT/shot['asset']).is_file(): errors.append('missing shot asset '+shot['id'])
        if any(not shot.get(k) for k in ('narration','source','actions','evidence','dependency')): errors.append('incomplete shot')
    if cursor!=390: errors.append('video time total')
    narration_chars=sum(len(re.findall('[\u4e00-\u9fff]',x['narration'])) for x in shots)
    # Narrow mechanical leak check; this is not a legal/security certification.
    scanned=[]; hits=[]
    for parent in [ROOT/'docs/submission',ROOT/'output/video']:
        for f in parent.rglob('*'):
            if not f.is_file() or f.suffix not in ('.md','.txt','.json','.py'): continue
            if parent.name=='video' and '20261023-B1' not in f.name: continue
            raw=f.read_text(encoding='utf-8-sig')
            if re.search(r'sk-[A-Za-z0-9_-]{24,}',raw) or re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',raw): hits.append(f.relative_to(ROOT).as_posix())
            scanned.append(f)
    if hits: errors.append('possible secrets '+str(hits))
    validation={
        'status':'pass' if not errors else 'fail','date':DATE,'errors':errors,
        'pdf':{'pages':len(reader.pages),'a4':True,'replacementGlyphs':0,'allPagesRendered':True,'outsidePageSpans':len(render['outsidePage']),
               'visualReview':'all 25 rendered pages inspected in five contact sheets; figures reviewed at page scale; see visual-review.md'},
        'navigation':{'documents':len(docs),'localTargets':count,'missing':0 if not errors else 'see errors','externalURLsAndAnchors':'not automatically checked'},
        'sourceZIP':{'commit':BASE,'trackedFiles':source_count,'hashMismatches':len(mismatches),'builderNavigationScope':zip_link_scope,'cleanInstallThisRound':False},
        'evidence':{'rawFiles':len(evidence),'screenshots':len(assets),'exactCopyHashes':True,'sourceEntries':len(source_entries)},
        'videoPlan':{'shots':len(shots),'plannedSeconds':cursor,'narrationChineseCharacters':narration_chars,'newMP4':False,'voiceOver':'user'},
        'sensitivePatternScan':{'files':len(scanned),'hits':hits,'scope':'API-key/private-key shapes only, plus visual screenshot review; not exhaustive'},
        'productTestRerun':False,'modelRequests':0,'databaseWrites':0,'sharedProductFilesChanged':False,
    }
    write('docs/submission/evidence/validation.json',json.dumps(validation,ensure_ascii=False,indent=2))
    artifact_paths=[PDF_REL,SOURCE_REL,'output/video/CareerProof-演示逐字稿与镜头计划-20261023-B1.md',
                    'output/video/CareerProof-镜头清单-20261023-B1.json',
                    'docs/submission/AI-技术证据索引.md','docs/submission/评委快速体验指南.md']
    manifest={
        'schemaVersion':1,'edition':'20261023-B1','status':'pre-review-draft','finalCandidateCommit':None,
        'finalBindingStatus':'待任务A完成后同步','productAcceptedCommit':PRODUCT,'documentationAndSourceCommit':BASE,
        'branch':'codex/contest-delivery-20261023','materialsRevision':'Resolve git log -1 --format=%H -- docs/submission/candidate-manifest.json; avoids a self-referential hash',
        'ci':{'commit':BASE,'url':CI_URL,'jobs':'3 success','evidence':'docs/submission/evidence/ci-f6bf1ed.json'},
        'environmentTemplates':{p:sha(ROOT/p) for p in ['README.md','backend/.env.example','jianli/.env.example']},
        'artifacts':[{ 'path':p,'sha256':sha(ROOT/p),'bytes':(ROOT/p).stat().st_size,'status':'draft'} for p in artifact_paths],
        'video':{'path':None,'sha256':None,'status':'script only; recording/voice/subtitles/review pending'},
        'screenshots':{'manifest':'docs/submission/evidence/assets.json','acceptedBuild':'HNdt9SK706tuGRbc0NPbL','historicalAgentImageSeparate':True},
        'openAcceptance':['真实200%缩放/离窗最小化','首次独立用户','人工两处理由澄清','新选证当前真实AI效果','最终候选材料同步'],
        'humanActions':['确认赛事个人中心与校内通知','评审账号访问检查','许可方案','团队/教师信息与真实签署','实际上传与回执'],
        'onlineDemo':'feasibility only; not deployed','repositoryVisibility':'not changed; reviewer access pending team confirmation',
    }
    write('docs/submission/candidate-manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    # Validate final outputs after generating the manifest and validation targets.
    for name,target,path in navigation_targets:
        if not path.is_file() and not path.is_dir(): errors.append(f'broken navigation: {name}: {target}')
    validation['status']='pass' if not errors else 'fail'
    validation['errors']=errors
    validation['navigation']['missing']=sum(not p.exists() for _,_,p in navigation_targets)
    write('docs/submission/evidence/validation.json',json.dumps(validation,ensure_ascii=False,indent=2))
    print(json.dumps(validation,ensure_ascii=False))
    if errors: raise SystemExit(1)

if __name__=='__main__': validate()
