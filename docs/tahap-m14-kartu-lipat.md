# Tahap M14 — Kartu ESP32-CAM sendiri dan kartu yang bisa dilipat

## Perubahan
- Simulasi kamera ESP32-CAM (M11) dipindah dari kartu **Automation** ke kartu sendiri **ESP32-CAM**
  (`id="camera-box"`). Kartu ini tetap hanya tampil untuk device IoT Platform (`camera_sim.js` → `attach`).
- Kartu kolom kiri (**Subscriptions**, **Publish**, **Automation**, **ESP32-CAM**) sekarang `<details class="card fold-card">`
  dengan judul di `<summary>` dan tanda ▸/▾, seperti kartu *JSON rule* dan *Run on devices* di IoT Platform.
- Keadaan buka/tutup diingat per browser: `static/js/fold_cards.js`, kunci `localStorage` `mqttclient.fold.<id kartu>`
  (dibungkus try/catch; tanpa localStorage semua kartu terbuka).
- Judul kartu menampilkan keadaan penting agar tetap terlihat saat dilipat: jumlah langganan (`#subscriptions-badge`),
  *Repeating* saat publish berulang berjalan (`#repeat-badge`), *Simulating* saat simulasi kamera aktif (`#camera-badge`).
- Tombol *Saved* di kartu Publish dipindah dari judul ke isi kartu (tombol di dalam `<summary>` ikut melipat kartu).

## Berkas
- `connections/templates/connections/session.html`
- `static/js/fold_cards.js` (baru), `static/js/session.js`, `static/js/camera_sim.js`
- `static/css/app.css` (bagian *Kartu yang bisa dilipat*)
- `userdocs/.../subscribe-publish.html`, `camera-simulator.html`
- Tes: `connections/tests_m11.py` → `test_session_cards_can_be_folded`
