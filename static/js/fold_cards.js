/* Kartu yang bisa dilipat di halaman koneksi (<details class="fold-card">), seperti kartu
   JSON rule dan Run on devices di IoT Platform. Keadaan buka/tutup tiap kartu diingat
   di browser ini (localStorage, per id kartu, berlaku untuk semua koneksi). */
(function () {
  "use strict";
  const PREFIX = "mqttclient.fold.";
  function load(id) {
    try { return localStorage.getItem(PREFIX + id); } catch (e) { return null; }
  }
  function save(id, open) {
    try { localStorage.setItem(PREFIX + id, open ? "open" : "closed"); } catch (e) { /* mode privat */ }
  }
  document.querySelectorAll("details.fold-card[id]").forEach((card) => {
    const state = load(card.id);
    if (state === "closed") card.open = false;
    else if (state === "open") card.open = true;
    card.addEventListener("toggle", () => save(card.id, card.open));
  });
})();
