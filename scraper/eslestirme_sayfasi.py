#!/usr/bin/env python3
"""boykot.co ↔ Boykot Dedektifi elle eşleştirme sayfası üretir (tek dosya, internetsiz çalışır; logolar için internet gerekir).

Kullanım:  python scraper/eslestirme_sayfasi.py [--root .] [--out eslestirme.html]
Sayfada yapılan seçimler `eslesmeler.json` olarak indirilir → config/eslesmeler.json yerine konur.
"""
import argparse
import html
import json
import os
import sys
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import compact, metin_temizle  # noqa: E402
from merge import resolve_keys  # noqa: E402

GENERIC = {"grup", "group", "holding", "deterjan", "su", "com", "beauty", "gida", "tv", "ag", "inc", "sirketi", "company"}


def suggestions(k, bd_keys, n=6):
    """Bir boykot.co anahtarı için en olası Dedektif markaları."""
    ck = compact(k)
    words = [w for w in k.split() if len(w) >= 3 and w not in GENERIC]
    scored = []
    for d in bd_keys:
        cd = compact(d)
        r = SequenceMatcher(None, ck, cd).ratio()
        dw = d.split()
        bonus = 0.0
        if words and any(w in dw for w in words):
            bonus = 0.35            # ortak anlamlı kelime ("omo deterjan" ↔ "omo")
        if len(cd) >= 4 and (cd in ck or ck in cd):
            bonus = max(bonus, 0.3)
        s = r + bonus
        if s >= 0.6:
            scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:n]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(HERE))
    ap.add_argument("--out", default="eslestirme.html")
    a = ap.parse_args()
    root = a.root
    seen = json.load(open(os.path.join(root, "state", "gorulme.json"), encoding="utf-8"))
    decisions = json.load(open(os.path.join(root, "config", "eslesmeler.json"), encoding="utf-8"))
    bd = {k: v["entry"] for k, v in seen["boykotdedektifi"].items()}
    bc = {k: v["entry"] for k, v in seen["boykotco"].items()}
    mapping, _ = resolve_keys(bd, bc, decisions)

    bd_keys = sorted(bd)
    bd_list = [{"k": k, "n": bd[k]["name"], "l": bd[k].get("logo"), "c": bd[k].get("categories", [])[:3],
                "u": bd[k]["url"], "s": bd[k]["label"]} for k in bd_keys]
    items = []
    for k in sorted(bc, key=lambda x: metin_temizle(bc[x]["name"])):
        e = bc[k]
        target = mapping[k] if mapping[k] in bd else None
        items.append({
            "k": k, "n": e["name"], "l": e.get("logo"), "c": e.get("categories", []), "u": e["url"],
            "d": (e.get("desc") or "")[:160],
            "auto": target,                         # otomatik eşleştiği Dedektif markası (yoksa null)
            "same": target == k,               # ad (büyük/küçük harf, Türkçe karakter, noktalama hariç) birebir aynı
            "sug": [] if target else suggestions(k, bd_keys),
        })
    data = {"bd": bd_list, "bc": items, "decisions": decisions}
    page = TEMPLATE.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page)
    un = sum(1 for i in items if not i["auto"])
    print(f"{a.out}: {len(items)} boykot.co markası ({un} eşleşmemiş), {len(bd_list)} Dedektif markası")


TEMPLATE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Marka Eşleştirme</title>
<style>
:root{--bg:#f6f7f5;--card:#fff;--text:#16211b;--muted:#5d6b63;--line:#e3e7e4;--accent:#2f7a3a;--accent-bg:#e7f3e8;--warn:#b5651d;--warn-bg:#fbefe3;--bad:#b42318;--bad-bg:#fdecea;--chip:#eef1ef}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111513;--card:#1a201d;--text:#e7ece9;--muted:#9aa8a0;--line:#2b332f;--accent:#6cc070;--accent-bg:#1f3322;--warn:#e6a35c;--warn-bg:#35281b;--bad:#f2786d;--bad-bg:#3a1f1d;--chip:#242b27}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line);padding:12px 16px}
.wrap{max-width:1100px;margin:0 auto}
h1{font-size:19px;margin:0 0 2px}
.sub{color:var(--muted);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}
.tabs button,.btn{border:1px solid var(--line);background:var(--card);color:var(--text);padding:7px 12px;border-radius:999px;cursor:pointer;font:inherit;font-size:14px}
.tabs button[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.count{color:var(--muted);font-size:13px;margin-left:auto}
input[type=search]{border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:10px;padding:8px 10px;font:inherit;min-width:220px}
main{padding:14px 16px 80px}
.help{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-bottom:12px;font-size:14px;color:var(--muted)}
.row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:14px;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px;margin-bottom:10px}
.row.done{border-color:var(--accent)}
.row.split{border-color:var(--bad)}
.brand{display:flex;gap:10px;align-items:flex-start;min-width:0}
.logo{width:48px;height:48px;border-radius:10px;background:#fff;border:1px solid var(--line);object-fit:contain;flex:none}
.ph{width:48px;height:48px;border-radius:10px;background:var(--chip);display:grid;place-items:center;font-weight:700;color:var(--muted);flex:none}
.name{font-weight:650;word-break:break-word}
.name a{color:inherit}
.meta{font-size:12.5px;color:var(--muted)}
.desc{font-size:12.5px;color:var(--muted);margin-top:2px}
.src{font-size:11px;font-weight:700;letter-spacing:.04em;color:var(--muted);text-transform:uppercase}
.right{min-width:0}
.cands{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
.cand{display:flex;gap:6px;align-items:center;border:1px solid var(--line);background:var(--chip);color:var(--text);border-radius:10px;padding:4px 8px 4px 4px;cursor:pointer;font:inherit;font-size:13px;max-width:100%}
.cand img,.cand .mini{width:26px;height:26px;border-radius:6px;background:#fff;object-fit:contain;flex:none}
.cand .mini{display:grid;place-items:center;background:var(--card);font-size:11px;color:var(--muted)}
.cand[aria-pressed=true]{background:var(--accent-bg);border-color:var(--accent)}
.cand small{color:var(--muted)}
.choice{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:6px}
.pill{font-size:12.5px;padding:3px 9px;border-radius:999px;background:var(--chip);color:var(--muted)}
.pill.ok{background:var(--accent-bg);color:var(--accent)}
.pill.no{background:var(--bad-bg);color:var(--bad)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.link{background:none;border:none;color:var(--accent);cursor:pointer;font:inherit;font-size:13px;padding:2px 4px;text-decoration:underline}
.link.bad{color:var(--bad)}
.search{position:relative}
.search input{width:100%}
.results{position:absolute;z-index:3;left:0;right:0;top:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;margin-top:4px;max-height:280px;overflow:auto;box-shadow:0 8px 24px rgba(0,0,0,.12)}
.results button{display:flex;gap:8px;align-items:center;width:100%;text-align:left;border:none;background:none;color:var(--text);padding:6px 8px;cursor:pointer;font:inherit;font-size:13.5px}
.results button:hover,.results button:focus{background:var(--chip)}
.results img,.results .mini{width:26px;height:26px;border-radius:6px;background:#fff;object-fit:contain}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--card);border-top:1px solid var(--line);padding:10px 16px}
footer .wrap{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.toast{color:var(--accent);font-size:13px}
@media (max-width:720px){.row{grid-template-columns:1fr}input[type=search]{min-width:0;flex:1}}
</style>
</head>
<body>
<header><div class="wrap">
  <h1>boykot.co ↔ Boykot Dedektifi eşleştirme</h1>
  <div class="sub">Her boykot.co markası için Boykot Dedektifi'ndeki karşılığını seçin. Bitince alttan <b>eslesmeler.json</b>'u indirip gönderin.</div>
  <div class="bar">
    <div class="tabs" role="group">
      <button data-tab="un" aria-pressed="true">Eşleşmeyenler</button>
      <button data-tab="diff">Farklı yazılmış eşleşmeler</button>
      <button data-tab="auto">Tüm otomatik eşleşmeler</button>
    </div>
    <input type="search" id="filter" placeholder="Marka ara…">
    <span class="count" id="count"></span>
  </div>
</div></header>
<main><div class="wrap">
  <div class="help" id="help"></div>
  <div id="list"></div>
</div></main>
<footer><div class="wrap">
  <span id="summary" class="sub"></span>
  <span class="toast" id="toast"></span>
  <span style="flex:1"></span>
  <button class="btn" id="copy">Panoya kopyala</button>
  <button class="btn primary" id="download">eslesmeler.json indir</button>
</div></footer>
<script>
const DATA = /*DATA*/null;
const BD = new Map(DATA.bd.map(b => [b.k, b]));
const norm = s => s.toLocaleLowerCase('tr').normalize('NFKD').replace(/[̀-ͯ]/g,'').replace(/ı/g,'i').replace(/[^a-z0-9]+/g,' ').trim();
// Kararlar: k (boykot.co anahtarı) → {t:'merge', d:dedektif anahtarı} | {t:'none'} (Dedektif'te yok) | {t:'split'} (otomatik eşleşme yanlış)
const choice = new Map();
let tab = 'un';
const HELP = {
  un: 'Bu markalar Boykot Dedektifi\'ndeki hiçbir adla otomatik eşleşmedi. Öneri varsa doğru olana tıklayın, yoksa aramadan bulun. Dedektif\'te gerçekten yoksa <b>"Dedektif\'te yok"</b> deyin (ayrı marka olarak kalır).',
  diff: 'Adları birebir aynı olmayan ama otomatik birleştirilen markalar (ör. "Kitkat" ↔ "Kit Kat"). Yanlışsa <b>"Yanlış eşleşme"</b> deyin ya da doğru markayı seçin.',
  auto: 'Adı birebir aynı olduğu için otomatik birleştirilen markalar. Genelde doğrudur; farklı bir şirketse <b>"Yanlış eşleşme"</b> deyin.'
};
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const logo = (u, n, cls='logo') => u ? `<img class="${cls}" src="${esc(u)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'${cls==='logo'?'ph':'mini'}',textContent:'${esc((n||'?')[0])}'}))">` : `<div class="${cls==='logo'?'ph':'mini'}">${esc((n||'?')[0])}</div>`;

function itemsFor(t){
  return DATA.bc.filter(i => t==='un' ? !i.auto : t==='diff' ? (i.auto && !i.same) : (i.auto && i.same));
}
function current(i){
  const c = choice.get(i.k);
  if (c) return c;
  return i.auto ? {t:'merge', d:i.auto, auto:true} : null;
}
function render(){
  document.querySelectorAll('.tabs button').forEach(b => b.setAttribute('aria-pressed', b.dataset.tab===tab));
  document.getElementById('help').innerHTML = HELP[tab];
  const q = norm(document.getElementById('filter').value || '');
  const items = itemsFor(tab).filter(i => !q || norm(i.n).includes(q) || (i.auto && norm(BD.get(i.auto).n).includes(q)));
  const list = document.getElementById('list');
  const limit = tab==='auto' && !q ? 150 : 2000;
  list.innerHTML = items.slice(0, limit).map(rowHTML).join('') + (items.length > limit ? `<div class="help">İlk ${limit} gösteriliyor — aramayla daraltın.</div>` : '');
  document.getElementById('count').textContent = `${items.length} marka`;
  summary();
}
function bdCard(b, cls='cand', pressed=false, k=''){
  return `<button class="${cls}" data-k="${esc(k)}" data-d="${esc(b.k)}" aria-pressed="${pressed}">${logo(b.l, b.n, 'mini')}<span><b>${esc(b.n)}</b> <small>${esc((b.c||[]).join(', '))}${b.s?' · '+esc(b.s):''}</small></span></button>`;
}
function rowHTML(i){
  const c = current(i);
  const merged = c && c.t==='merge' ? BD.get(c.d) : null;
  const status = !c ? '<span class="pill warn">Karar bekliyor</span>'
    : c.t==='none' ? '<span class="pill">Dedektif\'te yok — ayrı marka</span>'
    : c.t==='split' ? '<span class="pill no">Yanlış eşleşme — ayrı tutulacak</span>'
    : `<span class="pill ok">${c.auto ? 'Otomatik' : 'Seçildi'}: ${esc(merged.n)}</span>`;
  const sug = (i.sug||[]).map(k => BD.get(k)).filter(Boolean)
    .map(b => bdCard(b, 'cand', !!(c && c.t==='merge' && c.d===b.k), i.k)).join('');
  const shown = merged && !(i.sug||[]).includes(merged.k) ? bdCard(merged, 'cand', true, i.k) : '';
  const actions = i.auto
    ? `<button class="link bad" data-act="split" data-k="${esc(i.k)}">Yanlış eşleşme</button>`
    : `<button class="link" data-act="none" data-k="${esc(i.k)}">Dedektif'te yok</button>`;
  const undo = choice.has(i.k) ? `<button class="link" data-act="undo" data-k="${esc(i.k)}">Geri al</button>` : '';
  return `<div class="row ${c && !c.auto && c.t!=='split' ? 'done' : ''} ${c && c.t==='split' ? 'split' : ''}">
    <div class="brand">${logo(i.l, i.n)}<div style="min-width:0">
      <div class="src">boykot.co</div>
      <div class="name"><a href="${esc(i.u)}" target="_blank" rel="noopener">${esc(i.n)}</a></div>
      <div class="meta">${esc(i.c.join(', '))}</div>
      ${i.d ? `<div class="desc">${esc(i.d)}</div>` : ''}
    </div></div>
    <div class="right">
      <div class="src">Boykot Dedektifi'ndeki karşılığı</div>
      <div class="choice">${status} ${actions} ${undo}</div>
      <div class="cands">${shown}${sug}</div>
      <div class="search"><input type="search" placeholder="Dedektif'te ara (ör. Omo)…" data-search="${esc(i.k)}" autocomplete="off"><div class="results" hidden></div></div>
    </div>
  </div>`;
}
function summary(){
  let merge=0, none=0, split=0;
  choice.forEach(c => { if (c.t==='merge') merge++; else if (c.t==='none') none++; else split++; });
  const pending = itemsFor('un').filter(i => !choice.has(i.k)).length;
  document.getElementById('summary').innerHTML = `Seçimleriniz: <b>${merge}</b> eşleştirme · <b>${none}</b> "Dedektif'te yok" · <b>${split}</b> yanlış eşleşme · eşleşmeyenlerden <b>${pending}</b> karar bekliyor`;
}
function output(){
  const out = JSON.parse(JSON.stringify(DATA.decisions));
  out.birlestir = out.birlestir || {}; out.ayri = out.ayri || [];
  const key = (a,b) => a+'|'+b;
  const have = new Set(out.ayri.map(p => key(norm(p[0]), norm(p[1]))));
  choice.forEach((c, k) => {
    const i = DATA.bc.find(x => x.k===k);
    if (c.t==='merge') {
      out.birlestir[k] = c.d;
      out.ayri = out.ayri.filter(p => norm(p[0]) !== k);
    } else if (c.t==='split') {
      delete out.birlestir[k];
      if (!have.has(key(k, i.auto))) { out.ayri.push([k, i.auto]); have.add(key(k, i.auto)); }
    } else if (c.t==='none') {
      delete out.birlestir[k];
      (i.sug||[]).forEach(d => { if (!have.has(key(k,d))) { out.ayri.push([k, d]); have.add(key(k,d)); } });
    }
  });
  return JSON.stringify(out, null, 2) + '\n';
}
function toast(t){ const el=document.getElementById('toast'); el.textContent=t; setTimeout(()=>el.textContent='',2500); }

document.addEventListener('click', e => {
  const tb = e.target.closest('.tabs button');
  if (tb){ tab = tb.dataset.tab; render(); return; }
  const cand = e.target.closest('.cand, .results button');
  if (cand && cand.dataset.k){
    const i = DATA.bc.find(x => x.k===cand.dataset.k);
    if (i.auto === cand.dataset.d) choice.delete(i.k); else choice.set(i.k, {t:'merge', d:cand.dataset.d});
    render(); return;
  }
  const act = e.target.closest('[data-act]');
  if (act){
    const k = act.dataset.k;
    if (act.dataset.act==='undo') choice.delete(k); else choice.set(k, {t:act.dataset.act});
    render(); return;
  }
  if (!e.target.closest('.search')) document.querySelectorAll('.results').forEach(r => r.hidden = true);
});
document.addEventListener('input', e => {
  if (e.target.id==='filter'){ render(); return; }
  const k = e.target.dataset.search;
  if (k === undefined) return;
  const q = norm(e.target.value);
  const box = e.target.nextElementSibling;
  if (q.length < 2){ box.hidden = true; return; }
  const res = DATA.bd.filter(b => norm(b.n).includes(q)).slice(0, 30);
  box.innerHTML = res.length ? res.map(b => `<button data-k="${esc(k)}" data-d="${esc(b.k)}">${logo(b.l, b.n, 'mini')}<span><b>${esc(b.n)}</b> <small>${esc((b.c||[]).join(', '))}</small></span></button>`).join('') : '<div class="sub" style="padding:8px">Bulunamadı</div>';
  box.hidden = false;
});
document.getElementById('download').onclick = () => {
  const blob = new Blob([output()], {type:'application/json'});
  const a = Object.assign(document.createElement('a'), {href: URL.createObjectURL(blob), download: 'eslesmeler.json'});
  document.body.appendChild(a); a.click(); a.remove();
  toast('İndirildi');
};
document.getElementById('copy').onclick = async () => {
  try { await navigator.clipboard.writeText(output()); toast('Kopyalandı'); }
  catch { toast('Kopyalanamadı — indirmeyi kullanın'); }
};
window.addEventListener('beforeunload', e => { if (choice.size) { e.preventDefault(); e.returnValue = ''; } });
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
