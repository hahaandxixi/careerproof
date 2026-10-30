"""Bundle owned material plus a fixed source snapshot; verify actual unpacked content."""
from pathlib import Path, PurePosixPath
import json
from zipfile import ZipFile, ZIP_DEFLATED
from build_review_materials import ROOT, BASE, PRODUCT, PDF_REL, SOURCE_REL, sha, write


def package():
    data=json.loads((ROOT/'docs/submission/evidence/verified-index.json').read_text(encoding='utf-8'))
    retained={(ROOT/e['reviewCopy']).resolve() for e in data}
    originals=(ROOT/'docs/submission/evidence/originals').resolve()
    archive=(ROOT/'tmp/pdfs/B1/superseded-authoring-copies').resolve()
    archive.relative_to(ROOT.resolve()); originals.relative_to(ROOT.resolve())
    for path in originals.iterdir():
        if path.resolve() not in retained:
            path.resolve().relative_to(originals)
            archive.mkdir(parents=True,exist_ok=True)
            # Only this task's untracked intermediate copies move, never repository source evidence.
            target=archive/path.name
            if target.exists():
                if sha(target)!=sha(path): raise RuntimeError('archive collision')
                continue
            path.rename(target)
    owned=sorted(p for p in (ROOT/'docs/submission').rglob('*') if p.is_file()
                 and '__pycache__' not in p.parts and p.suffix!='.pyc')
    owned += [ROOT/PDF_REL,ROOT/SOURCE_REL]
    owned += sorted((ROOT/'output/video').glob('*20261023-B1.*'))
    out=ROOT/'output/source/CareerProof-review-materials-20261023-B1.zip'
    if out.exists(): raise FileExistsError('Use a new edition instead of replacing a review bundle')
    with ZipFile(out,'x',compression=ZIP_DEFLATED,compresslevel=9) as z:
        for p in owned: z.write(p,p.relative_to(ROOT).as_posix())
    unpack=(ROOT/'tmp/pdfs/B1/unpacked-review').resolve()
    unpack.relative_to(ROOT.resolve()); unpack.mkdir(parents=True,exist_ok=True)
    with ZipFile(out) as z:
        for name in z.namelist():
            if '..' in PurePosixPath(name).parts or PurePosixPath(name).is_absolute(): raise RuntimeError('unsafe bundle')
        z.extractall(unpack)
    mismatch=[p.relative_to(ROOT).as_posix() for p in owned if sha(p)!=sha(unpack/p.relative_to(ROOT))]
    with ZipFile(unpack/SOURCE_REL) as z:
        # Check source snapshot after real extraction as well as at ZIP byte level.
        dest=ROOT/'tmp/pdfs/B1/unpacked-source'
        for name in z.namelist():
            if '..' in PurePosixPath(name).parts or PurePosixPath(name).is_absolute(): raise RuntimeError('unsafe source')
        z.extractall(dest)
    sm=json.loads((dest/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    source_bad=[name for name,meta in sm['files'].items() if sha(dest/name)!=meta['sha256']]
    if mismatch or source_bad: raise RuntimeError('unpacked hash mismatch')
    write('docs/submission/evidence/package-check.json',json.dumps({
        'bundle':out.relative_to(ROOT).as_posix(),'sha256':sha(out),'bytes':out.stat().st_size,
        'files':len(owned),'actualExtraction':True,'mismatches':mismatch,
        'sourceExtractedFiles':len(sm['files']),'sourceMismatches':source_bad,
        'sourceCommit':BASE,'productAccepted':PRODUCT,
        'scope':'Packaged files are frozen; this external receipt is created after bundling and is not inside that ZIP. No installation/runtime validation.'
    },ensure_ascii=False,indent=2))
    print(json.dumps({'bundle':out.relative_to(ROOT).as_posix(),'files':len(owned),'unpackedMismatch':0,'sourceFiles':len(sm['files'])}))


if __name__=='__main__': package()
