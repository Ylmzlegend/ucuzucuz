/* ucuzucuz: filtre/sıralama, karşılaştırma seçimi, karşılaştırma tablosu. Bağımlılık yok. */
(function () {
  'use strict';
  var html = document.documentElement;
  var ROOT = html.getAttribute('data-root') || './';
  var EXPL = html.getAttribute('data-explicit') === '1';
  var D = window.UCUZ || { products: [], categories: {} };
  var MAX_CMP = 3;

  function href(path) { return ROOT + path + (EXPL && /\/$/.test(path) ? 'index.html' : ''); }
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function norm(s) {
    var m = { 'ç': 'c', 'ğ': 'g', 'ı': 'i', 'İ': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u', 'Ç': 'c', 'Ğ': 'g', 'Ö': 'o', 'Ş': 's', 'Ü': 'u' };
    return String(s).replace(/[çğıİöşüÇĞÖŞÜ]/g, function (c) { return m[c]; }).toLowerCase();
  }
  var nf0 = new Intl.NumberFormat('tr-TR');
  var nf1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
  function tl(n) { return n == null ? '-' : nf0.format(Math.round(n)) + ' TL'; }
  function byId(id) { for (var i = 0; i < D.products.length; i++) if (D.products[i].id === id) return D.products[i]; return null; }
  function all(sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); }

  /* karşılaştırma seçimi: yalnızca aynı kategoriden, en fazla 3 */
  var selected = [];
  var bar = document.querySelector('[data-cmpbar]');
  var boxes = all('[data-cmp]');
  function selKat() { var p = selected.length ? byId(selected[0]) : null; return p ? p.kategori : null; }
  function updateBar() {
    var k = selKat();
    boxes.forEach(function (cb) {
      var other = k && cb.getAttribute('data-kat') !== k;
      var full = selected.length >= MAX_CMP && !cb.checked;
      cb.disabled = !!(other || full);
      cb.parentNode.title = other ? 'Yalnızca aynı kategoriden modeller karşılaştırılabilir' : (full ? 'En fazla 3 model seçilebilir' : '');
    });
    if (!bar) return;
    bar.hidden = selected.length === 0;
    var t = bar.querySelector('[data-cmptext]');
    var a = bar.querySelector('[data-cmplink]');
    t.textContent = selected.length + ' model seçildi' + (selected.length < 2 ? ', en az 2 gerekli' : '');
    a.href = href('karsilastir/') + '#' + selected.join('-');
    a.classList.toggle('btn-pasif', selected.length < 2);
    a.classList.toggle('btn-ana', selected.length >= 2);
    a.setAttribute('aria-disabled', selected.length < 2 ? 'true' : 'false');
  }
  boxes.forEach(function (cb) {
    cb.addEventListener('change', function () {
      var id = cb.value;
      if (cb.checked) {
        if (selected.length >= MAX_CMP || (selKat() && cb.getAttribute('data-kat') !== selKat())) { cb.checked = false; return; }
        selected.push(id);
      } else {
        selected = selected.filter(function (x) { return x !== id; });
      }
      all('[data-cmp][value="' + id + '"]').forEach(function (o) { o.checked = cb.checked; });
      updateBar();
    });
  });

  /* kategori listesi: filtre + sıralama */
  var list = document.querySelector('[data-list]');
  var form = document.querySelector('[data-filters]');
  if (list && form) {
    var items = all('[data-item]', list);
    var fboxes = all('[data-fkey]', form);
    var countEl = document.querySelector('[data-count]');
    var emptyEl = document.querySelector('[data-empty]');
    var val = function (li, k) { var v = parseFloat(li.getAttribute('data-' + k)); return isNaN(v) ? null : v; };
    var sortKey = function () {
      var v = form.sort.value;
      if (v === 'deger') return ['deger', 1];
      if (v === 'fark') return ['spread', -1];
      if (v === 'satici') return ['sellers', -1];
      if (v.indexOf('sp:') === 0) { var s = v.split(':'); return ['spec-' + s[1], s[2] === 'max' ? -1 : 1]; }
      return ['price', 1];
    };
    var apply = function () {
      var q = norm(form.q.value || '').trim();
      var resmi = form.resmi.checked;
      var vis = 0;
      items.forEach(function (li) {
        var ok = true;
        if (q && li.getAttribute('data-name').indexOf(q) < 0) ok = false;
        if (resmi && li.getAttribute('data-resmi') !== '1') ok = false;
        fboxes.forEach(function (cb) {
          if (!ok || !cb.checked) return;
          var v = val(li, 'spec-' + cb.getAttribute('data-fkey'));
          var t = parseFloat(cb.getAttribute('data-val'));
          var op = cb.getAttribute('data-op');
          if (v == null || (op === 'eq' && v !== t) || (op === 'lte' && v > t) || (op === 'gte' && v < t)) ok = false;
        });
        li.hidden = !ok;
        if (ok) vis++;
      });
      var kk = sortKey();
      items.slice().sort(function (a, b) {
        var av = val(a, kk[0]), bv = val(b, kk[0]);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av - bv) * kk[1];
      }).forEach(function (li) { list.appendChild(li); });
      countEl.textContent = vis + ' model';
      if (emptyEl) emptyEl.hidden = vis !== 0;
    };
    form.addEventListener('input', apply);
    form.addEventListener('change', apply);
    apply();
  }

  /* karşılaştırma sayfası */
  var host = document.querySelector('[data-compare]');
  var picker = document.querySelector('[data-cmp-add]');
  if (host && picker) {
    var raw = location.hash.replace(/^#/, '') || (new URLSearchParams(location.search).get('ids') || '').replace(/,/g, '-');
    var ids = [];
    raw.split('-').forEach(function (x) {
      var p = byId(x);
      if (!p || ids.length >= MAX_CMP || ids.indexOf(x) >= 0) return;
      if (ids.length && byId(ids[0]).kategori !== p.kategori) return;
      ids.push(x);
    });
    var fmt = function (v, o) {
      if (v == null || v === '') return '-';
      if (o.tip === 'evet_hayir') return v ? 'Evet' : 'Hayır';
      if (o.tip === 'metin') return String(v);
      return nf1.format(v) + (o.birim ? ' ' + o.birim : '');
    };
    var render = function () {
      var ps = ids.map(byId);
      var kat = ps.length ? ps[0].kategori : null;
      var opts = '<option value="">Model seç</option>';
      Object.keys(D.categories).forEach(function (k) {
        if (kat && k !== kat) return;
        var items = D.products.filter(function (p) { return p.kategori === k && ids.indexOf(p.id) < 0; });
        if (!items.length) return;
        opts += '<optgroup label="' + esc(D.categories[k].ad) + '">' + items.map(function (p) {
          return '<option value="' + esc(p.id) + '">' + esc(p.ad) + '</option>';
        }).join('') + '</optgroup>';
      });
      picker.innerHTML = opts;
      picker.disabled = ids.length >= MAX_CMP;
      if (!ps.length) {
        host.innerHTML = '<p class="bos">Karşılaştırmak için yukarıdan bir model ekle. Kategori sayfalarındaki "Karşılaştır" kutularını da kullanabilirsin.</p>';
        return;
      }
      var C = D.categories[kat];
      var rows = [
        { ad: 'En düşük toplam fiyat', get: function (p) { return p.best; }, f: tl, iyi: 'min' },
        { ad: 'Resmi garantili en düşük', get: function (p) { return p.best_resmi; }, f: tl, iyi: 'min' },
        { ad: 'Teklif sayısı', get: function (p) { return p.sellers; }, f: function (v) { return v == null ? '-' : String(v); }, iyi: 'max' }
      ];
      if (C.deger) rows.push({ ad: 'TL (' + C.deger.etiket + ')', get: function (p) { return p.deger; }, f: function (v) { return v == null ? '-' : nf1.format(v) + ' TL'; }, iyi: 'min' });
      C.ozellikler.forEach(function (o) {
        rows.push({
          ad: o.ad + (o.iddia ? ' (üretici iddiası)' : ''),
          get: function (p) { return p.specs[o.key]; },
          f: function (v) { return fmt(v, o); },
          iyi: o.tip === 'sayi' ? o.iyi : null
        });
      });
      var h = '<p class="kars-kat">' + esc(C.ad) + ' karşılaştırması</p><div class="kars-sar"><table class="kars"><thead><tr><th scope="col"><span class="sr">Özellik</span></th>';
      ps.forEach(function (p) {
        h += '<th scope="col"><a href="' + esc(href(p.path)) + '">' + esc(p.ad) + '</a><button type="button" class="kaldir" data-del="' + esc(p.id) + '">Çıkar</button></th>';
      });
      h += '</tr></thead><tbody>';
      rows.forEach(function (r) {
        var vals = ps.map(r.get);
        var best = null;
        var nums = vals.filter(function (v) { return typeof v === 'number'; });
        if (r.iyi && nums.length >= 2) {
          best = r.iyi === 'min' ? Math.min.apply(null, nums) : Math.max.apply(null, nums);
          if (nums.every(function (v) { return v === best; })) best = null;
        }
        h += '<tr><th scope="row">' + esc(r.ad) + '</th>';
        vals.forEach(function (v) { h += '<td' + (best != null && v === best ? ' class="iyi"' : '') + '>' + esc(r.f(v)) + '</td>'; });
        h += '</tr>';
      });
      h += '</tbody></table></div>';
      host.innerHTML = h;
      all('[data-del]', host).forEach(function (b) {
        b.addEventListener('click', function () { ids = ids.filter(function (x) { return x !== b.getAttribute('data-del'); }); sync(); });
      });
    };
    var sync = function () {
      render();
      try { history.replaceState(null, '', location.pathname + (ids.length ? '#' + ids.join('-') : '')); } catch (e) { /* önemsiz */ }
    };
    picker.addEventListener('change', function () {
      if (picker.value && ids.length < MAX_CMP) { ids.push(picker.value); sync(); }
    });
    render();
  }
})();
