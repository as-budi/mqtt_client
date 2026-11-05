/*
 * Editor payload JSON di kartu Publish (tahap M9).
 *
 * Saat format "JSON" dipilih, textarea payload tampil seperti code editor:
 *   - nomor baris di kiri (ikut menggulir), baris error ditandai merah,
 *   - warna key/string/angka/literal sama dengan penampil JSON (json_viewer.js),
 *   - placeholder {{...}} diberi warna sendiri (juga di dalam string),
 *   - Tab menyisipkan 2 spasi, Enter mempertahankan indentasi baris sebelumnya,
 *   - tab Preview: penampil JSON berlipat (JsonViewer.create) dari payload yang
 *     placeholder-nya sudah diisi contoh.
 * Format "Text": textarea biasa seperti sebelumnya.
 *
 * Caranya sama dengan editor impor di IoT Platform: textarea tetap textarea (teksnya
 * transparan) dan di belakangnya ada <pre> berwarna dengan font dan padding yang sama.
 * Isi yang dikirim tetap textarea.value, jadi kode publish tidak berubah.
 *
 *   const editor = PayloadEditor.attach(textarea, { isJson, prepare, errorAt });
 *   editor.refresh();   // setelah value diubah lewat kode (fillPublish, Format, ...)
 */
(function () {
  "use strict";

  // Placeholder di luar string dicocokkan lebih dulu, supaya {{random:20:30}} diwarnai utuh.
  const TOKEN = /(\{\{[^{}\n]*\}\})|("(?:\\.|[^"\\\n])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b/g;
  const PLACEHOLDER = /\{\{[^{}\n]*\}\}/g;

  function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function plain(text) {
    return escapeHtml(text).replace(PLACEHOLDER, (m) => `<span class="pe-ph">${m}</span>`);
  }

  /* Teks (boleh belum sah) -> HTML berwarna. Semua teks di-escape dulu. */
  function highlight(text) {
    let html = "";
    let last = 0;
    text.replace(TOKEN, (match, ph, str, colon, num, literal, offset) => {
      html += plain(text.slice(last, offset));
      if (ph !== undefined) {
        html += `<span class="pe-ph">${escapeHtml(ph)}</span>`;
      } else if (str !== undefined) {
        html += `<span class="${colon ? "jv-key" : "jv-string"}">${plain(str)}</span>`;
        if (colon) html += escapeHtml(colon);
      } else if (num !== undefined) {
        html += `<span class="jv-number">${num}</span>`;
      } else {
        html += `<span class="jv-literal">${literal}</span>`;
      }
      last = offset + match.length;
      return match;
    });
    return html + plain(text.slice(last)) + "\n";   // "\n": baris kosong terakhir tetap punya tinggi
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function attach(textarea, options) {
    const isJson = options.isJson;                     // () -> true bila format JSON
    const prepare = options.prepare || ((t) => t);    // isi placeholder untuk Preview
    const errorAt = options.errorAt || (() => null);  // teks -> nomor baris error (atau null)

    // --- Susun elemen: bar (Edit/Preview), kotak edit (gutter + highlight + textarea), preview ---
    const bar = el("div", "pe-bar");
    const tabs = el("div", "btn-group btn-group-sm");
    const editTab = el("button", "btn btn-outline-secondary active", "Edit");
    const previewTab = el("button", "btn btn-outline-secondary", "Preview");
    [editTab, previewTab].forEach((b) => { b.type = "button"; });
    tabs.append(editTab, previewTab);
    bar.append(tabs, el("span", "pe-hint", "Preview fills placeholders with example values."));

    const box = el("div", "pe-edit");
    const gutter = el("div", "pe-gutter");
    gutter.setAttribute("aria-hidden", "true");
    const shade = el("pre", "pe-highlight");
    shade.setAttribute("aria-hidden", "true");
    textarea.parentNode.insertBefore(bar, textarea);
    textarea.parentNode.insertBefore(box, textarea);
    box.append(gutter, shade, textarea);
    const preview = el("div", "pe-preview");
    preview.hidden = true;
    box.insertAdjacentElement("afterend", preview);

    let active = false;
    let showing = "edit";

    function syncScroll() {
      shade.scrollTop = textarea.scrollTop;
      shade.scrollLeft = textarea.scrollLeft;
      gutter.scrollTop = textarea.scrollTop;
    }

    function paint() {
      const text = textarea.value;
      shade.innerHTML = highlight(text);
      const lines = text.split("\n").length;
      const bad = errorAt(text);
      let html = "";
      for (let i = 1; i <= lines; i++) html += i === bad ? `<div class="pe-error-line">${i}</div>` : `<div>${i}</div>`;
      gutter.innerHTML = html + "<div>&nbsp;</div>";
      syncScroll();
    }

    function renderPreview() {
      preview.textContent = "";
      let data;
      try { data = JSON.parse(prepare(textarea.value)); } catch (e) {
        preview.append(el("div", "pe-preview-empty", "Not valid JSON yet. Fix it in Edit to see the preview."));
        return;
      }
      if (data === null || typeof data !== "object") {
        preview.append(el("pre", "pe-preview-scalar", JSON.stringify(data)));
        return;
      }
      preview.append(window.JsonViewer.create(data));
    }

    function show(which) {
      showing = which;
      editTab.classList.toggle("active", which === "edit");
      previewTab.classList.toggle("active", which === "preview");
      box.hidden = which === "preview";
      preview.hidden = which !== "preview";
      if (which === "preview") renderPreview(); else textarea.focus();
    }

    function refresh() {
      const want = Boolean(isJson()) && Boolean(window.JsonViewer);
      if (want !== active) {
        active = want;
        box.classList.toggle("pe-active", active);
        bar.hidden = !active;
        // Tanpa pembungkusan baris supaya nomor baris selalu sejajar (gulir ke samping).
        if (active) textarea.setAttribute("wrap", "off"); else textarea.removeAttribute("wrap");
        if (!active) show("edit");
      }
      if (!active) return;
      paint();
      if (showing === "preview") renderPreview();
    }

    textarea.addEventListener("input", refresh);
    textarea.addEventListener("scroll", syncScroll);
    editTab.addEventListener("click", () => show("edit"));
    previewTab.addEventListener("click", () => show("preview"));

    // Tab = 2 spasi, Enter = baris baru dengan indentasi yang sama (+2 setelah { atau [).
    textarea.addEventListener("keydown", (event) => {
      if (!active || event.ctrlKey || event.metaKey || event.altKey) return;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const value = textarea.value;
      let insert = null;
      if (event.key === "Tab" && !event.shiftKey) {
        insert = "  ";
      } else if (event.key === "Enter" && !event.shiftKey) {
        const lineStart = value.lastIndexOf("\n", start - 1) + 1;
        const indent = value.slice(lineStart, start).match(/^\s*/)[0];
        const before = value.slice(lineStart, start).trimEnd();
        insert = "\n" + indent + (/[{[]$/.test(before) ? "  " : "");
      }
      if (insert === null) return;
      event.preventDefault();
      // setRangeText menjaga riwayat undo di kebanyakan browser lebih baik daripada mengganti value.
      textarea.setRangeText(insert, start, end, "end");
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    });

    bar.hidden = true;
    refresh();
    return { refresh, show };
  }

  window.PayloadEditor = { attach, highlight };
})();
