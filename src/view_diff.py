#!/usr/bin/env python3
"""
src/view_diff.py (v3)
---------------------
Interactive review UI with "Mark for Review" persistence.

 • ← / → navigation & Jump-to
 • Displays commit metadata & diff
 • Button toggles “Mark for Review”
 • Saves curated selections to mined_patches_curated/

Dependencies: standard Python 3 libs.
"""

import os, sys, json, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
from html import escape
from io import BytesIO

BASE_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
RAW_DIR = os.path.join(BASE_DIR, "mined_patches_raw")
CURATED_DIR = os.path.join(BASE_DIR, "mined_patches_curated")
os.makedirs(CURATED_DIR, exist_ok=True)

# load latest categorized dataset
raw_files = [f for f in os.listdir(RAW_DIR) if f.endswith("_categorized.json")]
if not raw_files:
    print("❌ No categorized JSON in mined_patches_raw/")
    sys.exit(1)
raw_files.sort(key=lambda f: os.path.getmtime(os.path.join(RAW_DIR, f)), reverse=True)
RAW_FILE = os.path.join(RAW_DIR, raw_files[0])

with open(RAW_FILE, "r", encoding="utf-8", errors="replace") as f:
    DATA = json.load(f)

CATEGORIES = list(DATA.keys())
CURATED_FILE = os.path.join(CURATED_DIR, os.path.basename(RAW_FILE).replace("_categorized","_curated"))

# ensure curated file
if os.path.exists(CURATED_FILE):
    with open(CURATED_FILE,"r",encoding="utf-8",errors="replace") as f:
        CURATED=json.load(f)
else:
    CURATED={cat:[] for cat in CATEGORIES}
    with open(CURATED_FILE,"w",encoding="utf-8") as f: json.dump(CURATED,f,indent=2)

# ---------------------------------------------------------------------
STYLE = """
<style>
body{background:#111;color:#ddd;font-family:system-ui,sans-serif;margin:0;padding:.6rem 1rem;}
header{display:flex;align-items:center;flex-wrap:wrap;gap:.4rem;margin-bottom:.6rem;}
h1{font-size:1.3rem;color:#6cf;margin-right:1rem;}
select,input,button{background:#222;color:#ddd;border:1px solid #333;
  border-radius:4px;font-size:1rem;padding:.3rem .5rem;}
button:hover{background:#333;cursor:pointer;}
#view{margin-top:.6rem;}
.meta{line-height:1.4em;font-size:.95em;margin-bottom:.4rem;}
.diff{white-space:pre;font-family:monospace;line-height:1.2em;
  background:#000;border:1px solid #333;padding:1rem;
  overflow-x:auto;max-height:75vh;margin-top:.4rem;}
.add{color:#2ecc71;} .del{color:#e74c3c;} .info{color:#888;}
footer{text-align:center;color:#666;margin-top:.4rem;font-size:.85em;}
.marked{color:#2ecc71;font-weight:bold;}
</style>
<script>
let category=null,commits=[],idx=0,curated={};

async function initCurated(){let r=await fetch('/curated');curated=await r.json();}
async function loadCategory(cat){
  category=cat;
  const res=await fetch('/category?name='+encodeURIComponent(cat));
  commits=await res.json(); idx=0;
  renderCommit();
}
async function renderCommit(){
  const view=document.getElementById('view');const status=document.getElementById('status');
  if(!category||!commits.length){view.innerHTML='<p style="color:#777">Select a category.</p>';status.textContent='';return;}
  const r=await fetch(`/diff?cat=${encodeURIComponent(category)}&idx=${idx}`);
  const c=await r.json();
  const files=(c.files_changed||[]).join(', ');
  let diffHTML=''; c.diff.split('\\n').forEach(line=>{
      if(line.startsWith('+')) diffHTML+=`<span class='add'>${line}</span>\\n`;
      else if(line.startsWith('-')) diffHTML+=`<span class='del'>${line}</span>\\n`;
      else diffHTML+=`<span class='info'>${line}</span>\\n`;
  });
  const markBtn=document.getElementById('markbtn');
  const marked=isMarked(c.commit);
  markBtn.textContent=marked?'Unmark 🚫':'Mark for Review ✅';
  markBtn.className=marked?'marked':'';
  markBtn.onclick=()=>toggleMark(c.commit);
  view.innerHTML=`
   <div class="meta">
     <span><b>Category:</b> ${category}</span>
     <span><b>Commit:</b> ${c.commit}</span>
     <span><b>Author:</b> ${escapeHTML(c.author)} &lt;${escapeHTML(c.email)}&gt;</span>
     <span><b>Date:</b> ${c.date}</span>
     <span><b>Files:</b> ${escapeHTML(files)}</span>
     <span><b>Insertions:</b> ${c.insertions} | <b>Deletions:</b> ${c.deletions}</span>
   </div>
   <h3>${escapeHTML(c.message)}</h3>
   <div class="diff">${diffHTML}</div>`;
  status.textContent=`Commit ${idx+1}/${commits.length}`;
}
function nextCommit(){if(idx<commits.length-1){idx++;renderCommit();}}
function prevCommit(){if(idx>0){idx--;renderCommit();}}
function jumpTo(){
  let n=parseInt(document.getElementById('jump').value);
  if(isNaN(n)||!commits.length)return;
  n=Math.max(1,Math.min(n,commits.length));
  idx=n-1;renderCommit();
}
function escapeHTML(s){return s?s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])):'';}
function isMarked(hash){return curated[category]?.some(c=>c.commit===hash);}
async function toggleMark(hash){
  const marked=isMarked(hash);
  await fetch('/mark',{method:'POST',body:JSON.stringify({cat:category,commit:hash,action:marked?'remove':'add'})});
  curated=await (await fetch('/curated')).json();
  renderCommit();
}
document.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight'||e.key==='d'||e.key==='D')nextCommit();
  else if(e.key==='ArrowLeft'||e.key==='a'||e.key==='A')prevCommit();
});
</script>
"""

def index_html():
    opts="\n".join(f"<option value='{escape(c)}'>{escape(c)}</option>"for c in CATEGORIES)
    return f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>SQuire Review</title>{STYLE}</head>
<body onload="initCurated()">
<header>
  <h1>SQuire Reviewer</h1>
  <label>Category:</label>
  <select id="category" onchange="loadCategory(this.value)">
    <option value="">-- Select --</option>{opts}
  </select>
  <button onclick="prevCommit()">← Prev</button>
  <button onclick="nextCommit()">Next →</button>
  <input id="jump" type="number" min="1" placeholder="Go #" style="width:6em;"
         onkeydown="if(event.key==='Enter')jumpTo()">
  <button onclick="jumpTo()">Go</button>
  <button id="markbtn">Mark for Review ✅</button>
  <span id="status" style="margin-left:1rem;color:#999"></span>
</header>
<hr style="border:0;border-top:1px solid #333;"><div id="view"></div></body></html>"""

# ---------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path=="/": return self.send(200,"text/html",index_html())
        if parsed.path=="/category":
            cat=parse_qs(parsed.query).get("name",[""])[0]
            return self.send_json(DATA.get(cat,[]))
        if parsed.path=="/diff":
            q=parse_qs(parsed.query)
            cat=q.get("cat",[""])[0]; i=int(q.get("idx",[0])[0])
            arr=DATA.get(cat,[])
            return self.send_json(arr[i] if 0<=i<len(arr) else {})
        if parsed.path=="/curated":
            return self.send_json(CURATED)
        self.send(404,"text/plain","Not found")

    def do_POST(self):
        length=int(self.headers.get("Content-Length","0"))
        body=self.rfile.read(length).decode("utf-8","replace")
        data=json.loads(body or "{}")
        cat=data.get("cat"); commit_hash=data.get("commit")
        action=data.get("action")
        if not (cat and commit_hash): return self.send_json({"status":"error"})
        changed=False
        if action=="add":
            entry=next((c for c in DATA.get(cat,[]) if c["commit"]==commit_hash),None)
            if entry and not any(c["commit"]==commit_hash for c in CURATED.get(cat,[])):
                CURATED[cat].append(entry); changed=True
        elif action=="remove":
            CURATED[cat]=[c for c in CURATED.get(cat,[]) if c["commit"]!=commit_hash]
            changed=True
        if changed:
            with open(CURATED_FILE,"w",encoding="utf-8",errors="replace") as f:
                json.dump(CURATED,f,indent=2,ensure_ascii=False)
        self.send_json({"status":"ok","action":action})

    def send(self,code,ctype,body):
        self.send_response(code)
        self.send_header("Content-Type",f"{ctype}; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8","replace") if isinstance(body,str) else body)

    def send_json(self,obj):
        self.send(200,"application/json",json.dumps(obj,ensure_ascii=False))

# ---------------------------------------------------------------------
def main():
    port=5000
    url=f"http://127.0.0.1:{port}/"
    print(f"🌐 Serving on {url}")
    webbrowser.open(url)
    HTTPServer(("127.0.0.1",port),Handler).serve_forever()

if __name__=="__main__":
    main()