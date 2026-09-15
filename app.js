// The browser owns installation: Chrome/Edge use the address-bar install icon;
// Safari uses Add to Home Screen. Do not intercept beforeinstallprompt.
window.addEventListener("DOMContentLoaded", () => {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/fon-takip-paneli/sw.js?v=8").then(registration => registration.update()).catch(() => {});
  }
});

// The dashboard keeps its fast preset periods, but operators also need to
// examine an exact inclusive date interval.  This stays entirely client-side:
// it filters the already validated static archive and never opens a TEFAS call.
(() => {
  let archive;
  let defaultPeriodApplied = false;

  const formatNumber = value => value == null ? "—" : new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(value);
  const formatMoney = value => value == null ? "—" : new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0, notation: Math.abs(value) >= 1e6 ? "compact" : "standard" }).format(value) + " ₺";
  const formatMoneyFull = value => value == null ? "—" : new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 0 }).format(value) + " ₺";
  const formatPercent = value => value == null ? "—" : (value > 0 ? "+" : "") + value.toLocaleString("tr-TR", { maximumFractionDigits: 2 }) + "%";
  const rangeStatus = value => value > 0 ? "GİRİŞ" : value < 0 ? "ÇIKIŞ" : "DENGE";
  const rangeClass = value => value > 0 ? "positive" : value < 0 ? "negative" : "neutral";

  async function loadArchive() {
    const response = await fetch("data/funds/dashboard.json?t=" + Date.now(), { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    archive = await response.json();
  }

  function activeFund() {
    const title = document.getElementById("fundName")?.textContent || "";
    const code = title.split(" — ")[0].trim();
    return archive?.funds?.find(item => item.fund.code === code) || archive?.funds?.[0];
  }

  function pearson(rows, xKey, yKey) {
    if (rows.length < 2) return null;
    const xMean = rows.reduce((sum, row) => sum + row[xKey], 0) / rows.length;
    const yMean = rows.reduce((sum, row) => sum + row[yKey], 0) / rows.length;
    let numerator = 0, xSquares = 0, ySquares = 0;
    rows.forEach(row => {
      const x = row[xKey] - xMean, y = row[yKey] - yMean;
      numerator += x * y;
      xSquares += x * x;
      ySquares += y * y;
    });
    const denominator = Math.sqrt(xSquares * ySquares);
    return denominator ? numerator / denominator : null;
  }

  function ranks(values) {
    const sorted = values.map((value, index) => ({ value, index })).sort((a, b) => a.value - b.value);
    const result = Array(values.length);
    for (let start = 0; start < sorted.length;) {
      let end = start;
      while (end + 1 < sorted.length && sorted[end + 1].value === sorted[start].value) end++;
      const rank = (start + end + 2) / 2;
      for (let index = start; index <= end; index++) result[sorted[index].index] = rank;
      start = end + 1;
    }
    return result;
  }

  function relationshipLabel(flow, investors) {
    if (flow > 0 && investors > 0) return "Para ↑ · Yatırımcı ↑";
    if (flow > 0 && investors < 0) return "Para ↑ · Yatırımcı ↓";
    if (flow < 0 && investors > 0) return "Para ↓ · Yatırımcı ↑";
    if (flow < 0 && investors < 0) return "Para ↓ · Yatırımcı ↓";
    return "Dengeli / değişimsiz";
  }

  function renderRelationship(fund) {
    const historyByDate = new Map();
    fund.history.forEach((row, index) => {
      const previous = fund.history[index - 1];
      historyByDate.set(row.date, previous && row.investor_count != null && previous.investor_count != null ? row.investor_count - previous.investor_count : null);
    });
    const paired = fund.metrics.daily.map(row => ({ date: row.date, flow: row.estimated_net_flow, investors: historyByDate.get(row.date) })).filter(row => Number.isFinite(row.flow) && Number.isFinite(row.investors));
    const sample = paired.slice(-30);
    const correlation = sample.length >= 20 ? pearson(sample, "flow", "investors") : null;
    const xRanks = ranks(sample.map(row => row.flow));
    const yRanks = ranks(sample.map(row => row.investors));
    const ranked = sample.map((row, index) => ({ ...row, xRank: xRanks[index], yRank: yRanks[index] }));
    const spearman = sample.length >= 20 ? pearson(ranked, "xRank", "yRank") : null;
    const outlierSensitive = correlation != null && spearman != null && Math.abs(correlation - spearman) >= 0.2;
    const sameDirection = sample.filter(row => (row.flow > 0 && row.investors > 0) || (row.flow < 0 && row.investors < 0)).length;
    const latest = sample.at(-1);
    let section = document.getElementById("moneyInvestorRelationship");
    if (!section) {
      section = document.createElement("section");
      section.id = "moneyInvestorRelationship";
      section.className = "panel relationship-panel";
      document.getElementById("aumChart").closest(".panel").before(section);
    }
    const correlationText = correlation == null ? "Yetersiz veri" : correlation.toLocaleString("tr-TR", { maximumFractionDigits: 2 });
    const sameDirectionText = sample.length ? `${sameDirection}/${sample.length} gün` : "—";
    const latestEffect = latest?.investors ? formatMoney(latest.flow / latest.investors) : "—";
    const rows = sample.slice(-10).reverse().map(row => `<tr><td>${row.date}</td><td class="${rangeClass(row.flow)}"><strong>${row.flow > 0 ? "+" : ""}${formatMoneyFull(row.flow)}</strong></td><td class="${rangeClass(row.investors)}"><strong>${row.investors > 0 ? "+" : ""}${formatNumber(row.investors)}</strong></td><td>${relationshipLabel(row.flow, row.investors)}</td></tr>`).join("");
    section.innerHTML = `<h2>Para–yatırımcı ilişkisi</h2><div class="relationship-kpis"><div><span>30 günlük korelasyon</span><strong>${correlationText}</strong></div><div><span>Aynı yöndeki günler</span><strong>${sameDirectionText}</strong></div><div><span>Son günün davranışı</span><strong>${latest ? relationshipLabel(latest.flow, latest.investors) : "—"}</strong></div><div><span>Son gün değişim başına akış</span><strong>${latestEffect}</strong></div></div>${sample.length < 20 ? '<p class="relationship-warning">En az 20 ortak işlem günü olmadan korelasyon hesaplanmaz.</p>' : ''}${outlierSensitive ? '<p class="relationship-warning">Korelasyon uç değerlerden etkileniyor olabilir; sonuç temkinli yorumlanmalıdır.</p>' : ''}<div class="table-wrap"><table class="relationship-table"><thead><tr><th>Tarih</th><th>Net para akışı</th><th>Yatırımcı değişimi</th><th>Davranış</th></tr></thead><tbody>${rows}</tbody></table></div><p class="relationship-note">Net para akışı tahmindir; gerçekleşmiş işlem verisi değildir. “Değişim başına akış” gerçek kişi başı yatırım tutarı değildir. Korelasyon birlikte hareketi gösterir, nedensellik göstermez.</p>`;
  }

  function rangeRows(fund, start, end) {
    return fund.history.filter(row => row.date >= start && row.date <= end);
  }

  function exportRange(fund, rows, start, end) {
    if (!window.XLSX) {
      document.getElementById("error").textContent = "Excel kütüphanesi yüklenemedi.";
      document.getElementById("error").classList.remove("hidden");
      return;
    }
    const reportRows = rows.map((row, index) => {
      const previous = rows[index - 1];
      return {
        "Tarih": row.date,
        "Fon kodu": row.fund_code,
        "Fon adı": row.fund_name,
        "Pay fiyatı": row.price,
        "Fon büyüklüğü": row.portfolio_size,
        "Toplam yatırımcı": row.investor_count,
        "Günlük yatırımcı değişimi": previous && row.investor_count != null && previous.investor_count != null ? row.investor_count - previous.investor_count : null,
        "Pay adedi": row.shares_outstanding,
      };
    });
    const workbook = XLSX.utils.book_new();
    const sheet = XLSX.utils.json_to_sheet(reportRows);
    sheet["!cols"] = [{ wch: 13 }, { wch: 11 }, { wch: 58 }, { wch: 14 }, { wch: 20 }, { wch: 18 }, { wch: 27 }, { wch: 20 }];
    XLSX.utils.book_append_sheet(workbook, sheet, "Seçilen Tarih Aralığı");
    XLSX.writeFile(workbook, `${fund.fund.code}_${start}_${end}_raporu.xlsx`);
  }

  function applyRange() {
    const start = document.getElementById("rangeStart").value;
    const end = document.getElementById("rangeEnd").value;
    const error = document.getElementById("error");
    if (!start || !end) {
      error.textContent = "Başlangıç ve bitiş tarihini seçin.";
      error.classList.remove("hidden");
      return;
    }
    if (start > end) {
      error.textContent = "Başlangıç tarihi bitiş tarihinden sonra olamaz.";
      error.classList.remove("hidden");
      return;
    }
    const fund = activeFund();
    const rows = rangeRows(fund, start, end);
    if (rows.length < 2) {
      error.textContent = "Seçilen aralıkta hesaplama için en az iki işlem günü gerekir.";
      error.classList.remove("hidden");
      return;
    }
    error.classList.add("hidden");
    const daily = fund.metrics.daily.filter(row => row.date >= rows[0].date && row.date <= rows.at(-1).date);
    const first = rows[0], last = rows.at(-1);
    const netFlow = daily.reduce((total, row) => total + (row.estimated_net_flow || 0), 0);
    const investorChange = last.investor_count - first.investor_count;
    const returnPct = first.price ? ((last.price / first.price) - 1) * 100 : null;

    document.querySelectorAll("[data-days]").forEach(button => button.classList.remove("active"));
    document.getElementById("flow").className = "amount " + rangeClass(netFlow);
    document.getElementById("flow").textContent = (netFlow > 0 ? "+" : "") + formatMoney(netFlow);
    document.getElementById("flowCaption").textContent = `${rows.length} işlem günü · ${start} – ${end}`;
    document.getElementById("signal").textContent = `SEÇİLEN DÖNEM: ${rangeStatus(netFlow)}`;
    document.getElementById("summary").innerHTML = [
      ["Tahmini net akış (seçilen dönem)", (netFlow > 0 ? "+" : "") + formatMoney(netFlow)],
      ["Yatırımcı net değişimi (seçilen dönem)", (investorChange > 0 ? "+" : "") + formatNumber(investorChange)],
      ["Dönem getirisi (seçilen dönem)", formatPercent(returnPct)],
      ["Veri noktası (seçilen dönem)", rows.length + " Gün"],
    ].map(([label, value]) => `<div class="row"><span class="muted">${label}</span><strong>${value}</strong></div>`).join("");

    document.getElementById("investorRows").innerHTML = rows.map((row, index) => {
      const previous = rows[index - 1];
      const change = previous ? row.investor_count - previous.investor_count : null;
      const signed = change == null ? "—" : (change > 0 ? "+" : "") + formatNumber(change);
      return `<tr><td>${row.date}</td><td>${formatNumber(row.investor_count)}</td><td class="${rangeClass(change || 0)}"><strong>${signed}</strong></td></tr>`;
    }).reverse().join("");

    const flowCanvas = document.getElementById("flowChart");
    const aumCanvas = document.getElementById("aumChart");
    Chart.getChart(flowCanvas)?.destroy();
    Chart.getChart(aumCanvas)?.destroy();
    new Chart(flowCanvas, { type: "bar", data: { labels: daily.map(row => row.date), datasets: [{ label: "Tahmini net akış", data: daily.map(row => row.estimated_net_flow), backgroundColor: daily.map(row => row.estimated_net_flow >= 0 ? "#30d158" : "#ff453a") }] }, options: { responsive: true, maintainAspectRatio: false } });
    new Chart(aumCanvas, { type: "line", data: { labels: rows.map(row => row.date), datasets: [{ label: "Fon büyüklüğü", data: rows.map(row => row.portfolio_size), borderColor: "#0a84ff", tension: .25, pointRadius: 0 }] }, options: { responsive: true, maintainAspectRatio: false } });
    document.getElementById("excel").onclick = () => exportRange(fund, rows, start, end);
  }

  function installRangeControls() {
    const controls = document.getElementById("periods");
    const fund = activeFund();
    if (!controls || !fund) return;
    renderRelationship(fund);
    const escapeStatus = value => String(value || "Bilinmeyen hata").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
    const summaryStatus = fund.status?.summary;
    document.querySelectorAll("#tefasSummary .tefas-card p.muted").forEach(paragraph => {
      if (paragraph.textContent.startsWith("Özet güncellenemedi:")) paragraph.remove();
    });
    const refresh = controls.querySelector("#refresh");
    const collectorStatus = fund.status;
    let statusNotice = document.getElementById("panelStatus");
    if (!statusNotice) {
      statusNotice = document.createElement("div");
      statusNotice.id = "panelStatus";
      statusNotice.className = "panel-status";
      statusNotice.setAttribute("role", "status");
      statusNotice.setAttribute("aria-live", "polite");
      document.querySelector(".footer").before(statusNotice);
    }
    const hasCollectorError = collectorStatus && collectorStatus.state !== "ok";
    const hasSummaryError = summaryStatus?.state === "error";
    if (hasCollectorError || hasSummaryError) {
      const messages = [];
      if (hasCollectorError) messages.push(collectorStatus.message);
      if (hasSummaryError) messages.push(summaryStatus.message);
      statusNotice.className = "panel-status panel-status-error";
      statusNotice.setAttribute("role", "alert");
      statusNotice.innerHTML = `<strong>⚠ VERİ GÜNCELLEME SORUNU</strong><span>Son başarılı veriler gösteriliyor. Sistem bir sonraki taramada yeniden deneyecek.</span><details><summary>Teknik ayrıntıyı göster</summary><small>${messages.map(escapeStatus).join("<br>")}</small></details>`;
    } else {
      const checkedAt = collectorStatus?.checked_at ? new Date(collectorStatus.checked_at).toLocaleString("tr-TR") : null;
      statusNotice.className = "panel-status panel-status-ok";
      statusNotice.setAttribute("role", "status");
      statusNotice.innerHTML = `<strong>✓ Veriler güncel</strong><span>${checkedAt ? `Son başarılı tarama: ${checkedAt}` : "Son veri taraması başarıyla tamamlandı."}</span>`;
    }
    if (refresh && !refresh.dataset.archiveRefresh) {
      const standardRefresh = refresh.onclick;
      refresh.dataset.archiveRefresh = "true";
      refresh.onclick = async () => {
        refresh.disabled = true;
        refresh.textContent = "Yenileniyor…";
        try {
          await standardRefresh();
          await loadArchive();
          const checkedAt = activeFund()?.status?.checked_at;
          const message = checkedAt ? `Statik arşiv yenilendi · son kontrol: ${new Date(checkedAt).toLocaleString("tr-TR")}` : "Statik arşiv yenilendi.";
          const notice = document.getElementById("error");
          notice.textContent = message;
          notice.classList.remove("hidden");
          setTimeout(() => notice.classList.add("hidden"), 3500);
        } finally {
          refresh.disabled = false;
          refresh.textContent = "Veriyi Yenile";
        }
      };
    }
    if (!controls.querySelector("#tefasOpen")) {
      const code = encodeURIComponent(fund.fund.code);
      controls.querySelector("#excel")?.insertAdjacentHTML("afterend", `<a id="tefasOpen" class="tefas-open" href="https://www.tefas.gov.tr/tr/fon-detayli-analiz/${code}" target="_blank" rel="noopener">TEFAS'ta Aç</a>`);
    }
    if (controls.querySelector("#dateRange")) return;
    const dates = fund.history.map(row => row.date);
    controls.insertAdjacentHTML("beforeend", `<div class="date-range" id="dateRange"><label>Başlangıç<input id="rangeStart" type="date" min="${dates[0]}" max="${dates.at(-1)}"></label><label>Bitiş<input id="rangeEnd" type="date" min="${dates[0]}" max="${dates.at(-1)}"></label><button id="applyRange" type="button">Tarihi Göster</button></div>`);
    document.getElementById("applyRange").onclick = applyRange;
    controls.querySelectorAll("[data-days]").forEach(button => {
      const standardRender = button.onclick;
      button.onclick = () => {
        standardRender();
      };
    });
    if (!defaultPeriodApplied) {
      defaultPeriodApplied = true;
      setTimeout(() => controls.querySelector('[data-days="1"]')?.click(), 0);
    }
  }

  const relationshipStyle = document.createElement("style");
  relationshipStyle.textContent = ".relationship-kpis{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:12px}.relationship-kpis>div{padding:10px;border:1px solid var(--line);border-radius:10px;background:color-mix(in srgb,var(--card) 92%,var(--bg))}.relationship-kpis span{display:block;color:var(--muted);font-size:11px;margin-bottom:5px}.relationship-kpis strong{display:block;text-align:right;font-size:15px}.relationship-table{width:100%;border-collapse:collapse;table-layout:fixed}.relationship-table th,.relationship-table td{padding:9px 6px;border-bottom:1px solid var(--line);text-align:right;font-size:12px}.relationship-table th{color:var(--muted);font-weight:600;white-space:normal}.relationship-table th:first-child,.relationship-table td:first-child{text-align:left;width:18%}.relationship-table th:nth-child(2),.relationship-table td:nth-child(2){width:25%}.relationship-table th:nth-child(3),.relationship-table td:nth-child(3){width:22%}.relationship-table th:last-child,.relationship-table td:last-child{width:35%}.relationship-warning{margin:8px 0;padding:8px 10px;border-radius:8px;background:#ff9f0a20;color:var(--muted);font-size:11px}.relationship-note{margin:10px 0 0;color:var(--muted);font-size:11px;line-height:1.45}@media(max-width:520px){.relationship-kpis{grid-template-columns:1fr 1fr}.relationship-kpis strong{font-size:13px}.relationship-table th,.relationship-table td{padding:8px 3px;font-size:10px}.relationship-table th:first-child,.relationship-table td:first-child{width:21%}.relationship-table th:nth-child(2),.relationship-table td:nth-child(2){width:24%}.relationship-table th:nth-child(3),.relationship-table td:nth-child(3){width:21%}.relationship-table th:last-child,.relationship-table td:last-child{width:34%;white-space:normal}}";
  relationshipStyle.textContent += "@media(max-width:520px){.relationship-table td:nth-child(-n+3){white-space:nowrap}.relationship-table td:nth-child(2){font-size:9px;letter-spacing:-.2px}}";
  document.head.append(relationshipStyle);
  const style = document.createElement("style");
  style.textContent = ".panel-status{margin:16px 0 0;padding:11px 14px;border-radius:12px;color:var(--text)}.panel-status strong{display:block;margin-bottom:3px;font-size:13px}.panel-status span{display:block;font-size:12px;line-height:1.4}.panel-status-ok{border:1px solid var(--green);border-left:5px solid var(--green);background:color-mix(in srgb,var(--green) 8%,var(--card))}.panel-status-ok strong{color:var(--green)}.panel-status-error{border:1px solid var(--red);border-left:5px solid var(--red);background:color-mix(in srgb,var(--red) 10%,var(--card))}.panel-status-error strong{color:var(--red)}.panel-status details{margin-top:6px}.panel-status summary{color:var(--muted);font-size:11px;cursor:pointer}.panel-status small{display:block;margin-top:5px;color:var(--muted);font-size:11px;line-height:1.4;overflow-wrap:anywhere}.tefas-open{border:0;border-radius:999px;padding:8px 13px;background:var(--card);color:var(--muted);font:600 13px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;box-shadow:0 1px 3px #0001;text-decoration:none;white-space:nowrap}.date-range{display:flex;align-items:end;gap:7px;flex-wrap:wrap;margin-left:auto}.date-range label{display:grid;gap:3px;color:var(--muted);font-size:11px;font-weight:600}.date-range input{border:1px solid var(--line);border-radius:10px;padding:7px;background:var(--card);color:var(--text);font:inherit}@media(max-width:520px){.panel-status{padding:10px 12px}.date-range{width:100%;margin-left:0;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);column-gap:12px;row-gap:6px}.date-range label{min-width:0}.date-range input{min-width:0;width:100%;padding:6px;font-size:13px}.date-range button{grid-column:1/-1;justify-self:end;padding:7px 10px}}";
  document.head.append(style);
  window.addEventListener("load", async () => {
    try {
      await loadArchive();
      installRangeControls();
      new MutationObserver(installRangeControls).observe(document.getElementById("periods"), { childList: true });
    } catch (error) {
      console.error("Tarih aralığı arşivi yüklenemedi", error);
    }
  });
})();
