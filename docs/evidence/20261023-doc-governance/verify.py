"""Offline, read-only checks for the 2026-10-23 documentation migration.

Run with Python's standard library; no database, model or browser interaction.
--root accepts a checkout or an exported committed tree. --output is optional.
History is reconstructed by reversing only recorded link edits and removing
archive-added anchors, then compared with the original LF-normalized hash.
"""
import argparse
import hashlib
import importlib.util
import json
import posixpath
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

EVIDENCE = 'docs/evidence/20261023-doc-governance'
ROOT_STAGE = '阶段1-比赛需求拆解与项目总控.md'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def anchors(text):
    found = set(re.findall(r'<a\s+id=["\']([^"\']+)', text))
    counts = {}
    fence = False
    for line in text.splitlines():
        if re.match(r'^\s{0,3}(```|~~~)', line):
            fence = not fence
        if fence:
            continue
        heading = re.match(r'^#{1,6}\s+(.+?)(?:\s+#+)?$', line)
        if not heading:
            continue
        title = re.sub(r'<[^>]*>', '', heading[1]).lower()
        title = re.sub(r'[`*_~]', '', title)
        # GitHub anchors preserve Unicode letters/numbers and strip punctuation.
        title = ''.join(c for c in title if c in '_- ' or unicodedata.category(c)[0] in 'LN')
        title = title.replace(' ', '-')
        n = counts.get(title, 0)
        counts[title] = n + 1
        found.add(title + (f'-{n}' if n else ''))
    return found


def verify(root):
    manifest = json.loads((root/EVIDENCE/'migration.json').read_text(encoding='utf-8'))
    restored = []
    for item in manifest['sources']:
        content = (root/item['archive']).read_text(encoding='utf-8')
        start = f"<!-- archive:{item['marker']}:begin -->\n"
        end = f"<!-- archive:{item['marker']}:end -->"
        body = content.split(start, 1)[1].split(end, 1)[0]
        if item['marker'] in ('handoff', 'tasks'):
            body = re.sub(r'^<a id="(?:handoff|tasks)-[^"\n]+"></a>\n', '', body, flags=re.M)
        lines = body.splitlines(keepends=True)
        for change in item['linkEdits']:
            index = change['line'] - 1
            assert lines[index].rstrip('\n') == change['after'], (item['source'],change['line'])
            lines[index] = change['before'] + ('\n' if lines[index].endswith('\n') else '')
        recovered = ''.join(lines)
        assert sha(recovered.encode()) == item['originalNormalizedSha256'], item['source']
        assert len(recovered.splitlines()) == item['originalLines'], item['source']
        raw = recovered.replace('\n','\r\n') if item['originalLineEndings']=='CRLF' else recovered
        assert sha(raw.encode()) == item['originalSha256'], 'Raw byte reconstruction: '+item['source']
        restored.append({'source':item['source'],'lines':item['originalLines'],'normalizedAndOriginalBytesMatch':True})
    spec=importlib.util.spec_from_file_location('source_package',root/'scripts/build_source_package.py')
    package=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    scope = ['AGENTS.md','README.md','docs/README.md','docs/协作规则.md','docs/当前接力.md','docs/任务清单.md',ROOT_STAGE]
    scope += [p.relative_to(root).as_posix() for p in (root/'docs/history').glob('*.md')]
    scope += [p.relative_to(root).as_posix() for p in (root/'docs/guides').glob('*.md')]
    scope += [EVIDENCE+'/README.md'] if (root/EVIDENCE/'README.md').exists() else []
    # Existing evidence pointing at a moved heading must retain a valid bookmark.
    for p in (root/'docs/evidence').rglob('*.md'):
        if str(p).find('20261023-doc-governance') >= 0:
            continue
        text=p.read_text(encoding='utf-8-sig')
        if re.search(r'(?:当前接力|任务清单)\.md#|阶段1-比赛需求拆解与项目总控\.md',text):
            scope.append(p.relative_to(root).as_posix())
    failures=[]; warnings=[]; local=0; fragment_count=0; hosted=0
    cache={}
    for name in sorted(set(scope)):
        content=(root/name).read_text(encoding='utf-8-sig')
        for line,dest in package.markdown_destinations(content):
            dest=re.sub(r'\\([\\() ])',r'\1',dest)
            url=urlsplit(dest)
            prefix='/hahaandxixi/careerproof/blob/main/'
            if url.netloc == 'github.com' and url.path.startswith(prefix):
                target=unquote(url.path[len(prefix):]); hosted+=1
            elif url.scheme or url.netloc:
                continue
            else:
                target=posixpath.normpath(posixpath.join(posixpath.dirname(name),unquote(url.path))) if url.path else name
                if url.path.startswith('/'):
                    target=url.path.lstrip('/')
                local+=1
            p=root/target
            if not p.exists():
                failures.append({'source':name,'line':line,'destination':dest,'target':target,'kind':'missing-path'})
                continue
            if url.fragment and p.suffix=='.md':
                fragment_count+=1
                if target not in cache: cache[target]=anchors(p.read_text(encoding='utf-8-sig'))
                if unquote(url.fragment) not in cache[target]:
                    failures.append({'source':name,'line':line,'destination':dest,'target':target,'kind':'missing-anchor'})
    tasks=(root/'docs/任务清单.md').read_text(encoding='utf-8')
    active=tasks.split('## 活动任务',1)[1].split('## 已关闭事项索引',1)[0]
    ids=re.findall(r'^\| (CP-[A-Z]+-\d+) \|',active,re.M)
    assert len(ids)==len(set(ids))==10, ids
    assert not re.search(r'^\| CP-.*\| 已完成 \|',active,re.M)
    return {'history':restored,'documentsChecked':len(set(scope)), 'localLinksChecked':local,
            'repositoryHostedLinksCheckedAgainstTree':hosted,'markdownFragmentsChecked':fragment_count,
            'openTasks':len(ids),'handoffLines':len((root/'docs/当前接力.md').read_text(encoding='utf-8').splitlines()),
            'failures':failures,'warnings':warnings,
            'limits':'No general external URL availability check, live application test, or new CI/model execution. GitHub main document URLs validated against this tree.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=verify(args.root.resolve())
    rendered=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output: args.output.write_text(rendered,encoding='utf-8')
    print(rendered)
    raise SystemExit(1 if result['failures'] else 0)
