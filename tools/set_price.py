#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bir teklifin fiyatını hızlıca güncelle. Fiyat geçmişini de kendisi yazar.

Örnekler:
  python tools/set_price.py T012 27990              fiyat 27.990 TL oldu, bugün kontrol edildi
  python tools/set_price.py T012 27990 --kargo 350  kargo da değişti
  python tools/set_price.py T012 --ayni             fiyat aynı; sadece "bugün kontrol ettim" de
  python tools/set_price.py T012 --stok-yok         stokta kalmadı
  python tools/set_price.py T012 --stok-var
  --tarih 2026-11-26                                 başka bir gün için kayıt (isteğe bağlı)
Fiyatı noktasız yaz: 27990 (27.990 değil).
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build import DATA, read_table, write_table  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("teklif_id")
    ap.add_argument("fiyat", nargs="?", type=float)
    ap.add_argument("--kargo", type=float)
    ap.add_argument("--ayni", action="store_true")
    ap.add_argument("--stok-yok", action="store_true")
    ap.add_argument("--stok-var", action="store_true")
    ap.add_argument("--tarih")
    a = ap.parse_args()

    if a.fiyat is None and not (a.ayni or a.stok_yok or a.stok_var or a.kargo is not None):
        ap.error("fiyat yaz ya da --ayni / --stok-yok / --stok-var / --kargo kullan")
    if a.fiyat is not None and a.fiyat < 500:
        ap.error(f"{a.fiyat:g} çok düşük görünüyor. Fiyatı noktasız yaz, örn. 27990")

    tarih = datetime.strptime(a.tarih, "%Y-%m-%d").date() if a.tarih else date.today()
    cols, rows, delim = read_table(DATA / "offers.csv")
    row = next((r for r in rows if r["id"] == a.teklif_id), None)
    if row is None:
        sys.exit(f"'{a.teklif_id}' offers.csv içinde yok.")

    eski = float(row["fiyat_tl"]) + float(row["kargo_tl"] or 0)
    if a.fiyat is not None:
        row["fiyat_tl"] = f"{a.fiyat:g}"
    if a.kargo is not None:
        row["kargo_tl"] = f"{a.kargo:g}"
    if a.stok_yok:
        row["stok"] = "0"
    if a.stok_var:
        row["stok"] = "1"
    row["son_kontrol"] = tarih.isoformat()
    yeni = float(row["fiyat_tl"]) + float(row["kargo_tl"] or 0)
    write_table(DATA / "offers.csv", cols, rows, delim)

    hcols, hrows, hdelim = read_table(DATA / "price_history.csv")
    var = [h for h in hrows if h["offer_id"] == a.teklif_id]
    if yeni != eski or not var:
        hrows = [h for h in hrows if not (h["offer_id"] == a.teklif_id and h["tarih"] == tarih.isoformat())]
        hrows.append({"offer_id": a.teklif_id, "tarih": tarih.isoformat(), "toplam_tl": f"{yeni:g}"})
        write_table(DATA / "price_history.csv", hcols or ["offer_id", "tarih", "toplam_tl"], hrows, hdelim)
        print(f"{a.teklif_id}: toplam {eski:,.0f} → {yeni:,.0f} TL, geçmişe yazıldı.")
    else:
        print(f"{a.teklif_id}: toplam {yeni:,.0f} TL aynı; kontrol tarihi {tarih.isoformat()} yapıldı.")


if __name__ == "__main__":
    main()
