# PDF OCR Master 📄➡️📊

Tento projekt slúži na lokálnu extrakciu textu a tabuliek z PDF dokumentov do formátov **Markdown, Excel a CSV**. Kombinuje tri špičkové open-source nástroje: **PaddleOCR**, **Marker** a **Docling**.

## 🛠️ Inštalácia a nastavenie

Projekt využíva `uv` pre rýchlu správu závislostí. Pre inicializáciu prostredia a inštaláciu všetkých knižníc použi:

```bash
uv sync
```

*Poznámka: Pri prvom spustení každého nástroja sa automaticky stiahnu potrebné AI modely (niekoľko GB).*

## 🚀 Použitie

Hlavným nástrojom je skript `ocr_master.py`. Spúšťa sa cez `uv run`.

### 1. PaddleOCR (Najlepšie pre tabuľky 📊)
Ideálne pre komplexné tabuľky s nepravidelným orámovaním alebo zložitými hlavičkami.

```bash
# Extrakcia z celého PDF (vytvorí Markdown + Excel + CSV)
uv run python ocr_master.py "cesta/k/dokumentu.pdf" --tool paddle --output vystup_paddle

# Extrakcia len konkrétnych strán (napr. 1, 3 a rozsah 5-10)
uv run python ocr_master.py "cesta/k/dokumentu.pdf" --tool paddle --pages 1,3,5-10 --output vystup_strany
```

### 2. Marker (Najlepšie pre čistý Markdown 📝)
Vynikajúce na prevod celých dokumentov, zachováva vzorce, nadpisy a obrázky v Markdown formáte.

```bash
uv run python ocr_master.py "cesta/k/dokumentu.pdf" --tool marker --output vystup_marker
```

### 3. Docling (Rýchla a moderná extrakcia ⚡)
Nový nástroj od IBM, veľmi stabilný pre štruktúrované PDF.

```bash
uv run python ocr_master.py "cesta/k/dokumentu.pdf" --tool docling --output vystup_docling
```

## 📂 Štruktúra výstupu (PaddleOCR)

Ak použiješ `--tool paddle`, v cieľovom priečinku nájdeš:
- `extracted_tables.md` – súhrnný súbor so všetkými nájdenými tabuľkami v Markdown formáte.
- Priečinky `page_X/` – obsahujú:
  - `*.xlsx` – tabuľky priamo v Exceli (každá tabuľka zvlášť).
  - `*.csv` – tabuľky v CSV formáte.
  - Vizualizáciu detekcie (obrázky).

## 💡 Tipy
- Ak máš **NVIDIA GPU**, proces bude výrazne rýchlejší.
- Pre tabuľky bez čiar (borderless) je **PaddleOCR** s voľbou `layout=True` najspoľahlivejšia voľba.
- Skript `ocr_master.py` môžeš ďalej upravovať podľa potreby.
