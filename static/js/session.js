/*
 * Halaman koneksi MQTT (tahap M3): connect, subscribe, daftar pesan, publish.
 *
 * Protokol MQTT dijalankan pustaka mqtt.js (static/vendor/mqtt.min.js) DI BROWSER.
 * Server aplikasi hanya dimintai "bahan connect" (POST .../connect/): alamat yang dibuka
 * (broker langsung, atau relay bertiket untuk mqtt:// dan mqtts://), client ID, Last Will,
 * langganan tersimpan, dan, untuk device IoT Platform, access token device.
 *
 * Reconnect dikerjakan SENDIRI (bukan oleh mqtt.js): setiap percobaan meminta bahan connect
 * baru, karena tiket relay hanya berlaku sekali.
 *
 * Keamanan: payload pesan selalu ditampilkan dengan textContent (bukan innerHTML), jadi
 * pesan berisi <script> dari broker tidak bisa menjalankan apa pun di halaman ini.
 */
(function () {
  "use strict";

  const config = JSON.parse(document.getElementById("session-config").textContent);
  const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]").value;
  const MAX_MESSAGES = 2000;
  const RETRY_DELAYS = [1, 2, 5, 10, 20, 30];        // detik
  const $ = (id) => document.getElementById(id);

  // ---------------------------------------------------------------- penyimpanan browser
  // localStorage bisa tidak tersedia (mode privat): semua akses dibungkus try/catch.
  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
    },
    set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* abaikan */ } },
    remove(key) { try { localStorage.removeItem(key); } catch (e) { /* abaikan */ } },
  };
  const PASSWORD_KEY = `mqttc:password:${config.id}`;
  const HISTORY_KEY = `mqttc:history:${config.id}`;

  // ---------------------------------------------------------------- aturan topik MQTT
  // Sama dengan connections/validators.py.
  function topicFilterError(topic) {
    if (!topic) return "Enter a topic filter.";
    let levels = topic.split("/");
    if (levels[0] === "$share" && levels.length >= 3) levels = levels.slice(2);
    for (let i = 0; i < levels.length; i++) {
      const level = levels[i];
      if (level.includes("#") && (level !== "#" || i !== levels.length - 1)) return '"#" must be a whole level and the last one, e.g. "iot/#".';
      if (level.includes("+") && level !== "+") return '"+" must fill a whole level, e.g. "iot/+/telemetry".';
    }
    return "";
  }
  function topicNameError(topic) {
    if (!topic) return "Enter a topic.";
    if (topic.includes("+") || topic.includes("#")) return "A topic you publish to cannot contain + or #.";
    return "";
  }
  // Apakah `topic` cocok dengan `filter` ("+" = satu level, "#" = sisa level).
  function matches(filter, topic) {
    let f = filter.split("/");
    if (f[0] === "$share" && f.length >= 3) f = f.slice(2);
    const t = topic.split("/");
    // Topik berawalan $ (mis. $SYS) tidak cocok dengan wildcard di level pertama.
    if (t[0].startsWith("$") && (f[0] === "+" || f[0] === "#")) return false;
    for (let i = 0; i < f.length; i++) {
      if (f[i] === "#") return true;
      if (i >= t.length) return false;
      if (f[i] !== "+" && f[i] !== t[i]) return false;
    }
    return f.length === t.length;
  }

  // ---------------------------------------------------------------- status dan pesan error
  const STATUS = {
    disconnected: ["Disconnected", "status-disconnected"],
    connecting: ["Connecting…", "status-connecting"],
    connected: ["Connected", "status-connected"],
    reconnecting: ["Reconnecting…", "status-connecting"],
    error: ["Not connected", "status-error"],
  };
  function setStatus(name, text) {
    const [label, css] = STATUS[name];
    const el = $("status");
    el.textContent = text || label;
    el.className = `status-pill ${css}`;
    const busy = name === "connected" || name === "connecting" || name === "reconnecting";
    $("connect").classList.toggle("d-none", busy);
    $("disconnect").classList.toggle("d-none", !busy);
    $("publish").disabled = name !== "connected";
    $("clear-retained").disabled = name !== "connected";
  }
  function showAlert(text, kind) {
    const el = $("alert");
    el.textContent = text || "";
    el.className = text ? `alert alert-${kind || "danger"}` : "alert d-none";
  }

  // Arti kode penolakan CONNACK (MQTT 3.1.1: 1–5; MQTT 5: 0x80 ke atas).
  const CONNACK = {
    1: "The broker does not accept this MQTT version.", 2: "The client ID was rejected.",
    3: "The broker is unavailable.", 4: "Wrong username or password.", 5: "Not authorized.",
    0x84: "The broker does not accept this MQTT version.", 0x85: "The client ID was rejected.",
    0x86: "Wrong username or password.", 0x87: "Not authorized.", 0x88: "The broker is unavailable.",
    0x8a: "You are banned by the broker.", 0x8c: "Bad authentication method.",
  };
  const FATAL_CODES = new Set([1, 2, 4, 5, 0x84, 0x85, 0x86, 0x87, 0x8a, 0x8c]);

  // ---------------------------------------------------------------- koneksi
  let client = null;
  let wanted = false;          // pengguna ingin tersambung (bukan menekan Disconnect)
  let attempt = 0;
  let retryTimer = null;
  let deviceTopics = null;     // topik device IoT Platform (dari bahan connect)
  let deviceInfo = null;       // nama, board, versi firmware, variabel device (tahap M5)
  let sandboxInfo = null;      // {root, shared} akun sandbox platform (tahap M5)
  const subscriptions = new Map();   // topik -> {qos, color, muted, state, preset}
  // Langganan tersimpan di profil, tampil sebelum Connect. Topik device IoT Platform masih
  // berisi {prefix}/{token}; diganti topik sebenarnya pada connect pertama.
  for (const sub of config.subscriptions) subscriptions.set(sub.topic, { ...sub, state: "pending", preset: true });
  let presetsApplied = false;

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    let data = {};
    try { data = await response.json(); } catch (e) { /* bukan JSON */ }
    if (!response.ok) {
      const err = new Error(data.error || `The server answered HTTP ${response.status}.`);
      err.status = response.status;
      err.signin = data.signin;
      throw err;
    }
    return data;
  }

  function password() {
    const input = $("password");
    return input ? input.value : undefined;
  }

  async function connect() {
    clearTimeout(retryTimer);
    wanted = true;
    showAlert("");
    setStatus(attempt ? "reconnecting" : "connecting");
    let info;
    try {
      info = await postJson(config.urls.connect);
    } catch (err) {
      if (err.status === 401 && err.signin) { window.location.href = err.signin; return; }
      // 4xx = masalah pengaturan, tidak akan sembuh dengan mencoba lagi.
      if (err.status && err.status < 500 && err.status !== 429) { stop(err.message); return; }
      retry(err.message);
      return;
    }
    if (!wanted) return;     // Disconnect ditekan selagi menunggu

    deviceTopics = info.topics;
    deviceInfo = info.device;
    sandboxInfo = info.sandbox;
    showDeviceTopics();
    // Connect pertama: ganti langganan tersimpan dengan versi yang sudah diisi server
    // (status mute dari halaman ini dipertahankan). Reconnect: daftar di halaman yang berlaku.
    if (!presetsApplied) {
      const muted = [...subscriptions.values()].filter((s) => s.preset).map((s) => s.muted);
      for (const [topic, sub] of [...subscriptions]) if (sub.preset) subscriptions.delete(topic);
      info.subscriptions.forEach((sub, index) => {
        subscriptions.set(sub.topic, { ...sub, muted: muted[index] ?? sub.muted, state: "pending", preset: false });
      });
      presetsApplied = true;
    }
    renderSubscriptions();

    const remember = $("remember-password");
    if (remember && remember.checked) store.set(PASSWORD_KEY, password());
    const options = {
      clientId: info.clientId,
      username: info.username || undefined,
      password: info.password || (info.askPassword ? password() : undefined) || undefined,
      protocolVersion: info.options.protocolVersion,
      keepalive: info.options.keepalive,
      clean: info.options.clean,
      reconnectPeriod: 0,          // reconnect dikerjakan sendiri (lihat atas)
      connectTimeout: 10000,
      resubscribe: false,
    };
    if (info.options.will) options.will = { ...info.options.will };

    let connected = false;
    let lastError = "";
    const current = mqtt.connect(info.url, options);
    client = current;

    current.on("connect", () => {
      if (client !== current) return;
      connected = true;
      attempt = 0;
      setStatus("connected");
      for (const [topic, sub] of subscriptions) subscribe(topic, sub.qos);
    });
    current.on("message", (topic, payload, packet) => {
      addMessage("in", topic, payload, packet.qos, packet.retain, packet.properties);
      automate(topic, payload);
    });
    current.on("error", (err) => {
      lastError = CONNACK[err.code] || err.message || String(err);
      if (FATAL_CODES.has(err.code)) wanted = false;
    });
    current.on("close", async () => {
      if (client !== current) return;
      current.end(true);
      client = null;
      for (const sub of subscriptions.values()) sub.state = "pending";
      renderSubscriptions();
      if (!connected && info.ticketId) {
        const failure = await relayFailure(info.ticketId);
        if (failure) {
          lastError = failure.message;
          // Alamat diblokir, TLS gagal, dsb.: mencoba lagi tidak akan berhasil.
          if (failure.fatal) wanted = false;
        }
      }
      if (!connected && !lastError) {
        lastError = info.route === "relay"
          ? "The relay could not open the connection to the broker."
          : `Could not open ${info.url}. Check the address, port and path, and whether the broker accepts WebSocket connections there.`;
      }
      if (wanted) retry(lastError);
      else if (lastError) stop(lastError);
      else setStatus("disconnected");
    });
  }

  // Alasan kegagalan relay (tahap M4), mis. alamat diblokir atau TLS gagal.
  const FATAL_RELAY = new Set(["address_not_allowed", "tls_failed", "bad_request"]);
  async function relayFailure(ticketId) {
    try {
      const url = config.urls.relayStatus.replace("/0/", `/${ticketId}/`);
      const response = await fetch(url, { credentials: "same-origin" });
      const data = await response.json();
      if (data.failure) {
        return { message: data.message + (data.detail ? ` (${data.detail})` : ""), fatal: FATAL_RELAY.has(data.failure) };
      }
    } catch (e) { /* abaikan */ }
    return null;
  }

  function retry(message) {
    const delay = RETRY_DELAYS[Math.min(attempt, RETRY_DELAYS.length - 1)];
    attempt += 1;
    if (message) showAlert(`${message} Retrying in ${delay} s.`, "warning");
    setStatus("reconnecting", `Reconnecting in ${delay} s`);
    retryTimer = setTimeout(connect, delay * 1000);
  }

  function stop(message) {
    wanted = false;
    attempt = 0;
    clearTimeout(retryTimer);
    if (client) { const c = client; client = null; c.end(true); }
    setStatus(message ? "error" : "disconnected");
    if (message) showAlert(message);
  }

  $("connect-form").addEventListener("submit", (event) => { event.preventDefault(); attempt = 0; connect(); });
  $("disconnect").addEventListener("click", () => {
    wanted = false;
    clearTimeout(retryTimer);
    if (client) client.end(); else setStatus("disconnected");
    showAlert("");
  });
  window.addEventListener("beforeunload", () => { if (client) client.end(true); });

  // Password yang diingat di browser ini (bila pengguna mencentang "Remember here").
  if ($("password")) {
    const saved = store.get(PASSWORD_KEY, null);
    if (saved !== null) { $("password").value = saved; $("remember-password").checked = true; }
    $("remember-password").addEventListener("change", (event) => {
      if (event.target.checked) store.set(PASSWORD_KEY, password()); else store.remove(PASSWORD_KEY);
    });
  }

  // ---------------------------------------------------------------- langganan
  function subscribe(topic, qos) {
    const sub = subscriptions.get(topic);
    if (!client || !client.connected) return;
    sub.state = "pending";
    renderSubscriptions();
    client.subscribe(topic, { qos }, (err, granted) => {
      const result = granted && granted[0];
      // qos 128 (MQTT 3.1.1) atau reason code >= 0x80 (MQTT 5) = ditolak broker, mis. karena ACL.
      sub.state = err || !result || result.qos >= 0x80 ? "refused" : "active";
      sub.grantedQos = result ? result.qos : null;
      renderSubscriptions();
    });
  }

  function renderSubscriptions() {
    const list = $("subscriptions");
    list.textContent = "";
    if (!subscriptions.size) {
      const li = document.createElement("li");
      li.className = "text-muted";
      li.textContent = "No subscriptions.";
      list.append(li);
      return;
    }
    for (const [topic, sub] of subscriptions) {
      const li = document.createElement("li");
      li.className = `subscription color-${sub.color || "gray"}${sub.muted ? " is-muted" : ""}`;
      const dot = document.createElement("span");
      dot.className = "dot";
      const name = document.createElement("code");
      name.className = "flex-grow-1 text-break";
      name.textContent = topic;
      const qos = document.createElement("span");
      qos.className = "badge text-bg-light border";
      qos.textContent = `QoS ${sub.qos}`;
      const state = document.createElement("span");
      state.className = `sub-state sub-${sub.state}`;
      state.textContent = { pending: "…", active: "✓", refused: "refused" }[sub.state];
      state.title = { pending: "Not subscribed yet", active: "Subscribed", refused: "Not authorized for this topic" }[sub.state];
      const mute = document.createElement("button");
      mute.type = "button";
      mute.className = "btn btn-sm btn-link p-0";
      mute.textContent = sub.muted ? "show" : "mute";
      mute.title = sub.muted ? "Show messages of this subscription" : "Hide messages of this subscription";
      mute.addEventListener("click", () => { sub.muted = !sub.muted; renderSubscriptions(); renderMessages(); });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-sm btn-link text-danger p-0";
      remove.textContent = "✕";
      remove.title = "Unsubscribe";
      remove.setAttribute("aria-label", `Unsubscribe ${topic}`);
      remove.addEventListener("click", () => {
        if (client && client.connected) client.unsubscribe(topic);
        subscriptions.delete(topic);
        renderSubscriptions();
      });
      li.append(dot, name, qos, state, mute, remove);
      list.append(li);
    }
  }

  $("subscribe-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const topic = $("subscribe-topic").value.trim();
    const problem = topicFilterError(topic);
    $("subscribe-error").textContent = problem;
    if (problem) return;
    const qos = Number($("subscribe-qos").value);
    subscriptions.set(topic, { topic, qos, color: "blue", muted: false, state: "pending" });
    renderSubscriptions();
    subscribe(topic, qos);
    $("subscribe-topic").value = "";
  });

  // ---------------------------------------------------------------- daftar pesan
  let messages = [];
  let nextId = 1;
  let paused = false;
  let pending = false;
  const encoder = new TextEncoder();
  const strictDecoder = new TextDecoder("utf-8", { fatal: true });

  function subscriptionFor(topic) {
    for (const [filter, sub] of subscriptions) if (matches(filter, topic)) return sub;
    return null;
  }

  function addMessage(direction, topic, payload, qos, retain, properties) {
    const bytes = typeof payload === "string" ? encoder.encode(payload) : new Uint8Array(payload);
    const message = { id: nextId++, time: new Date(), direction, topic, bytes, qos, retain, properties };
    messages.push(message);
    track(message);
    if (messages.length > MAX_MESSAGES) messages = messages.slice(-MAX_MESSAGES);
    if (!paused) scheduleRender();
    else $("message-count").textContent = `(${messages.length}, paused)`;
  }

  // Banyak pesan per detik: digambar paling sering sekali per frame layar.
  function scheduleRender() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; renderMessages(); });
  }

  function decodeText(bytes) {
    try { return strictDecoder.decode(bytes); } catch (e) { return null; }
  }
  function toHex(bytes) {
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(" ");
  }
  function toBase64(bytes) {
    let binary = "";
    bytes.forEach((b) => { binary += String.fromCharCode(b); });
    return btoa(binary);
  }
  function show(bytes, view) {
    const text = decodeText(bytes);
    if (view === "hex") return toHex(bytes);
    if (view === "base64") return toBase64(bytes);
    if (text === null) return view === "text" ? "(not UTF-8 text) " + toHex(bytes) : toHex(bytes);
    if (view === "json" || view === "auto") {
      try { return JSON.stringify(JSON.parse(text), null, 2); } catch (e) {
        return view === "json" ? "(not JSON) " + text : text;
      }
    }
    return text;
  }

  function visible(message, filter, direction) {
    if (direction !== "all" && message.direction !== direction) return false;
    const sub = message.direction === "in" ? subscriptionFor(message.topic) : null;
    if (sub && sub.muted) return false;
    if (!filter) return true;
    if (message.topic.toLowerCase().includes(filter)) return true;
    const text = decodeText(message.bytes);
    return text !== null && text.toLowerCase().includes(filter);
  }

  function renderMessages() {
    const list = $("messages");
    const filter = $("filter").value.trim().toLowerCase();
    const direction = $("direction").value;
    const view = $("view").value;
    const shown = messages.filter((m) => visible(m, filter, direction)).slice(-500).reverse();
    list.textContent = "";
    for (const message of shown) list.append(messageElement(message, view));
    $("messages-empty").classList.toggle("d-none", messages.length > 0 || activeTab !== "list");
    $("message-count").textContent = messages.length
      ? `(${shown.length < messages.length ? `${shown.length} of ` : ""}${messages.length})` : "";
    // Tab Topics / Charts ikut diperbarui saat pesan baru datang.
    if (activeTab === "tree") renderTree();
    if (activeTab === "charts") renderCharts();
  }

  function messageElement(message, view) {
    const sub = message.direction === "in" ? subscriptionFor(message.topic) : null;
    const item = document.createElement("div");
    item.className = `message message-${message.direction} color-${sub ? sub.color : "blue"}`;
    const head = document.createElement("div");
    head.className = "message-head";
    const arrow = document.createElement("span");
    arrow.className = "message-dir";
    arrow.textContent = message.direction === "in" ? "↓" : "↑";
    arrow.title = message.direction === "in" ? "Received" : "Published";
    const topic = document.createElement("code");
    topic.className = "message-topic";
    topic.textContent = message.topic;
    const meta = document.createElement("span");
    meta.className = "message-meta";
    meta.textContent = `QoS ${message.qos}${message.retain ? " · retained" : ""}${describeProperties(message.properties)} · ${message.bytes.length} B · `
      + message.time.toLocaleTimeString([], { hour12: false }) + "." + String(message.time.getMilliseconds()).padStart(3, "0");
    const actions = document.createElement("span");
    actions.className = "message-actions";
    actions.append(
      actionButton("Copy topic", () => copy(message.topic)),
      actionButton("Copy payload", () => copy(decodeText(message.bytes) ?? toHex(message.bytes))),
      actionButton("Publish again", () => fillPublish(message.topic, decodeText(message.bytes) ?? "", message.qos, message.retain)),
    );
    head.append(arrow, topic, meta, actions);
    const body = document.createElement("pre");
    body.className = "message-payload";
    body.textContent = message.bytes.length ? show(message.bytes, view) : "(empty)";
    item.append(head, body);
    return item;
  }

  function actionButton(label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-link btn-sm p-0";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
  }

  function copy(text) {
    if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
  }

  ["filter", "direction", "view"].forEach((id) => $(id).addEventListener("input", renderMessages));
  $("pause").addEventListener("click", (event) => {
    paused = !paused;
    event.target.textContent = paused ? "Resume" : "Pause";
    event.target.setAttribute("aria-pressed", String(paused));
    if (!paused) renderMessages();
  });
  $("clear").addEventListener("click", () => { messages = []; renderMessages(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) {
      event.preventDefault();
      $("filter").focus();
    }
  });

  // ---------------------------------------------------------------- publish
  function fillPublish(topic, payload, qos, retain) {
    $("publish-topic").value = topic;
    $("publish-payload").value = payload;
    $("publish-qos").value = String(qos || 0);
    $("publish-retain").checked = Boolean(retain);
    // Payload berbentuk objek/array JSON -> format JSON (divalidasi sebelum publish).
    try { $("publish-format").value = typeof JSON.parse(payload) === "object" && payload.trim() ? "json" : "text"; }
    catch (e) { $("publish-format").value = "text"; }
    checkPayload();
    $("publish-payload").focus();
  }

  function checkPayload() {
    const status = $("payload-status");
    if ($("publish-format").value !== "json") { status.textContent = ""; return true; }
    try {
      // Placeholder {{...}} diisi dulu (contoh), baru diperiksa sebagai JSON.
      JSON.parse(expand($("publish-payload").value, { counter: 1 }));
      status.textContent = /\{\{/.test($("publish-payload").value) ? "Valid JSON (with placeholders)" : "Valid JSON";
      status.className = "small text-success mb-2";
      return true;
    } catch (e) {
      status.textContent = `Not valid JSON: ${e.message}`;
      status.className = "small text-danger mb-2";
      return false;
    }
  }
  $("publish-payload").addEventListener("input", checkPayload);
  $("publish-format").addEventListener("change", checkPayload);
  $("format-json").addEventListener("click", () => {
    try {
      $("publish-payload").value = JSON.stringify(JSON.parse($("publish-payload").value), null, 2);
      $("publish-format").value = "json";
      checkPayload();
    } catch (e) { checkPayload(); }
  });

  // Publish satu pesan. `template` boleh berisi placeholder {{...}} (diisi di sini);
  // riwayat menyimpan templatnya, bukan hasilnya.
  function publish(topic, template, qos, retain, options = {}) {
    $("publish-error").textContent = "";
    const problem = topicNameError(topic);
    if (problem) { $("publish-error").textContent = problem; return false; }
    if (!client || !client.connected) { $("publish-error").textContent = "Connect first."; return false; }
    const payload = expand(template, { counter: ++publishCounter, ...(options.values || {}) });
    const publishOptions = { qos, retain };
    const properties = options.properties === undefined ? publishProperties() : options.properties;
    if (properties) publishOptions.properties = properties;
    client.publish(topic, payload, publishOptions, (err) => {
      if (err) { $("publish-error").textContent = err.message; return; }
      addMessage("out", topic, payload, qos, retain, properties);
    });
    if (!options.quiet) remember({ topic, payload: template, qos, retain });
    return true;
  }

  $("publish-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!checkPayload()) return;
    publish($("publish-topic").value.trim(), $("publish-payload").value,
      Number($("publish-qos").value), $("publish-retain").checked);
  });
  $("publish-payload").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      $("publish-form").requestSubmit();
    }
  });
  $("clear-retained").addEventListener("click", () => {
    const topic = $("publish-topic").value.trim();
    const problem = topicNameError(topic);
    if (problem) { $("publish-error").textContent = problem; return; }
    if (!window.confirm(`Remove the retained message on "${topic}"? An empty retained message is published.`)) return;
    publish(topic, "", 0, true);
  });

  // Riwayat 20 publish terakhir (di browser ini).
  function remember(entry) {
    const key = JSON.stringify(entry);
    const history = store.get(HISTORY_KEY, []).filter((h) => JSON.stringify(h) !== key);
    history.unshift(entry);
    store.set(HISTORY_KEY, history.slice(0, 20));
    renderHistory();
  }
  function renderHistory() {
    const menu = $("history-menu");
    menu.textContent = "";
    const history = store.get(HISTORY_KEY, []);
    if (!history.length) menu.append(menuNote("Nothing published yet."));
    for (const entry of history) {
      menu.append(menuItem(entry.topic, entry.payload, () => fillPublish(entry.topic, entry.payload, entry.qos, entry.retain)));
    }
    updateSuggestions();
  }

  function menuItem(title, subtitle, onClick, onDelete) {
    const li = document.createElement("li");
    li.className = "d-flex align-items-start";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dropdown-item";
    const strong = document.createElement("div");
    strong.className = "font-monospace small text-truncate";
    strong.textContent = title;
    const small = document.createElement("div");
    small.className = "small text-muted text-truncate";
    small.textContent = subtitle || "(empty)";
    button.append(strong, small);
    button.addEventListener("click", onClick);
    li.append(button);
    if (onDelete) {
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn btn-sm btn-link text-danger";
      del.textContent = "✕";
      del.title = "Delete";
      del.addEventListener("click", (event) => { event.stopPropagation(); onDelete(); });
      li.append(del);
    }
    return li;
  }
  function menuNote(text) {
    const li = document.createElement("li");
    li.className = "dropdown-item-text small text-muted";
    li.textContent = text;
    return li;
  }

  // Saran topik: riwayat + topik device IoT Platform.
  function updateSuggestions() {
    const list = $("topic-suggestions");
    list.textContent = "";
    const topics = new Set(store.get(HISTORY_KEY, []).map((h) => h.topic));
    if (deviceTopics) ["telemetry", "status", "firmware"].forEach((k) => deviceTopics[k] && topics.add(deviceTopics[k]));
    for (const topic of topics) {
      const option = document.createElement("option");
      option.value = topic;
      list.append(option);
    }
  }

  // Tombol cepat: topik device IoT Platform, atau topik sandbox (tahap M5).
  function showDeviceTopics() {
    const box = $("device-topics");
    const buttons = $("device-topic-buttons");
    buttons.textContent = "";
    box.classList.toggle("d-none", !deviceTopics && !sandboxInfo);
    $("device-automation").classList.toggle("d-none", !deviceTopics);
    let examples = [];
    if (deviceTopics) {
      $("device-topics-label").textContent = "Device topics";
      examples = [
        ["Telemetry", deviceTopics.telemetry, '{"temperature": 25.1}', 0, false],
        ["Online", deviceTopics.status, "online", 1, true],
        ["Firmware", deviceTopics.firmware, `{"version": "${(deviceInfo && deviceInfo.firmware) || "1.0.0"}", "board": "${(deviceInfo && deviceInfo.board) || "sim"}"}`, 0, false],
        ["Command response", deviceTopics.command_response, '{"success": true}', 1, false],
      ];
    } else if (sandboxInfo) {
      $("device-topics-label").textContent = "Sandbox topics";
      examples = [
        ["My topic", `${sandboxInfo.root}/test`, "hello {{counter}}", 0, false],
        ["Sensor", `${sandboxInfo.root}/sensor`, '{"temperature": {{random:20:30}}, "time": "{{timestamp}}"}', 0, false],
        ["Shared chat", `${sandboxInfo.shared}/chat`, "hi from {{unix}}", 0, false],
      ];
    }
    for (const [label, topic, payload, qos, retain] of examples) {
      if (!topic) continue;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-sm btn-outline-success";
      button.textContent = label;
      button.title = topic;
      button.addEventListener("click", () => fillPublish(topic, payload, qos, retain));
      buttons.append(button);
    }
    updateSuggestions();
  }

  // Saved messages (disimpan di server, lihat connections/saved.py).
  async function loadSaved() {
    const menu = $("saved-menu");
    menu.textContent = "";
    try {
      const response = await fetch(config.urls.saved, { credentials: "same-origin" });
      const data = await response.json();
      if (!data.messages.length) menu.append(menuNote("No saved messages. Use Save under Publish."));
      for (const m of data.messages) {
        menu.append(menuItem(m.name + (m.profile ? "" : "  (all connections)"), m.topic,
          () => fillPublish(m.topic, m.payload, m.qos, m.retain),
          async () => {
            await postJson(config.urls.savedDelete.replace("/0/", `/${m.id}/`));
            loadSaved();
          }));
      }
    } catch (e) {
      menu.append(menuNote("Could not load saved messages."));
    }
  }
  $("save-message").addEventListener("click", () => {
    $("save-panel").classList.toggle("d-none");
    $("save-name").focus();
  });
  $("save-confirm").addEventListener("click", async () => {
    try {
      await postJson(config.urls.saved, {
        name: $("save-name").value.trim() || $("publish-topic").value.trim(),
        topic: $("publish-topic").value.trim(),
        payload: $("publish-payload").value,
        qos: Number($("publish-qos").value),
        retain: $("publish-retain").checked,
        allConnections: $("save-all").checked,
      });
      $("save-panel").classList.add("d-none");
      $("save-name").value = "";
      $("publish-error").textContent = "";
      loadSaved();
    } catch (err) {
      $("publish-error").textContent = err.message;
    }
  });

  // ================================================================ tahap M5: otomatisasi
  // Placeholder di topik/payload publish (diisi SETIAP kali publish):
  //   {{counter}}         1, 2, 3, ... (nomor publish di halaman ini)
  //   {{timestamp}}       waktu ISO 8601, mis. 2026-10-22T06:15:02.123Z
  //   {{unix}}            detik sejak 1970
  //   {{random:20:30}}    bilangan acak 20..30 (2 desimal)
  //   {{int:0:100}}       bilangan bulat acak 0..100
  //   {{bool}}            true / false acak
  // Auto-responder juga mengenal {{id}} dan {{method}} dari command yang diterima.
  let publishCounter = 0;

  function expand(template, values) {
    return String(template).replace(/\{\{\s*([a-z]+)(?::(-?[\d.]+):(-?[\d.]+))?\s*\}\}/gi, (match, name, a, b) => {
      const key = name.toLowerCase();
      const low = Number(a);
      const high = Number(b);
      if (key === "random" && a !== undefined) return String(Number((low + Math.random() * (high - low)).toFixed(2)));
      if (key === "int" && a !== undefined) return String(Math.floor(low + Math.random() * (high - low + 1)));
      if (key === "timestamp") return new Date().toISOString();
      if (key === "unix") return String(Math.floor(Date.now() / 1000));
      if (key === "bool") return Math.random() < 0.5 ? "true" : "false";
      if (values && values[key] !== undefined) return String(values[key]);
      return match;
    });
  }

  // ---------------------------------------------------------------- publish berulang
  let repeatTimer = null;
  let repeatSent = 0;
  function stopRepeat() {
    clearInterval(repeatTimer);
    repeatTimer = null;
    $("repeat-toggle").textContent = "Start";
    $("repeat-toggle").classList.replace("btn-danger", "btn-outline-primary");
    $("repeat-status").textContent = repeatSent ? `Stopped after ${repeatSent} message(s).` : "";
  }
  $("repeat-toggle").addEventListener("click", () => {
    if (repeatTimer) { stopRepeat(); return; }
    const seconds = Math.max(1, Number($("repeat-seconds").value) || 5);     // minimal 1 detik
    $("repeat-seconds").value = String(seconds);
    if (!checkPayload()) return;
    repeatSent = 0;
    const tick = () => {
      // Saat terputus, lewati saja; pengiriman lanjut sendiri setelah tersambung lagi.
      if (!client || !client.connected) { $("repeat-status").textContent = "Waiting for the connection…"; return; }
      const ok = publish($("publish-topic").value.trim(), $("publish-payload").value,
        Number($("publish-qos").value), $("publish-retain").checked, { quiet: repeatSent > 0 });
      if (!ok) { stopRepeat(); return; }
      repeatSent += 1;
      $("repeat-status").textContent = `Sent ${repeatSent} message(s), every ${seconds} s.`;
    };
    tick();
    repeatTimer = setInterval(tick, seconds * 1000);
    $("repeat-toggle").textContent = "Stop";
    $("repeat-toggle").classList.replace("btn-outline-primary", "btn-danger");
  });

  // ---------------------------------------------------------------- simulator sensor device
  // Payload telemetri dari variabel device di IoT Platform: sensor angka -> {{random:min:max}},
  // on/off -> {{int:0:1}}. Aktuator dilewati (keadaannya dikirim oleh "Report desired states").
  $("simulate-sensors").addEventListener("click", () => {
    if (!deviceTopics) return;
    const parts = [];
    for (const v of (deviceInfo && deviceInfo.variables) || []) {
      if (v.kind === "actuator") continue;
      if (v.value_type === "boolean") parts.push(`"${v.key}": {{int:0:1}}`);
      else parts.push(`"${v.key}": {{random:${v.min ?? 0}:${v.max ?? 100}}}`);
    }
    if (!parts.length) parts.push('"temperature": {{random:20:30}}', '"humidity": {{random:40:80}}');
    fillPublish(deviceTopics.telemetry, `{${parts.join(", ")}}`, 0, false);
    $("repeat-status").textContent = "Telemetry template ready. Press Start to send it repeatedly.";
  });

  // ---------------------------------------------------------------- auto-responder device
  // Pesan masuk untuk device: command (jawab otomatis, OTA) dan desired state (laporkan balik).
  function automate(topic, payload) {
    if (!deviceTopics) return;
    let data = null;
    try { data = JSON.parse(new TextDecoder().decode(payload)); } catch (e) { return; }
    const commandBase = deviceTopics.commands.replace(/\+$/, "");
    if (topic.startsWith(commandBase) && !topic.endsWith("/response")) {
      const id = topic.slice(commandBase.length);
      const method = (data && data.method) || "";
      const responseTopic = deviceTopics.command_response.replace("{id}", id);
      if (method === "ota" && $("auto-ota").checked) { simulateOta(responseTopic, data.params || {}); return; }
      if ($("auto-answer").checked) {
        publish(responseTopic, $("auto-answer-template").value, 1, false,
          { quiet: true, values: { id, method }, properties: null });
      }
      return;
    }
    if (topic === deviceTopics.desired && $("auto-desired").checked && data && typeof data === "object") {
      // Desired state {"lamp": 1} -> device "menjalankan" lalu melaporkan keadaannya sebagai telemetri.
      publish(deviceTopics.telemetry, JSON.stringify(data), 0, false, { quiet: true, properties: null });
    }
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  // Simulasi pembaruan firmware OTA, mengikuti laporan ESP32 (firmware/esp32_mqtt di platform).
  async function simulateOta(responseTopic, params) {
    const report = (body) => publish(deviceTopics.firmware, JSON.stringify(body), 0, false, { quiet: true, properties: null });
    const update = params.update;
    publish(responseTopic, JSON.stringify({ success: true, message: "Update accepted" }), 1, false, { quiet: true, properties: null });
    const result = $("auto-ota-result").value;
    for (const progress of [0, 25, 50, 75, 100]) {
      await sleep(500);
      if (result === "fail" && progress === 50) {
        report({ update, state: "FAILED", error: "Simulated download error" });
        return;
      }
      report({ update, state: "DOWNLOADING", progress });
    }
    for (const state of ["DOWNLOADED", "VERIFIED", "UPDATING"]) { await sleep(400); report({ update, state }); }
    await sleep(1000);   // "restart"
    if (deviceInfo) deviceInfo.firmware = params.version || deviceInfo.firmware;
    report({ version: params.version, board: (deviceInfo && deviceInfo.board) || "sim" });
  }

  // ================================================================ tahap M6
  // ---------------------------------------------------------------- properti MQTT 5
  const isV5 = config.protocolVersion === 5;
  $("v5-properties").classList.toggle("d-none", !isV5);
  function publishProperties() {
    if (!isV5) return null;
    const properties = {};
    const contentType = $("prop-content-type").value.trim();
    const responseTopic = $("prop-response-topic").value.trim();
    const expiry = Number($("prop-expiry").value);
    if (contentType) properties.contentType = contentType;
    if (responseTopic) properties.responseTopic = responseTopic;
    if (expiry > 0) properties.messageExpiryInterval = expiry;
    const userProperties = {};
    for (const line of $("prop-user").value.split("\n")) {
      const index = line.indexOf("=");
      if (index > 0) userProperties[line.slice(0, index).trim()] = line.slice(index + 1).trim();
    }
    if (Object.keys(userProperties).length) properties.userProperties = userProperties;
    return Object.keys(properties).length ? properties : null;
  }
  function describeProperties(properties) {
    if (!properties) return "";
    const parts = [];
    if (properties.contentType) parts.push(`content-type ${properties.contentType}`);
    if (properties.responseTopic) parts.push(`response ${properties.responseTopic}`);
    for (const [key, value] of Object.entries(properties.userProperties || {})) parts.push(`${key}=${value}`);
    return parts.length ? ` · ${parts.join(", ")}` : "";
  }

  // ---------------------------------------------------------------- statistik topik dan grafik
  const topicStats = new Map();      // topik -> {count, last, time}
  const series = new Map();          // "topik › key" -> {label, points: [{t, v}]}
  const MAX_POINTS = 120;
  const MAX_SERIES = 30;

  function addPoint(label, value, time) {
    if (!Number.isFinite(value)) return;
    if (!series.has(label)) {
      if (series.size >= MAX_SERIES) return;
      series.set(label, { label, points: [] });
    }
    const points = series.get(label).points;
    points.push({ t: time, v: value });
    if (points.length > MAX_POINTS) points.shift();
  }

  function track(message) {
    const text = decodeText(message.bytes);
    const stat = topicStats.get(message.topic) || { count: 0 };
    stat.count += 1;
    stat.last = text === null ? toHex(message.bytes.slice(0, 32)) : text;
    stat.time = message.time;
    topicStats.set(message.topic, stat);
    if (text === null || message.direction !== "in") return;
    // Angka polos ("23.5") atau field angka di JSON ({"temperature": 23.5}, satu tingkat).
    const number = Number(text.trim());
    if (text.trim() !== "" && Number.isFinite(number)) { addPoint(message.topic, number, message.time); return; }
    try {
      const data = JSON.parse(text);
      if (data && typeof data === "object" && !Array.isArray(data)) {
        for (const [key, value] of Object.entries(data)) {
          if (typeof value === "number") addPoint(`${message.topic} › ${key}`, value, message.time);
          else if (typeof value === "boolean") addPoint(`${message.topic} › ${key}`, value ? 1 : 0, message.time);
        }
      }
    } catch (e) { /* bukan JSON */ }
  }

  let activeTab = "list";
  document.querySelectorAll("[data-message-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      activeTab = tab.dataset.messageTab;
      document.querySelectorAll("[data-message-tab]").forEach((t) => t.classList.toggle("active", t === tab));
      $("messages").classList.toggle("d-none", activeTab !== "list");
      $("topic-tree").classList.toggle("d-none", activeTab !== "tree");
      $("charts").classList.toggle("d-none", activeTab !== "charts");
      renderMessages();
    });
  });

  // Pohon topik: setiap level "/" menjadi cabang; daun menampilkan jumlah dan nilai terakhir.
  function renderTree() {
    const root = { children: new Map(), count: 0 };
    for (const [topic, stat] of topicStats) {
      let node = root;
      topic.split("/").forEach((level, index, levels) => {
        if (!node.children.has(level)) node.children.set(level, { children: new Map(), count: 0, path: levels.slice(0, index + 1).join("/") });
        node = node.children.get(level);
        node.count += stat.count;
      });
      node.stat = stat;
    }
    const container = $("topic-tree");
    container.textContent = "";
    if (!topicStats.size) { container.append(note("No topics yet.")); return; }
    container.append(treeList(root));
  }
  function treeList(node) {
    const list = document.createElement("ul");
    list.className = "topic-tree";
    for (const [name, child] of [...node.children].sort((a, b) => a[0].localeCompare(b[0]))) {
      const item = document.createElement("li");
      const label = document.createElement("button");
      label.type = "button";
      label.className = "btn btn-link btn-sm p-0 font-monospace";
      label.textContent = name || "(empty)";
      label.title = `Show messages of ${child.path}${child.children.size ? "/#" : ""}`;
      label.addEventListener("click", () => {
        $("filter").value = child.path;
        document.querySelector('[data-message-tab="list"]').click();
      });
      const count = document.createElement("span");
      count.className = "badge text-bg-light border ms-1";
      count.textContent = child.count;
      item.append(label, count);
      if (child.stat) {
        const value = document.createElement("span");
        value.className = "tree-value";
        value.textContent = child.stat.last.length > 80 ? child.stat.last.slice(0, 80) + "…" : child.stat.last;
        value.title = child.stat.time.toLocaleTimeString([], { hour12: false });
        item.append(value);
      }
      if (child.children.size) item.append(treeList(child));
      list.append(item);
    }
    return list;
  }

  // Grafik kecil (sparkline SVG) untuk setiap deret angka.
  function renderCharts() {
    const container = $("charts");
    container.textContent = "";
    if (!series.size) { container.append(note("Numbers in received messages appear here, e.g. 23.5 or {\"temperature\": 23.5}.")); return; }
    const svgNs = "http://www.w3.org/2000/svg";
    for (const { label, points } of series.values()) {
      const values = points.map((p) => p.v);
      const min = Math.min(...values);
      const max = Math.max(...values);
      const card = document.createElement("div");
      card.className = "chart-card";
      const title = document.createElement("div");
      title.className = "chart-title font-monospace";
      title.textContent = label;
      const stats = document.createElement("div");
      stats.className = "chart-stats";
      stats.textContent = `last ${values[values.length - 1]} · min ${min} · max ${max} · ${values.length} pts`;
      const svg = document.createElementNS(svgNs, "svg");
      svg.setAttribute("viewBox", "0 0 300 60");
      svg.setAttribute("preserveAspectRatio", "none");
      svg.setAttribute("class", "sparkline");
      const line = document.createElementNS(svgNs, "polyline");
      const span = max - min || 1;
      line.setAttribute("points", values.map((v, i) => {
        const x = values.length === 1 ? 150 : (i / (values.length - 1)) * 300;
        return `${x.toFixed(1)},${(56 - ((v - min) / span) * 52).toFixed(1)}`;
      }).join(" "));
      svg.append(line);
      card.append(title, stats, svg);
      container.append(card);
    }
  }
  function note(text) {
    const p = document.createElement("p");
    p.className = "text-muted small text-center py-4 mb-0";
    p.textContent = text;
    return p;
  }

  // ---------------------------------------------------------------- ekspor pesan
  function download(name, type, text) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportRows() {
    return messages.map((m) => {
      const text = decodeText(m.bytes);
      return { time: m.time.toISOString(), direction: m.direction === "in" ? "received" : "published", topic: m.topic,
        qos: m.qos, retain: Boolean(m.retain), payload: text === null ? toBase64(m.bytes) : text,
        encoding: text === null ? "base64" : "utf-8" };
    });
  }
  function exportName(extension) {
    const slug = config.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "messages";
    return `mqtt-${slug}-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`;
  }
  $("export-json").addEventListener("click", () => {
    // JSON juga membawa properti MQTT 5 (CSV tidak, supaya kolomnya tetap sederhana).
    const rows = exportRows().map((row, index) => ({ ...row, properties: messages[index].properties || null }));
    download(exportName("json"), "application/json", JSON.stringify(rows, null, 2));
  });
  $("export-csv").addEventListener("click", () => {
    const quote = (value) => `"${String(value).replace(/"/g, '""')}"`;
    const rows = exportRows();
    const header = ["time", "direction", "topic", "qos", "retain", "payload", "encoding"];
    const lines = [header.join(",")].concat(rows.map((row) => header.map((key) => quote(row[key])).join(",")));
    // BOM UTF-8 supaya Excel membaca huruf non-ASCII dengan benar.
    download(exportName("csv"), "text/csv", "﻿" + lines.join("\r\n"));
  });

  // ---------------------------------------------------------------- mulai
  if (typeof mqtt === "undefined") {
    showAlert("The MQTT library (static/vendor/mqtt.min.js) is missing. See README.");
    $("connect").disabled = true;
  }
  setStatus("disconnected");
  renderSubscriptions();
  renderMessages();
  renderHistory();
  loadSaved();
})();
