const state = {
  archivo: null,
  analizando: false,
  controller: null,
  analisisId: 0,
  turnstileToken: null,
  esperandoAnalisis: false,
  pasoAnimToken: 0,
};

const MAX_MB = 10;
const MAX_BYTES = MAX_MB * 1024 * 1024;
const TIMEOUT_GLOBAL = 30000;

const DURACION_PASO_1 = 1600;
const DURACION_PASO_2 = 2200;
const DURACION_PASO_3 = 2600;
const DURACION_PASO_4 = 1500;

function mostrarToast(mensaje, tipo = "error") {
  const existente = document.getElementById("sifis-toast");
  if (existente) existente.remove();

  const toast = document.createElement("div");
  toast.id = "sifis-toast";
  toast.className = `sifis-toast sifis-toast--${tipo}`;
  toast.setAttribute("role", "alert");
  toast.setAttribute("aria-live", "assertive");
  toast.setAttribute("tabindex", "-1");
  toast.textContent = mensaje;
  document.body.appendChild(toast);

  toast.focus();
  toast.getBoundingClientRect();
  toast.classList.add("sifis-toast--visible");

  setTimeout(() => {
    toast.classList.remove("sifis-toast--visible");
    toast.addEventListener("transitionend", () => toast.remove(), { once: true });
  }, 4000);
}

function mostrarPantalla(id) {
  document.querySelectorAll(".pantalla").forEach((p) => {
    p.classList.remove("activa");
    p.setAttribute("aria-hidden", "true");
  });
  const activa = document.getElementById(id);
  activa.classList.add("activa");
  activa.removeAttribute("aria-hidden");

  window.scrollTo({ top: 0, behavior: "smooth" });
}

function resetearPasos() {
  for (let i = 1; i <= 4; i++) {
    const paso = document.getElementById(`paso-${i}`);
    const barra = document.getElementById(`barra-${i}`);
    if (!paso || !barra) continue;
    paso.classList.remove("paso-activo", "paso-completado");
    const estadoEl = paso.querySelector(".paso-estado");
    if (estadoEl) estadoEl.textContent = "En espera";
    barra.style.width = "0%";
  }
}

function animarBarra(num, duracion) {
  return new Promise((resolve) => {
    const paso = document.getElementById(`paso-${num}`);
    const barra = document.getElementById(`barra-${num}`);
    if (!paso || !barra) {
      resolve();
      return;
    }

    const estadoEl = paso.querySelector(".paso-estado");
    paso.classList.remove("paso-completado");
    paso.classList.add("paso-activo");
    if (estadoEl) estadoEl.textContent = "Procesando...";

    const miToken = state.pasoAnimToken;
    const inicio = performance.now();

    function frame(ts) {
      if (state.pasoAnimToken !== miToken) {
        resolve();
        return;
      }

      const transcurrido = ts - inicio;
      const progreso = Math.min(transcurrido / duracion, 1);
      barra.style.width = (progreso * 100).toFixed(1) + "%";

      if (progreso < 1) {
        requestAnimationFrame(frame);
      } else {
        paso.classList.remove("paso-activo");
        paso.classList.add("paso-completado");
        if (estadoEl) estadoEl.textContent = "Completado";
        resolve();
      }
    }

    requestAnimationFrame(frame);
  });
}

async function iniciarAnimacionPasos() {
  resetearPasos();
  await animarBarra(1, DURACION_PASO_1);
  await animarBarra(2, DURACION_PASO_2);
  await animarBarra(3, DURACION_PASO_3);
}

function detenerAnimacionPasos() {
  state.pasoAnimToken++;
}

function alternarTarjetaSubida(mostrar) {
  const zonaSubida = document.getElementById("zonaSubida");
  const subirCard = zonaSubida ? zonaSubida.closest(".subir-card") : null;
  if (subirCard) subirCard.style.display = mostrar ? "block" : "none";
}

function onTurnstileSuccess(token) {
  state.turnstileToken = token;

  if (state.esperandoAnalisis && state.archivo) {
    state.esperandoAnalisis = false;
    iniciarAnalisis(state.archivo);
  }
}

function onTurnstileExpired() {
  state.turnstileToken = null;

  if (state.esperandoAnalisis) {
    const btnConfirmarAnalizar = document.getElementById("btn-confirmar-analizar");
    if (btnConfirmarAnalizar) btnConfirmarAnalizar.disabled = false;
  }
}

function onTurnstileError() {
  state.turnstileToken = null;
  mostrarToast("No se pudo cargar la verificación de seguridad. Recarga la página.");
}

function resetTurnstile() {
  state.turnstileToken = null;
  if (window.turnstile && document.getElementById("turnstileWidget")) {
    try {
      window.turnstile.reset("#turnstileWidget");
    } catch (e) {}
  }
}

function alternarCaptcha(mostrar) {
  const widget = document.getElementById("turnstileWidget");
  if (widget) widget.style.display = mostrar ? "block" : "none";
}

window.onTurnstileSuccess = onTurnstileSuccess;
window.onTurnstileExpired = onTurnstileExpired;
window.onTurnstileError = onTurnstileError;

function procesarArchivo(file) {
  if (state.analizando) return;

  const inputImagen = document.getElementById("inputImagen");
  const permitidos = ["image/jpeg", "image/png", "image/webp"];

  if (!permitidos.includes(file.type)) {
    mostrarToast("Formato no permitido. Usa JPG, PNG o WEBP.");
    inputImagen.value = "";
    return;
  }

  if (file.size > MAX_BYTES) {
    mostrarToast(`La imagen supera el límite de ${MAX_MB} MB.`);
    inputImagen.value = "";
    return;
  }

  state.archivo = file;

  const reader = new FileReader();
  reader.onload = (e) => {
    const preview = document.getElementById("preview-imagen-inicio");
    preview.src = e.target.result;
    preview.alt = `Vista previa de ${file.name}`;

    document.getElementById("zonaSubida").style.display = "none";
    alternarTarjetaSubida(false);

    const zonaPreview = document.getElementById("zonaPreview");
    zonaPreview.style.display = "block";
    zonaPreview.removeAttribute("aria-hidden");
  };
  reader.readAsDataURL(file);
}

function limpiarSeleccion() {
  state.archivo = null;
  document.getElementById("inputImagen").value = "";

  const preview = document.getElementById("preview-imagen-inicio");
  preview.src = "";
  preview.alt = "";

  const zonaPreview = document.getElementById("zonaPreview");
  zonaPreview.style.display = "none";
  zonaPreview.setAttribute("aria-hidden", "true");

  document.getElementById("zonaSubida").style.display = "block";
  alternarTarjetaSubida(true);

  state.esperandoAnalisis = false;
  alternarCaptcha(false);
  resetTurnstile();
}

function animarNumero(el, target) {
  const dur = 1100;
  let t0 = null;
  function step(ts) {
    if (!t0) t0 = ts;
    const p = Math.min((ts - t0) / dur, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(ease * target) + "%";
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

async function enviarImagen(file, animacionPasosPromise) {
  state.controller = new AbortController();
  const miAnalisisId = ++state.analisisId;

  const formData = new FormData();
  formData.append("imagen", file);
  formData.append("cf-turnstile-response", state.turnstileToken || "");

  const timeoutId = setTimeout(() => {
    if (miAnalisisId !== state.analisisId) return;
    if (state.controller) {
      state.controller.abort();
      mostrarToast("El análisis está tomando demasiado tiempo. Intenta de nuevo.");
      reiniciar();
    }
  }, TIMEOUT_GLOBAL);

  try {
    const fetchPromise = fetch("/analizar", {
      method: "POST",
      body: formData,
      signal: state.controller.signal,
    });

    const [res] = await Promise.all([fetchPromise, animacionPasosPromise]);

    clearTimeout(timeoutId);

    if (!res.ok) {
      const errorData = await res.text();
      let mensaje = `Error ${res.status}`;
      try {
        const json = JSON.parse(errorData);
        mensaje = json.error || mensaje;
      } catch (e) {
        mensaje = errorData || mensaje;
      }
      throw new Error(mensaje);
    }

    const data = await res.json();

    if (data.error) {
      throw new Error(data.error);
    }
    if (typeof data.prediccion !== "string" || typeof data.confianza !== "number") {
      throw new Error("Respuesta del servidor inválida");
    }

    if (miAnalisisId !== state.analisisId) return;

    await animarBarra(4, DURACION_PASO_4);

    if (miAnalisisId !== state.analisisId) return;
    mostrarResultados(data);

  } catch (err) {
    clearTimeout(timeoutId);

    if (err.name === "AbortError") return;
    if (miAnalisisId !== state.analisisId) return;

    const mensaje = err.message.includes("Failed to fetch")
      ? "No se pudo conectar con el servidor. Revisa tu conexión."
      : err.message || "Ocurrió un error inesperado.";
    mostrarToast(mensaje);
    reiniciar();
  }
}

function iniciarAnalisis(file) {
  if (state.analizando) return;

  if (!state.turnstileToken) {
    mostrarToast("Completa la verificación de seguridad antes de analizar.");
    return;
  }

  state.analizando = true;

  const btnAnalizar = document.getElementById("btn-analizar");
  btnAnalizar.disabled = true;

  const btnConfirmarAnalizar = document.getElementById("btn-confirmar-analizar");
  if (btnConfirmarAnalizar) btnConfirmarAnalizar.disabled = true;

  const reader = new FileReader();
  reader.onload = (e) => {
    const previewAnalisis = document.getElementById("preview-analisis");
    const placeholder = document.getElementById("placeholder-analisis");
    previewAnalisis.src = e.target.result;
    previewAnalisis.alt = `Imagen seleccionada: ${file.name}`;
    previewAnalisis.style.display = "block";
    placeholder.style.display = "none";

    const prevRes = document.getElementById("preview-resultado");
    prevRes.src = e.target.result;
    prevRes.alt = `Resultado del análisis: ${file.name}`;
    prevRes.style.display = "block";
  };
  reader.readAsDataURL(file);

  mostrarPantalla("pantalla-analisis");

  const animacionPasosPromise = iniciarAnimacionPasos();
  enviarImagen(file, animacionPasosPromise);
}

function nivelDeConfianza(porcentaje) {
  if (porcentaje >= 85) return "Alto";
  if (porcentaje >= 60) return "Medio";
  return "Bajo";
}

function mostrarResultados(data) {
  mostrarPantalla("pantalla-resultado");

  const esIA = data.prediccion === "IA";
  const confianza = data.confianza;

  const banner = document.getElementById("resultado-banner");
  banner.className = "resultado-banner" + (esIA ? " falsa" : "");

  document.getElementById("banner-num").textContent = esIA ? "IA" : "R";
  document.getElementById("banner-titulo").textContent = esIA ? "Imagen generada por IA" : "Imagen real";

  const alertaTexto = document.getElementById("banner-alerta-texto");
  if (alertaTexto) {
    alertaTexto.textContent = esIA
      ? "Imagen probablemente de IA"
      : "Imagen probablemente real";
  }

  const pctEl = document.getElementById("banner-pct");
  pctEl.textContent = "0%";
  animarNumero(pctEl, confianza);

  const fill = document.getElementById("banner-barra-fill");
  fill.style.width = "0%";
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      fill.style.width = confianza + "%";
    })
  );

  const probabilidadIA = data.prediccion_cruda * 100;
  const labelProbabilidad = document.getElementById("label-probabilidad");
  const valProbabilidad = document.getElementById("val-probabilidad");

  if (esIA) {
    labelProbabilidad.textContent = "Probabilidad de IA";
    valProbabilidad.textContent = probabilidadIA.toFixed(1) + "%";
  } else {
    labelProbabilidad.textContent = "Probabilidad de Real";
    valProbabilidad.textContent = (100 - probabilidadIA).toFixed(1) + "%";
  }

  document.getElementById("val-confianza").textContent = nivelDeConfianza(confianza);
  document.getElementById("val-clasificacion").textContent = esIA ? "IA" : "Real";

  if (state.archivo) {
    document.getElementById("val-archivo").textContent =
      `${state.archivo.name} · ${(state.archivo.size / 1024 / 1024).toFixed(2)} MB`;
  }

  if (data.ela_imagen) {
    document.getElementById("ela-imagen").src = "data:image/png;base64," + data.ela_imagen;
    document.getElementById("ela-panel").style.display = "block";
  }

  const elaToggle = document.getElementById("ela-toggle");
  const elaBody = document.getElementById("ela-body");
  const elaChevron = document.getElementById("ela-chevron");

  elaBody.classList.remove("oculto");
  elaToggle.setAttribute("aria-expanded", "true");
  elaChevron.textContent = "▼";
  elaToggle.onclick = () => {
    const oculto = elaBody.classList.toggle("oculto");
    elaChevron.textContent = oculto ? "▶" : "▼";
    elaToggle.setAttribute("aria-expanded", String(!oculto));
  };

  resetTurnstile();
  state.analizando = false;
}

function reiniciar() {
  state.analisisId++;

  detenerAnimacionPasos();

  if (state.controller) {
    state.controller.abort();
    state.controller = null;
  }

  state.archivo = null;
  state.analizando = false;

  const inputImagen = document.getElementById("inputImagen");
  inputImagen.value = "";

  const btnAnalizar = document.getElementById("btn-analizar");
  btnAnalizar.disabled = false;
  btnAnalizar.textContent = "Seleccionar archivo de imagen";

  const btnConfirmarAnalizar = document.getElementById("btn-confirmar-analizar");
  if (btnConfirmarAnalizar) btnConfirmarAnalizar.disabled = false;

  resetearPasos();

  const previewAnalisis = document.getElementById("preview-analisis");
  previewAnalisis.src = "";
  previewAnalisis.alt = "";
  previewAnalisis.style.display = "none";
  document.getElementById("placeholder-analisis").style.display = "flex";

  const prevRes = document.getElementById("preview-resultado");
  prevRes.src = "";
  prevRes.alt = "";
  prevRes.style.display = "none";

  const fill = document.getElementById("banner-barra-fill");
  if (fill) fill.style.width = "0%";
  const pctEl = document.getElementById("banner-pct");
  if (pctEl) pctEl.textContent = "—";

  const alertaTextoReset = document.getElementById("banner-alerta-texto");
  if (alertaTextoReset) alertaTextoReset.textContent = "—";

  const labelProbabilidadReset = document.getElementById("label-probabilidad");
  if (labelProbabilidadReset) labelProbabilidadReset.textContent = "Probabilidad de IA";

  document.getElementById("val-probabilidad").textContent = "—";
  document.getElementById("val-confianza").textContent = "—";
  document.getElementById("val-clasificacion").textContent = "—";
  document.getElementById("val-archivo").textContent = "—";

  document.getElementById("ela-panel").style.display = "none";
  document.getElementById("ela-body").classList.remove("oculto");
  document.getElementById("ela-chevron").textContent = "▼";

  limpiarSeleccion();
  mostrarPantalla("pantalla-inicio");
}

document.addEventListener("DOMContentLoaded", function () {
  const zonaSubida = document.getElementById("zonaSubida");
  const inputImagen = document.getElementById("inputImagen");
  const btnAnalizar = document.getElementById("btn-analizar");
  const btnEliminarPreview = document.getElementById("btn-eliminar-preview");
  const btnCambiarImagen = document.getElementById("btn-cambiar-imagen");
  const btnConfirmarAnalizar = document.getElementById("btn-confirmar-analizar");
  const btnReiniciar = document.getElementById("btn-reiniciar");

  btnAnalizar.addEventListener("click", () => {
    if (state.analizando) return;
    inputImagen.click();
  });

  zonaSubida.addEventListener("click", (e) => {
    if (e.target.closest("#btn-analizar")) return;
    if (state.analizando) return;
    inputImagen.click();
  });

  if (window.matchMedia("(hover: none)").matches) {
    const titulo = zonaSubida.querySelector(".subir-titulo");
    const hint = zonaSubida.querySelector(".subir-hint");
    if (titulo) titulo.textContent = "Toca para seleccionar tu imagen";
    if (hint) hint.style.display = "none";
  }

  zonaSubida.addEventListener("dragover", (e) => {
    e.preventDefault();
    zonaSubida.classList.add("drag-over");
  });

  zonaSubida.addEventListener("dragleave", (e) => {
    if (!zonaSubida.contains(e.relatedTarget)) {
      zonaSubida.classList.remove("drag-over");
    }
  });

  zonaSubida.addEventListener("drop", (e) => {
    e.preventDefault();
    zonaSubida.classList.remove("drag-over");
    if (state.analizando) return;
    const file = e.dataTransfer.files[0];
    if (file) procesarArchivo(file);
  });

  inputImagen.addEventListener("change", () => {
    const file = inputImagen.files[0];
    if (file) procesarArchivo(file);
  });

  btnEliminarPreview.addEventListener("click", limpiarSeleccion);
  btnCambiarImagen.addEventListener("click", limpiarSeleccion);

  btnConfirmarAnalizar.addEventListener("click", () => {
    if (!state.archivo || state.analizando) return;

    if (state.turnstileToken) {
      btnConfirmarAnalizar.disabled = true;
      iniciarAnalisis(state.archivo);
      return;
    }

    alternarCaptcha(true);
    state.esperandoAnalisis = true;
    btnConfirmarAnalizar.disabled = true;
    mostrarToast("Completa la verificación de seguridad para continuar.", "info");
  });

  btnReiniciar.addEventListener("click", reiniciar);

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "Enter" && state.archivo && !state.analizando && state.turnstileToken) {
      e.preventDefault();
      iniciarAnalisis(state.archivo);
    }
  });

  window.addEventListener("beforeunload", () => {
    if (state.controller) {
      state.controller.abort();
    }
  });
});

window.SIFIS = {
  reiniciar,
  state,
};