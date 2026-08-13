const state = {
  archivo: null,
  analizando: false,
  controller: null,
  analisisId: 0,
  turnstileToken: null,
  turnstileWidgetId: null,
  turnstileReady: false,
  esperandoCaptcha: false,
  pasoAnimToken: 0,
};

const MAX_MB = 10;
const MAX_BYTES = MAX_MB * 1024 * 1024;
const TIMEOUT_GLOBAL = 30000;

const DURACION_PASO_1 = 1600;
const DURACION_PASO_2 = 2200;
const DURACION_PASO_3 = 2600;
const DURACION_PASO_4 = 1500;
const PAUSA_CAPTCHA_CONFIRMADO = 1200;

const ICONO_CHECK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>`;

function mostrarToast(mensaje, tipo = "error") {
  const existente = document.getElementById("sifis-toast");
  if (existente) existente.remove();

  const toast = document.createElement("div");
  toast.id = "sifis-toast";
  toast.className = `sifis-toast sifis-toast--${tipo}`;
  const esError = tipo === "error";
  toast.setAttribute("role", esError ? "alert" : "status");
  toast.setAttribute("aria-live", esError ? "assertive" : "polite");
  toast.setAttribute("aria-atomic", "true");
  toast.textContent = mensaje;
  document.body.appendChild(toast);

  toast.getBoundingClientRect();
  toast.classList.add("sifis-toast--visible");

  setTimeout(() => {
    toast.classList.remove("sifis-toast--visible");
    toast.addEventListener("transitionend", () => toast.remove(), { once: true });
    setTimeout(() => toast.remove(), 500);
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

  const encabezado = activa.querySelector("h1, h2");
  if (encabezado) {
    encabezado.setAttribute("tabindex", "-1");
    encabezado.focus({ preventScroll: true });
  }
}

function resetearPasos() {
  for (let i = 1; i <= 4; i++) {
    const paso = document.getElementById(`paso-${i}`);
    const barra = document.getElementById(`barra-${i}`);
    if (!paso || !barra) continue;
    paso.classList.remove("paso-activo", "paso-completado");
    const estadoEl = paso.querySelector(".paso-estado");
    if (estadoEl) estadoEl.textContent = "En espera";
    const numEl = paso.querySelector(".paso-num");
    if (numEl) numEl.textContent = i;
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

        const numEl = paso.querySelector(".paso-num");
        if (numEl) numEl.innerHTML = ICONO_CHECK;

        resolve();
      }
    }

    requestAnimationFrame(frame);
  });
}

async function iniciarAnimacionPasos() {
  const tokenAnimacion = ++state.pasoAnimToken;
  resetearPasos();
  await animarBarra(1, DURACION_PASO_1);
  if (state.pasoAnimToken !== tokenAnimacion) return;
  await animarBarra(2, DURACION_PASO_2);
  if (state.pasoAnimToken !== tokenAnimacion) return;
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

function obtenerBotonConfirmar() {
  return document.getElementById("btn-confirmar-analizar");
}

function abrirModalCaptcha() {
  const modal = document.getElementById("captchaModal");
  if (!modal) return;
  modal.hidden = false;
  modal.removeAttribute("aria-hidden");
  document.body.classList.add("captcha-modal-abierto");
  document.getElementById("btn-cerrar-captcha")?.focus();
}

function cerrarModalCaptcha({ cancelar = false } = {}) {
  const modal = document.getElementById("captchaModal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  modal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("captcha-modal-abierto");

  if (cancelar) {
    state.turnstileToken = null;
    state.esperandoCaptcha = false;
    const botonConfirmar = obtenerBotonConfirmar();
    if (botonConfirmar) {
      botonConfirmar.disabled = false;
      botonConfirmar.focus();
    }
    if (window.turnstile && state.turnstileWidgetId !== null) {
      window.turnstile.reset(state.turnstileWidgetId);
    }
  }
}

function mostrarCaptcha() {
  const widget = document.getElementById("turnstileWidget");
  const sitekey = widget?.dataset.sitekey;
  if (!widget || !sitekey) {
    state.esperandoCaptcha = false;
    obtenerBotonConfirmar().disabled = false;
    mostrarToast("Cloudflare Turnstile no está configurado. Agrega las claves en el archivo .env.");
    return;
  }
  if (!state.turnstileReady || !window.turnstile) {
    state.esperandoCaptcha = false;
    obtenerBotonConfirmar().disabled = false;
    mostrarToast("La verificación de seguridad todavía está cargando. Inténtalo de nuevo.", "info");
    return;
  }

  abrirModalCaptcha();
  if (state.turnstileWidgetId === null) {
    state.turnstileWidgetId = window.turnstile.render(widget, {
      sitekey,
      action: "analyze-image",
      language: "es",
      theme: "auto",
      size: "flexible",
      callback: onTurnstileSuccess,
      "expired-callback": onTurnstileExpired,
      "error-callback": onTurnstileError,
    });
  } else {
    window.turnstile.reset(state.turnstileWidgetId);
  }
}

function onTurnstileSuccess(token) {
  state.turnstileToken = token;
  if (!state.esperandoCaptcha || !state.archivo) return;
  state.esperandoCaptcha = false;
  const archivoConfirmado = state.archivo;
  setTimeout(() => {
    if (state.archivo === archivoConfirmado && state.turnstileToken && !state.analizando) {
      cerrarModalCaptcha();
      iniciarAnalisis(archivoConfirmado);
    } else {
      cerrarModalCaptcha();
    }
  }, PAUSA_CAPTCHA_CONFIRMADO);
}

function onTurnstileExpired() {
  state.turnstileToken = null;
  state.esperandoCaptcha = false;
  cerrarModalCaptcha();
  obtenerBotonConfirmar().disabled = false;
  mostrarToast("La verificación expiró. Pulsa Analizar imagen para intentarlo otra vez.", "info");
}

function onTurnstileError(errorCode) {
  state.turnstileToken = null;
  state.esperandoCaptcha = false;
  cerrarModalCaptcha();
  obtenerBotonConfirmar().disabled = false;
  console.error("Error de Turnstile:", errorCode || "desconocido");
  mostrarToast("No se pudo completar la verificación de seguridad. Inténtalo de nuevo.");
  return true;
}

window.onTurnstileLoad = function () {
  state.turnstileReady = true;
};

window.onTurnstileScriptError = function () {
  state.turnstileReady = false;
  state.esperandoCaptcha = false;
  cerrarModalCaptcha();
  const botonConfirmar = obtenerBotonConfirmar();
  if (botonConfirmar) botonConfirmar.disabled = false;
  mostrarToast("No se pudo conectar con Cloudflare Turnstile. Revisa la conexión y vuelve a intentarlo.");
};

function procesarArchivo(file) {
  if (state.analizando) return;

  const inputImagen = document.getElementById("inputImagen");
  const permitidos = ["image/jpeg", "image/png", "image/webp"];

  if (!file || file.size === 0) {
    mostrarToast("El archivo está vacío. Selecciona otra imagen.");
    inputImagen.value = "";
    return;
  }

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
  state.turnstileToken = null;
  state.esperandoCaptcha = false;
  document.getElementById("inputImagen").value = "";

  const preview = document.getElementById("preview-imagen-inicio");
  preview.src = "";
  preview.alt = "";

  const zonaPreview = document.getElementById("zonaPreview");
  zonaPreview.style.display = "none";
  zonaPreview.setAttribute("aria-hidden", "true");

  document.getElementById("zonaSubida").style.display = "block";
  alternarTarjetaSubida(true);

  cerrarModalCaptcha();
  if (window.turnstile && state.turnstileWidgetId !== null) {
    window.turnstile.reset(state.turnstileWidgetId);
  }

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
    const res = await fetch("/analizar", {
      method: "POST",
      body: formData,
      signal: state.controller.signal,
    });

    if (!res.ok) {
      const errorData = await res.text();
      let mensaje = `Error ${res.status}`;
      try {
        const json = JSON.parse(errorData);
        mensaje = json.error || mensaje;
      } catch (e) {
        mensaje = res.status >= 500
          ? "El servidor no pudo completar el análisis. Inténtalo de nuevo."
          : errorData || mensaje;
      }
      throw new Error(mensaje);
    }

    let data;
    try {
      data = await res.json();
    } catch (error) {
      throw new Error("El servidor devolvió una respuesta inválida.");
    }

    if (data.error) {
      throw new Error(data.error);
    }
    if (
      !["REAL", "IA"].includes(data.prediccion) ||
      typeof data.confianza !== "number" ||
      typeof data.probabilidad_ia !== "number" ||
      typeof data.umbral_ia !== "number"
    ) {
      throw new Error("El servidor devolvió una respuesta inválida.");
    }

    if (miAnalisisId !== state.analisisId) return;

    await animacionPasosPromise;

    if (miAnalisisId !== state.analisisId) return;

    await animarBarra(4, DURACION_PASO_4);

    if (miAnalisisId !== state.analisisId) return;
    mostrarResultados(data);

  } catch (err) {
    if (err.name === "AbortError") return;
    if (miAnalisisId !== state.analisisId) return;

    const esErrorDeRed = err instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(err.message);
    const mensaje = esErrorDeRed
      ? "No se pudo conectar con el servidor. Revisa tu conexión."
      : err.message || "Ocurrió un error inesperado.";
    mostrarToast(mensaje);
    reiniciar();
  } finally {
    clearTimeout(timeoutId);
    if (miAnalisisId === state.analisisId) {
      state.controller = null;
    }
  }
}

function iniciarAnalisis(file) {
  if (state.analizando) return;

  if (!state.turnstileToken) {
    obtenerBotonConfirmar().disabled = false;
    mostrarToast("Completa la verificación de seguridad antes de continuar.");
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
  const probabilidadIA = data.probabilidad_ia;
  const umbralIA = data.umbral_ia;

  const banner = document.getElementById("resultado-banner");
  banner.className = "resultado-banner" + (esIA ? " falsa" : "");

  document.getElementById("banner-titulo").textContent = esIA
    ? "Imagen probablemente de IA"
    : "Imagen probablemente humana";
  document.getElementById("banner-clasificacion").textContent = esIA
    ? "Imagen generada por IA"
    : "Fotografía humana";
  document.getElementById("banner-etiqueta").textContent = esIA ? "IA" : "R";

  const pctEl = document.getElementById("banner-pct");
  pctEl.textContent = "0%";
  pctEl.setAttribute("aria-label", "Confianza de la clasificación");
  animarNumero(pctEl, confianza);

  const fill = document.getElementById("banner-barra-fill");
  fill.style.width = "0%";
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      fill.style.width = confianza + "%";
    })
  );

  const labelProbabilidad = document.getElementById("label-probabilidad");
  const valProbabilidad = document.getElementById("val-probabilidad");
  labelProbabilidad.textContent = esIA
    ? "Puntuación de imagen real"
    : "Puntuación de IA";
  valProbabilidad.textContent = esIA
    ? (100 - probabilidadIA).toFixed(1) + "%"
    : probabilidadIA.toFixed(1) + "%";

  document.getElementById("val-confianza").textContent = nivelDeConfianza(confianza);
  document.getElementById("val-clasificacion").textContent = esIA
    ? "IA"
    : "Real";

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

  state.analizando = false;
  state.turnstileToken = null;
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

  const labelProbabilidadReset = document.getElementById("label-probabilidad");
  if (labelProbabilidadReset) labelProbabilidadReset.textContent = "Puntuación de IA";

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
  const btnCerrarCaptcha = document.getElementById("btn-cerrar-captcha");
  const btnCancelarCaptcha = document.getElementById("btn-cancelar-captcha");
  const captchaModal = document.getElementById("captchaModal");

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

    btnConfirmarAnalizar.disabled = true;
    state.turnstileToken = null;
    state.esperandoCaptcha = true;
    mostrarCaptcha();
  });

  btnReiniciar.addEventListener("click", reiniciar);
  btnCerrarCaptcha.addEventListener("click", () => cerrarModalCaptcha({ cancelar: true }));
  btnCancelarCaptcha.addEventListener("click", () => cerrarModalCaptcha({ cancelar: true }));
  captchaModal.querySelector("[data-captcha-cerrar]").addEventListener("click", () => {
    cerrarModalCaptcha({ cancelar: true });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !captchaModal.hidden) {
      e.preventDefault();
      cerrarModalCaptcha({ cancelar: true });
      return;
    }
    if (e.ctrlKey && e.key === "Enter" && state.archivo && !state.analizando) {
      e.preventDefault();
      btnConfirmarAnalizar.click();
    }
  });

  window.addEventListener("beforeunload", () => {
    if (state.controller) {
      state.controller.abort();
    }
  });
});
