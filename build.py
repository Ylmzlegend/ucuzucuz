#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ucuzucuz statik site üreticisi.

Kullanım:
  python build.py             yayın için dist/ klasörünü üretir
  python build.py --preview   dosyadan çift tıklayıp açılabilen dist/ üretir
                              (klasör linklerine index.html eklenir)

Veri: data/urunler/<kategori>.csv, data/sellers.csv, data/offers.csv, data/price_history.csv
Ayarlar ve kategori tanımları: config.json  |  Şablonlar: templates/  |  Stil/JS: static/
"""
import argparse
import csv
import io
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
URUNLER = DATA / "urunler"

TR_MAP = str.maketrans({"ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i",
                        "ö": "o", "Ö": "o", "ş": "s", "Ş": "s", "ü": "u", "Ü": "u"})
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
         "Eylül", "Ekim", "Kasım", "Aralık"]
AYLAR_KISA = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
OZELLIK_TIPLERI = ("sayi", "evet_hayir", "metin")
TEMEL_SUTUNLAR = ("id", "marka", "model", "gtin", "aciklama")


# ---------------------------------------------------------------- yardımcılar
def slugify(s):
    s = s.translate(TR_MAP).lower()
    out, prev_dash = [], True
    for ch in s:
        if ch.isascii() and ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


def ascii_ara(s):
    return s.translate(TR_MAP).lower()


def f_tl(n):
    if n is None:
        return "-"
    return f"{round(n):,}".replace(",", ".") + " TL"


def f_num(n):
    if n is None:
        return "-"
    n = float(n)
    return str(int(n)) if n.is_integer() else f"{n:g}".replace(".", ",")


def f_tarih(d):
    return f"{d.day} {AYLAR[d.month - 1]} {d.year}"


def f_gun_once(n):
    if n <= 0:
        return "bugün kontrol edildi"
    if n == 1:
        return "dün kontrol edildi"
    return f"{n} gün önce kontrol edildi"


def spec_deger(o, v):
    """Bir özelliği ekranda gösterilecek metne çevir."""
    if v is None or v == "":
        return "-"
    if o["tip"] == "evet_hayir":
        return "Evet" if v else "Hayır"
    if o["tip"] == "metin":
        return str(v)
    s = f_num(v)
    return f"{s} {o['birim']}" if o.get("birim") else s


def spec_ozet(specs, kat):
    """Liste satırındaki kısa özellik özeti: '256 GB, 8 GB RAM, 6,7 inç ekran'."""
    parts = []
    for o in kat["ozellikler"]:
        if not o.get("ozet"):
            continue
        v = specs.get(o["key"])
        if v is None or v == "":
            continue
        if o["tip"] == "evet_hayir":
            if v:
                parts.append(o.get("ozet_ek") or o["ad"])
            continue
        if o["tip"] == "metin":
            parts.append(str(v))
            continue
        s = spec_deger(o, v)
        if o.get("ozet_ek"):
            s += " " + o["ozet_ek"]
        parts.append(s)
    return ", ".join(parts)


class DataError(Exception):
    pass


def read_table(path):
    """CSV oku. Türkçe Excel'in noktalı virgüllü CSV'sini de otomatik tanır."""
    text = Path(path).read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines:
        return [], [], ","
    head = lines[0]
    delim = ";" if head.count(";") > head.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    rows = []
    for r in reader:
        row = {(k or "").strip(): (v or "").strip() for k, v in r.items() if k}
        if any(row.values()):
            rows.append(row)
    return [c.strip() for c in reader.fieldnames], rows, delim


def write_table(path, fieldnames, rows, delim=","):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=delim, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def parse_num(raw, key, where, errors):
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        errors.append(f"{where}: '{key}' sayı olmalı, bulunan: '{raw}'")
        return None


# ---------------------------------------------------------------- ayar kontrolü
def check_config(cfg):
    errors = []
    for key, kat in cfg["categories"].items():
        if slugify(key) != key:
            errors.append(f"config.json: kategori anahtarı '{key}' yalnızca küçük harf, rakam ve tire içermeli")
        keys = set()
        for o in kat.get("ozellikler", []):
            if o.get("tip") not in OZELLIK_TIPLERI:
                errors.append(f"config.json → {key}: '{o.get('key')}' için tip {OZELLIK_TIPLERI} olmalı")
            if o.get("key") in TEMEL_SUTUNLAR or o.get("key") in keys:
                errors.append(f"config.json → {key}: özellik anahtarı '{o.get('key')}' tekrar ediyor veya ayrılmış")
            keys.add(o.get("key"))
        for ref in [kat.get("deger"), kat.get("yasal")] + kat.get("filtreler", []):
            if ref and ref.get("key") not in keys:
                errors.append(f"config.json → {key}: '{ref.get('key')}' özelliği tanımlı değil")
        for f in kat.get("filtreler", []):
            if f.get("op") not in ("eq", "lte", "gte"):
                errors.append(f"config.json → {key}: filtre '{f.get('ad')}' için op eq, lte veya gte olmalı")
        kat.setdefault("ozellikler", [])
        kat.setdefault("filtreler", [])
    if errors:
        raise DataError("\n".join(errors))


# ---------------------------------------------------------------- veri yükleme
def load_catalog(cfg, today):
    errors, warns = [], []
    cats = cfg["categories"]

    _, srow, _ = read_table(DATA / "sellers.csv")
    _, orow, _ = read_table(DATA / "offers.csv")
    hpath = DATA / "price_history.csv"
    _, hrow, _ = read_table(hpath) if hpath.exists() else ([], [], ",")

    sellers = {}
    for i, r in enumerate(srow, start=2):
        w = f"sellers.csv satır {i}"
        sid = r.get("id", "")
        if not sid:
            errors.append(f"{w}: id boş")
            continue
        if sid in sellers:
            errors.append(f"{w}: '{sid}' iki kez tanımlı")
        tip = r.get("tip", "magaza")
        if tip not in cfg["satici_tipleri"]:
            errors.append(f"{w}: tip '{tip}' geçersiz (pazaryeri, magaza, uretici)")
        sellers[sid] = {"id": sid, "ad": r.get("ad", sid), "tip": tip, "web": r.get("web", ""),
                        "platform": r.get("platform", "")}

    if URUNLER.exists():
        for f in URUNLER.glob("*.csv"):
            if f.stem not in cats:
                warns.append(f"urunler/{f.name}: '{f.stem}' config.json'da kategori olarak tanımlı değil, atlandı")

    products, slugs = {}, set()
    for kat_key, kat in cats.items():
        path = URUNLER / f"{kat_key}.csv"
        if not path.exists():
            continue
        cols, rows, _ = read_table(path)
        ozk = {o["key"]: o for o in kat["ozellikler"]}
        for c in cols:
            if c and c not in TEMEL_SUTUNLAR and c not in ozk:
                warns.append(f"urunler/{kat_key}.csv: '{c}' sütunu config.json'da tanımlı değil, gösterilmeyecek")
        for i, r in enumerate(rows, start=2):
            w = f"urunler/{kat_key}.csv satır {i}"
            pid = r.get("id", "")
            if not pid:
                errors.append(f"{w}: id boş")
                continue
            if not (pid.isascii() and pid.isalnum()):
                errors.append(f"{w}: id '{pid}' yalnızca harf ve rakam içermeli (örn. P01)")
            if pid in products:
                errors.append(f"{w}: id '{pid}' başka bir ürün dosyasında da var; id'ler tüm dosyalarda tek olmalı")
                continue
            ad = f"{r.get('marka', '')} {r.get('model', '')}".strip()
            if not ad:
                errors.append(f"{w}: marka ve model boş")
                continue
            slug = slugify(ad)
            if slug in slugs:
                errors.append(f"{w}: '{ad}' adı başka bir ürünle aynı adresi üretiyor; modeli ayırt edecek şekilde yaz")
            slugs.add(slug)
            specs = {}
            for o in kat["ozellikler"]:
                raw = (r.get(o["key"]) or "").strip()
                if raw == "":
                    specs[o["key"]] = None
                elif o["tip"] == "sayi":
                    specs[o["key"]] = parse_num(raw, o["key"], w, errors)
                elif o["tip"] == "evet_hayir":
                    if raw not in ("0", "1"):
                        errors.append(f"{w}: '{o['key']}' 0 veya 1 olmalı")
                    specs[o["key"]] = raw == "1"
                else:
                    specs[o["key"]] = raw
            products[pid] = {
                "id": pid, "kategori": kat_key, "marka": r.get("marka", ""), "model": r.get("model", ""),
                "ad": ad, "slug": slug, "path": f"urun/{slug}/", "ara": ascii_ara(ad),
                "specs": specs, "ozet": spec_ozet(specs, kat),
                "gtin": r.get("gtin", ""), "aciklama": r.get("aciklama", ""),
            }

    offers = []
    for i, r in enumerate(orow, start=2):
        w = f"offers.csv satır {i}"
        oid, pid, sid = r.get("id", ""), r.get("urun_id", ""), r.get("satici_id", "")
        if not oid:
            errors.append(f"{w}: id boş")
            continue
        if pid not in products:
            errors.append(f"{w}: urun_id '{pid}' hiçbir ürün dosyasında yok")
            continue
        if sid not in sellers:
            errors.append(f"{w}: satici_id '{sid}' sellers.csv içinde yok")
            continue
        fraw = (r.get("fiyat_tl") or "").strip()
        if not fraw:
            errors.append(f"{w}: fiyat_tl boş olamaz")
            continue
        fiyat = parse_num(fraw, "fiyat_tl", w, errors)
        kraw = (r.get("kargo_tl") or "").strip()
        kargo = parse_num(kraw, "kargo_tl", w, errors) if kraw else None  # boş = bilinmiyor
        if fiyat is None or (kraw and kargo is None):
            continue
        if fiyat < 100:
            warns.append(f"{w}: fiyat {fiyat:g} çok düşük; nokta/virgül karışmış olabilir (26990 gibi yaz)")
        gt = r.get("garanti_tipi") or "belirsiz"
        if gt not in cfg["garanti_tipleri"]:
            errors.append(f"{w}: garanti_tipi '{gt}' geçersiz ({', '.join(cfg['garanti_tipleri'])})")
            continue
        stok = r.get("stok", "1") or "1"
        if stok not in ("0", "1"):
            errors.append(f"{w}: stok 0 veya 1 olmalı")
            continue
        try:
            d = datetime.strptime(r.get("son_kontrol", ""), "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"{w}: son_kontrol YYYY-AA-GG biçiminde olmalı (örn. 2026-11-26)")
            continue
        gun = (today - d).days
        if gun < 0:
            warns.append(f"{w}: son_kontrol gelecekte görünüyor")
            gun = 0
        araw = (r.get("garanti_ay") or "").strip()
        ay = parse_num(araw, "garanti_ay", w, errors) if araw else None
        o = {
            "id": oid, "urun_id": pid, "satici": sellers[sid], "url": r.get("url", ""),
            "fiyat": fiyat, "kargo": kargo, "kargo_bilinmiyor": kargo is None,
            "toplam": fiyat + (kargo or 0.0),
            "garanti_tipi": gt, "garanti_ay": int(ay) if ay else None,
            "stok": stok == "1", "son_kontrol": d, "gun": gun, "not": r.get("not", ""),
        }
        o["eski"] = gun > cfg["stale_days_exclude"]
        o["gecerli"] = o["stok"] and not o["eski"]
        if gun <= cfg["fresh_days"]:
            o["kontrol_sinifi"] = "taze"
        elif gun <= cfg["stale_days_warn"]:
            o["kontrol_sinifi"] = "orta"
        elif gun <= cfg["stale_days_exclude"]:
            o["kontrol_sinifi"] = "uyari"
        else:
            o["kontrol_sinifi"] = "eski"
        offers.append(o)

    hist = {}
    for i, r in enumerate(hrow, start=2):
        w = f"price_history.csv satır {i}"
        try:
            d = datetime.strptime(r.get("tarih", ""), "%Y-%m-%d").date()
            v = float((r.get("toplam_tl") or "").replace(",", "."))
        except ValueError:
            errors.append(f"{w}: tarih (YYYY-AA-GG) veya toplam_tl hatalı")
            continue
        hist.setdefault(r.get("offer_id", ""), []).append((d, v))
    for k in hist:
        hist[k].sort()

    if errors:
        raise DataError("\n".join(errors))
    return products, sellers, offers, hist, warns


# ---------------------------------------------------------------- hesaplar
def daily_series(hists, start, end):
    n = len(hists)
    ptr, last = [0] * n, [None] * n
    out = []
    d = start
    while d <= end:
        for i, h in enumerate(hists):
            while ptr[i] < len(h) and h[ptr[i]][0] <= d:
                last[i] = h[ptr[i]][1]
                ptr[i] += 1
        vals = [v for v in last if v is not None]
        out.append((d, min(vals) if vals else None))
        d += timedelta(days=1)
    return out


def chart_svg(series, W=640, H=220):
    pts = [(d, v) for d, v in series if v is not None]
    if len(pts) < 2 or (pts[-1][0] - pts[0][0]).days < 7:
        return None
    padL, padR, padT, padB = 78, 16, 16, 30
    x0, x1 = pts[0][0], pts[-1][0]
    span = max((x1 - x0).days, 1)
    vals = [v for _, v in pts]
    vmin, vmax = min(vals), max(vals)
    lo, hi = vmin, vmax
    if lo == hi:
        lo, hi = lo - max(lo * 0.02, 50), hi + max(hi * 0.02, 50)
    pad = (hi - lo) * 0.14
    lo, hi = lo - pad, hi + pad

    def X(d):
        return padL + (d - x0).days / span * (W - padL - padR)

    def Y(v):
        return padT + (hi - v) / (hi - lo) * (H - padT - padB)

    path = [f"M{X(pts[0][0]):.1f} {Y(pts[0][1]):.1f}"]
    prev = pts[0][1]
    for d, v in pts[1:]:
        if v != prev:
            path.append(f"H{X(d):.1f} V{Y(v):.1f}")
            prev = v
    path.append(f"H{X(x1):.1f}")

    grid = []
    for v in sorted({vmin, vmax}):
        y = Y(v)
        grid.append(f'<line class="g" x1="{padL}" x2="{W - padR}" y1="{y:.1f}" y2="{y:.1f}"/>')
        grid.append(f'<text class="t" x="{padL - 10}" y="{y + 4:.1f}" text-anchor="end">{f_tl(v)}</text>')
    yb = H - 8
    lab = (f'<text class="t" x="{padL}" y="{yb}" text-anchor="start">{x0.day} {AYLAR_KISA[x0.month - 1]}</text>'
           f'<text class="t" x="{W - padR}" y="{yb}" text-anchor="end">{x1.day} {AYLAR_KISA[x1.month - 1]}</text>')
    last = pts[-1][1]
    label = (f"Son {span} günde en düşük toplam fiyat {f_tl(vmin)} ile {f_tl(vmax)} arasında değişti, "
             f"şu an {f_tl(last)}.")
    svg = (f'<svg class="grafik" viewBox="0 0 {W} {H}" role="img" aria-label="{label}">'
           f'{"".join(grid)}<path class="cizgi" d="{" ".join(path)}"/>'
           f'<circle class="nokta" cx="{X(x1):.1f}" cy="{Y(last):.1f}" r="4.5"/>{lab}</svg>')
    return Markup(svg)


def enrich(cfg, products, offers, hist, today):
    cats = cfg["categories"]
    by_prod = {}
    for o in offers:
        by_prod.setdefault(o["urun_id"], []).append(o)

    win = cfg["history_window_days"]
    dwin = cfg["drop_window_days"]

    for p in products.values():
        kat = cats[p["kategori"]]
        offs = by_prod.get(p["id"], [])
        gec = sorted([o for o in offs if o["gecerli"]],
                     key=lambda o: (o["toplam"], 1 if o["kargo_bilinmiyor"] else 0,
                                    0 if o["garanti_tipi"] == "resmi_uretici" else 1, o["gun"]))
        pas = sorted([o for o in offs if not o["gecerli"]], key=lambda o: o["toplam"])
        p["teklifler"] = gec + pas
        p["gecerli_teklifler"] = gec
        p["best"] = gec[0] if gec else None
        resmi = [o for o in gec if o["garanti_tipi"] == "resmi_uretici"]
        p["best_resmi"] = resmi[0] if resmi else None
        p["resmi_var"] = bool(resmi)
        p["etiket_en_dusuk"] = min(gec, key=lambda o: (o["fiyat"], o["toplam"])) if gec else None
        p["satici_sayisi"] = len(gec)
        p["fark_tl"] = p["fark_pct"] = None
        if len(gec) >= 2:
            p["fark_tl"] = gec[-1]["toplam"] - gec[0]["toplam"]
            p["fark_pct"] = p["fark_tl"] / gec[0]["toplam"] * 100
        p["resmi_fark"] = None
        if p["best"] and p["best_resmi"] and p["best_resmi"]["id"] != p["best"]["id"]:
            p["resmi_fark"] = p["best_resmi"]["toplam"] - p["best"]["toplam"]
        p["etiket_farki"] = None
        p["platformlar"] = sorted({o["satici"]["platform"] for o in gec if o["satici"]["platform"]})
        if (p["best"] and p["etiket_en_dusuk"] and p["etiket_en_dusuk"]["id"] != p["best"]["id"]
                and not p["etiket_en_dusuk"]["kargo_bilinmiyor"]):
            p["etiket_farki"] = p["etiket_en_dusuk"]["toplam"] - p["best"]["toplam"]

        # değer metriği (örn. TL/Wh, TL/inç)
        dg = kat.get("deger")
        dv = p["specs"].get(dg["key"]) if dg else None
        p["deger"] = (p["best"]["toplam"] / dv) if (dg and p["best"] and dv) else None

        # yasal / kullanım notu
        p["yasal_not"] = p["yasal_kisa"] = ""
        y = kat.get("yasal")
        yv = p["specs"].get(y["key"]) if y else None
        if y and yv is not None and yv > y["esik"]:
            p["yasal_not"] = y["not"].replace("{v}", f_num(yv))
            p["yasal_kisa"] = y.get("kisa", "")
        elif kat.get("genel_not"):
            p["yasal_not"] = kat["genel_not"]

        # fiyat geçmişi
        hs = [hist[o["id"]] for o in offs if o["id"] in hist]
        p["grafik"] = p["son30"] = p["dusus_pct"] = None
        if hs:
            first = min(h[0][0] for h in hs)
            start = max(today - timedelta(days=win - 1), first)
            series = daily_series(hs, start, today)
            p["grafik"] = chart_svg(series)
            recent = [v for d, v in series if v is not None and d >= today - timedelta(days=dwin)]
            known = [d for d, v in series if v is not None]
            if recent and known and (known[-1] - known[0]).days >= 7:
                p["son30"] = {"min": min(recent), "max": max(recent), "ort": sum(recent) / len(recent)}
            ref = next((v for d, v in series if d == today - timedelta(days=dwin) and v is not None), None)
            if ref and p["best"]:
                pct = (ref - p["best"]["toplam"]) / ref * 100
                if pct >= cfg["drop_min_pct"]:
                    p["dusus_pct"] = pct
                    p["dusus_tl"] = ref - p["best"]["toplam"]
    return products


# ---------------------------------------------------------------- çıktı
def make_link(depth, explicit):
    root = "../" * depth if depth else "./"

    def link(path=""):
        if path == "" or path.endswith("/"):
            return root + path + ("index.html" if explicit else "")
        return root + path
    return root, link


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="dosyadan açılabilir çıktı (index.html linkleri)")
    ap.add_argument("--today", help="YYYY-AA-GG (test için)")
    ap.add_argument("--out", default="dist")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    try:
        check_config(cfg)
        products, sellers, offers, hist, warns = load_catalog(cfg, today)
    except DataError as e:
        print("VERİ HATASI, site üretilmedi:\n" + str(e), file=sys.stderr)
        sys.exit(1)
    for w in warns:
        print("uyarı:", w)
    enrich(cfg, products, offers, hist, today)
    cats = cfg["categories"]

    out = ROOT / args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    for f in (ROOT / "static").iterdir():
        shutil.copy(f, out / "assets" / f.name)

    plist = sorted(products.values(), key=lambda p: (p["best"]["toplam"] if p["best"] else 1e12, p["ad"]))

    # yalnızca ürünü olan kategoriler sitede görünür
    aktif = []
    for key, kat in cats.items():
        lst = [p for p in plist if p["kategori"] == key]
        if not lst:
            continue
        farklar = [p["fark_pct"] for p in lst if p["fark_pct"] is not None]
        aktif.append({"key": key, "kat": kat, "urunler": lst, "sayi": len(lst),
                      "maks_fark": max(farklar) if farklar else None})

    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update(tl=f_tl, num=f_num, tarih=f_tarih, gun_once=f_gun_once)
    env.globals.update(cfg=cfg, demo=cfg["demo"], today=today, year=today.year,
                       explicit=args.preview, aktif=aktif, spec_deger=spec_deger)

    pages = []  # sitemap için

    def render(tpl, rel_dir, **ctx):
        depth = 0 if rel_dir == "" else len(Path(rel_dir).parts)
        root, link = make_link(depth, args.preview)
        if tpl == "404.html" and not args.preview:  # 404 her yoldan açılabilir: mutlak yol
            root, link = "/", (lambda path="": "/" + path)
        html = env.get_template(tpl).render(root=root, link=link, **ctx)
        target = out / rel_dir / "index.html" if tpl != "404.html" else out / "404.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        if tpl != "404.html":
            pages.append(rel_dir + ("/" if rel_dir else ""))

    # ana sayfa
    adaylar = sorted([p for p in plist if p["best"] and p["etiket_farki"]], key=lambda p: -p["etiket_farki"])
    if not adaylar:  # kargo farkı gösterecek örnek yoksa: iki pazaryerinde de satılan, teklifleri en çok ayrışan model
        adaylar = sorted([p for p in plist if p["satici_sayisi"] >= 3 and len(p["platformlar"]) >= 2],
                         key=lambda p: -(p["fark_tl"] or 0))
    fis = adaylar[0] if adaylar else next((p for p in plist if p["satici_sayisi"] >= 2), None)
    farkli = sorted([p for p in plist if p["fark_pct"] is not None], key=lambda p: -p["fark_pct"])[:6]
    dusenler = sorted([p for p in plist if p["dusus_pct"]], key=lambda p: -p["dusus_pct"])[:5]
    render("home.html", "", title=None, description=cfg["tagline"], fis=fis, farkli=farkli,
           dusenler=dusenler, canonical=cfg["base_url"] + "/")

    # kategori sayfaları
    for a in aktif:
        render("category.html", a["key"], title=a["kat"]["baslik"], description=a["kat"]["aciklama"],
               kat=a["kat"], kat_key=a["key"], urunler=a["urunler"], maks_fark=a["maks_fark"] or 1,
               canonical=f'{cfg["base_url"]}/{a["key"]}/')

    # ürün sayfaları
    for p in plist:
        kat = cats[p["kategori"]]
        benzer = [q for q in plist if q["kategori"] == p["kategori"] and q["id"] != p["id"] and q["best"]]
        if p["best"]:
            benzer.sort(key=lambda q: abs(q["best"]["toplam"] - p["best"]["toplam"]))
        ld = None
        if p["best"]:
            gec = p["gecerli_teklifler"]
            ld = json.dumps({
                "@context": "https://schema.org", "@type": "Product", "name": p["ad"],
                "brand": {"@type": "Brand", "name": p["marka"]},
                **({"gtin": p["gtin"]} if p["gtin"] else {}),
                "offers": {"@type": "AggregateOffer", "priceCurrency": "TRY",
                           "lowPrice": round(gec[0]["toplam"]), "highPrice": round(gec[-1]["toplam"]),
                           "offerCount": len(gec)},
            }, ensure_ascii=False).replace("</", "<\\/")
        desc = (f'{p["ad"]} için {p["satici_sayisi"]} teklif, kargo dahil en düşük {f_tl(p["best"]["toplam"])}.'
                if p["best"] else f'{p["ad"]} için güncel teklif yok.')
        render("product.html", p["path"].rstrip("/"), title=f'{p["ad"]} fiyatı', description=desc, p=p,
               kat=kat, kat_key=p["kategori"], benzer=benzer[:3],
               ld=Markup(ld) if ld else None, canonical=f'{cfg["base_url"]}/{p["path"]}')

    render("compare.html", "karsilastir", title="Modelleri karşılaştır",
           description="Aynı kategoriden seçtiğin modelleri özellik ve toplam fiyat olarak yan yana koy.",
           canonical=cfg["base_url"] + "/karsilastir/")
    render("about.html", "nasil-calisiyoruz", title="Nasıl çalışıyoruz",
           description="Toplam maliyet, garanti ve fiyat tazeliği nasıl hesaplanıyor.",
           canonical=cfg["base_url"] + "/nasil-calisiyoruz/")
    render("404.html", "", title="Sayfa bulunamadı", description="")

    # karşılaştırma verisi
    js = {
        "categories": {a["key"]: {
            "ad": a["kat"]["ad"],
            "deger": a["kat"].get("deger"),
            "ozellikler": [{k: o.get(k) for k in ("key", "ad", "birim", "tip", "iyi", "iddia")}
                           for o in a["kat"]["ozellikler"]],
        } for a in aktif},
        "products": [{
            "id": p["id"], "ad": p["ad"], "kategori": p["kategori"], "path": p["path"], "specs": p["specs"],
            "best": round(p["best"]["toplam"]) if p["best"] else None,
            "best_resmi": round(p["best_resmi"]["toplam"]) if p["best_resmi"] else None,
            "sellers": p["satici_sayisi"],
            "deger": round(p["deger"], 1) if p["deger"] else None,
        } for p in plist],
    }
    (out / "assets" / "data.js").write_text(
        "window.UCUZ=" + json.dumps(js, ensure_ascii=False) + ";", encoding="utf-8")

    # sitemap + robots
    base = cfg["base_url"].rstrip("/")
    urls = "".join(f"<url><loc>{base}/{p}</loc><lastmod>{today.isoformat()}</lastmod></url>" for p in pages)
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', encoding="utf-8")
    robots = ("User-agent: *\nDisallow: /\n" if cfg["demo"]
              else f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    (out / "robots.txt").write_text(robots, encoding="utf-8")
    if not args.preview and not cfg["demo"]:  # GitHub Pages özel alan adı
        from urllib.parse import urlparse
        (out / "CNAME").write_text(urlparse(base).hostname + "\n", encoding="utf-8")

    n_best = sum(1 for p in plist if p["best"])
    bos = [k for k in cats if k not in {a["key"] for a in aktif}]
    print(f"Tamam: {len(aktif)} kategori, {len(plist)} ürün ({n_best} tanesinin güncel fiyatı var), "
          f"{len(offers)} teklif, {len(pages)} sayfa → {out}")
    if bos:
        print("Ürünü olmadığı için gizlenen kategoriler:", ", ".join(bos))


if __name__ == "__main__":
    main()
