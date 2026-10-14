"use strict";
const $=(id)=>document.getElementById(id);
function esc(s){const d=document.createElement("div");d.textContent=String(s);return d.innerHTML;}
function pathViz(path){return `<div class="path" aria-label="receipt path">${path.map((p,i)=>`${i?'<i aria-hidden="true">›</i>':''}<span>${esc(p)}</span>`).join("")}</div>`;}
function cards(title,rows,oracle){
  if(!rows||!rows.length)return `<h3>${esc(title)}</h3><p>No rows returned.</p>`;
  const set=new Set(oracle);
  return `<h3>${esc(title)}</h3><div class="cards">${rows.map((r,i)=>`<article class="card"><div class="head"><span>#${i+1} <code>${esc(r.aid)}</code></span><span class="score">${Number(r.score).toFixed(4)}</span></div>${pathViz(r.path)}<p>${esc(r.text)}</p>${set.has(r.aid)?'<span class="hit">In exact sample-oracle top-K</span>':''}</article>`).join("")}</div>`;
}
function metric(v,k){return `<div class="metric"><div class="v">${esc(v)}</div><div class="k">${esc(k)}</div></div>`;}
async function init(){
  const res=await fetch("/api/probes");const data=await res.json();
  if(!res.ok)throw new Error(data.error||res.status);
  $("probe").innerHTML=data.probes.map(p=>`<option value="${p.id}">#${p.id} — ${esc(p.family)} — ${esc(p.sources.join(", "))}</option>`).join("");
  $("status").textContent=`${data.probes.length} receipt probes loaded. Ready to query.`;
}
$("query-form").addEventListener("submit",async(e)=>{
  e.preventDefault();$("error").textContent="";$("status").textContent="Running frozen query…";
  try{
    const res=await fetch("/api/query",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({probe_id:Number($("probe").value),mode:$("mode").value,top_k:Number($("topk").value),leave_source_out:$("lso").checked})});
    const d=await res.json();if(!res.ok)throw new Error(d.error||res.status);
    let m=metric(d.sample_atoms,"sample atoms searched")+metric("Top "+d.top_k,"results requested");
    if(d.guided)m+=metric(d.guided.recall_at_k_vs_sample_oracle.toFixed(3),"guided recall vs sample oracle");
    if(d.flat)m+=metric(d.flat.recall_at_k_vs_sample_oracle.toFixed(3),"flat recall vs sample oracle (matched budget "+d.flat.budget+")");
    $("metrics").innerHTML=m;
    let html=`<p>Probe #${d.probe.id} (${esc(d.probe.family)}). Exact sample-oracle top-${d.top_k}: <code>${esc(d.oracle_top.join(", "))}</code></p>`;
    if(d.guided)html+=cards("Guided — hierarchy-routed (frozen)",d.guided.rows,d.oracle_top)+`<details><summary>Guided work report</summary><pre>${esc(JSON.stringify(d.guided.report.work,null,2))}</pre></details>`;
    if(d.flat)html+=cards("Flat control — same scoring budget (frozen)",d.flat.rows,d.oracle_top)+`<details><summary>Flat work report</summary><pre>${esc(JSON.stringify(d.flat.report.work,null,2))}</pre></details>`;
    $("results").innerHTML=html;
    $("evidence").innerHTML=d.recorded_10m_row
      ?`<p>Recorded full-10M row for this probe (receipt, not recomputed):</p><div class="metrics">${metric(d.recorded_10m_row.guided_recall10,"recorded guided recall@10")}${metric(d.recorded_10m_row.flat_recall10,"recorded flat recall@10")}${metric(Number(d.recorded_10m_row.guided_scoring_rows).toLocaleString(),"guided scoring rows")}${metric(Number(d.recorded_10m_row.eligible_atoms).toLocaleString(),"eligible atoms")}</div>`
      :"<p>No recorded 10M row for this probe/mode.</p>";
    $("status").textContent="Query complete.";
    document.getElementById("results-view").scrollIntoView({block:"start"});
  }catch(err){$("error").textContent="Error: "+err.message;$("status").textContent="";}
});
$("evidence-btn").addEventListener("click",async()=>{
  $("error").textContent="";
  try{
    const res=await fetch("/api/evidence");const d=await res.json();if(!res.ok)throw new Error(d.error||res.status);
    const a=d.summary.all_sources,l=d.summary.leave_source_out;
    $("evidence").innerHTML=`<div class="metrics">${metric(d.input.actual_tokens.toLocaleString(),"recorded tokens")}${metric(d.input.complete_documents.toLocaleString(),"documents")}${metric(d.input.atoms.toLocaleString(),"atoms")}${metric(d.oracle_queries,"oracle queries exact")}</div>
    <p><strong>${esc(d.oracle_status)}</strong> — counts match: ${d.oracle_counts_match}; store before/after identical: ${d.store_before_after_identical}. Cache misses: ${d.input.cache_misses}. ${esc(d.input.normalization)}.</p>
    <table><caption>Recorded harness recall@10 (both modes, matched flat controls)</caption><thead><tr><th scope="col">Mode</th><th scope="col">Guided</th><th scope="col">Matched flat</th></tr></thead><tbody>
    <tr><td>All sources</td><td>${a.guided_recall10.toFixed(3)}</td><td>${a.flat_recall10.toFixed(3)}</td></tr>
    <tr><td>Leave-source-out</td><td>${l.guided_recall10.toFixed(3)}</td><td>${l.flat_recall10.toFixed(3)}</td></tr></tbody></table>
    <p>${esc(d.scope)}</p><details><summary>Provenance pin</summary><p><code>${esc(JSON.stringify(d.pin))}</code></p></details>`;
    $("status").textContent="Evidence loaded.";
    document.getElementById("evidence-view").scrollIntoView({block:"start"});
  }catch(err){$("error").textContent="Error: "+err.message;}
});
init().catch(err=>{$("error").textContent="Error loading probes: "+err.message;});
