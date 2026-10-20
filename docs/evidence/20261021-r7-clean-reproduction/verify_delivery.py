from pathlib import Path
from zipfile import ZipFile
import json,hashlib,importlib.util
r=Path.cwd(); e=r/'docs/evidence/20261021-r7-clean-reproduction'; run=r/'backend/.tmp/r7-clean-20261021'; old=r/'output/source/CareerProof-source-review-20261020-r7.zip'; new=r/'output/source/CareerProof-source-review-20261021-r8.zip'; dest=run/'source-r8'
with ZipFile(old) as z: a=json.loads(z.read('SOURCE_MANIFEST.json'))
with ZipFile(new) as z:
 b=json.loads(z.read('SOURCE_MANIFEST.json')); assert set(a['files'])==set(b['files'])
 for name,meta in b['files'].items(): assert hashlib.sha256(z.read(name)).hexdigest()==meta['sha256'],name
changed=[n for n in a['files'] if a['files'][n]['sha256']!=b['files'][n]['sha256']]; assert sorted(changed)==['backend/README.md','jianli/README.md']
spec=importlib.util.spec_from_file_location('package',dest/'scripts/build_source_package.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); contents={n:(dest/n).read_bytes() for n in b['files']}; nav=m.validate_document_links(contents); assert m.REQUIRED<=set(contents)
mutated=[n for n,meta in a['files'].items() if hashlib.sha256((run/'source'/n).read_bytes()).hexdigest()!=meta['sha256']]; assert not mutated,mutated
report=json.loads((e/'report-first.json').read_text(encoding='utf-8')); previews={p['id']:p for p in json.loads((e/'file-previews.json').read_text(encoding='utf-8'))}; citations=0
with ZipFile(run/'source/jianli/public/demo-assets/scenarios/event-api-project.zip') as upload: originalFiles={Path(n).name:upload.read(n) for n in upload.namelist() if not n.endswith('/')}
for item in report['items']:
 for ev in item['evidenceList']:
  f=previews[ev['projectFileId']]; lines=f['content'].splitlines(); assert ev['snippet'].strip()=='\n'.join(lines[ev['lineStart']-1:ev['lineEnd']]).strip(),ev['citationId']; assert f['projectVersionId']==ev['projectVersionId']; assert ev['contentHash']==hashlib.sha256(originalFiles[Path(ev['filePath']).name]).hexdigest(); citations+=1
assert report['analysisMode']=='rules' and report['aiProvider'] is None and report['aiUsage'] is None and report['aiToolCalls']==[]
record={'r7Sha256':hashlib.sha256(old.read_bytes()).hexdigest(),'r7Commit':a['commit'],'r8Sha256':hashlib.sha256(new.read_bytes()).hexdigest(),'r8Commit':b['commit'],'r8Files':len(b['files']),'r8LocalNavigationDocuments':len(nav),'changedPackageFiles':changed,'r7ExecutedSourceMutations':mutated,'r8RuntimeAndDependencyFilesIdenticalToExecutedR7':True,'r8SeparateCleanInstallPerformed':False,'verifiedCitationSpansUploadByteHashesAndVersions':citations,'browserLoginAndReportCitationObserved':True,'uploadsAndReportCreation':'HTTP through isolated production frontend proxy','databaseAndServicesRestarted':True,'reportUnchangedAfterRestart':True,'externalAiRequests':0,'independentFirstUserAcceptance':False,'installation':{'python':'fresh .venv, include-system-site-packages=false','frontend':'fresh source/jianli/node_modules, npm ci','downloadCacheAllowed':True,'borrowedInstalledEnvironment':False,'pipInstallExitCode':None,'npmCiExitCode':None,'installExitCodeNote':'Tool response interrupted by user; background installs completed with successful logs. Fresh import, pip check, migration, build and running flow independently verified.'},'verifiedExitCodes':{'pipCheck':0,'migration':0,'frontendBuild':0,'documentedSeedReplay':0,'r8Build':0}}
(e/'verification.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); (e/'r8-manifest.json').write_text(json.dumps(b,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('r8 only two README changes; runtime/dependencies identical to freshly installed r7; navigation',len(nav),'citation spans/upload hashes/versions',citations)
