/*
 * Form profil koneksi:
 *   - pratinjau alamat lengkap (mis. wss://broker.emqx.io:8084/mqtt);
 *   - kolom "WebSocket path" hanya untuk ws:// dan wss://;
 *   - catatan "lewat relay" untuk mqtt:// dan mqtts://;
 *   - tombol "Add subscription" menambah baris formset Django.
 */
(function () {
  "use strict";

  const DEFAULT_PORTS = { wss: 443, ws: 80, mqtts: 8883, mqtt: 1883 };
  const scheme = document.getElementById("id_scheme");
  const host = document.getElementById("id_host");
  const port = document.getElementById("id_port");
  const path = document.getElementById("id_path");
  const pathField = document.getElementById("path-field");
  const preview = document.getElementById("url-preview");
  const relayNote = document.getElementById("relay-note");

  function update() {
    const value = scheme.value;
    const websocket = value === "ws" || value === "wss";
    pathField.classList.toggle("d-none", !websocket);
    relayNote.classList.toggle("d-none", websocket);
    port.placeholder = DEFAULT_PORTS[value];
    let text = `${value}://${host.value.trim() || "host"}:${port.value || DEFAULT_PORTS[value]}`;
    if (websocket) {
      const p = path.value.trim() || "/";
      text += p.startsWith("/") ? p : "/" + p;
    }
    preview.textContent = text;
  }
  [scheme, host, port, path].forEach((el) => el.addEventListener("input", update));
  update();

  // Formset Django: TOTAL_FORMS harus ikut bertambah, dan "__prefix__" diganti nomor baris.
  const total = document.getElementById("id_subscriptions-TOTAL_FORMS");
  const rows = document.getElementById("subscription-rows");
  const template = document.getElementById("subscription-template");
  document.getElementById("add-subscription").addEventListener("click", () => {
    const index = Number(total.value);
    rows.insertAdjacentHTML("beforeend", template.innerHTML.replace(/__prefix__/g, String(index)));
    total.value = String(index + 1);
    rows.lastElementChild.querySelector("input[type=text]").focus();
  });
})();
