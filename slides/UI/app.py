"""Demo UI: nhập một nhận định -> hiển thị chi tiết từng bước của Facet Graph RAG.

Chạy từ bất kỳ đâu:
    python3 FINAL/slides/UI/app.py [--port 7860] [--no-dense]

- Dùng đúng các module thật của hệ thống (không mock).
- Cần .env ở gốc FINAL (OPENAI_API_KEY cho phân rã khía cạnh bằng LLM — thiếu thì
  tự chuyển sang rule-based; GEMINI_API_KEY cho bước kiểm chứng — thiếu thì hiển thị
  prompt nhưng không có phán quyết).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from src.common.io import load_yaml
from src.facet.graph_index import GraphIndex
from src.facet.extract_claim_facets import extract_row, load_env_file
from src.facet.match_facets import match_row
from src.facet.retrieve_evidence import retrieve_row
from src.facet.rerank_evidence import rerank_row
from src.facet.fuse_hybrid_facet import fuse_row
from src.facet import verify_facet as vf
from src.rag.retrieve import load_corpus, reciprocal_rank_fusion, top_indices

STATE: dict = {}


def tokenize(text: str) -> list[str]:
    return text.lower().split()


def load_env_fallback() -> None:
    """Nạp FINAL/.env; nếu thiếu, thử .env ở thư mục cha (repo gốc)."""
    for env_path in (ROOT / ".env", ROOT.parent / ".env"):
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def startup(no_dense: bool) -> None:
    load_env_file()
    load_env_fallback()
    print("[1/4] Nạp cấu hình + đồ thị tri thức ...")
    cfg = load_yaml("configs/facet/facet_full.yaml")
    gi = GraphIndex(cfg)
    print(f"      GraphIndex: {len(gi.nodes)} nút, {len(gi.edges)} cạnh")

    print("[2/4] Nạp corpus + dựng chỉ mục BM25 ...")
    docs = load_corpus("data/outputs/corpus/chunks.json")
    from rank_bm25 import BM25Okapi
    bm25 = BM25Okapi([tokenize(d["text"]) for d in docs])

    dense_model, corpus_emb = None, None
    if not no_dense:
        try:
            print("[3/4] Nạp BGE-M3 + mã hóa 540 đoạn (lần đầu hơi lâu) ...")
            import numpy as np
            from sentence_transformers import SentenceTransformer
            dense_model = SentenceTransformer("BAAI/bge-m3")
            device = str(getattr(dense_model, "device", "?"))
            print(f"      Thiết bị: {device}" + ("  ⚠ CPU sẽ mất vài phút — cân nhắc --no-dense" if "cuda" not in device else ""))
            corpus_emb = dense_model.encode(
                [d["text"] for d in docs], normalize_embeddings=True,
                show_progress_bar=True, batch_size=16,
            )
            print("      Dense OK")
        except Exception as exc:
            print(f"      Bỏ qua dense ({exc}) — chạy BM25-only")
    else:
        print("[3/4] --no-dense: chạy BM25-only")

    print("[4/4] Sẵn sàng.")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    vertex_project = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT_ID")
                      or os.getenv("GEMINI_PROJECT_ID") or os.getenv("PROJECT_ID"))
    STATE.update(cfg=cfg, gi=gi, docs=docs, bm25=bm25, dense=dense_model, emb=corpus_emb,
                 openai_key=os.getenv("OPENAI_API_KEY"),
                 gemini_key=gemini_key,
                 gemini_ok=bool(gemini_key or vertex_project),
                 gemini_via=("API key" if gemini_key else (f"Vertex AI ({vertex_project})" if vertex_project else "—")))
    print(f"      OpenAI key: {'có' if STATE['openai_key'] else 'KHÔNG'} | Gemini: {STATE['gemini_via']}")


def hybrid_retrieve(claim: str, final_k: int = 5, pool: int = 20) -> list[dict]:
    import numpy as np
    docs, bm25 = STATE["docs"], STATE["bm25"]
    bm25_scores = np.asarray(bm25.get_scores(tokenize(claim)))
    bm25_top = top_indices(bm25_scores, pool)
    if STATE["dense"] is not None:
        q = STATE["dense"].encode(claim, normalize_embeddings=True)
        dense_scores = np.asarray(q @ STATE["emb"].T)
        dense_top = top_indices(dense_scores, pool)
        fused = reciprocal_rank_fusion([bm25_top, dense_top], 60)
        ranked = sorted(fused, key=fused.get, reverse=True)[:final_k]
    else:
        dense_scores = np.zeros(len(docs))
        fused = {i: float(bm25_scores[i]) for i in bm25_top[:final_k]}
        ranked = bm25_top[:final_k]
    out = []
    for rank, idx in enumerate(ranked, start=1):
        d = docs[idx]
        out.append({
            "rank": rank, "doc_id": d["doc_id"], "book": d["book"],
            "page": d.get("page"), "pages": d.get("pages", []),
            "source": d.get("source"), "section": d.get("section"),
            "year_mentions": d.get("year_mentions", []),
            "score": float(fused.get(idx, 0.0)),
            "bm25_score": float(bm25_scores[idx]), "dense_score": float(dense_scores[idx]),
            "text": d["text"],
        })
    return out


def run_pipeline(claim: str) -> dict:
    import time
    from concurrent.futures import ThreadPoolExecutor
    cfg, gi = STATE["cfg"], STATE["gi"]
    item = {"ID": "demo", "claim": claim, "label": "", "key": "", "relevant": ""}
    use_llm = bool(STATE["openai_key"])
    timing = {}
    t0 = time.perf_counter()

    # NHÁNH TEXT chạy song song với NHÁNH FACET->GRAPH (độc lập nhau)
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_text = pool.submit(lambda: (time.perf_counter(), hybrid_retrieve(claim)))
        t = time.perf_counter()
        facet_row = extract_row(item, 0, gi, cfg, use_llm, STATE["openai_key"])
        timing["facet_llm"] = round(time.perf_counter() - t, 2)
        t = time.perf_counter()
        matched = match_row(facet_row, gi, cfg)
        evidence = retrieve_row(matched, gi, cfg)
        reranked = rerank_row(evidence, cfg)
        timing["graph_local"] = round(time.perf_counter() - t, 2)
        t_start_text, text_docs = fut_text.result()
        timing["text_retrieval"] = round(time.perf_counter() - t_start_text, 2)

    fused = fuse_row({"retrieved_context": text_docs}, reranked, cfg)

    prompt = vf.build_prompt(fused, cfg)
    verdict, raw = None, ""
    if STATE["gemini_ok"]:
        try:
            t = time.perf_counter()
            res = vf.call_model_verify(fused, cfg, "gemini", STATE["gemini_key"], "gemini-2.5-flash")
            timing["verify_llm"] = round(time.perf_counter() - t, 2)
            raw = res.pop("raw_response", "")
            verdict = res
        except Exception as exc:
            verdict = {"error": str(exc)}
    else:
        verdict = {"error": "Chưa cấu hình Gemini (GEMINI_API_KEY hoặc PROJECT_ID/Vertex) trong .env — hiển thị prompt, bỏ qua phán quyết."}

    max_chars = int(cfg["verifier"].get("max_chars_per_evidence", 1400))
    fused_view = []
    for i, ev in enumerate(fused["top_evidence"], start=1):
        cropped = vf.crop_text_to_claim(str(ev.get("text", "")), claim, max_chars)
        fused_view.append({
            "eid": f"E{i}", "branch": ev.get("source_branch"),
            "chunk_id": ev.get("chunk_id"), "book": ev.get("book"),
            "pages": ev.get("pages"), "section": ev.get("section"),
            "facet_hits": [f"{h.get('facet_type')}={h.get('facet_value')}" for h in ev.get("facet_hits", [])[:4]],
            "cropped": cropped[:600] + ("…" if len(cropped) > 600 else ""),
            "was_cropped": len(str(ev.get("text", ""))) > max_chars,
        })
    return {
        "facets": {k: v for k, v in facet_row.get("facets", {}).items() if v},
        "facet_source": "LLM (GPT-4o-mini)" if use_llm and not facet_row.get("llm_error") else "rule-based (không có OPENAI_API_KEY)",
        "matches": [
            {"facet": f"{m['facet_type']} = {m['facet_value']}", "matched": m["matched"],
             "nodes": [f"{x['node_name']} ({x['node_type']}, {x['match_method']})" for x in m["matches"][:3]]}
            for m in matched.get("facet_matches", [])
        ],
        "text_top5": [
            {"rank": d["rank"], "doc_id": d["doc_id"], "book": d["book"], "section": d.get("section"),
             "bm25": round(d["bm25_score"], 2), "dense": round(d["dense_score"], 3), "rrf": round(d["score"], 4),
             "snippet": d["text"][:280] + "…"} for d in text_docs
        ],
        "graph_top": [
            {"chunk_id": e.get("chunk_id"), "book": e.get("book"), "section": e.get("section"),
             "final": round(e.get("scores", {}).get("final", 0), 3),
             "facet_hits": [f"{h.get('facet_type')}={h.get('facet_value')}" for h in e.get("facet_hits", [])[:4]],
             "snippet": str(e.get("text", ""))[:280] + "…"}
            for e in reranked.get("top_evidence", [])[:3]
        ],
        "fused": fused_view,
        "llm": {"provider": f"Google Gemini — {STATE['gemini_via']}", "model": "gemini-2.5-flash (temperature 0)",
                "facet_model": "GPT-4o-mini" if use_llm else "rule-based",
                "embed_model": "BAAI/bge-m3" if STATE["dense"] is not None else "(tắt — BM25 only)",
                "prompt": prompt, "raw_response": raw},
        "verdict": verdict,
        "timing": {**timing, "total": round(time.perf_counter() - t0, 2)},
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # bớt ồn
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/verify":
            return self._send(404, "{}")
        try:
            n = int(self.headers.get("Content-Length", 0))
            claim = json.loads(self.rfile.read(n)).get("claim", "").strip()
            if not claim:
                return self._send(400, json.dumps({"error": "claim rỗng"}))
            result = run_pipeline(claim)
            self._send(200, json.dumps(result, ensure_ascii=False))
        except Exception as exc:
            self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False))


PAGE = r"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"><title>Facet Graph RAG — Demo</title>
<style>
:root{--blue:#2563eb;--ink:#0f172a;--mut:#64748b;--bg:#f1f5f9}
*{box-sizing:border-box;margin:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--ink)}
header{background:linear-gradient(120deg,#1e3a8a,#2563eb 60%,#3b82f6);color:#fff;padding:30px 0 26px;text-align:center}
header h1{font-size:26px;letter-spacing:.3px} header p{opacity:.85;margin-top:6px;font-size:14px}
.wrap{max-width:1060px;margin:0 auto;padding:22px 18px 60px}
.inputrow{display:flex;gap:10px;margin:-46px auto 26px;max-width:900px;background:#fff;border-radius:14px;
  box-shadow:0 10px 30px rgba(2,6,23,.18);padding:14px}
textarea{flex:1;border:1.5px solid #e2e8f0;border-radius:10px;padding:12px 14px;font-size:15.5px;resize:none;height:64px;font-family:inherit}
button{background:var(--blue);color:#fff;border:0;border-radius:10px;padding:0 26px;font-size:16px;font-weight:700;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}
.samples{max-width:900px;margin:0 auto 24px;font-size:13.5px;color:var(--mut)}
.samples span{color:var(--blue);cursor:pointer;text-decoration:underline dotted}
.card{background:#fff;border-radius:14px;box-shadow:0 2px 10px rgba(2,6,23,.07);padding:20px 24px;margin-bottom:18px;display:none}
.card h2{font-size:17px;color:var(--blue);margin-bottom:12px;display:flex;align-items:center;gap:10px}
.step{background:var(--blue);color:#fff;width:26px;height:26px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:14px;flex:none}
.chip{display:inline-block;background:#eef2ff;border:1px solid #c7d2fe;color:#3730a3;border-radius:20px;padding:3px 12px;margin:3px 4px 3px 0;font-size:13.5px}
.chip b{color:#1e3a8a}
.ev{border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;margin-bottom:10px;font-size:13.5px}
.ev .meta{color:var(--mut);font-size:12.5px;margin-bottom:6px;display:flex;gap:10px;flex-wrap:wrap}
.badge{border-radius:6px;padding:1px 8px;font-weight:700;font-size:11.5px}
.b-text{background:#e0f2fe;color:#0369a1}.b-graph{background:#fef3c7;color:#92400e}.b-crop{background:#fee2e2;color:#b91c1c}
.verdict{border-radius:14px;padding:22px 26px;font-size:16px;display:none;margin-bottom:18px}
.v-fake{background:#fef2f2;border:2px solid #f87171}.v-real{background:#f0fdf4;border:2px solid #4ade80}
.v-label{font-size:30px;font-weight:800}
details{margin-top:8px} summary{cursor:pointer;color:var(--blue);font-size:13.5px}
pre{background:#0f172a;color:#e2e8f0;border-radius:10px;padding:14px;font-size:12px;overflow:auto;max-height:340px;white-space:pre-wrap;margin-top:8px}
.loading{display:none;text-align:center;color:var(--mut);padding:26px;font-size:15px}
.spin{display:inline-block;width:22px;height:22px;border:3px solid #c7d2fe;border-top-color:var(--blue);border-radius:50%;animation:r 0.8s linear infinite;vertical-align:-5px;margin-right:10px}
@keyframes r{to{transform:rotate(360deg)}}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.kv{font-size:13.5px;color:var(--mut)} .kv b{color:var(--ink)}
</style></head>
<body>
<header><h1>🔎 Facet Graph RAG — Kiểm chứng nhận định lịch sử Việt Nam</h1>
<p>Nhập một nhận định · hệ thống hiển thị chi tiết từng bước: phân rã khía cạnh → truy xuất 2 kênh → hợp nhất → LLM kiểm chứng</p></header>
<div class="wrap">
  <div class="inputrow">
    <textarea id="claim" placeholder="Ví dụ: Mặt trận Việt Minh được thành lập ngày 19 tháng 5 năm 1942."></textarea>
    <button id="go" onclick="run()">Kiểm chứng</button>
  </div>
  <div class="samples">Thử nhanh:
    <span onclick="fill(this)">Thực dân Pháp đã triển khai chương trình khai thác thuộc địa lần thứ hai tại Đông Dương, chủ yếu tập trung ở Campuchia, bắt đầu vào năm 1910.</span> ·
    <span onclick="fill(this)">Tổng Bí thư Nguyễn Văn Cừ đã chủ trì Hội nghị Ban Chấp hành Trung ương Đảng diễn ra vào tháng 12 năm 1945 tại Hà Nội</span>
  </div>

  <div class="loading" id="loading"><span class="spin"></span><span id="stage">Đang xử lý…</span></div>
  <div class="verdict" id="verdict"></div>

  <div class="card" id="c-facet"><h2><span class="step">1</span>Phân rã khía cạnh <span class="kv" id="facetsrc"></span></h2><div id="facets"></div></div>
  <div class="card" id="c-match"><h2><span class="step">2</span>Khớp khía cạnh vào đồ thị tri thức</h2><div id="matches"></div></div>
  <div class="card" id="c-text"><h2><span class="step">3</span>Truy xuất văn bản — Hybrid BM25 + BGE-M3 → RRF (top-5)</h2><div id="text5"></div></div>
  <div class="card" id="c-graph"><h2><span class="step">4</span>Truy xuất đồ thị — mention · 1-hop · năm → rerank (top-3)</h2><div id="graph3"></div></div>
  <div class="card" id="c-fuse"><h2><span class="step">5</span>Hợp nhất 5+3 + Smart crop 1.400 ký tự</h2><div id="fused"></div></div>
  <div class="card" id="c-llm"><h2><span class="step">6</span>LLM kiểm chứng</h2>
    <div class="grid2" id="llminfo"></div>
    <details><summary>Xem prompt đầy đủ gửi cho LLM</summary><pre id="prompt"></pre></details>
    <details><summary>Xem phản hồi thô của LLM</summary><pre id="raw"></pre></details>
  </div>
</div>
<script>
function fill(el){document.getElementById('claim').value=el.textContent;}
const stages=['Phân rã khía cạnh…','Khớp đồ thị tri thức…','Truy xuất văn bản (BM25 + BGE-M3)…','Truy xuất đồ thị…','Hợp nhất + smart crop…','Gọi Gemini kiểm chứng…'];
let t=null;
async function run(){
  const claim=document.getElementById('claim').value.trim(); if(!claim)return;
  document.querySelectorAll('.card').forEach(c=>c.style.display='none');
  document.getElementById('verdict').style.display='none';
  const L=document.getElementById('loading'); L.style.display='block';
  let si=0; document.getElementById('stage').textContent=stages[0];
  t=setInterval(()=>{si=(si+1)%stages.length;document.getElementById('stage').textContent=stages[si];},2200);
  document.getElementById('go').disabled=true;
  try{
    const r=await fetch('/api/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({claim})});
    const d=await r.json(); render(d);
  }catch(e){alert('Lỗi: '+e);}
  clearInterval(t); L.style.display='none'; document.getElementById('go').disabled=false;
}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function render(d){
  if(d.error && !d.facets){alert(d.error);return;}
  // verdict
  const v=document.getElementById('verdict'); const vd=d.verdict||{};
  if(vd.label_rag){
    const fake=vd.label_rag==='fake';
    v.className='verdict '+(fake?'v-fake':'v-real');
    v.innerHTML=`<span class="v-label">${fake?'❌ SAI (FAKE)':'✅ ĐÚNG (REAL)'}</span>
      <span style="margin-left:14px;color:var(--mut)">độ tin cậy ${vd.confidence}</span>
      <div style="margin-top:8px"><b>Khía cạnh sai:</b> ${ (vd.wrong_facets||[]).join(', ')||'—' }
      &nbsp;·&nbsp;<b>Bằng chứng trích dẫn:</b> ${(vd.evidence_ids||[]).join(', ')||'—'}</div>
      <div style="margin-top:8px;line-height:1.55"><b>Giải thích:</b> ${esc(vd.reasoning)}</div>`;
  }else{
    v.className='verdict v-fake'; v.innerHTML='⚠️ '+esc(vd.error||'không có phán quyết');
  }
  v.style.display='block';
  // 1 facets
  document.getElementById('facetsrc').textContent='· nguồn: '+d.facet_source;
  document.getElementById('facets').innerHTML=Object.entries(d.facets).map(([k,vs])=>
    vs.map(x=>`<span class="chip"><b>${k}</b>: ${esc(x)}</span>`).join('')).join('')||'<i>không tách được khía cạnh nào</i>';
  // 2 matches
  document.getElementById('matches').innerHTML=d.matches.map(m=>
    `<div class="ev"><b>${esc(m.facet)}</b> — ${m.matched?'✅ khớp':'⛔ không khớp'}<br>
     <span class="kv">${m.nodes.map(esc).join(' · ')||''}</span></div>`).join('');
  // 3 text
  document.getElementById('text5').innerHTML=d.text_top5.map(x=>
    `<div class="ev"><div class="meta"><span class="badge b-text">#${x.rank}</span><b>${esc(x.doc_id)}</b>
     <span>${esc(x.book)}</span><span>RRF ${x.rrf} · BM25 ${x.bm25} · dense ${x.dense}</span></div>${esc(x.snippet)}</div>`).join('');
  // 4 graph
  document.getElementById('graph3').innerHTML=d.graph_top.map(x=>
    `<div class="ev"><div class="meta"><span class="badge b-graph">graph</span><b>${esc(x.chunk_id)}</b>
     <span>score ${x.final}</span><span>${x.facet_hits.map(esc).join(' · ')}</span></div>${esc(x.snippet)}</div>`).join('')
     ||'<i>không có bằng chứng đồ thị cho câu này</i>';
  // 5 fused
  document.getElementById('fused').innerHTML=d.fused.map(x=>
    `<div class="ev"><div class="meta"><b>${x.eid}</b>
     <span class="badge ${x.branch==='graph'?'b-graph':'b-text'}">${x.branch}</span>
     <span>${esc(x.chunk_id)}</span>${x.was_cropped?'<span class="badge b-crop">đã smart-crop</span>':''}</div>${esc(x.cropped)}</div>`).join('');
  // 6 llm
  const tm=d.timing||{};
  document.getElementById('llminfo').innerHTML=
    `<div class="kv">Bộ kiểm chứng: <b>${d.llm.model}</b><br>Phân rã khía cạnh: <b>${d.llm.facet_model}</b></div>
     <div class="kv">Embedding: <b>${d.llm.embed_model}</b><br>Provider: <b>${d.llm.provider}</b></div>
     <div class="kv" style="grid-column:1/-1">⏱ Thời gian: tách facet <b>${tm.facet_llm??'—'}s</b> ∥ truy xuất text <b>${tm.text_retrieval??'—'}s</b> · đồ thị (local) <b>${tm.graph_local??'—'}s</b> · Gemini verify <b>${tm.verify_llm??'—'}s</b> · tổng <b>${tm.total??'—'}s</b></div>`;
  document.getElementById('prompt').textContent=d.llm.prompt;
  document.getElementById('raw').textContent=d.llm.raw_response||'(không có)';
  document.querySelectorAll('.card').forEach(c=>c.style.display='block');
}
document.getElementById('claim').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();run();}});
</script>
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--no-dense", action="store_true", help="Bỏ BGE-M3, chỉ dùng BM25 (khởi động nhanh)")
    args = ap.parse_args()
    startup(args.no_dense)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"\n  ✅ Demo sẵn sàng:  http://localhost:{args.port}\n  (Ctrl+C để dừng)\n")
    server.serve_forever()


if __name__ == "__main__":
    main()
