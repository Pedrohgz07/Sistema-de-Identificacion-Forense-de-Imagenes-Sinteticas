(function () {
  const STORAGE_KEY = "sifis-tema";

  function obtenerTemaInicial() {
    const guardado = localStorage.getItem(STORAGE_KEY);
    if (guardado === "light" || guardado === "dark") return guardado;
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  }

  function aplicarTema(tema) {
    if (tema === "light") {
      document.documentElement.setAttribute("data-theme", "light");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }

    const iconoSol = document.getElementById("icono-sol");
    const iconoLuna = document.getElementById("icono-luna");
    const botonTema = document.getElementById("btn-tema");
    if (iconoSol) iconoSol.style.display = tema === "light" ? "none" : "block";
    if (iconoLuna) iconoLuna.style.display = tema === "light" ? "block" : "none";
    if (botonTema) {
      const destino = tema === "light" ? "oscuro" : "claro";
      botonTema.setAttribute("aria-label", `Cambiar a modo ${destino}`);
      botonTema.setAttribute("title", `Cambiar a modo ${destino}`);
      botonTema.setAttribute("aria-pressed", String(tema === "dark"));
    }
  }

  const temaInicial = obtenerTemaInicial();
  aplicarTema(temaInicial);

  document.addEventListener("DOMContentLoaded", function () {
    aplicarTema(temaInicial);

    const botonTema = document.getElementById("btn-tema");
    if (!botonTema) return;

    botonTema.addEventListener("click", function () {
      const temaActual = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
      const temaNuevo = temaActual === "light" ? "dark" : "light";
      aplicarTema(temaNuevo);
      localStorage.setItem(STORAGE_KEY, temaNuevo);
    });
  });
})();
