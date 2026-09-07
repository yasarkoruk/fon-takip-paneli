let installPrompt;

function showInstallHelp(message) {
  const detail = document.getElementById("installDetail");
  if (detail) detail.textContent = message;
}

function addInstallPanel() {
  const wrap = document.querySelector(".wrap");
  if (!wrap || document.getElementById("installPanel")) return;
  const panel = document.createElement("section");
  panel.id = "installPanel";
  panel.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px;padding:12px 14px;border-radius:14px;background:var(--card);box-shadow:0 1px 5px #00000012";
  panel.innerHTML = '<div><strong style="font-size:13px">Cihaza ekle</strong><div id="installDetail" class="muted">Windows/Chrome/Edge: tarayıcıdaki Yükle simgesini kullanın. macOS Safari: Dosya › Dock’a Ekle.</div></div><button id="installButton">Yükle</button>';
  wrap.prepend(panel);
  document.getElementById("installButton").addEventListener("click", async () => {
    if (installPrompt) {
      installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      return;
    }
    if (/iphone|ipad|ipod/i.test(navigator.userAgent)) {
      showInstallHelp("iPhone/iPad: Paylaş simgesi › Ana Ekrana Ekle › Ekle.");
    } else {
      showInstallHelp("Tarayıcıdaki Yükle / Uygulama olarak kaydet seçeneğini kullanın. macOS Safari’de Dosya › Dock’a Ekle seçin.");
    }
  });
}

window.addEventListener("beforeinstallprompt", event => {
  event.preventDefault();
  installPrompt = event;
  showInstallHelp("Uygulamayı masaüstüne veya Başlat menüsüne eklemek için Yükle düğmesini kullanın.");
});

window.addEventListener("DOMContentLoaded", () => {
  addInstallPanel();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
});
