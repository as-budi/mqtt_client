/*
 * Simulasi kamera ESP32-CAM (tahap M11, docs/tahap-m11-simulasi-kamera.md).
 *
 * Meniru template firmware/esp32cam_mqtt di IoT Platform:
 *   - command "capture"      -> potret -> unggah (X-Source: command, X-Command-Id) -> jawab
 *                               {"success": true, "snapshot": <id>, "size": <byte>}
 *   - desired snapshot_interval / framesize / quality / flash -> dipakai dan dilaporkan balik
 *   - snapshot berkala (X-Source: periodic) dan tombol "Capture & upload now" (X-Source: device)
 *
 * Gambar dibuat di browser (<canvas>): test pattern, file gambar pilihan pengguna, atau webcam.
 * Gambar TIDAK lewat MQTT: dikirim ke server aplikasi ini (POST /connections/<pk>/snapshot/,
 * connections/snapshot.py), yang meneruskannya ke POST /api/v1/<token>/snapshot di platform.
 *
 * session.js memanggil: CameraSim.init(host), .attach(deviceInfo, deviceTopics),
 * .handles(method), .capture(id, responseTopic), .desired(data, reportBack).
 */
window.CameraSim = (function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  // framesize esp32-camera (framesize_t): nomor -> [lebar, tinggi, nama]. Firmware membatasi 1..13.
  const FRAMES = {
    1: [160, 120, "QQVGA"], 2: [176, 144, "QCIF"], 3: [240, 176, "HQVGA"], 4: [240, 240, "240X240"],
    5: [320, 240, "QVGA"], 6: [400, 296, "CIF"], 7: [480, 320, "HVGA"], 8: [640, 480, "VGA"],
    9: [800, 600, "SVGA"], 10: [1024, 768, "XGA"], 11: [1280, 720, "HD"], 12: [1280, 1024, "SXGA"],
    13: [1600, 1200, "UXGA"],
  };
  // Batas platform bawaan (CAMERA_MAX_SNAPSHOT_KB = 512); kualitas diturunkan sampai muat.
  const TARGET_BYTES = 500 * 1024;
  const TOO_LARGE_BYTES = 600 * 1024;     // Fault "Too large": sengaja melewati batas platform
  const HISTORY = 5;

  let host = null;
  let deviceInfo = null;
  const settings = { interval: 0, framesize: 8, quality: 12, flash: false };
  let counter = 0;
  let lastCaptureId = "";      // command QoS 1 bisa datang dua kali: potret sekali saja
  let lastPeriodic = 0;
  let busy = false;
  let files = [];
  let fileIndex = 0;
  let stream = null;
  let starting = null;          // Promise getUserMedia yang sedang berjalan
  let webcamError = "";         // alasan webcam tidak bisa dipakai (ditampilkan saat memotret)
  const history = [];

  // ------------------------------------------------------------------ antarmuka
  function enabled() { return Boolean($("camera-sim")) && $("camera-sim").checked; }

  function init(hostApi) {
    host = hostApi;
    if (!$("camera-sim")) return;
    $("camera-sim").addEventListener("change", () => { refreshPanel(); syncWebcam(); });
    $("camera-source").addEventListener("change", () => { refreshPanel(); syncWebcam(); });
    $("camera-files").addEventListener("change", (event) => {
      files = [...event.target.files].filter((f) => f.type.startsWith("image/"));
      fileIndex = 0;
      $("camera-files-info").textContent = files.length ? `${files.length} image(s), used in turn.` : "";
    });
    $("camera-interval").addEventListener("change", () => {
      settings.interval = clampInterval($("camera-interval").value);
      $("camera-interval").value = settings.interval;
      lastPeriodic = Date.now();
    });
    $("camera-now").addEventListener("click", () => run("device", ""));
    setInterval(tick, 1000);
    refreshPanel();
    syncWebcam();     // browser bisa memulihkan pilihan "Webcam" setelah reload (tanpa event change)
  }

  function attach(info, topics) {
    const first = deviceInfo === null;
    deviceInfo = info;
    const box = $("camera-box");
    if (!box) return;
    box.classList.toggle("d-none", !topics);
    // Board ESP32-CAM di platform: simulasi kamera langsung aktif (sekali, saat connect pertama).
    if (first && info && info.board === "esp32cam" && !enabled()) {
      $("camera-sim").checked = true;
      refreshPanel();
      syncWebcam();
    }
  }

  function refreshPanel() {
    if (!$("camera-sim")) return;
    const on = enabled();
    $("camera-options").classList.toggle("d-none", !on);
    $("camera-badge").classList.toggle("d-none", !on);     // terlihat juga saat kartu dilipat
    const source = $("camera-source").value;
    $("camera-files-row").classList.toggle("d-none", source !== "files");
    $("camera-video").classList.toggle("d-none", !(on && source === "webcam"));
    $("camera-settings").textContent = describeSettings();
  }

  function describeSettings() {
    const [w, h, name] = FRAMES[settings.framesize] || FRAMES[8];
    return `framesize ${settings.framesize} (${name} ${w}×${h}) · quality ${settings.quality}` +
      (settings.flash ? " · flash on" : "");
  }

  function clampInterval(value) {
    const n = Math.max(0, Math.round(Number(value) || 0));
    return n === 0 ? 0 : Math.max(2, n);    // platform: paling sering 1 gambar / 2 detik
  }

  // ------------------------------------------------------------------ webcam
  // Header Permissions-Policy server (nginx) bisa melarang kamera: camera=() .
  function cameraBlockedByPolicy() {
    const policy = document.permissionsPolicy || document.featurePolicy;
    try { return Boolean(policy && policy.allowsFeature && !policy.allowsFeature("camera")); } catch (e) { return false; }
  }

  function syncWebcam() {
    const want = enabled() && $("camera-source").value === "webcam";
    if (!want) { stopWebcam(); return Promise.resolve(false); }
    if (stream) return Promise.resolve(true);
    if (!starting) starting = startWebcam().finally(() => { starting = null; });
    return starting;
  }

  async function startWebcam() {
    webcamError = "";
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      webcamError = "the webcam needs HTTPS (or localhost) and a browser that supports it";
    } else if (cameraBlockedByPolicy()) {
      webcamError = "the server forbids the camera (Permissions-Policy camera=()); update the nginx configuration of this app";
    }
    if (webcamError) { setStatus(`Webcam: ${webcamError}.`, "danger"); return false; }
    setStatus("Starting the webcam… allow the camera when the browser asks.", "muted");
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 } }, audio: false });
      const video = $("camera-video");
      video.srcObject = stream;
      await video.play();
      // Ukuran gambar baru diketahui setelah bingkai pertama.
      for (let i = 0; i < 30 && !video.videoWidth; i += 1) await new Promise((r) => setTimeout(r, 100));
      if (!video.videoWidth) throw new Error("no picture from the camera");
      setStatus("Webcam on. It stays on while this option is selected.", "muted");
      return true;
    } catch (err) {
      stopWebcam();
      const reasons = {
        NotAllowedError: "access was refused (allow the camera for this site in the browser's address bar)",
        NotFoundError: "no camera found",
        NotReadableError: "the camera is in use by another application",
      };
      webcamError = reasons[err.name] || err.message || err.name;
      setStatus(`Webcam: ${webcamError}.`, "danger");
      return false;
    }
  }

  function stopWebcam() {
    if (!stream) return;
    stream.getTracks().forEach((t) => t.stop());
    stream = null;
    if ($("camera-video")) $("camera-video").srcObject = null;
  }

  // ------------------------------------------------------------------ membuat gambar
  function canvasFor() {
    const [w, h] = FRAMES[settings.framesize] || FRAMES[8];
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    return canvas;
  }

  function drawPattern(ctx, w, h, label) {
    const hue = (counter * 37) % 360;
    const gradient = ctx.createLinearGradient(0, 0, w, h);
    gradient.addColorStop(0, `hsl(${hue}, 55%, 35%)`);
    gradient.addColorStop(1, `hsl(${(hue + 60) % 360}, 55%, 20%)`);
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, w, h);
    // Kotak-kotak: memudahkan melihat ukuran dan kompresi.
    const step = Math.max(16, Math.round(w / 16));
    ctx.fillStyle = "rgba(255,255,255,0.06)";
    for (let y = 0; y < h; y += step) {
      for (let x = (y / step) % 2 ? step : 0; x < w; x += step * 2) ctx.fillRect(x, y, step, step);
    }
    // Pita warna di bawah (seperti kartu uji).
    const bars = ["#fff", "#ff0", "#0ff", "#0f0", "#f0f", "#f00", "#00f", "#000"];
    const barH = Math.round(h * 0.12);
    bars.forEach((color, i) => {
      ctx.fillStyle = color;
      ctx.fillRect(Math.round((i * w) / bars.length), h - barH, Math.ceil(w / bars.length), barH);
    });
    const big = Math.max(12, Math.round(h / 8));
    ctx.fillStyle = "#fff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `600 ${big}px system-ui, sans-serif`;
    ctx.fillText(new Date().toLocaleTimeString(), w / 2, h * 0.38);
    ctx.font = `${Math.round(big * 0.42)}px system-ui, sans-serif`;
    ctx.fillText((deviceInfo && deviceInfo.name) || "Device", w / 2, h * 0.38 + big * 0.95);
    ctx.fillText(label, w / 2, h * 0.38 + big * 1.5);
  }

  function drawCover(ctx, source, sw, sh, w, h) {
    const scale = Math.max(w / sw, h / sh);
    const dw = sw * scale;
    const dh = sh * scale;
    ctx.drawImage(source, (w - dw) / 2, (h - dh) / 2, dw, dh);
  }

  function stamp(ctx, w, h, label) {
    const size = Math.max(10, Math.round(h / 24));
    ctx.font = `${size}px ui-monospace, monospace`;
    const text = `${new Date().toLocaleString()} · ${label}`;
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(0, h - size * 1.8, w, size * 1.8);
    ctx.fillStyle = "#fff";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(text, size * 0.6, h - size * 0.9);
  }

  async function drawFrame(canvas, label) {
    const ctx = canvas.getContext("2d");
    const { width: w, height: h } = canvas;
    const source = $("camera-source").value;
    if (source === "webcam") {
      const video = $("camera-video");
      if (!stream || !video.videoWidth) await syncWebcam();     // belum dinyalakan: coba sekarang
      if (!stream || !video.videoWidth) throw new Error(`Webcam not ready: ${webcamError || "still starting"}`);
      drawCover(ctx, video, video.videoWidth, video.videoHeight, w, h);
      stamp(ctx, w, h, label);
    } else if (source === "files") {
      if (!files.length) throw new Error("No image chosen");
      const file = files[fileIndex % files.length];
      fileIndex += 1;
      const bitmap = await createImageBitmap(file);
      drawCover(ctx, bitmap, bitmap.width, bitmap.height, w, h);
      bitmap.close();
      stamp(ctx, w, h, label);
    } else {
      drawPattern(ctx, w, h, label);
    }
    if (settings.flash) {                       // LED flash: gambar lebih terang
      ctx.fillStyle = "rgba(255,255,240,0.25)";
      ctx.fillRect(0, 0, w, h);
    }
  }

  const toBlob = (canvas, type, quality) => new Promise((resolve) => canvas.toBlob(resolve, type, quality));

  // quality esp32-camera 10 (terbaik) .. 63 (terkecil) -> kualitas JPEG browser 0,95 .. 0,30.
  function jpegQuality() {
    return 0.95 - ((settings.quality - 10) * 0.65) / 53;
  }

  async function encode(canvas, fault) {
    if (fault === "not_jpeg") return toBlob(canvas, "image/png");
    let quality = jpegQuality();
    let blob = await toBlob(canvas, "image/jpeg", quality);
    if (fault === "too_large") {
      // Tambahkan byte kosong setelah gambar: tetap JPEG, tetapi lebih besar dari batas platform.
      const padding = new Uint8Array(Math.max(0, TOO_LARGE_BYTES - blob.size));
      return new Blob([blob, padding], { type: "image/jpeg" });
    }
    // Seperti memilih framesize/quality yang lebih kecil di ESP32-CAM bila gambar terlalu besar.
    while (blob.size > TARGET_BYTES && quality > 0.25) {
      quality -= 0.1;
      blob = await toBlob(canvas, "image/jpeg", quality);
    }
    return blob;
  }

  const readDataUrl = (blob) => new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(blob);
  });

  // ------------------------------------------------------------------ unggah + jawab
  async function upload(blob, source, commandId) {
    const headers = { "X-CSRFToken": host.csrfToken, "Content-Type": blob.type, "X-Source": source };
    if (commandId) headers["X-Command-Id"] = commandId;
    let response;
    try {
      response = await fetch(host.urls.snapshot, { method: "POST", headers, body: blob, credentials: "same-origin" });
    } catch (err) {
      return { status: 0, data: { error: "No connection to this app's server" } };
    }
    let data = {};
    try { data = await response.json(); } catch (e) { /* bukan JSON */ }
    return { status: response.status, data };
  }

  // Satu kali potret. source: command | periodic | device. Mengembalikan jawaban untuk command.
  async function run(source, commandId) {
    if (busy) return { success: false, error: "Camera busy" };
    busy = true;
    counter += 1;
    const fault = $("camera-fault").value;
    const label = commandId ? `command #${commandId}` : source;
    try {
      await new Promise((r) => setTimeout(r, 300 + Math.random() * 700));   // waktu memotret
      if (fault === "camera_error") {
        record(label, null, "Camera error (simulated): nothing uploaded", false);
        return { success: false, error: "Capture failed" };
      }
      const canvas = canvasFor();
      try {
        await drawFrame(canvas, `SIMULATED · ${label}`);
      } catch (err) {
        record(label, null, err.message, false);
        return { success: false, error: `Capture failed: ${err.message}` };
      }
      const blob = await encode(canvas, fault);
      const preview = await readDataUrl(blob);
      const { status, data } = await upload(blob, source, commandId);
      const size = `${canvas.width}×${canvas.height} · ${Math.round(blob.size / 1024)} KB`;
      if (status === 201) {
        record(label, preview, `${size} → 201 snapshot #${data.id}`, true);
        if (source !== "command") lastPeriodic = Date.now();
        return { success: true, snapshot: data.id, size: data.size };
      }
      if (status === 401 && data.signin) record(label, preview, "Sign in to IoT Platform again", false);
      else record(label, preview, `${size} → HTTP ${status || "—"} ${data.error || ""}`, false);
      return { success: false, error: `Upload failed: HTTP ${status}` + (data.error ? ` ${data.error}` : "") };
    } finally {
      busy = false;
    }
  }

  function handles(method) { return method === "capture" && enabled(); }

  async function capture(id, responseTopic) {
    if (id === lastCaptureId) return;            // pesan ganda (QoS 1)
    lastCaptureId = id;
    const result = await run("command", id);
    if ($("camera-fault").value === "no_answer") {
      setStatus(`Command #${id}: not answered (Fault “No answer”).`, "warning");
      return;
    }
    host.publish(responseTopic, result);
  }

  // Desired state: kunci kamera dipakai; reportBack = laporkan balik sebagai telemetri (seperti firmware).
  function desired(data, reportBack) {
    if (!enabled()) return;
    const report = {};
    const has = (key) => data[key] !== undefined && data[key] !== null && !Number.isNaN(Number(data[key]));
    if (has("snapshot_interval")) {
      settings.interval = clampInterval(data.snapshot_interval);
      $("camera-interval").value = settings.interval;
      lastPeriodic = Date.now();
      report.snapshot_interval = settings.interval;
    }
    if (has("framesize")) {
      settings.framesize = Math.min(13, Math.max(1, Math.round(Number(data.framesize))));
      report.framesize = settings.framesize;
    }
    if (has("quality")) {
      settings.quality = Math.min(63, Math.max(10, Math.round(Number(data.quality))));
      report.quality = settings.quality;
    }
    if (has("flash")) {
      settings.flash = Number(data.flash) >= 0.5;
      report.flash = settings.flash ? 1 : 0;
    }
    refreshPanel();
    if (reportBack && Object.keys(report).length) host.report(report);
  }

  function tick() {
    if (!enabled() || !settings.interval || busy || !host.connected()) return;
    if (Date.now() - lastPeriodic >= settings.interval * 1000) {
      lastPeriodic = Date.now();
      run("periodic", "");
    }
  }

  // ------------------------------------------------------------------ catatan
  function setStatus(text, tone) {
    const el = $("camera-status");
    el.className = `small text-${tone || "muted"}`;
    el.textContent = text;
  }

  function record(label, preview, text, ok) {
    const time = new Date().toLocaleTimeString();
    if (preview) {
      $("camera-preview").src = preview;
      $("camera-preview").classList.remove("d-none");
    }
    setStatus(`${time} · ${label} · ${text}`, ok ? "success" : "danger");
    history.unshift(`${time} · ${label} · ${text}`);
    history.length = Math.min(history.length, HISTORY);
    const list = $("camera-history");
    list.textContent = "";
    for (const line of history.slice(1)) {
      const li = document.createElement("li");
      li.textContent = line;
      list.append(li);
    }
  }

  return { init, attach, handles, capture, desired, enabled, settings, FRAMES };
})();
