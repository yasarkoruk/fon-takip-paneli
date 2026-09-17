// Static KAP evidence and liquidity guardrails. Collector failures are not fund risks.
(() => {
  let archive, metrics, expanded = false, includeRelated = false;
  const escape = value => String(value ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
  const date = value => value ? new Date(value).toLocaleString("tr-TR", {timeZone:"Europe/Istanbul"}) : "Henüz başarılı kontrol yok";
  const source = event => `<a href="https://www.kap.org.tr/tr/Bildirim/${Number(event.disclosure_id || event.id)}" target="_blank" rel="noopener">Resmi KAP bildirimi ↗</a>`;
  function render() {
    const code = document.getElementById("fundName")?.textContent.split(" — ")[0].trim();
    const anchor = document.getElementById("tefasSummary");
    if (!code || !anchor || !archive) return;
    let panel = document.getElementById("kapPanel");
    if (!panel) {
      panel = document.createElement("section");
      panel.id = "kapPanel"; panel.className = "panel kap-panel";
      anchor.after(panel);
    }
    const monitored = Object.hasOwn(archive.funds || {}, code);
    const openDetails = [".kap-market", ".kap-candidates"].filter(selector => panel.querySelector(selector)?.open);
    const records = archive.funds?.[code] || [];
    const active = (archive.reviewed_events || []).filter(e => e.code === code && e.state === "active");
    const candidates = records.filter(e => e.candidate && !archive.reviewed_events?.some(r => r.disclosure_id === e.id));
    const filtered = records.filter(e => includeRelated || e.scope === "Fon");
    const rows = (expanded ? filtered : filtered.slice(0, 5)).map(e => `<li><time>${escape(date(e.published_at))}</time><div><strong>${escape(e.summary || e.title)}</strong><small>${escape(e.title)} · ${escape(e.scope)}</small>${source(e)}</div></li>`).join("");
    const fund = metrics?.funds?.find(e => e.fund.code === code);
    const allocation = fund?.tefas_summary?.asset_allocation?.find(e => e.code === "hs");
    const allocationDate = fund?.tefas_summary?.source_date;
    const riskRows = [
      ["İade / likidite", active.length ? "⚠ Resmi temerrüt bildirimi açık" : "Kesin durum değerlendirilmedi", active.length ? "İade ödemelerindeki gecikme, fiyat yükselse veya para girişi görünse de önemini korur." : "Bildirim bulunmaması, fonun risksiz veya ödemelerinin sorunsuz olduğunu kanıtlamaz."],
      ["Ödeme tarihi / valör", active[0]?.payment_date || "Resmi ödeme tarihi doğrulanmadı", "Aracı kurumunuzdan iade talebinizin durumu ve güncel valörünü teyit edin."],
      ["Hisse senedi oranı", allocation ? `%${allocation.ratio_pct.toLocaleString("tr-TR")} (${allocationDate})` : "Veri yok", "Varlık türü oranı tek-hisse yoğunlaşmasını veya varlıkların ne hızla satılabileceğini göstermez."],
      ["Para–yatırımcı ilişkisi", "Likidite güvencesi değildir", "Tahmini net akış ve yatırımcı sayısı, borç ödeme kapasitesini ve gerçek nakit bakiyesini göstermez."]
    ].map(r => `<tr>${r.map(v => `<td>${escape(v)}</td>`).join("")}</tr>`).join("");
    panel.innerHTML = `<h2>KAP bildirimleri ve likidite takibi</h2><p class="kap-muted">${escape(code)} · Resmi bildirimler · Son 5 kayıt</p>${active.map(e => `<div class="kap-risk" role="note"><strong>⚠ ${escape(e.label)}</strong><p>${escape(e.description)}</p><small>Olay tarihi: ${escape(date(e.published_at))} · Kapsam: ${escape(e.scope)} · Resmi çözüm doğrulanmadı</small>${source(e)}</div>`).join("")}${candidates.length ? `<details class="kap-candidates"><summary>İnceleme gerektiren ${candidates.length} bildirim — kesin risk hükmü değildir</summary>${candidates.map(e => `<p>${escape(e.summary || e.title)} · ${source(e)}</p>`).join("")}</details>` : ""}<label class="kap-filter"><input type="checkbox" id="kapRelated" ${includeRelated ? "checked" : ""}> İlişkili kurum / piyasa bildirimlerini de göster</label><ul class="kap-news">${rows || `<li>${monitored ? "Bu kapsamda kayıt bulunamadı." : "Bu fon henüz KAP takip kapsamına eklenmedi; risk değerlendirmesi yapılamaz."}</li>`}</ul>${filtered.length > 5 ? `<button id="kapExpand" type="button" aria-expanded="${expanded}">${expanded ? "⌃ Daha az göster" : `⌄ Diğer ${filtered.length-5} bildirimi göster`}</button>` : ""}<h3>Risk / likidite okuma tablosu</h3><table class="kap-risk-table"><thead><tr><th>Kontrol</th><th>Gözlem</th><th>Dikkat edilecek nokta</th></tr></thead><tbody>${riskRows}</tbody></table><details class="kap-market"><summary>Piyasa izleme notları — fon kapsamlarını karıştırmayın</summary>${(archive.reviewed_events || []).filter(e => e.code !== code).map(e => `<p><strong>${escape(e.code)} · ${escape(e.label)}</strong><br>${escape(e.description)}<br><small>${escape(e.scope)} · ${escape(date(e.published_at))}</small><br>${source(e)}</p>`).join("")}</details><p class="kap-muted">Kontrol kapsamı KAP takip listesine eklenen fonlarla sınırlıdır. Ek dosyalar otomatik yorumlanmaz. Finansal risk uyarıları sistem erişim hatalarından ayrıdır; otomatik yatırım tavsiyesi veya iflas puanı üretilmez.</p>`;
    panel.querySelector("#kapRelated").onchange = e => { includeRelated = e.target.checked; expanded = false; render(); };
    const toggle = panel.querySelector("#kapExpand");
    if (toggle) toggle.onclick = () => { expanded = !expanded; render(); };
    openDetails.forEach(selector => { const detail = panel.querySelector(selector); if (detail) detail.open = true; });
    status();
  }
  function status(loadError) {
    let notice = document.getElementById("kapStatus");
    const footer = document.querySelector(".footer");
    if (!footer) return;
    if (!notice) { notice = document.createElement("div"); notice.id = "kapStatus"; footer.before(notice); }
    const s = archive?.status;
    const hour = Number(new Intl.DateTimeFormat("en-GB", {hour:"2-digit",hourCycle:"h23",timeZone:"Europe/Istanbul"}).format(new Date()));
    const stale = s?.last_success_at && Date.now()-Date.parse(s.last_success_at) > (hour >= 8 && hour <= 23 ? 150 : 360)*60000;
    const failure = loadError || s?.state !== "ok" || !s?.last_success_at || stale;
    notice.className = `panel-status panel-status-${failure ? "error" : "ok"}`;
    notice.setAttribute("role", failure ? "alert" : "status");
    const reviewed = new Set((archive?.reviewed_events || []).map(e => e.disclosure_id));
    const rapid = archive?.reviewed_events?.some(e => e.state === "active") || s?.state === "error" || Object.values(archive?.funds || {}).some(rows => rows.some(r => r.candidate && !reviewed.has(r.id)));
    notice.innerHTML = `<strong>${failure ? "⚠ KAP KONTROL UYARISI" : "✓ KAP kontrolü başarılı"}</strong><span>Son başarılı kontrol: ${escape(date(s?.last_success_at))}<br>08:00–23:30 Türkiye saati: ${rapid ? "kritik olay / erişim sorunu nedeniyle 30 dakikada bir" : "saatlik"}; gece 02:00 ve 05:00. Son kontrol: ${escape(date(s?.last_attempt_at))}</span>${failure ? `<details><summary>Ayrıntıyı göster</summary><small>${escape(loadError || (stale ? "Son başarılı kontrol beklenen süreden eski. Otomasyon ve KAP erişimini kontrol edin." : (s?.errors || []).join("; ") || "KAP verisi henüz alınamadı."))}</small></details>` : `<span>${s.new_count ? `${s.new_count} yeni bildirim arşivlendi.` : "Yeni bildirim yok; arşiv ve açık olaylar korunuyor."}</span>`}`;
  }
  async function load() {
    try {
      const response = await fetch("data/kap/archive.json?t="+Date.now(), {cache:"no-store"});
      if (!response.ok) throw new Error("KAP arşivi yüklenemedi: HTTP "+response.status);
      const next = await response.json();
      if (!next.funds || !next.status) throw new Error("KAP arşiv şeması geçersiz");
      archive = next;
      try {
        const data = await fetch("data/funds/dashboard.json?t="+Date.now(), {cache:"no-store"});
        if (data.ok) metrics = await data.json();
      } catch (_) { /* KAP official evidence is independent of optional TEFAS context. */ }
      render();
    } catch (error) { render(); status(error.message); }
  }
  const style = document.createElement("style");
  style.textContent = `.kap-panel{margin-top:16px}.kap-panel a{color:var(--blue,#3478f6);font-size:12px;display:inline-block;margin-top:5px}.kap-muted,.kap-panel small{color:var(--muted);font-size:11px;line-height:1.5}.kap-risk{border:1px solid var(--red);border-left:5px solid var(--red);border-radius:10px;padding:12px;margin:12px 0;background:color-mix(in srgb,var(--red) 7%,var(--card))}.kap-risk>strong{color:var(--red)}.kap-risk p{font-size:13px;line-height:1.5;margin:6px 0}.kap-risk small{display:block}.kap-filter{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:7px;margin:12px 0}.kap-news{list-style:none;padding:0;margin:0}.kap-news li{display:grid;grid-template-columns:155px minmax(0,1fr);gap:12px;padding:12px 0;border-bottom:1px solid var(--line)}.kap-news time{font-size:12px;color:var(--muted)}.kap-news strong{font-size:13px}.kap-news small{display:block;margin-top:3px}.kap-risk-table{table-layout:fixed;width:100%;border-collapse:collapse;font-size:12px}.kap-risk-table th,.kap-risk-table td{text-align:left;vertical-align:top;padding:10px 6px;border-bottom:1px solid var(--line);overflow-wrap:anywhere;line-height:1.5}.kap-risk-table th:first-child{width:22%}.kap-risk-table th:nth-child(2){width:28%}.kap-market,.kap-candidates{font-size:12px;padding:10px 0}.kap-panel summary{cursor:pointer}.kap-panel h3{font-size:14px;margin-top:18px}.kap-panel button{margin-top:8px}@media(max-width:520px){.kap-news li{grid-template-columns:1fr;gap:3px}.kap-risk-table{font-size:10px}.kap-risk-table th,.kap-risk-table td{padding:8px 4px}.kap-risk-table th:first-child{width:23%}.kap-risk-table th:nth-child(2){width:30%}}`;
  document.head.append(style);
  const start = () => {
    const footer = document.querySelector(".footer");
    if (footer) footer.textContent = "Fon verileri TEFAS, resmi bildirimler KAP collector tarafından üretilen kalıcı JSON arşivlerinden gelir. ‘Veriyi Yenile’ kaynak servislere değil, son statik arşivlere yeniden bağlanır.";
    load();
    const title = document.getElementById("fundName");
    if (title) new MutationObserver(() => {expanded = false; render();}).observe(title,{childList:true,subtree:true,characterData:true});
    document.addEventListener("click", e => {if (e.target.closest("#refresh")) load();});
    setInterval(load, 60000); // only static snapshot; browser never queries KAP
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
})();
