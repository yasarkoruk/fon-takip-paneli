// The browser owns installation: Chrome/Edge use the address-bar install icon;
// Safari uses Add to Home Screen. Do not intercept beforeinstallprompt.
window.addEventListener("DOMContentLoaded", () => {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/fon-takip-paneli/sw.js").catch(() => {});
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
    const refresh = controls.querySelector("#refresh");
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

  const style = document.createElement("style");
  style.textContent = ".tefas-open{border:0;border-radius:999px;padding:8px 13px;background:var(--card);color:var(--muted);font:600 13px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;box-shadow:0 1px 3px #0001;text-decoration:none;white-space:nowrap}.date-range{display:flex;align-items:end;gap:7px;flex-wrap:wrap;margin-left:auto}.date-range label{display:grid;gap:3px;color:var(--muted);font-size:11px;font-weight:600}.date-range input{border:1px solid var(--line);border-radius:10px;padding:7px;background:var(--card);color:var(--text);font:inherit}@media(max-width:520px){.date-range{width:100%;margin-left:0}.date-range label{flex:1}.date-range input{width:100%}}";
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
