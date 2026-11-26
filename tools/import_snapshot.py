#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Toplanan fiyat anlık görüntüsünü (data/kaynak/YYYY-AA-GG.json) sitenin CSV dosyalarına aktarır.

Kullanım:
  python tools/import_snapshot.py data/kaynak/2026-11-26.json

- Ürün dosyaları (data/urunler/<kategori>.csv) anlık görüntüdeki ürünlerle yeniden yazılır.
- offers.csv ve sellers.csv yeniden yazılır; teklif kimlikleri (ürün + platform + satıcı) sabittir,
  böylece aynı teklifin fiyat geçmişi birikir.
- price_history.csv'ye o günün fiyatları eklenir (eski kayıtlar korunur).

Anlık görüntü biçimi: her teklif
  [platform (TY/HB), satıcı, fiyat, kargo (0 = ücretsiz, null = bilinmiyor), garanti_tipi, garanti_ay, yol, not]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build import DATA, ROOT, URUNLER, read_table, slugify, write_table  # noqa: E402

PLATFORMLAR = {
    "TY": ("Trendyol", "https://www.trendyol.com"),
    "HB": ("Hepsiburada", "https://www.hepsiburada.com"),
}
RESMI_MAGAZA_IPUCU = ("resmi mağaza", "türkiye", "authorized")


def satici_tipi(ad, platform_adi):
    if ad.strip().lower() == platform_adi.lower():
        return "pazaryeri"
    if any(k in ad.lower() for k in RESMI_MAGAZA_IPUCU):
        return "uretici"
    return "magaza"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    snap = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    tarih = snap["tarih"]
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

    # ürün dosyaları
    by_kat = {}
    for u in snap["urunler"]:
        if u["kategori"] not in cfg["categories"]:
            sys.exit(f"{u['id']}: kategori '{u['kategori']}' config.json'da yok")
        by_kat.setdefault(u["kategori"], []).append(u)
    for kat, urunler in by_kat.items():
        keys = [o["key"] for o in cfg["categories"][kat]["ozellikler"]]
        rows = []
        for u in urunler:
            r = {"id": u["id"], "marka": u["marka"], "model": u["model"], "gtin": u.get("gtin", ""),
                 "aciklama": u.get("aciklama", "")}
            for k, v in u.get("specs", {}).items():
                if k not in keys:
                    sys.exit(f"{u['id']}: '{k}' özelliği {kat} kategorisinde tanımlı değil")
                r[k] = v
            rows.append(r)
        write_table(URUNLER / f"{kat}.csv", ["id", "marka", "model"] + keys + ["gtin", "aciklama"], rows)

    # satıcılar ve teklifler
    sellers, offers, hist_new = {}, [], []
    for u in snap["urunler"]:
        for plat, ad, fiyat, kargo, gt, ay, yol, notu in u["teklifler"]:
            p_ad, p_web = PLATFORMLAR[plat]
            sid = f"{plat}-{slugify(ad)}"
            sellers.setdefault(sid, {"id": sid, "ad": ad, "tip": satici_tipi(ad, p_ad), "web": "", "platform": p_ad})
            oid = f"{u['id']}-{plat}-{slugify(ad)}"
            if any(o["id"] == oid for o in offers):
                sys.exit(f"{oid}: aynı ürün için aynı satıcı iki kez var")
            offers.append({
                "id": oid, "urun_id": u["id"], "satici_id": sid, "url": p_web + yol,
                "fiyat_tl": f"{fiyat:g}", "kargo_tl": "" if kargo is None else f"{kargo:g}",
                "garanti_tipi": gt, "garanti_ay": ay or "", "stok": 1, "son_kontrol": tarih, "not": notu,
            })
            hist_new.append({"offer_id": oid, "tarih": tarih,
                             "toplam_tl": f"{fiyat + (kargo or 0):g}"})

    write_table(DATA / "sellers.csv", ["id", "ad", "tip", "platform", "web"], list(sellers.values()))
    write_table(DATA / "offers.csv", ["id", "urun_id", "satici_id", "url", "fiyat_tl", "kargo_tl", "garanti_tipi",
                                      "garanti_ay", "stok", "son_kontrol", "not"], offers)

    hpath = DATA / "price_history.csv"
    old = read_table(hpath)[1] if hpath.exists() else []
    keep = [h for h in old if (h["offer_id"], h["tarih"]) not in {(n["offer_id"], n["tarih"]) for n in hist_new}]
    write_table(hpath, ["offer_id", "tarih", "toplam_tl"], keep + hist_new)

    print(f"{len(snap['urunler'])} ürün, {len(offers)} teklif, {len(sellers)} satıcı aktarıldı ({tarih}).")


if __name__ == "__main__":
    main()
