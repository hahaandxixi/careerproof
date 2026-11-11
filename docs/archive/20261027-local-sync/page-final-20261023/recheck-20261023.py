import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

root = Path('D:/jbcode/web ai/jianli')
stage = root / 'backend/.tmp/page-final-20261023'
evidence = root / 'docs/evidence/20261023-page-final'

def git(*args, cwd=root):
    return subprocess.check_output(['git', *args], cwd=cwd).decode('utf-8').strip()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

status = subprocess.check_output(['git', 'status', '--porcelain=v1', '-z', '--untracked-files=all'], cwd=root)
entries = [entry.decode('utf-8') for entry in status.split(b'\0') if entry]
snapshot = {entry[3:]: sha(root / entry[3:]) for entry in entries if (root / entry[3:]).is_file()}
(stage / 'recheck-workspace-before.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
candidate = json.loads((evidence / 'candidate.json').read_text(encoding='utf-8-sig'))
build_id = (stage / 'jianli/.next/BUILD_ID').read_text().strip()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
http = []
for path, origin in [('/', 'http://127.0.0.1:3138'), (f'/_next/static/{build_id}/_buildManifest.js', 'http://127.0.0.1:3138'), ('/api/v1/health', 'http://127.0.0.1:8114')]:
    with opener.open(origin + path, timeout=12) as response:
        body = response.read()
        item = {'url': origin + path, 'status': response.status, 'sha256': hashlib.sha256(body).hexdigest()}
        if '_buildManifest' in path:
            item['matchesBuildOnDisk'] = body == (stage / 'jianli/.next/static' / build_id / '_buildManifest.js').read_bytes()
        if path.endswith('/health'):
            item['response'] = json.loads(body)
        http.append(item)
production_paths = ['jianli', 'backend/app', 'backend/alembic', 'backend/pyproject.toml']
result = {
    'checkedAt': datetime.now().astimezone().isoformat(),
    'git': {'head': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'), 'acceptedProductSource': candidate['acceptedSourceCommit'], 'productionDiffSinceAccepted': git('diff', '--name-only', candidate['acceptedSourceCommit'], 'HEAD', '--', *production_paths), 'stageHead': git('rev-parse', 'HEAD', cwd=stage), 'stageTreeEqualsAccepted': git('rev-parse', 'HEAD^{tree}', cwd=stage) == git('rev-parse', candidate['acceptedSourceCommit'] + '^{tree}'), 'stageTrackedDiff': git('diff', '--name-only', 'HEAD', '--', *production_paths, cwd=stage)},
    'buildId': build_id,
    'httpReadOnly': http,
    'artifacts': [{'kind': a['kind'], 'path': a['path'], 'sha256': sha(root / a['path']), 'matchesPriorArtifact': sha(root / a['path']) == a['sha256'], 'status': a['status']} for a in candidate['deliveryArtifacts']],
    'screenshots': {'reusedCount': len(json.loads((evidence / 'screenshots.json').read_text())), 'allMatchManifest': all(sha(evidence / image['file']) == image['sha256'] for image in json.loads((evidence / 'screenshots.json').read_text())), 'newNativeScreenshots': 0},
    'workspaceBefore': {'tracked': sum(not e.startswith('?? ') for e in entries), 'untracked': sum(e.startswith('?? ') for e in entries)},
    'nativeBrowser': {'app': 'Microsoft Edge', 'windowId': 722390, 'initialState': 'minimized', 'attempt': 'selected unique returned window; activated it as instructed; state capture stopped before any page input', 'stopReason': 'Computer Use has been stopped for this turn because it could not determine the current browser URL on Windows with enough confidence to enforce policy.', 'continuedNativeInput': False, 'real200Percent': 'pending manual', 'realHiddenTab': 'pending manual', 'realMinimizeRestore': 'pending manual', 'realOutsideClick': 'pending manual', 'zoomChanged': False},
    'limits': 'HTTP and process/source checks do not replace browser interaction. No new drafts, reports, viewed events, database writes, service restarts, or model requests. Prior save/refresh/account-boundary results are reused because their accepted code and build are unchanged.'
}
(evidence / 'recheck-20261023.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
