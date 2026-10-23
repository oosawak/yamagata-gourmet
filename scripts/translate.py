#!/usr/bin/env python3
"""Build-time optional DeepL translation cache. No runtime API calls.

DEEP(L)_AUTH_KEY should be configured as a GitHub Actions secret.
If unset, manually reviewed sample translations remain available.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
import yaml
import mistune
import re

ROOT=Path(__file__).resolve().parents[1]
CONTENT=ROOT/'content'
CACHE=ROOT/'cache/translations/en.json'
MANUAL=CONTENT/'i18n/en.json'

def hash_source(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

def parse_md(path):
    text=path.read_text(encoding='utf-8')
    match=re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$',text,re.S)
    if not match: raise ValueError(f'Invalid frontmatter: {path}')
    return yaml.safe_load(match.group(1)),match.group(2)

def request_translations(texts:list[str],auth_key:str):
    if not texts:return []
    api=os.getenv('DEEPL_API_URL') or ('https://api-free.deepl.com/v2/translate' if auth_key.endswith(':fx') else 'https://api.deepl.com/v2/translate')
    body=urllib.parse.urlencode({'text':texts,'source_lang':'JA','target_lang':'EN-US','tag_handling':'html'},doseq=True).encode('utf-8')
    req=urllib.request.Request(api,data=body,headers={'Authorization':'DeepL-Auth-Key '+auth_key,'Content-Type':'application/x-www-form-urlencoded','User-Agent':'StaticJsonNetworkTranslator/1.0'})
    with urllib.request.urlopen(req,timeout=45) as response:
        payload=json.load(response)
    translated=[x['text'] for x in payload['translations']]
    if len(translated)!=len(texts):raise RuntimeError('Translator response count mismatch')
    return translated

def translate_fields(fields:dict,auth_key:str):
    keys=list(fields)
    result={}
    # Batch translation; keep safely below request limits.
    for offset in range(0,len(keys),15):
        chunk=keys[offset:offset+15]
        values=request_translations([str(fields[key]) for key in chunk],auth_key)
        result.update(dict(zip(chunk,values)))
    return result

def run():
    secret=os.getenv('DEEPL_AUTH_KEY','').strip()
    if not secret:
        print('DeepL not configured: using bundled English samples and cached translations. To automatically translate new entries, set DEEPL_AUTH_KEY.');return
    manual=json.loads(MANUAL.read_text(encoding='utf-8'))
    cached=json.loads(CACHE.read_text(encoding='utf-8')) if CACHE.exists() else {'sites':{},'posts':{}}
    cached.setdefault('sites',{})
    cached.setdefault('posts',{})
    changed=0
    for p in sorted((CONTENT/'sites').glob('*.yml')):
        cfg=yaml.safe_load(p.read_text(encoding='utf-8'))
        key=cfg['id']
        digest=hash_source(cfg)
        if (manual.get('sites',{}).get(key,{ }).get('source_hash')==digest or cached['sites'].get(key,{}).get('source_hash')==digest):continue
        fields={x:cfg[x] for x in ('name','short_name','kind_label','hero_title','description','subtitle','hero_note','about') if x in cfg}
        translated=translate_fields(fields,secret)
        cached['sites'][key]={'source_hash':digest,'fields':translated}
        changed+=1
    for path in sorted((CONTENT/'posts').glob('*/*.md')):
        fm,body=parse_md(path)
        sid=path.parent.name
        slug=path.stem[11:]
        key=f'{sid}:{slug}'
        digest=hash_source({'frontmatter':fm,'markdown':body})
        if (manual.get('posts',{}).get(key,{}).get('source_hash')==digest or cached['posts'].get(key,{}).get('source_hash')==digest):continue
        # Translate short metadata and HTML before Base64 images are embedded.
        html=mistune.create_markdown(renderer=mistune.HTMLRenderer(escape=True))(body)
        fields={x:fm[x] for x in ('title','category','summary','cover_alt','unit','stock') if x in fm}
        fields['html']=html
        translated=translate_fields(fields,secret)
        cached['posts'][key]={'source_hash':digest,'fields':translated}
        changed+=1
    CACHE.parent.mkdir(parents=True,exist_ok=True)
    CACHE.write_text(json.dumps(cached,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f'DeepL translations updated for {changed} changed records (unchanged records reused).')

if __name__=='__main__':
    try: run()
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,RuntimeError) as e:
        print(f'Translation API unavailable: {e}. Existing valid translations will be reused; untranslated changes remain Japanese.',file=sys.stderr)
        # Allow publishing the base Japanese content and previous translations.
