// The browser owns installation: Chrome/Edge use the address-bar install icon;
// Safari uses Add to Home Screen. Do not intercept beforeinstallprompt.
window.addEventListener("DOMContentLoaded", () => {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/fon-takip-paneli/sw.js").catch(() => {});
  }
});
