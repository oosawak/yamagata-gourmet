#!/usr/bin/env python3
"""Convert independent Markdown sources into static JSON sites."""
from __future__ import annotations
import base64
from io import BytesIO
import json
from pathlib import Path
import re
import shutil
import hashlib
import os
from html import escape
from functools import lru_cache
from PIL import Image, ImageOps
import mistune
import bleach
import yaml

ROOT=Path(__file__).resolve().parents[1]
CONTENT=ROOT/'content'
DIST=ROOT/'dist'
POSTS=CONTENT/'posts'
IMAGES=CONTENT/'images'
COLOR_THUMB=(720,450)
CATEGORY_COVERS={'麺':'gourmet/ramen.webp','郷土料理':'gourmet/imoni.webp','甘いもの':'gourmet/fruit.webp','カフェ':'gourmet/cafe.webp'}
DEFAULT_COVER='gourmet/hero-imoni.webp'
MANUAL_I18N=json.loads((CONTENT/'i18n/en.json').read_text(encoding='utf-8'))
TRANSLATION_CACHE=ROOT/'cache/translations/en.json'
CACHED_I18N=json.loads(TRANSLATION_CACHE.read_text(encoding='utf-8')) if TRANSLATION_CACHE.is_file() else {'sites':{},'posts':{}}

def source_hash(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

def translated(group,key,original):
    fallback=MANUAL_I18N.get(group,{}).get(key,{})
    if fallback.get('source_hash')!=source_hash(original):
        fallback={}
    else:
        fallback={k:v for k,v in fallback.items() if k!='source_hash'}
    cached=CACHED_I18N.get(group,{}).get(key,{})
    if cached.get('source_hash')==source_hash(original):
        return {**fallback,**cached.get('fields',{})}
    return fallback

def embed_html_images(html_text):
    # Relative image links in translated HTML are embedded after translation.
    def replace_image(match):
        src=match.group(2)
        if src.startswith('data:image/webp;base64,'): return match.group(0)
        uri,_=image_uri(src,'detail')
        return match.group(1)+escape(uri,quote=True)+match.group(3)
    return re.sub(r'(<img[^>]*\bsrc=["\'])([^"\']+)(["\'])',replace_image,html_text)

ALLOWED_MARKDOWN_TAGS={'p','h1','h2','h3','h4','h5','h6','ul','ol','li','strong','em','b','i','code','pre','blockquote','a','img','hr','br','del','table','thead','tbody','tr','th','td'}

def article_attribute(tag,name,value):
    if tag=='img':
        return name=='alt' or (name=='src' and value.startswith('data:image/webp;base64,')) or (name=='loading' and value in ('lazy','eager'))
    if tag=='a':
        if name=='title':return True
        if name=='href':
            # Data, javascript, protocol-relative, and other executable URLs are forbidden.
            if value.startswith('#'):return True
            return value.startswith(('https://','http://','mailto:'))
    return False

def sanitize_article_html(content):
    return bleach.clean(content,tags=ALLOWED_MARKDOWN_TAGS,attributes=article_attribute,protocols=['http','https','mailto','data'],strip=True)

def save_image_file(rel, out_path, kind='detail'):
    rel=rel.strip().lstrip('/')
    filepath=(IMAGES/rel).resolve()
    if not filepath.is_relative_to(IMAGES.resolve()) or not filepath.exists():
        raise ValueError(f'Image not found or unsafe: {rel}')
    with Image.open(filepath) as src:
        im=ImageOps.exif_transpose(src).convert('RGB')
        if kind=='thumb':
            im=ImageOps.fit(im,COLOR_THUMB,method=Image.Resampling.LANCZOS,centering=(.5,.48))
            quality=74
        else:
            im.thumbnail((1540,1540),Image.Resampling.LANCZOS)
            quality=83
        out_path.parent.mkdir(parents=True,exist_ok=True)
        im.save(out_path,format='WEBP',quality=quality,method=5)

SEO_DESCRIPTION='山形の郷土料理、麺、スイーツ、カフェなど、実際のお店を訪ねた記録を集めたグルメ案内です。'

def article_page(detail, origin, site_name):
    title=detail['title']
    desc=str(detail.get('summary','')).replace('\n',' ')
    page_url=origin+f"posts/{detail['slug']}.html"
    og_image=origin+f"og/{detail['slug']}.webp"
    source=''
    if detail.get('embed_url'):
        source=f'<p>元の投稿：<a href="{escape(detail["embed_url"],quote=True)}" rel="noopener" target="_blank">{escape(detail.get("embed_platform",""))}</a></p>'
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} | {escape(site_name)}</title>
<meta name="description" content="{escape(desc,quote=True)}">
<link rel="canonical" href="{page_url}">
<meta property="og:type" content="article"><meta property="og:site_name" content="{escape(site_name,quote=True)}">
<meta property="og:title" content="{escape(title,quote=True)}">
<meta property="og:description" content="{escape(desc,quote=True)}">
<meta property="og:url" content="{page_url}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<style>body{{font-family:system-ui,-apple-system,'Hiragino Sans','Noto Sans JP',sans-serif;margin:0;background:#f8f7f1;color:#2b2620}}main{{max-width:760px;margin:0 auto;padding:20px 16px 48px}}img.cover{{width:100%;height:auto;border-radius:12px}}h1{{font-size:26px;line-height:1.4;margin:16px 0 6px}}.meta{{color:#8a7a63;font-size:13px}}article{{line-height:1.9;font-size:16px}}article img{{max-width:100%;height:auto}}a{{color:#8d5b2b}}</style>
</head><body><main>
<p><a href="{origin}">{escape(site_name)}</a></p>
<img class="cover" src="../og/{detail['slug']}.webp" alt="{escape(detail['cover'].get('alt',title),quote=True)}">
<h1>{escape(title)}</h1>
<p class="meta">{escape(str(detail.get('date','')))} ／ {escape(str(detail.get('category','')))}</p>
<article>{detail['html']}</article>
{source}
<p><a href="{escape(detail['url'],quote=True)}">サイトでこの記事を開く</a></p>
</main></body></html>"""

@lru_cache(maxsize=200)
def image_uri(rel: str, kind: str) -> tuple[str,int]:
    rel=rel.strip().lstrip('/')
    filepath=(IMAGES/rel).resolve()
    if not filepath.is_relative_to(IMAGES.resolve()) or not filepath.exists():
        raise ValueError(f'Image not found or unsafe: {rel}')
    with Image.open(filepath) as src:
        im=ImageOps.exif_transpose(src).convert('RGB')
        if kind=='thumb':
            im=ImageOps.fit(im,COLOR_THUMB,method=Image.Resampling.LANCZOS,centering=(.5,.48))
            quality=74
        else:
            im.thumbnail((1540,1540),Image.Resampling.LANCZOS)
            quality=83
        output=BytesIO()
        im.save(output,format='WEBP',quality=quality,method=5)
    content=output.getvalue()
    return 'data:image/webp;base64,'+base64.b64encode(content).decode('ascii'),len(content)

class InlineImageRenderer(mistune.HTMLRenderer):
    def image(self,text:str,url:str,title:str|None=None)->str:
        # Only locally managed images are embedded; no remote/network images from Markdown.
        uri,_=image_uri(url,'detail')
        return f'<img src="{escape(uri,quote=True)}" alt="{escape(text,quote=True)}" loading="lazy">'

md=mistune.create_markdown(renderer=InlineImageRenderer(escape=True),plugins=['table'])

def parse_md(path:Path):
    raw=path.read_text(encoding='utf-8')
    match=re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$',raw,re.S)
    if not match:raise ValueError(f'Missing YAML frontmatter: {path}')
    fm=yaml.safe_load(match.group(1))
    body=match.group(2)
    if not isinstance(fm,dict):raise ValueError(f'Bad YAML frontmatter: {path}')
    return fm,body

def required(obj, keys, context):
    for key in keys:
        if key not in obj or obj[key] in [None,'']:
            raise ValueError(f'Missing {key} in {context}')

def write_json(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def shell(default_site,root_prefix):
    title_map={'portal':'まちのつながり | 統合ポータル','bakery':'haru no tane bakery','town':'みどり野町','fruit':'果実日和','gourmet':'山形グルメ案内'}
    title=title_map.get(default_site, 'まちのつながり')
    return f'''<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#f8f7f1"><meta name="description" content="架空の町・店舗・フルーツ通販を結ぶJSONサイトのデモです。">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' https://www.instagram.com https://www.threads.net https://www.threads.com; frame-src https://www.instagram.com https://www.threads.net https://www.threads.com; style-src 'self' 'unsafe-hashes' 'sha256-xK+TcQ9StFcaVVSroz1BgC50XqBvx1GcKyflF9XE4A0=' 'sha256-l6khRnjaVBZm7Z9S5+A/4ZrRnU7hBbTAGeVNTXpAbwU='; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'">
<title>{escape(title)}</title><link rel="stylesheet" href="{root_prefix}assets/style.css"></head>
<body><div id="app" data-default="{default_site}" data-root="{root_prefix}"><p class="loading">読み込み中…</p></div>
<noscript>このサイトの表示にはJavaScriptが必要です。</noscript>
<script src="{root_prefix}assets/app.js" defer></script></body></html>
'''


SITE_ID="gourmet"

def base_url():
    from urllib.parse import urlsplit
    custom=os.environ.get('SITE_URL','').strip()
    if custom:
        p=urlsplit(custom)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment:
            raise ValueError('SITE_URL must be an HTTPS public URL without query/fragment')
        return custom.rstrip('/')+'/'
    repo=os.environ.get('GITHUB_REPOSITORY','').strip()
    if repo:
        owner,name=repo.split('/',1)
        if not re.fullmatch(r'[A-Za-z0-9_-]+',owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+',name):
            raise ValueError('Invalid GITHUB_REPOSITORY')
        if name.lower()==owner.lower()+'.github.io':
            return f'https://{owner.lower()}.github.io/'
        return f'https://{owner.lower()}.github.io/{name}/'
    # Local preview only; GitHub Actions supplies GITHUB_REPOSITORY automatically.
    return 'https://example.org/'+SITE_ID+'/'

def shell(origin=''):
    site_titles={'bakery':'haru no tane bakery','town':'みどり野町','fruit':'果実日和','gourmet':'山形グルメ案内'}
    title=site_titles[SITE_ID]
    portal_url=os.environ.get('PORTAL_URL','').strip()
    if portal_url and (not portal_url.startswith('https://') or '"' in portal_url or '<' in portal_url or '\n' in portal_url):
        raise ValueError('PORTAL_URL must be a safe HTTPS URL')
    attrs=f'data-default="{SITE_ID}" data-root="./" data-mode="site" data-site-id="{SITE_ID}" data-portal-url="{escape(portal_url,quote=True)}"'
    og=''
    if origin:
        og=(f'<meta property="og:type" content="website"><meta property="og:site_name" content="{escape(title,quote=True)}">'
            f'<meta property="og:title" content="{escape(title,quote=True)}">'
            f'<meta property="og:description" content="{SEO_DESCRIPTION}">'
            f'<meta property="og:url" content="{origin}">'
            f'<meta property="og:image" content="{origin}og/hero.webp">'
            f'<meta name="twitter:card" content="summary_large_image">'
            f'<link rel="canonical" href="{origin}">')
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{SEO_DESCRIPTION}">{og}<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' https://www.instagram.com https://www.threads.net https://www.threads.com; frame-src https://www.instagram.com https://www.threads.net https://www.threads.com; style-src 'self' 'unsafe-hashes' 'sha256-xK+TcQ9StFcaVVSroz1BgC50XqBvx1GcKyflF9XE4A0=' 'sha256-l6khRnjaVBZm7Z9S5+A/4ZrRnU7hBbTAGeVNTXpAbwU='; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'"><title>{escape(title)}</title><link rel="stylesheet" href="assets/style.css"></head><body><div id="app" {attrs}><p class="loading">読み込み中…</p></div><noscript>JavaScriptを有効にしてください。</noscript><script src="assets/app.js" defer></script></body></html>"""

def generate():
    if DIST.exists():shutil.rmtree(DIST)
    (DIST/'assets').mkdir(parents=True)
    shutil.copy2(ROOT/'assets/style.css',DIST/'assets/style.css')
    shutil.copy2(ROOT/'assets/app.js',DIST/'assets/app.js')
    cfgpath=CONTENT/'sites'/f'{SITE_ID}.yml'
    site=yaml.safe_load(cfgpath.read_text(encoding='utf-8'))
    required(site,['id','name','kind','hero_title','description','accent'],cfgpath)
    if site['id']!=SITE_ID:raise ValueError('Site ID mismatch')
    site['i18n']={'en':translated('sites',SITE_ID,site)}
    if site.get('hero_image'):
        site['hero_image_src']=image_uri(site['hero_image'],'detail')[0]
        site['hero_thumbnail']={'src':image_uri(site['hero_image'],'thumb')[0], 'alt':site['name'], 'mime':'image/webp'}
    origin=base_url()
    summaries=[]
    slugs=set()
    for postpath in sorted((POSTS/SITE_ID).glob('*.md')):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-[a-z0-9_-]+\.md',postpath.name):
            raise ValueError(f'Invalid post filename: {postpath.name}')
        fm,body=parse_md(postpath)
        required(fm,['title','date','category','summary'],postpath)
        source_url=str(fm.get('source_url','')).strip()
        embed_platform=''
        if source_url.startswith('https://'):
            if 'instagram.com' in source_url:embed_platform='instagram'
            elif 'threads.net' in source_url or 'threads.com' in source_url:embed_platform='threads'
        if not fm.get('cover') and not embed_platform:
            raise ValueError(f'cover or a supported source_url is required: {postpath}')
        cover_rel=fm.get('cover') or CATEGORY_COVERS.get(fm['category'],DEFAULT_COVER)
        slug=postpath.stem[11:]
        if slug in slugs:raise ValueError('Duplicate slug across dates: '+slug)
        slugs.add(slug)
        item_type=fm.get('type','article')
        if item_type not in ['article','product']:raise ValueError('Invalid post type')
        key=f'{SITE_ID}:{slug}'
        translation=translated('posts',key,{'frontmatter':fm,'markdown':body})
        english_summary={k:v for k,v in translation.items() if k not in ('markdown','html')}
        english_detail={**english_summary}
        if 'html' in translation:
            english_detail['html']=sanitize_article_html(embed_html_images(translation['html']))
        elif 'markdown' in translation:
            english_detail['html']=sanitize_article_html(md(translation['markdown']))
            english_detail['markdown']=translation['markdown']
        cover_alt=fm.get('cover_alt',fm['title'])
        summary={
            'id':key,'site_id':SITE_ID,'site_name':site['name'],'site_kind':site['kind'],
            'slug':slug,'type':item_type,'title':fm['title'],'subtitle':fm.get('subtitle',''),'author':fm.get('author',''),'date':str(fm['date']),
            'category':fm['category'],'summary':fm['summary'],
            'url':origin+f'#/post/{SITE_ID}/{slug}',
            'cover':{'src':image_uri(cover_rel,'thumb')[0],'alt':cover_alt,'mime':'image/webp'},
            'i18n':{'en':english_summary},
        }
        if embed_platform:
            summary['embed_url']=source_url
            summary['embed_platform']=embed_platform
        map_query=str(fm.get('map_query','')).strip()
        if map_query:
            summary['map_query']=map_query
        if item_type=='product':
            if SITE_ID!='fruit':raise ValueError('Products only supported in fruit demo')
            required(fm,['price_jpy','unit','stock'],postpath)
            price=int(fm['price_jpy'])
            if price<0:raise ValueError('Invalid price')
            summary.update({'price_jpy':price,'unit':fm['unit'],'stock':fm['stock']})
        detail={**summary,'cover':{'src':image_uri(cover_rel,'detail')[0], 'alt':cover_alt,'mime':'image/webp'},
                'markdown':body,'html':sanitize_article_html(md(body)),'i18n':{'en':english_detail}}
        write_json(DIST/'data/posts'/SITE_ID/f'{slug}.json',detail)
        save_image_file(cover_rel, DIST/'og'/f'{slug}.webp')
        (DIST/'posts').mkdir(parents=True,exist_ok=True)
        (DIST/'posts'/f'{slug}.html').write_text(article_page(detail, origin, site['name']),encoding='utf-8')
        summaries.append(summary)
    summaries.sort(key=lambda x:(x['date'],x['id']),reverse=True)
    feed={'version':1,'schema':'static-site-feed/v1','schema_version':'1.1.0','languages':['ja','en'],
          'site':site,'entries':summaries}
    write_json(DIST/'data/sites'/f'{SITE_ID}.json',feed)
    # A tiny local collection enables the original design without a portal dependency.
    portal={'version':1,'schema':'static-portal/v1','schema_version':'1.1.0','sites':[site],
            'entries':summaries, 'hero_image_src':site.get('hero_image_src','')}
    write_json(DIST/'data/portal.json',portal)
    write_json(DIST/'data/portal-local.json',portal)
    if site.get('hero_image'):
        save_image_file(site['hero_image'], DIST/'og/hero.webp')
    sm_lines=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    def sm_entry(loc,lastmod=''):
        lm=f'<lastmod>{lastmod}</lastmod>' if lastmod else ''
        return f'<url><loc>{escape(loc)}</loc>{lm}</url>'
    sm_lines.append(sm_entry(origin, summaries[0]['date'] if summaries else ''))
    sm_lines.append(sm_entry(origin+'en/'))
    for s in summaries:
        sm_lines.append(sm_entry(origin+f"posts/{s['slug']}.html", s['date']))
    sm_lines.append('</urlset>')
    (DIST/'sitemap.xml').write_text('\n'.join(sm_lines)+'\n',encoding='utf-8')
    (DIST/'index.html').write_text(shell(origin),encoding='utf-8')
    en_site=site.get('i18n',{}).get('en',{})
    en_name=str(en_site.get('name') or site['name'])
    en_desc=str(en_site.get('description') or site['description']).replace('\n',' ')
    en_page=f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{escape(en_desc,quote=True)}"><meta http-equiv="refresh" content="0; url=../#/en/"><title>{escape(en_name)}</title></head><body><p><a href="../#/en/">{escape(en_name)} &mdash; English</a></p></body></html>"""
    (DIST/'en').mkdir(parents=True,exist_ok=True)
    (DIST/'en'/'index.html').write_text(en_page,encoding='utf-8')
    print(f'Built independent {SITE_ID}: {len(summaries)} items at {origin}')

if __name__=='__main__':generate()
