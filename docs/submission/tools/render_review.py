"""Render every PDF page and contact sheets, with layout bounds for manual review."""
from pathlib import Path
import json
import fitz
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[3]
pdf=ROOT/'output/pdf/CareerProof-技术说明-预审版-20261023-B1.pdf'
dest=ROOT/'tmp/pdfs/B1'
dest.mkdir(parents=True,exist_ok=True)
doc=fitz.open(pdf)
outside=[]
for n,page in enumerate(doc,1):
    page.get_pixmap(matrix=fitz.Matrix(1.4,1.4)).save(dest/f'page-{n:02d}.png')
    for block in page.get_text('dict')['blocks']:
        if block['type']!=0: continue
        for line in block['lines']:
            for span in line['spans']:
                x0,y0,x1,y1=span['bbox']
                if x0<0 or y0<0 or x1>page.rect.width+.5 or y1>page.rect.height+.5:
                    outside.append({'page':n,'text':span['text'],'bbox':span['bbox']})
for start in range(1,len(doc)+1,5):
    sheet=Image.new('RGB',(1120,2420),'#dfe5ee')
    draw=ImageDraw.Draw(sheet)
    for k,n in enumerate(range(start,min(start+5,len(doc)+1))):
        im=Image.open(dest/f'page-{n:02d}.png').convert('RGB'); im.thumbnail((530,750))
        x=20+(k%2)*550; y=30+(k//2)*800
        sheet.paste(im,(x,y)); draw.text((x,y-18),f'PAGE {n}',fill='black')
    sheet.save(dest/f'contact-{start:02d}.jpg',quality=92)
(dest/'render-check.json').write_text(json.dumps({'pages':len(doc),'outsidePage':outside,'allPagesRendered':True},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'pages':len(doc),'outsidePageSpans':len(outside),'contactSheets':5}))
