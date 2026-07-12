
const API = "http://localhost:5000/api";

// ===== ESTADO =====
let state = {
  faenas: [], clientes: [], intermediarios: [], materiales: [],
  verArchivadas: false,
  detalleId: null,
  detalleActual: { gastos: [], presupuesto: [] }
};

// ===== ARRANQUE =====
async function init() {
  await Promise.all([
    cargarFaenas(), cargarClientes(),
    cargarIntermediarios(), cargarMateriales()
  ]);
  renderFaenas();
  renderClientes();
  renderInter();
  renderMateriales();
  poblarSelects();
  poblarSelectPolyboard();
  poblarSelectPresupuesto();
  cargarIP();
}

async function cargarIP() {
  try {
    const r = await api("GET", "/info/ip");
    if (r.ok) {
      document.getElementById("ip-valor").textContent = r.data.ip;
      document.getElementById("ip-banner").title = `IP del móvil: ${r.data.url} — Pulsa para copiar`;
    }
  } catch(e) {
    document.getElementById("ip-valor").textContent = "no disponible";
  }
}

function copiarIP() {
  const ip = document.getElementById("ip-valor").textContent;
  if (ip === "cargando..." || ip === "no disponible") return;
  navigator.clipboard.writeText(ip)
    .then(() => toast("✓ IP copiada: " + ip))
    .catch(() => toast("IP: " + ip));
}

// ===== API CALLS =====
async function api(method, path, body) {
  try {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(API + path, opts);
    return await r.json();
  } catch (e) {
    return { ok: false, error: "Error de conexión con el servidor" };
  }
}

async function cargarFaenas() {
  const r = await api("GET", state.verArchivadas ? "/faenas/archivadas" : "/faenas");
  if (r.ok) state.faenas = r.data;
}
async function cargarClientes() {
  const r = await api("GET", "/clientes");
  if (r.ok) state.clientes = r.data;
}
async function cargarIntermediarios() {
  const r = await api("GET", "/intermediarios");
  if (r.ok) state.intermediarios = r.data;
}
async function cargarMateriales() {
  const r = await api("GET", "/materiales");
  if (r.ok) state.materiales = r.data;
}

// ===== NAV =====
function nav(id) {
  document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
  document.querySelectorAll("nav button").forEach(b => b.classList.remove("active"));
  document.getElementById("s-" + id).classList.add("active");
  event.target.classList.add("active");
  if (id === "prompts") poblarSelectsPrompts();
  if (id === "polyboard") poblarSelectPolyboard();
  if (id === "presupuesto") { poblarSelectPresupuesto(); }
  if (id === "book") renderBook();
  if (id === "asistente") { poblarSelectAsistente(); }
}

// ===== MODALES =====
function abrirModal(id) {
  document.getElementById(id).classList.add("open");
}
function cerrarModal(id) {
  document.getElementById(id).classList.remove("open");
}
document.querySelectorAll(".overlay").forEach(o => {
  o.addEventListener("click", e => { if (e.target === o) o.classList.remove("open"); });
});

// ===== TOAST =====
function toast(msg, error = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (error ? " error" : "");
  setTimeout(() => t.className = "toast", 3000);
}

// ===== POBLAR SELECTS =====
function poblarSelects() {
  const sc = document.getElementById("f-cliente");
  sc.innerHTML = state.clientes.map(c => `<option value="${c.id}">${c.nombre}</option>`).join("");
  const si = document.getElementById("f-inter");
  si.innerHTML = state.intermediarios.map(i => `<option value="${i.id}">${i.id === 0 ? "— Directo —" : i.nombre}</option>`).join("");
  const sci = document.getElementById("c-inter");
  sci.innerHTML = state.intermediarios.map(i => `<option value="${i.id}">${i.id === 0 ? "— Directo —" : i.nombre}</option>`).join("");
  const sf = document.getElementById("ticket-faena-sel");
  sf.innerHTML = '<option value="">— Sin asignar —</option>' + state.faenas.map(f => `<option value="${f.id}">${f.numero} · ${f.cliente_nombre}</option>`).join("");
}

function poblarSelectsPrompts() {
  const sel = document.getElementById("prompt-faena-sel");
  sel.innerHTML = state.faenas.map(f => `<option value="${f.id}">${f.numero} · ${f.cliente_nombre}</option>`).join("");
}

// ===== RENDER FAENAS =====
function renderFaenas() {
  const q = document.getElementById("q-faena").value.toLowerCase();
  const lista = state.faenas.filter(f => {
    if (!q) return true;
    return (f.numero || "").toLowerCase().includes(q) ||
           (f.cliente_nombre || "").toLowerCase().includes(q) ||
           (f.tipo_trabajo || "").toLowerCase().includes(q) ||
           (f.direccion || "").toLowerCase().includes(q);
  });
  const el = document.getElementById("lista-faenas");
  el.innerHTML = lista.length ? lista.map(f => {
    const esDirecto = f.intermediario_id === 0;
    return `
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-id"><span class="num-faena">${f.numero}</span></div>
            <div class="card-title">${f.tipo_trabajo || "Sin descripción"}</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:4px;align-items:flex-end">
            <span class="badge ${esDirecto ? "b-direct" : "b-inter"}">${esDirecto ? "Directo" : f.intermediario_nombre}</span>
            ${f.importe > 0 ? `<span style="font-family:'Fraunces',serif;color:var(--green);font-size:0.95rem">${parseFloat(f.importe).toFixed(2)} €</span>` : ""}
          </div>
        </div>
        <div class="card-info">
          <strong>${f.cliente_nombre}</strong>
          ${f.direccion ? ` · ${f.direccion}` : ""}
          ${f.fecha_inicio ? ` · <span style="color:#aaa">${f.fecha_inicio}</span>` : ""}
        </div>
        <div class="card-actions">
          <button class="btn btn-s btn-sm" onclick="verDetalle(${f.id})">Ver detalle</button>
          <button class="btn btn-s btn-sm" onclick="abrirEditarFaena(${f.id})">✏️ Editar</button>
          <button class="btn btn-s btn-sm" onclick="abrirGasto(${f.id})">+ Gasto</button>
          <button class="btn btn-s btn-sm" onclick="abrirCarpetaDocumentos(${f.id})">📂 Documentos</button>
          ${!state.verArchivadas ? `<button class="btn btn-d btn-sm" onclick="archivar(${f.id})">Archivar</button>` : ""}
        </div>
      </div>`;
  }).join("") : `<div class="empty"><div class="empty-icon">🔨</div>${state.verArchivadas ? "No hay faenas archivadas" : "No hay faenas activas"}</div>`;
}

// ===== RENDER CLIENTES =====
function renderClientes() {
  const q = document.getElementById("q-cliente").value.toLowerCase();
  const lista = state.clientes.filter(c => !q || c.nombre.toLowerCase().includes(q));
  const el = document.getElementById("lista-clientes");
  el.innerHTML = lista.length ? lista.map(c => {
    const trabajos = state.faenas.filter(f => f.cliente_id === c.id);
    const total = trabajos.reduce((s, f) => s + (f.importe || 0), 0);
    return `
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">👤 ${c.nombre}</div>
            ${c.telefono ? `<div style="font-size:0.78rem;color:var(--green);margin-top:2px">📞 <a href="tel:${c.telefono}" style="color:var(--green)">${c.telefono}</a></div>` : ""}
          </div>
          <div style="display:flex;gap:6px;align-items:flex-start">
            <span class="badge b-direct">${trabajos.length} faena${trabajos.length !== 1 ? "s" : ""}</span>
            <button class="btn btn-s btn-sm" onclick="abrirEditarCliente(${c.id})">✏️</button>
          </div>
        </div>
        <div class="card-info">
          ${c.email ? "✉️ " + c.email + " &nbsp; " : ""}
          ${total > 0 ? `<strong style="color:var(--green)">${total.toFixed(2)} € total</strong>` : ""}
          ${c.intermediario_nombre && c.intermediario_id !== 0 ? `<br><span class="badge b-inter">${c.intermediario_nombre}</span>` : ""}
          ${c.notas ? `<br><em style="color:#aaa">${c.notas}</em>` : ""}
        </div>
        ${trabajos.length > 0 ? `
          <div style="margin-top:10px;border-top:1px solid var(--sawdust);padding-top:8px">
            <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.05em;color:#aaa;margin-bottom:6px">Faenas</div>
            ${trabajos.map(f => `
              <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px dashed var(--sawdust);cursor:pointer" onclick="verDetalle(${f.id})">
                <div>
                  <span class="num-faena" style="font-size:0.65rem">${f.numero}</span>
                  <span style="font-size:0.78rem;margin-left:6px">${f.tipo_trabajo || "Sin descripción"}</span>
                </div>
                <span style="font-size:0.75rem;color:var(--green)">${f.importe > 0 ? parseFloat(f.importe).toFixed(2) + " €" : ""}</span>
              </div>
            `).join("")}
          </div>
        ` : ""}
      </div>`;
  }).join("") : `<div class="empty"><div class="empty-icon">👤</div>No hay clientes</div>`;
}

// ===== RENDER INTERMEDIARIOS =====
function renderInter() {
  const el = document.getElementById("lista-inter");
  el.innerHTML = state.intermediarios.map(i => {
    const clientes = state.clientes.filter(c => c.intermediario_id === i.id);
    const faenas = state.faenas.filter(f => f.intermediario_id === i.id);
    return `
      <div class="card">
        <div class="card-header">
          <div class="card-title">${i.id === 0 ? "🏠" : "🤝"} ${i.nombre}</div>
          <span class="badge b-inter">${faenas.length} faena${faenas.length !== 1 ? "s" : ""}</span>
        </div>
        <div class="card-info">
          ${i.id === 0 ? '<em style="color:#aaa">Trabajos sin intermediario</em><br>' : ""}
          ${i.telefono ? "📞 " + i.telefono + " &nbsp; " : ""}
          ${i.email ? "✉️ " + i.email : ""}
          ${clientes.length > 0 ? `<br>Clientes: ${clientes.map(c => c.nombre).join(", ")}` : ""}
        </div>
      </div>`;
  }).join("");
}

// ===== RENDER MATERIALES (con definición) =====
function renderMateriales() {
  const q = document.getElementById("q-mat").value.toLowerCase();
  const lista = state.materiales.filter(m => !q || m.nombre.toLowerCase().includes(q) || m.categoria.toLowerCase().includes(q));
  const el = document.getElementById("lista-materiales");
  if (!lista.length) { el.innerHTML = `<div class="empty"><div class="empty-icon">📦</div>No hay materiales</div>`; return; }
  const cats = {};
  lista.forEach(m => {
    if (!cats[m.categoria]) cats[m.categoria] = [];
    cats[m.categoria].push(m);
  });
  el.innerHTML = Object.entries(cats).map(([cat, mats]) => `
    <div class="form-box" style="margin-bottom:16px">
      <div class="form-title">${cat}</div>
      <table class="mat-table">
        <thead>
          <tr><th>Material</th><th>Unidad</th><th>Definición</th><th>Proveedores y precios</th><th></th></tr>
        </thead>
        <tbody>
          ${mats.map(m => {
            const precios = [...(m.precios||[])].sort((a,b) => a.precio_unitario - b.precio_unitario);
            const preciosTxt = precios.map((p, i) =>
              `<span class="${i===0?"precio-min":""}">${p.proveedor}: ${parseFloat(p.precio_unitario).toFixed(2)}€</span>`
            ).join(" &nbsp;·&nbsp; ");
            const definicion = m.definicion ? m.definicion : '—';
            return `<tr>
              <td><strong>${m.nombre}</strong></td>
              <td>${m.unidad}</td>
              <td><span style="font-style:italic; color:#555;">${definicion}</span></td>
              <td>${preciosTxt || '<em style="color:#aaa">Sin precios</em>'}</td>
              <td><button class="btn btn-s btn-sm" onclick="abrirPrecio(${m.id})">+ Precio</button></td>
            </tr>`;
          }).join("")}
        </tbody>
       </table>
    </div>
  `).join("");
}

// ===== DETALLE FAENA =====
async function verDetalle(id) {
  const f = state.faenas.find(x => x.id === id);
  if (!f) return;
  const [rAnot, rConceptos, rDocs, rFotos] = await Promise.all([
    api("GET", `/faenas/${id}/anotaciones`),
    api("GET", `/faenas/${id}/conceptos`),
    api("GET", `/faenas/${id}/documentos`),
    api("GET", `/faenas/${id}/fotos`)
  ]);
  const cliente = state.clientes.find(c => c.id === f.cliente_id);
  const tel = cliente?.telefono || f.cliente_tel || "";
  const anotaciones = rAnot.ok ? rAnot.data : [];
  const conceptos = rConceptos.ok ? rConceptos.data : { presupuesto: [], gastos: [] };
  const presupuesto = conceptos.presupuesto || [];
  const gastos = conceptos.gastos || [];
  state.detalleId = id;
  state.detalleActual = { gastos, presupuesto };
  const docs = rDocs.ok ? rDocs.data : [];
  const fotos = rFotos.ok ? rFotos.data : [];
  const totalPresupuesto = presupuesto.reduce((s, g) => s + (parseFloat(g.total) || 0), 0);
  const totalGastos = gastos.reduce((s, g) => s + (g.total || 0), 0);
  const esDirecto = f.intermediario_id === 0;
  function formatBytes(b) {
    if (b < 1024) return b + " B";
    if (b < 1048576) return (b/1024).toFixed(1) + " KB";
    return (b/1048576).toFixed(1) + " MB";
  }
  function iconoArchivo(ext) {
    const map = { ".pdf": "📄", ".txt": "📝", ".pol": "🪵", ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".doc": "📃", ".docx": "📃", ".xls": "📊", ".xlsx": "📊" };
    return map[ext] || "📎";
  }
  document.getElementById("detalle-contenido").innerHTML = `
    <div class="modal-title" style="display:flex;justify-content:space-between;align-items:center">
      <div>🔨 <span class="num-faena">${f.numero}</span>
      &nbsp; <span class="badge ${esDirecto ? "b-direct" : "b-inter"}">${esDirecto ? "Directo" : f.intermediario_nombre}</span></div>
      <button class="btn btn-s btn-sm" onclick="cerrarModal('m-detalle');abrirEditarFaena(${f.id})">✏️ Editar</button>
    </div>
    <div class="det-row"><span class="det-k">Tipo de trabajo</span><span class="det-v">${f.tipo_trabajo || "—"}</span></div>
    <div class="det-row"><span class="det-k">Cliente</span><span class="det-v">${f.cliente_nombre}${tel ? `<br><a href="tel:${tel}" style="color:var(--green);font-size:0.78rem">📞 ${tel}</a>` : ""}</span></div>
    <div class="det-row"><span class="det-k">Dirección</span><span class="det-v">${f.direccion || "—"}</span></div>
    <div class="det-row"><span class="det-k">Importe</span><span class="det-v" style="color:var(--green);font-family:'Fraunces',serif">${totalPresupuesto > 0 ? totalPresupuesto.toFixed(2) + " €" : "—"}</span></div>
    <div class="det-row"><span class="det-k">Fecha inicio</span><span class="det-v">${f.fecha_inicio || "—"}</span></div>
    <hr>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <strong style="font-size:0.85rem">📷 Fotos (${fotos.length})</strong>
      <button class="btn btn-s btn-sm" onclick="abrirCarpetaFotos(${f.id})">📂 Abrir carpeta</button>
    </div>
    ${fotos.length ? `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-bottom:8px">
        ${fotos.map(foto => `
          <div style="position:relative;aspect-ratio:1;border-radius:6px;overflow:hidden;border:1px solid var(--sawdust)">
            <img src="${foto.data}" alt="${foto.nombre}"
                 style="width:100%;height:100%;object-fit:cover;cursor:pointer"
                 onclick="verFotoPC('${foto.data}','${foto.nombre}')">
            <button onclick="eliminarFotoPC(${f.id},'${foto.nombre}')"
                    style="position:absolute;top:4px;right:4px;background:rgba(139,32,32,0.85);color:white;border:none;border-radius:50%;width:22px;height:22px;cursor:pointer;font-size:0.75rem;display:flex;align-items:center;justify-content:center">×</button>
          </div>
        `).join("")}
      </div>
    ` : '<p style="font-size:0.82rem;color:#aaa;margin:8px 0">Sin fotos — súbelas desde el móvil</p>'}
    <hr>
    <div class="btn-row" style="margin:0;gap:6px">
      <button class="btn btn-s btn-sm" onclick="subirDocumento(${f.id})">+ Añadir</button>
      <button class="btn btn-s btn-sm" onclick="abrirCarpetaDocumentos(${f.id})">📂 Abrir carpeta</button>
    </div>
    ${docs.length ? `
      <div style="border:1px solid var(--sawdust);border-radius:6px;overflow:hidden;margin-bottom:8px">
        ${docs.map(d => `
          <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--sawdust);font-size:0.8rem;background:white">
            <span style="font-size:1.1rem">${iconoArchivo(d.extension)}</span>
            <div style="flex:1;min-width:0">
              <div style="font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${d.nombre}</div>
              <div style="font-size:0.68rem;color:#aaa">${formatBytes(d.tamaño)}</div>
            </div>
            <button class="btn btn-s btn-sm" onclick="abrirDocumento(${f.id},'${d.nombre}')">Abrir</button>
            <button class="btn btn-d btn-sm" onclick="eliminarDocumento(${f.id},'${d.nombre}')">×</button>
          </div>
        `).join("")}
      </div>
    ` : '<p style="font-size:0.82rem;color:#aaa;margin:8px 0">Sin documentos</p>'}
    <hr>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <strong style="font-size:0.85rem">Presupuesto (${presupuesto.length})</strong>
      <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
        <button class="btn btn-s btn-sm" onclick="abrirPresupuestoItem(${f.id})">+ Partida</button>
        <span class="badge b-orange">Total ${totalPresupuesto.toFixed(2)} €</span>
      </div>
    </div>
    ${presupuesto.length ? `
      <table class="gastos-table">
        <thead><tr><th>Descripción</th><th>Tipo</th><th>Cant.</th><th>P.Unit.</th><th>Total</th><th></th></tr></thead>
        <tbody>
          ${presupuesto.map(g => `<tr>
            <td>${g.descripcion}</td>
            <td><span class="badge b-orange">${g.tipo}</span></td>
            <td>${g.cantidad ?? ""}</td>
            <td>${g.precio_unitario != null ? parseFloat(g.precio_unitario).toFixed(2) + " €" : ""}</td>
            <td><strong>${parseFloat(g.total || 0).toFixed(2)} €</strong></td>
            <td><div class="btn-row" style="margin:0;gap:4px;justify-content:flex-end"><button class="btn btn-s btn-sm" onclick="abrirPresupuestoItem(${f.id}, ${g.id})">✏️</button><button class="btn btn-d btn-sm" onclick="eliminarPresupuestoItem(${g.id}, ${f.id})">×</button></div></td>
          </tr>`).join("")}
        </tbody>
       </table>
    ` : '<p style="font-size:0.82rem;color:#aaa;margin:8px 0">Sin conceptos de presupuesto</p>'}

    <hr>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <strong style="font-size:0.85rem">Gastos de fabricación (${gastos.length})</strong>
      <button class="btn btn-s btn-sm" onclick="cerrarModal('m-detalle');abrirGasto(${f.id})">+ Gasto</button>
    </div>
    ${gastos.length ? `
      <table class="gastos-table">
        <thead><tr><th>Descripción</th><th>Tipo</th><th>Cant.</th><th>P.Unit.</th><th>Total</th><th></th></tr></thead>
        <tbody>
          ${gastos.map(g => `<tr>
            <td>${g.descripcion}</td>
            <td><span class="badge b-gray">${g.tipo}</span></td>
            <td>${g.cantidad}</td>
            <td>${parseFloat(g.precio_unitario).toFixed(2)} €</td>
            <td><strong>${parseFloat(g.total).toFixed(2)} €</strong></td>
            <td><div class="btn-row" style="margin:0;gap:4px;justify-content:flex-end"><button class="btn btn-s btn-sm" onclick="abrirEditarGasto(${g.id}, ${f.id})">✏️</button><button class="btn btn-d btn-sm" onclick="eliminarGasto(${g.id}, ${f.id})">×</button></div></td>
          </tr>
           `).join("")}
        </tbody>
       </table>
      <div class="gastos-total">Total gastos: ${totalGastos.toFixed(2)} €</div>
    ` : '<p style="font-size:0.82rem;color:#aaa;margin:8px 0">Sin gastos registrados</p>'}
    <hr>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
      <strong style="font-size:0.85rem">Anotaciones (${anotaciones.length})</strong>
      <button class="btn btn-s btn-sm" onclick="abrirAnotacion(${f.id})">+ Anotación</button>
    </div>
    ${anotaciones.length ? anotaciones.map(a => `
      <div style="background:var(--paper-dark);border-radius:4px;padding:10px 12px;margin-bottom:8px;font-size:0.8rem;display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <div style="flex:1">
          <span class="badge b-gray" style="margin-bottom:4px">${a.tipo}</span>
          <div style="margin-top:4px;line-height:1.5">${a.contenido}</div>
          <div style="font-size:0.68rem;color:#aaa;margin-top:4px">${a.fecha}</div>
        </div>
        <div style="display:flex;gap:4px;flex-shrink:0">
          <button class="btn btn-s btn-sm" onclick="editarAnotacion(${a.id}, '${a.tipo}', \`${a.contenido.replace(/`/g,'\\`')}\`, ${f.id})">✏️</button>
          <button class="btn btn-d btn-sm" onclick="eliminarAnotacion(${a.id}, ${f.id})">×</button>
        </div>
      </div>
    `).join("") : '<p style="font-size:0.82rem;color:#aaa;margin:8px 0">Sin anotaciones</p>'}
  `;
  abrirModal("m-detalle");
}

// ===== FOTOS PC =====
function verFotoPC(src, nombre) {
  const o = document.createElement("div");
  o.className = "foto-overlay";
  o.innerHTML = `<img src="${src}" alt="${nombre}"><div class="foto-overlay-nombre">${nombre}</div><button class="btn btn-s btn-sm" onclick="this.parentNode.remove()">Cerrar</button>`;
  o.addEventListener("click", e => { if (e.target === o) o.remove(); });
  document.body.appendChild(o);
}
async function eliminarFotoPC(faenaId, nombre) {
  if (!confirm(`¿Eliminar la foto "${nombre}"?`)) return;
  const r = await api("DELETE", `/faenas/${faenaId}/fotos/${nombre}`);
  if (r.ok) { toast("Foto eliminada"); verDetalle(faenaId); }
  else toast(r.error, true);
}
async function abrirCarpetaFotos(faenaId) {
  const r = await api("POST", `/faenas/${faenaId}/fotos/carpeta`);
  if (!r.ok) toast(r.error, true);
}

// ===== DOCUMENTOS =====
async function subirDocumento(faenaId) {
  const r = await api("POST", `/faenas/${faenaId}/documentos`, {});
  if (r.ok) { toast(`✓ ${r.data.copiados.length} archivo${r.data.copiados.length !== 1 ? "s" : ""} añadido${r.data.copiados.length !== 1 ? "s" : ""}`); verDetalle(faenaId); }
  else toast(r.error || "No se añadieron archivos", r.ok ? false : true);
}
async function eliminarDocumento(faenaId, nombre) {
  if (!confirm(`¿Eliminar "${nombre}"?`)) return;
  const r = await api("DELETE", `/faenas/${faenaId}/documentos/${nombre}`);
  if (r.ok) { toast("Archivo eliminado"); verDetalle(faenaId); }
  else toast(r.error, true);
}
async function abrirDocumento(faenaId, nombre) {
  const r = await api("POST", `/faenas/${faenaId}/documentos/${nombre}/abrir`);
  if (!r.ok) toast(r.error, true);
}
async function abrirCarpetaDocumentos(faenaId) {
  const r = await api("POST", `/faenas/${faenaId}/documentos/carpeta`);
  if (!r.ok) toast(r.error, true);
}

// ===== EDITAR FAENA =====
function abrirEditarFaena(id) {
  const f = state.faenas.find(x => x.id === id);
  if (!f) return;
  document.getElementById("ef-id").value = f.id;
  document.getElementById("ef-dir").value = f.direccion || "";
  document.getElementById("ef-tipo").value = f.tipo_trabajo || "";
  document.getElementById("ef-importe").value = f.importe || "";
  document.getElementById("ef-fecha").value = f.fecha_inicio || "";
  abrirModal("m-editar-faena");
}
async function guardarEditarFaena() {
  const id = document.getElementById("ef-id").value;
  const r = await api("PUT", `/faenas/${id}`, {
    direccion: document.getElementById("ef-dir").value,
    tipo_trabajo: document.getElementById("ef-tipo").value,
    importe: parseFloat(document.getElementById("ef-importe").value) || 0,
    fecha_inicio: document.getElementById("ef-fecha").value
  });
  if (r.ok) { toast("✓ Faena actualizada"); cerrarModal("m-editar-faena"); await cargarFaenas(); renderFaenas(); verDetalle(parseInt(id)); }
  else toast(r.error, true);
}

// ===== EDITAR CLIENTE =====
function abrirEditarCliente(id) {
  const c = state.clientes.find(x => x.id === id);
  if (!c) return;
  document.getElementById("ec-id").value = c.id;
  document.getElementById("ec-nombre").value = c.nombre || "";
  document.getElementById("ec-tel").value = c.telefono || "";
  document.getElementById("ec-email").value = c.email || "";
  document.getElementById("ec-notas").value = c.notas || "";
  abrirModal("m-editar-cliente");
}
async function guardarEditarCliente() {
  const id = document.getElementById("ec-id").value;
  const r = await api("PUT", `/clientes/${id}`, {
    nombre: document.getElementById("ec-nombre").value,
    telefono: document.getElementById("ec-tel").value,
    email: document.getElementById("ec-email").value,
    notas: document.getElementById("ec-notas").value
  });
  if (r.ok) { toast("✓ Cliente actualizado"); cerrarModal("m-editar-cliente"); await cargarClientes(); renderClientes(); }
  else toast(r.error, true);
}

// ===== ACCIONES FAENAS =====
async function crearFaena() {
  const r = await api("POST", "/faenas", {
    cliente_id: parseInt(document.getElementById("f-cliente").value),
    intermediario_id: parseInt(document.getElementById("f-inter").value),
    direccion: document.getElementById("f-dir").value,
    tipo_trabajo: document.getElementById("f-tipo").value,
    importe: parseFloat(document.getElementById("f-importe").value) || 0,
    fecha_inicio: document.getElementById("f-fecha").value
  });
  if (r.ok) { toast(`✓ Faena ${r.data.numero} creada`); cerrarModal("m-faena"); document.getElementById("f-dir").value = ""; document.getElementById("f-tipo").value = ""; document.getElementById("f-importe").value = ""; await cargarFaenas(); renderFaenas(); poblarSelects(); }
  else toast(r.error, true);
}
async function archivar(id) {
  if (!confirm("¿Archivar esta faena? Dejará de aparecer en el móvil.")) return;
  const r = await api("POST", `/faenas/${id}/archivar`);
  if (r.ok) { toast("Faena archivada"); await cargarFaenas(); renderFaenas(); }
}
async function toggleArchivadas() {
  state.verArchivadas = !state.verArchivadas;
  document.getElementById("btn-archivadas").textContent = state.verArchivadas ? "Ver activas" : "Ver archivadas";
  await cargarFaenas(); renderFaenas();
}
async function abrirCursor(id, carpeta) {
  const r = await api("POST", "/cursor/abrir", { carpeta });
  if (!r.ok) toast(r.error, true);
}

// ===== ANOTACIONES =====
function abrirAnotacion(faenaId) {
  document.getElementById("anot-faena-id").value = faenaId;
  document.getElementById("anot-contenido").value = "";
  cerrarModal("m-detalle"); abrirModal("m-anotacion");
}
async function crearAnotacion() {
  const faenaId = document.getElementById("anot-faena-id").value;
  const r = await api("POST", `/faenas/${faenaId}/anotaciones`, { tipo: document.getElementById("anot-tipo").value, contenido: document.getElementById("anot-contenido").value });
  if (r.ok) { toast("✓ Anotación guardada"); cerrarModal("m-anotacion"); verDetalle(parseInt(faenaId)); }
  else toast(r.error, true);
}
function editarAnotacion(id, tipo, contenido, faenaId) {
  document.getElementById("ea-id").value = id; document.getElementById("ea-faena-id").value = faenaId; document.getElementById("ea-tipo").value = tipo; document.getElementById("ea-contenido").value = contenido;
  cerrarModal("m-detalle"); abrirModal("m-editar-anotacion");
}
async function guardarEditarAnotacion() {
  const id = document.getElementById("ea-id").value; const faenaId = document.getElementById("ea-faena-id").value;
  const r = await api("PUT", `/anotaciones/${id}`, { tipo: document.getElementById("ea-tipo").value, contenido: document.getElementById("ea-contenido").value });
  if (r.ok) { toast("✓ Anotación actualizada"); cerrarModal("m-editar-anotacion"); verDetalle(parseInt(faenaId)); }
  else toast(r.error, true);
}
async function eliminarAnotacion(id, faenaId) {
  if (!confirm("¿Eliminar esta anotación?")) return;
  await api("DELETE", `/anotaciones/${id}`);
  verDetalle(faenaId);
}

// ===== GASTOS =====
async function importarPDFGastos() {
  const faenaId = document.getElementById("gasto-faena-id").value;
  if (!faenaId) { toast("Selecciona una faena primero", true); return; }
  const r = await api("POST", `/faenas/${faenaId}/gastos/importar-pdf`, {});
  if (!r.ok) { toast(r.error || "Error al leer el PDF", true); return; }
  document.getElementById("pdf-gastos-prompt-txt").textContent = r.data.prompt;
  document.getElementById("pdf-gastos-prompt-box").style.display = "block";
  toast(`✓ PDF "${r.data.nombre_pdf}" procesado`);
}
async function cargarJsonGastosPDF() {
  const faenaId = document.getElementById("gasto-faena-id").value;
  const raw = document.getElementById("pdf-gastos-json").value.trim();
  if (!raw) { toast("Pega el JSON primero", true); return; }
  let datos;
  try { const limpio = raw.replace(/```json\n?/g, "").replace(/```\n?/g, "").trim(); datos = JSON.parse(limpio); } catch(e) { toast("JSON no válido", true); return; }
  const articulos = datos.articulos || [];
  if (!articulos.length) { toast("No se encontraron artículos", true); return; }
  let insertados = 0;
  for (const art of articulos) {
    if (!art.nombre || !art.precio_unitario) continue;
    const r = await api("POST", `/faenas/${faenaId}/gastos`, { tipo: "herraje", descripcion: art.nombre, cantidad: art.cantidad || 1, precio_unitario: art.precio_unitario });
    if (r.ok) insertados++;
  }
  toast(`✓ ${insertados} gasto${insertados !== 1 ? "s" : ""} añadido${insertados !== 1 ? "s" : ""}`);
  document.getElementById("pdf-gastos-json").value = "";
  document.getElementById("pdf-gastos-prompt-box").style.display = "none";
  cerrarModal("m-gasto"); verDetalle(parseInt(faenaId));
}
function abrirGasto(faenaId) {
  document.getElementById("gasto-faena-id").value = faenaId;
  document.getElementById("gasto-id").value = "";
  document.getElementById("gasto-modal-title").textContent = "💶 Nuevo Gasto";
  document.getElementById("g-desc").value = "";
  document.getElementById("g-cant").value = "1";
  document.getElementById("g-precio").value = "";
  abrirModal("m-gasto");
}
function abrirEditarGasto(gastoId, faenaId) {
  const gasto = (state.detalleActual.gastos || []).find(g => String(g.id) === String(gastoId));
  if (!gasto) return;
  document.getElementById("gasto-faena-id").value = faenaId;
  document.getElementById("gasto-id").value = gasto.id;
  document.getElementById("gasto-modal-title").textContent = "✏️ Editar Gasto";
  document.getElementById("g-desc").value = gasto.descripcion || "";
  document.getElementById("g-tipo").value = gasto.tipo || "otro";
  document.getElementById("g-cant").value = gasto.cantidad ?? 1;
  document.getElementById("g-precio").value = gasto.precio_unitario ?? 0;
  cerrarModal("m-detalle");
  abrirModal("m-gasto");
}
async function guardarGasto() {
  const faenaId = document.getElementById("gasto-faena-id").value;
  const gastoId = document.getElementById("gasto-id").value;
  const payload = {
    tipo: document.getElementById("g-tipo").value,
    descripcion: document.getElementById("g-desc").value,
    cantidad: parseFloat(document.getElementById("g-cant").value) || 1,
    precio_unitario: parseFloat(document.getElementById("g-precio").value) || 0
  };
  const r = gastoId
    ? await api("PUT", `/gastos/${gastoId}`, payload)
    : await api("POST", `/faenas/${faenaId}/gastos`, payload);
  if (r.ok) {
    toast(gastoId ? `✓ Gasto actualizado: ${r.data.total.toFixed(2)} €` : `✓ Gasto añadido: ${r.data.total.toFixed(2)} €`);
    cerrarModal("m-gasto");
    await verDetalle(parseInt(faenaId));
  }
  else toast(r.error, true);
}
async function eliminarGasto(id, faenaId) {
  if (!confirm("¿Eliminar este gasto?")) return;
  const r = await api("DELETE", `/gastos/${id}`);
  if (r.ok) verDetalle(faenaId);
  else toast(r.error, true);
}

// ===== CLIENTES =====
async function crearCliente() {
  const r = await api("POST", "/clientes", { nombre: document.getElementById("c-nombre").value, telefono: document.getElementById("c-tel").value, email: document.getElementById("c-email").value, intermediario_id: parseInt(document.getElementById("c-inter").value) || 0, notas: document.getElementById("c-notas").value });
  if (r.ok) { toast("✓ Cliente guardado"); cerrarModal("m-cliente"); document.getElementById("c-nombre").value = ""; document.getElementById("c-tel").value = ""; document.getElementById("c-email").value = ""; document.getElementById("c-notas").value = ""; await cargarClientes(); renderClientes(); poblarSelects(); }
  else toast(r.error, true);
}

// ===== INTERMEDIARIOS =====
async function crearInter() {
  const r = await api("POST", "/intermediarios", { nombre: document.getElementById("i-nombre").value, telefono: document.getElementById("i-tel").value, email: document.getElementById("i-email").value });
  if (r.ok) { toast("✓ Intermediario guardado"); cerrarModal("m-inter"); document.getElementById("i-nombre").value = ""; document.getElementById("i-tel").value = ""; document.getElementById("i-email").value = ""; await cargarIntermediarios(); renderInter(); poblarSelects(); }
  else toast(r.error, true);
}

// ===== MATERIALES =====
async function importarPDF() {
  const panel = document.getElementById("pdf-import-panel"); panel.style.display = "block"; panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const estado = document.getElementById("pdf-import-estado"); estado.textContent = "Abriendo explorador de archivos..."; document.getElementById("pdf-prompt-box").style.display = "none";
  const r = await api("POST", "/materiales/importar-pdf", {});
  if (!r.ok) { estado.textContent = "⚠️ " + (r.error || "Error al procesar el PDF"); return; }
  estado.innerHTML = `<strong>${r.data.nombre_pdf}</strong> — ${r.data.caracteres.toLocaleString()} caracteres extraídos.<br><span style="color:#aaa">Copia el prompt y pégalo en Claude.ai para obtener el JSON.</span>`;
  document.getElementById("pdf-prompt-txt").textContent = r.data.prompt; document.getElementById("pdf-prompt-box").style.display = "block";
}
async function cargarJsonPDF() {
  const raw = document.getElementById("pdf-json-input").value.trim();
  if (!raw) { toast("Pega el JSON primero", true); return; }
  let datos;
  try { const limpio = raw.replace(/```json\n?/g, "").replace(/```\n?/g, "").trim(); datos = JSON.parse(limpio); } catch(e) { toast("JSON no válido — revísalo", true); return; }
  const materiales = datos.materiales || []; const proveedor = datos.proveedor || "";
  if (!materiales.length) { toast("No se encontraron materiales en el JSON", true); return; }
  let insertados = 0, actualizados = 0;
  for (const mat of materiales) {
    if (!mat.nombre) continue;
    let existente = state.materiales.find(m => m.nombre.toLowerCase() === mat.nombre.toLowerCase());
    if (!existente) {
      const r = await api("POST", "/materiales", { nombre: mat.nombre, unidad: mat.unidad || "ud", categoria: mat.categoria || "Otro" });
      if (r.ok) { existente = { id: r.data.id }; insertados++; }
    }
    if (existente && proveedor && mat.precio_unitario) { await api("POST", `/materiales/${existente.id}/precio`, { proveedor: proveedor, precio_unitario: mat.precio_unitario }); actualizados++; }
  }
  await cargarMateriales(); renderMateriales();
  toast(`✓ ${insertados} nuevo${insertados !== 1 ? "s" : ""} · ${actualizados} precio${actualizados !== 1 ? "s" : ""} actualizado${actualizados !== 1 ? "s" : ""}`);
  document.getElementById("pdf-json-input").value = ""; document.getElementById("pdf-import-panel").style.display = "none";
}
async function crearMaterial() {
  const r = await api("POST", "/materiales", { nombre: document.getElementById("mat-nombre").value, unidad: document.getElementById("mat-unidad").value, categoria: document.getElementById("mat-cat").value });
  if (r.ok) { toast("✓ Material guardado"); cerrarModal("m-material"); document.getElementById("mat-nombre").value = ""; await cargarMateriales(); renderMateriales(); }
  else toast(r.error, true);
}
function abrirPrecio(matId) {
  document.getElementById("precio-mat-id").value = matId;
  document.getElementById("precio-prov").value = "";
  document.getElementById("precio-val").value = "";
  abrirModal("m-precio");
}
async function guardarPrecio() {
  const id = document.getElementById("precio-mat-id").value;
  const r = await api("POST", `/materiales/${id}/precio`, { proveedor: document.getElementById("precio-prov").value, precio_unitario: parseFloat(document.getElementById("precio-val").value) });
  if (r.ok) { toast("✓ Precio actualizado"); cerrarModal("m-precio"); await cargarMateriales(); renderMateriales(); }
  else toast(r.error, true);
}

// ===== PROMPTS =====
let ultimaRutaTicketProcesada = "";

function previewTicket(event) {
  const file = event.target.files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  document.getElementById("ticket-img").src = url;
  document.getElementById("ticket-preview").style.display = "block";
  const promptBox = document.getElementById("prompt-ticket-box");
  if (promptBox) promptBox.style.display = "none";
}
async function generarPromptTicket() {
  const r = await api("GET", "/prompts/ticket");
  if (r.ok) { document.getElementById("prompt-ticket-txt").textContent = r.data.prompt; document.getElementById("prompt-ticket-box").style.display = "block"; document.getElementById("prompt-ticket-box").scrollIntoView({ behavior: "smooth", block: "nearest" }); }
}

function archivoADataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function procesarTicketLocal() {
  const input = document.getElementById("ticket-foto-input");
  const file = input?.files?.[0];
  if (!file) { toast("Selecciona una foto primero", true); return; }

  const btn = document.getElementById("btn-procesar-ticket");
  if (btn) { btn.disabled = true; btn.textContent = "Procesando..."; }

  try {
    const data = await archivoADataUrl(file);
    const faenaId = document.getElementById("ticket-faena-sel")?.value || "";
    const r = await api("POST", "/tickets/procesar", {
      faena_id: faenaId ? parseInt(faenaId) : null,
      nombre: file.name,
      data
    });

    if (!r.ok) {
      toast(r.error || "No se pudo procesar el ticket", true);
      return;
    }

    const ticket = r.data || {};
    ultimaRutaTicketProcesada = ticket.ruta || "";

    const resumen = [
      `Proveedor: ${ticket.proveedor || "—"}`,
      `Fecha: ${ticket.fecha || "—"}`,
      `Artículos detectados: ${(ticket.articulos || []).length}`,
      `Gastos creados: ${ticket.gastos_creados || 0}`,
      `Total estimado: ${parseFloat(ticket.total_ticket || 0).toFixed(2)} €`
    ].join("\n");
    const resumenEl = document.getElementById("ticket-ocr-resumen");
    resumenEl.textContent = resumen;
    resumenEl.style.display = "block";
    toast("✓ Ticket procesado y guardado en la faena");
  } catch (e) {
    toast("Error al procesar la imagen", true);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Procesar con IA local"; }
  }
}

function previewMatFoto(event) {
  const file = event.target.files[0];
  if (!file) return;
  const url = URL.createObjectURL(file);
  document.getElementById("mat-img").src = url;
  document.getElementById("mat-preview").style.display = "block";
  document.getElementById("prompt-mat-box").style.display = "none";
}
async function generarPromptMateriales() {
  const r = await api("GET", "/prompts/materiales");
  if (r.ok) { document.getElementById("prompt-mat-txt").textContent = r.data.prompt; document.getElementById("prompt-mat-box").style.display = "block"; const hayFoto = document.getElementById("mat-foto-input").files.length > 0; document.getElementById("mat-foto-aviso").style.display = hayFoto ? "block" : "none"; document.getElementById("prompt-mat-box").scrollIntoView({ behavior: "smooth", block: "nearest" }); }
}
  document.getElementById("json-materiales").value = "";
}

// ===== POLYBOARD =====
let pbDatos = {};
function poblarSelectPolyboard() {
  const sel = document.getElementById("pb-faena-sel");
  sel.innerHTML = '<option value="">— Sin asignar —</option>' + state.faenas.map(f => `<option value="${f.id}">${f.numero} · ${f.cliente_nombre}</option>`).join("");
}
async function cargarPolyboard() {
  const faenaId = document.getElementById("pb-faena-sel").value;
  const r = await api("POST", "/polyboard/procesar", { ruta_txt: "", faena_id: faenaId });
  if (!r.ok) { toast(r.error, true); return; }
  pbDatos = r.data.piezas;
  document.getElementById("pb-ruta").textContent = "📄 " + r.data.ruta;
  document.getElementById("pb-resultado").style.display = "block";
  renderTablaPolyboard(); toast("✓ Despiece cargado");
}
function renderTablaPolyboard() {
  const excluirSep = document.getElementById("pb-excluir-sep").checked;
  const el = document.getElementById("pb-tabla");
  if (!pbDatos || Object.keys(pbDatos).length === 0) { el.innerHTML = '<div class="empty"><div class="empty-icon">🪵</div>No hay piezas cargadas</div>'; return; }
  let html = "";
  for (const [material, piezas] of Object.entries(pbDatos)) {
    if (excluirSep && material.toLowerCase().includes("separac")) continue;
    const totalPiezas = piezas.reduce((s, p) => s + p.cantidad, 0);
    html += `<div class="pb-mat-header">📦 ${material.toUpperCase()}</div><div class="pb-resumen">${piezas.length} referencia${piezas.length !== 1 ? "s" : ""} · ${totalPiezas} pieza${totalPiezas !== 1 ? "s" : ""} en total</div><table class="pb-table"><thead><tr><th>Cant.</th><th>Largo</th><th>CD</th><th>CI</th><th>Ancho</th><th>CA</th><th>CB</th><th class="col-pieza">Pieza</th></tr></thead><tbody>`;
    piezas.forEach((p, idx) => {
      html += `<tr><td contenteditable="true" onblur="editarCampo('${material}',${idx},'cantidad',this.textContent)">${p.cantidad}</td><td contenteditable="true" onblur="editarCampo('${material}',${idx},'largo',this.textContent)">${p.largo}</td><td class="canto-cell ${p.canto_der ? 'canto-on' : ''}" onclick="toggleCanto('${material}',${idx},'canto_der',this)">${p.canto_der ? "✔" : "–"}</td><td class="canto-cell ${p.canto_izq ? 'canto-on' : ''}" onclick="toggleCanto('${material}',${idx},'canto_izq',this)">${p.canto_izq ? "✔" : "–"}</td><td contenteditable="true" onblur="editarCampo('${material}',${idx},'ancho',this.textContent)">${p.ancho}</td><td class="canto-cell ${p.canto_arr ? 'canto-on' : ''}" onclick="toggleCanto('${material}',${idx},'canto_arr',this)">${p.canto_arr ? "✔" : "–"}</td><td class="canto-cell ${p.canto_ab ? 'canto-on' : ''}" onclick="toggleCanto('${material}',${idx},'canto_ab',this)">${p.canto_ab ? "✔" : "–"}</td><td class="col-pieza" contenteditable="true" onblur="editarCampo('${material}',${idx},'pieza',this.textContent)">${p.pieza}</td></tr>`;
    });
    html += `</tbody></table>`;
  }
  el.innerHTML = html || '<div class="empty"><div class="empty-icon">🪵</div>No hay materiales para mostrar</div>';
}
function toggleCanto(material, idx, campo, celda) {
  pbDatos[material][idx][campo] = pbDatos[material][idx][campo] ? 0 : 1;
  const activo = pbDatos[material][idx][campo];
  celda.textContent = activo ? "✔" : "–";
  celda.classList.toggle("canto-on", !!activo);
}
function editarCampo(material, idx, campo, valor) {
  const v = valor.trim();
  if (campo === "pieza") pbDatos[material][idx][campo] = v;
  else { const num = parseInt(v); if (!isNaN(num)) pbDatos[material][idx][campo] = num; }
}
async function generarPdfPedido() {
  const faenaId = document.getElementById("pb-faena-sel").value || null;
  const excluirSep = document.getElementById("pb-excluir-sep").checked;
  const excluir = excluirSep ? ["Separacion", "Separación", "separacion"] : [];
  toast("Generando PDF...");
  try {
    const response = await fetch(API + "/polyboard/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ piezas: pbDatos, faena_id: faenaId, excluir_materiales: excluir })
    });
    if (!response.ok) { const err = await response.json(); toast(err.error || "Error generando PDF", true); return; }
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `pedido_tableros.pdf`; a.click(); URL.revokeObjectURL(url); toast("✓ PDF generado — revisa tus descargas");
  } catch(e) { toast("Error de conexión", true); }
}

function generarPromptBusquedaValencia() {
  const descripcion = document.getElementById("pres-ollama-input").value.trim();
  const prompt = `Necesito encontrar los siguientes materiales de carpintería en tiendas o proveedores de Valencia (España):\n\n${descripcion || "[Describe aquí los materiales que necesitas]"}\n\nPor favor:\n1. Sugiere tiendas o distribuidores de carpintería en Valencia donde pueda encontrar estos materiales\n2. Indica el nombre comercial exacto de cada producto para buscarlo\n3. Si conoces precios aproximados orientativos, inclúyelos\n4. Incluye también opciones de compra online con envío a Valencia\n\nBusca especialmente en:\n- Tiendas de herrajes para carpintería en Valencia\n- Distribuidores de materiales para ebanistería\n- Ferreterías industriales de Valencia`;
  document.getElementById("pres-valencia-txt").textContent = prompt; document.getElementById("pres-valencia-box").style.display = "block"; document.getElementById("pres-valencia-box").scrollIntoView({ behavior: "smooth", block: "nearest" });
}
let presState = { materiales: [], manoObra: [] };
function poblarSelectPresupuesto() {
  const sel = document.getElementById("pres-faena-sel"); sel.innerHTML = '<option value="">— Selecciona una faena —</option>' + state.faenas.map(f => `<option value="${f.id}">${f.numero} · ${f.cliente_nombre}</option>`).join("");
}
async function cargarPresupuesto() {
  const id = document.getElementById("pres-faena-sel").value; if (!id) return;
  const r = await api("GET", `/faenas/${id}/presupuesto`);
  if (r.ok && r.data.contenido) parsearTxtPresupuesto(r.data.contenido);
  else { presState.materiales = []; presState.manoObra = []; renderTablasManoObra(); renderTablasMateriales(); actualizarTotales(); }
}
function parsearTxtPresupuesto(txt) {
  presState.materiales = []; presState.manoObra = []; const lineas = txt.split("\n"); let seccion = null;
  for (const linea of lineas) {
    if (linea.startsWith("MATERIALES")) { seccion = "mat"; continue; }
    if (linea.startsWith("MANO DE OBRA")) { seccion = "mo"; continue; }
    if (linea.startsWith("=") || linea.startsWith("-") || linea.startsWith("Subtotal") || linea.startsWith("Total") || linea.startsWith("Tarifa") || linea.trim() === "") continue;
    if (seccion === "mat") { const match = linea.match(/^(.+?)\s+([\d.]+)\s+€\s*$/); if (match) presState.materiales.push({ descripcion: match[1].trim(), cantidad: 1, precio_unitario: parseFloat(match[2]) }); }
    if (seccion === "mo") { const match = linea.match(/^(.+?)\s*\((\d+\.?\d*)(h|ud)\)\s*.+?([\d.]+)\s+€\s*$/); if (match) presState.manoObra.push({ descripcion: match[1].trim(), tipo: match[3] === "h" ? "hora" : "unidad", cantidad: parseFloat(match[2]), precio: 0 }); }
  }
  renderTablasMateriales(); renderTablasManoObra(); actualizarTotales();
}
function renderTablasMateriales() {
  const tbody = document.getElementById("tbody-materiales");
  if (!presState.materiales.length) { tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#aaa;padding:16px;font-size:0.8rem">Sin materiales — pulsa + Añadir</td></tr>`; return; }
  tbody.innerHTML = presState.materiales.map((m, i) => { const total = (parseFloat(m.cantidad) || 0) * (parseFloat(m.precio_unitario) || 0); return `<tr><td><input style="border:none;background:transparent;width:100%;font-size:0.8rem" value="${m.descripcion}" onchange="presState.materiales[${i}].descripcion=this.value"></td><td><input type="number" style="border:none;background:transparent;width:60px;text-align:center;font-size:0.8rem" value="${m.cantidad}" step="0.01" onchange="presState.materiales[${i}].cantidad=parseFloat(this.value)||0;actualizarTotales()"></td><td><input type="number" style="border:none;background:transparent;width:80px;text-align:center;font-size:0.8rem" value="${m.precio_unitario}" step="0.01" onchange="presState.materiales[${i}].precio_unitario=parseFloat(this.value)||0;actualizarTotales()"></td><td style="text-align:right;font-weight:500">${total.toFixed(2)} €</td><td><button class="btn btn-d btn-sm" onclick="eliminarMaterial(${i})">×</button></td></tr>`; }).join("");
}
function renderTablasManoObra() {
  const tarifa = parseFloat(document.getElementById("pres-tarifa").value) || 0;
  const tbody = document.getElementById("tbody-mo");
  if (!presState.manoObra.length) { tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#aaa;padding:16px;font-size:0.8rem">Sin mano de obra — pulsa + Añadir</td></tr>`; return; }
  tbody.innerHTML = presState.manoObra.map((l, i) => { const precio = l.tipo === "hora" ? tarifa : (parseFloat(l.precio) || 0); const total = (parseFloat(l.cantidad) || 0) * precio; return `<tr><td><input style="border:none;background:transparent;width:100%;font-size:0.8rem" value="${l.descripcion}" onchange="presState.manoObra[${i}].descripcion=this.value"></td><td><select style="border:none;background:transparent;font-size:0.78rem;font-family:'DM Mono',monospace" onchange="presState.manoObra[${i}].tipo=this.value;renderTablasManoObra();actualizarTotales()"><option value="hora" ${l.tipo==="hora"?"selected":""}>Por hora</option><option value="unidad" ${l.tipo==="unidad"?"selected":""}>Por unidad</option></select></td><td><input type="number" style="border:none;background:transparent;width:60px;text-align:center;font-size:0.8rem" value="${l.cantidad}" step="0.5" onchange="presState.manoObra[${i}].cantidad=parseFloat(this.value)||0;actualizarTotales()"></td><td>${l.tipo === "hora" ? `<span style="font-size:0.78rem;color:var(--accent)">${tarifa.toFixed(2)} €/h</span>` : `<input type="number" style="border:none;background:transparent;width:70px;text-align:center;font-size:0.8rem" value="${l.precio||0}" step="0.5" onchange="presState.manoObra[${i}].precio=parseFloat(this.value)||0;actualizarTotales()">`}</td><td style="text-align:right;font-weight:500">${total.toFixed(2)} €</td><td><button class="btn btn-d btn-sm" onclick="eliminarManoObra(${i})">×</button></td></tr>`; }).join("");
}
function actualizarTotales() {
  renderTablasMateriales(); renderTablasManoObra();
  const tarifa = parseFloat(document.getElementById("pres-tarifa").value) || 0;
  const totalMat = presState.materiales.reduce((s, m) => s + (parseFloat(m.cantidad)||0) * (parseFloat(m.precio_unitario)||0), 0);
  const totalMO = presState.manoObra.reduce((s, l) => { const precio = l.tipo === "hora" ? tarifa : (parseFloat(l.precio)||0); return s + (parseFloat(l.cantidad)||0) * precio; }, 0);
  document.getElementById("subtotal-mat").textContent = totalMat.toFixed(2) + " €";
  document.getElementById("subtotal-mo").textContent  = totalMO.toFixed(2) + " €";
  document.getElementById("total-faena").textContent  = (totalMat + totalMO).toFixed(2) + " €";
}
function añadirMaterial() { presState.materiales.push({ descripcion: "Nuevo material", cantidad: 1, precio_unitario: 0 }); renderTablasMateriales(); actualizarTotales(); }
function eliminarMaterial(i) { presState.materiales.splice(i, 1); renderTablasMateriales(); actualizarTotales(); }
function añadirManoObra() { presState.manoObra.push({ descripcion: "Nueva partida", tipo: "hora", cantidad: 1, precio: 0 }); renderTablasManoObra(); actualizarTotales(); }
function eliminarManoObra(i) { presState.manoObra.splice(i, 1); renderTablasManoObra(); actualizarTotales(); }
async function guardarPresupuesto() {
  const id = document.getElementById("pres-faena-sel").value; if (!id) { toast("Selecciona una faena primero", true); return; }
  const tarifa = parseFloat(document.getElementById("pres-tarifa").value) || 0;
  const moConPrecio = presState.manoObra.map(l => ({ ...l, precio: l.tipo === "hora" ? tarifa : (parseFloat(l.precio) || 0) }));
  const r = await api("POST", `/faenas/${id}/presupuesto`, { tarifa_hora: tarifa, materiales: presState.materiales, mano_obra: moConPrecio });
  if (r.ok) {
    toast(`✓ Presupuesto guardado · Total: ${r.data.total.toFixed(2)} €`);
    await cargarFaenas();
    renderFaenas();
  }
  else toast(r.error, true);
}
async function abrirPresupuestoEnCursor() {
  const id = document.getElementById("pres-faena-sel").value; if (!id) { toast("Selecciona una faena primero", true); return; }
  const faena = state.faenas.find(f => f.id === parseInt(id)); if (!faena) return;
  const r = await api("POST", "/cursor/abrir", { carpeta: faena.carpeta }); if (!r.ok) toast(r.error, true);
}
function abrirModalMateriales() { renderConsultaMat(); abrirModal("m-consulta-mat"); }
function renderConsultaMat() {
  const q = (document.getElementById("q-consulta-mat")?.value || "").toLowerCase();
  const lista = state.materiales.filter(m => !q || m.nombre.toLowerCase().includes(q) || (m.categoria||"").toLowerCase().includes(q));
  const el = document.getElementById("consulta-mat-lista");
  if (!lista.length) { el.innerHTML = '<div class="empty" style="padding:20px">Sin resultados</div>'; return; }
  el.innerHTML = lista.map(m => { const precios = [...(m.precios||[])].sort((a,b) => a.precio_unitario - b.precio_unitario); return `<div style="padding:10px 0;border-bottom:1px solid var(--sawdust)"><div style="display:flex;justify-content:space-between;align-items:center"><strong style="font-size:0.85rem">${m.nombre}</strong><span style="font-size:0.72rem;color:#aaa">${m.unidad} · ${m.categoria}</span></div><div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:8px">${precios.map((p, i) => `<span style="font-size:0.78rem;${i===0?"color:var(--green);font-weight:500":"color:#666"}">${p.proveedor}: ${parseFloat(p.precio_unitario).toFixed(2)}€<button class="btn btn-s btn-sm" style="padding:2px 6px;font-size:0.65rem;margin-left:4px" onclick="usarPrecioEnPresupuesto('${m.nombre.replace(/'/g,"\\'")}',${p.precio_unitario})">Usar</button></span>`).join("")}</div></div>`; }).join("");
}
function usarPrecioEnPresupuesto(nombre, precio) { presState.materiales.push({ descripcion: nombre, cantidad: 1, precio_unitario: precio }); renderTablasMateriales(); actualizarTotales(); cerrarModal("m-consulta-mat"); toast(`✓ ${nombre} añadido al presupuesto`); }

function abrirPresupuestoItem(faenaId, itemId = null) {
  document.getElementById("presupuesto-faena-id").value = faenaId;
  document.getElementById("presupuesto-item-id").value = itemId || "";
  const item = itemId ? (state.detalleActual.presupuesto || []).find(p => String(p.id) === String(itemId)) : null;
  document.getElementById("presupuesto-item-title").textContent = item ? "✏️ Editar Partida de Presupuesto" : "📋 Nueva Partida de Presupuesto";
  document.getElementById("presupuesto-desc").value = item?.descripcion || "";
  document.getElementById("presupuesto-tipo").value = item?.tipo || "material";
  document.getElementById("presupuesto-cant").value = item?.cantidad ?? 1;
  document.getElementById("presupuesto-precio").value = item?.precio_unitario ?? 0;
  cerrarModal("m-detalle");
  abrirModal("m-presupuesto-item");
}
async function guardarPresupuestoItem() {
  const faenaId = document.getElementById("presupuesto-faena-id").value;
  const itemId = document.getElementById("presupuesto-item-id").value;
  const payload = {
    tipo: document.getElementById("presupuesto-tipo").value,
    descripcion: document.getElementById("presupuesto-desc").value,
    cantidad: parseFloat(document.getElementById("presupuesto-cant").value) || 1,
    precio_unitario: parseFloat(document.getElementById("presupuesto-precio").value) || 0
  };
  const r = itemId
    ? await api("PUT", `/presupuestos/${itemId}`, payload)
    : await api("POST", `/faenas/${faenaId}/presupuesto/item`, payload);
  if (r.ok) {
    toast(itemId ? `✓ Partida actualizada: ${r.data.total.toFixed(2)} €` : `✓ Partida añadida: ${r.data.total.toFixed(2)} €`);
    cerrarModal("m-presupuesto-item");
    await cargarFaenas();
    renderFaenas();
    await verDetalle(parseInt(faenaId));
  } else toast(r.error, true);
}
async function eliminarPresupuestoItem(itemId, faenaId) {
  if (!confirm("¿Eliminar esta partida de presupuesto?")) return;
  const r = await api("DELETE", `/presupuestos/${itemId}`);
  if (r.ok) {
    await cargarFaenas();
    renderFaenas();
    verDetalle(faenaId);
  }
  else toast(r.error, true);
}

// ===== BOOK DE FOTOS =====
let bookState = { fotosDisponibles: [], fotoSeleccionada: null };
async function renderBook() {
  const r = await api("GET", "/book");
  if (!r.ok) return;
  const fotos = r.data;
  const el = document.getElementById("book-galeria");
  if (!fotos.length) { el.innerHTML = `<div class="empty"><div class="empty-icon">📸</div>No hay fotos en el book aún.<br><small>Añade las mejores fotos de tus faenas</small></div>`; return; }
  el.innerHTML = `<div class="book-grid">${fotos.map(f => `<div class="book-card"><img src="${f.data}" alt="${f.titulo || f.tipo_trabajo || ""}" loading="lazy"><div class="book-card-info"><div class="book-card-titulo">${f.titulo || f.tipo_trabajo || "Sin título"}</div><div class="book-card-meta">${f.faena_numero} · ${f.cliente_nombre || "—"}</div>${f.descripcion ? `<div class="book-card-desc">${f.descripcion}</div>` : ""}<div class="btn-row"><button class="btn btn-d btn-sm" onclick="eliminarDeBook(${f.id})">Quitar</button></div></div></div>`).join("")}</div>`;
}
function abrirModalAñadirBook() {
  const sel = document.getElementById("book-faena-sel"); sel.innerHTML = '<option value="">— Selecciona una faena —</option>' + state.faenas.map(f => `<option value="${f.id}">${f.numero} · ${f.cliente_nombre}</option>`).join("");
  document.getElementById("book-fotos-sel").innerHTML = ""; document.getElementById("book-form-datos").style.display = "none"; document.getElementById("book-form-desc").style.display = "none"; document.getElementById("book-btn-guardar").style.display = "none"; document.getElementById("book-btn-cancelar").style.display = "flex"; bookState.fotoSeleccionada = null; abrirModal("m-book-añadir");
}
async function cargarFotosParaBook() {
  const faenaId = document.getElementById("book-faena-sel").value; if (!faenaId) return;
  const el = document.getElementById("book-fotos-sel"); el.innerHTML = '<div style="font-size:0.8rem;color:#aaa;padding:8px">Cargando fotos...</div>';
  const r = await api("GET", `/book/fotos-faena/${faenaId}`); if (!r.ok || !r.data.length) { el.innerHTML = '<div style="font-size:0.8rem;color:#aaa;padding:8px">No hay fotos en esta faena</div>'; return; }
  bookState.fotosDisponibles = r.data;
  el.innerHTML = `<div style="font-size:0.78rem;color:#666;margin-bottom:8px">Toca una foto para seleccionarla:</div><div class="foto-sel-grid">${r.data.map((f, i) => `<div class="foto-sel-item" id="foto-sel-${i}" onclick="seleccionarFotoBook(${i})"><img src="${f.data}" alt="${f.nombre}" loading="lazy"><div class="check">✓</div></div>`).join("")}</div>`;
}
function seleccionarFotoBook(idx) {
  document.querySelectorAll(".foto-sel-item").forEach(el => el.classList.remove("selected")); document.getElementById(`foto-sel-${idx}`).classList.add("selected"); bookState.fotoSeleccionada = idx;
  document.getElementById("book-form-datos").style.display = "block"; document.getElementById("book-form-desc").style.display = "block"; document.getElementById("book-btn-guardar").style.display = "flex"; document.getElementById("book-btn-cancelar").style.display = "none";
}
async function guardarEnBook() {
  const faenaId = document.getElementById("book-faena-sel").value; if (!faenaId || bookState.fotoSeleccionada === null) { toast("Selecciona una foto", true); return; }
  const foto = bookState.fotosDisponibles[bookState.fotoSeleccionada];
  const r = await api("POST", "/book", { faena_id: parseInt(faenaId), ruta_foto: foto.ruta, titulo: document.getElementById("book-titulo").value, descripcion: document.getElementById("book-desc").value });
  if (r.ok) { toast("✓ Foto añadida al book"); cerrarModal("m-book-añadir"); document.getElementById("book-titulo").value = ""; document.getElementById("book-desc").value = ""; renderBook(); } else { toast(r.error, true); }
}
async function eliminarDeBook(id) { if (!confirm("¿Quitar esta foto del book?")) return; const r = await api("DELETE", `/book/${id}`); if (r.ok) { toast("Foto eliminada del book"); renderBook(); } }

// ===== ASISTENTE OLLAMA =====
let chatHistorial = [];
async function verificarOllama() {
  const el = document.getElementById("ollama-estado"); if (!el) return;
  try { const r = await api("GET", "/ollama/estado"); if (r.ok && r.data.disponible) { el.textContent = "● Ollama activo"; el.style.background = "#d4edda"; el.style.color = "var(--green)"; } else { el.textContent = "● Ollama inactivo"; el.style.background = "#fde8e8"; el.style.color = "var(--red)"; } } catch(e) { el.textContent = "● Sin conexión"; el.style.background = "#fde8e8"; el.style.color = "var(--red)"; }
}
function poblarSelectAsistente() {
  const sel = document.getElementById("asistente-faena-sel"); if (!sel) return; sel.innerHTML = '<option value="">— Todo el negocio —</option>' + state.faenas.map(f => `<option value="${f.id}">${f.numero} · ${f.cliente_nombre} · ${f.tipo_trabajo||"—"}</option>`).join("");
}
function añadirMensaje(texto, tipo) {
  const contenedor = document.getElementById("chat-mensajes"); const hora = new Date().toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }); const div = document.createElement("div"); div.className = `chat-msg ${tipo}`; div.innerHTML = `<div class="chat-burbuja">${texto}</div><div class="chat-hora">${hora}</div>`; const inicial = contenedor.querySelector("[style*='color:#ccc']"); if (inicial) inicial.remove(); contenedor.appendChild(div); contenedor.scrollTop = contenedor.scrollHeight; return div;
}
function mostrarTyping() { const contenedor = document.getElementById("chat-mensajes"); const div = document.createElement("div"); div.className = "chat-msg asistente"; div.id = "typing-indicator"; div.innerHTML = `<div class="chat-typing"><span></span><span></span><span></span></div>`; contenedor.appendChild(div); contenedor.scrollTop = contenedor.scrollHeight; }
function quitarTyping() { const el = document.getElementById("typing-indicator"); if (el) el.remove(); }
async function enviarConsulta() {
  const input = document.getElementById("chat-input"); const pregunta = input.value.trim(); if (!pregunta) return;
  const faenaId = document.getElementById("asistente-faena-sel")?.value || null; const btn = document.getElementById("btn-consulta");
  añadirMensaje(pregunta, "usuario"); input.value = ""; btn.disabled = true; btn.textContent = "..."; mostrarTyping();
  try {
    const r = await fetch(API + "/ollama/consulta", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pregunta, faena_id: faenaId ? parseInt(faenaId) : null }) });
    quitarTyping(); const data = await r.json();
    if (data.ok) añadirMensaje(data.data.respuesta, "asistente"); else añadirMensaje("⚠️ " + (data.error || "Error al consultar Ollama"), "asistente");
  } catch(e) { quitarTyping(); añadirMensaje("⚠️ No se pudo conectar con el asistente. ¿Está Ollama arrancado?", "asistente"); }
  btn.disabled = false; btn.textContent = "Enviar";
}
function usarSugerencia(texto) { document.getElementById("chat-input").value = texto; document.getElementById("chat-input").focus(); }
function limpiarChat() { const contenedor = document.getElementById("chat-mensajes"); contenedor.innerHTML = `<div style="text-align:center;color:#ccc;font-size:0.82rem;padding:20px 0">🪵 Pregúntame lo que quieras sobre tus faenas</div>`; chatHistorial = []; }

 init();
