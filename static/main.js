if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/service-worker.js")
    .then(() => console.log("SW registered"));
}

let deferredPrompt;

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;

  // Show your install button
  document.getElementById("installBtn").style.display = "block";
});

document.getElementById("installBtn").addEventListener("click", () => {
  deferredPrompt.prompt();
  deferredPrompt.userChoice.then(choice => {
    console.log(choice.outcome);
  });
});