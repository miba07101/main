import os
import sys
import argparse
import pandas as pd
import numpy as np
from pdf2image import convert_from_path
import cv2
from tqdm import tqdm
import time
import glob
from pathlib import Path

# --- Nastavenia prostredia ---
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

# --- Dynamické Importy ---
def get_docling():
    try:
        from docling.document_converter import DocumentConverter
        return DocumentConverter()
    except Exception: return None

def get_marker():
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        return PdfConverter(artifact_dict=create_model_dict())
    except Exception: return None

class OCRLayoutEngine:
    def __init__(self):
        self.engine = None
        self.rapid_ocr = None
        self.rapid_table = None
        
        # 1. Skúsime PPStructureV3 (PaddleOCR 3.x)
        try:
            try:
                from paddleocr import PPStructure
                self.engine = PPStructure(show_log=False, use_openvino=True, structure_version='PP-StructureV2', lang='en', layout=True)
            except ImportError:
                # Ak nie, skúsime priamo V3 pipelinu z tvojho site-packages (PaddleOCR 3.0+)
                from paddleocr._pipelines.pp_structurev3 import PPStructureV3
                self.engine = PPStructureV3(show_log=False, use_openvino=True, lang='en')
            print("INFO: Inicializovaný PaddleOCR (PP-StructureV3)")
        except Exception as e:
            print(f"DEBUG: PaddleOCR v3 zlyhal ({e}), skúsime fallback na Rapid...")
            try:
                from rapidocr_onnxruntime import RapidOCR
                from rapid_table import RapidTable
                self.rapid_ocr = RapidOCR()
                self.rapid_table = RapidTable()
            except Exception as e2:
                print(f"ERROR: Žiadny OCR engine nie je dostupný: {e2}")

    def __call__(self, img):
        if self.engine:
            return self.engine(img)
        
        res = []
        if self.rapid_ocr:
            ocr_res, _ = self.rapid_ocr(img)
            if ocr_res:
                text = " ".join([line[1] for line in ocr_res])
                res.append({'type': 'text', 'res': [{'text': text}]})
        
        if self.rapid_table:
            table_res = self.rapid_table(img)
            html = getattr(table_res, 'table_html', getattr(table_res, 'html', None))
            if not html and isinstance(table_res, (list, tuple)) and len(table_res) > 0:
                html = table_res[0]
            if html:
                res.append({'type': 'table', 'res': {'html': html}})
        return res

def get_paddle_engines():
    engine = OCRLayoutEngine()
    return engine if (engine.engine or engine.rapid_ocr) else None

# --- Spracovateľské funkcie ---

def process_docling(pdf_path, output_base, pages):
    print(f"\n--- Docling: {os.path.basename(pdf_path)} ---")
    converter = get_docling()
    if not converter:
        print("Chyba: Docling nie je nainštalovaný.")
        return
    result = converter.convert(pdf_path)
    out_dir = Path(f"output_docling") / Path(pdf_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "document.md", "w", encoding="utf-8") as f:
        f.write(result.document.export_to_markdown())
    print(f"Výsledok v: {out_dir}")

def process_marker(pdf_path, output_base, pages):
    print(f"\n--- Marker: {os.path.basename(pdf_path)} ---")
    converter = get_marker()
    if not converter:
        print("Chyba: Marker nie je nainštalovaný.")
        return
    from marker.output import text_from_rendered
    rendered = converter(pdf_path)
    full_text, _, images = text_from_rendered(rendered)
    out_dir = Path(output_base) / Path(pdf_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "document.md", "w", encoding="utf-8") as f:
        f.write(full_text)
    
    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    for name, img in images.items():
        img.save(img_dir / name)
    print(f"Výsledok v: {out_dir}")

def process_paddle(pdf_path, output_base, pages, is_hybrid=False):
    tool_name = "hybrid" if is_hybrid else "paddle"
    pdf_name = Path(pdf_path).stem
    print(f"\n--- Paddle/Rapid OCR: {pdf_name}.pdf ---")
    
    engine = get_paddle_engines()
    if not engine:
        print("Chyba: Žiadny engine nie je k dispozícii.")
        return

    first = min(pages) if pages else 1
    last = max(pages) if pages else None
    images = convert_from_path(pdf_path, first_page=first, last_page=last)

    out_dir = Path(f"output_{tool_name}") / pdf_name
    table_out_dir = out_dir / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    table_out_dir.mkdir(parents=True, exist_ok=True)
    
    all_md = []
    
    for i, img in enumerate(tqdm(images, desc=f"Spracovanie ({tool_name})")):
        page_num = pages[i] if pages else i + 1
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        
        regions = engine(img_cv)
        page_md = [f"## Strana {page_num}\n"]
        
        if isinstance(regions, list):
            for j, region in enumerate(regions):
                if isinstance(region, list): # Standard OCR
                    for line in region:
                        if isinstance(line, list) and len(line) > 1:
                            text = line[1][0]
                            page_md.append(f"{text}\n")
                    continue
                    
                if not isinstance(region, dict): continue
                r_type = region.get('type', '').lower()
                res = region.get('res', {})
                
                if r_type == 'table':
                    html = res.get('html')
                    if html:
                        try:
                            dfs = pd.read_html(html)
                            if dfs:
                                df = dfs[0]
                                base_fn = f"p{page_num}_t{j}"
                                df.to_excel(table_out_dir / f"{base_fn}.xlsx", index=False)
                                try: df.to_excel(table_out_dir / f"{base_fn}.ods", engine='odf', index=False)
                                except: pass
                                df.to_csv(table_out_dir / f"{base_fn}.csv", index=False, encoding='utf-8-sig')
                                page_md.append(f"\n### Tabuľka {j}\n{df.to_markdown(index=False)}\n")
                        except Exception as e:
                            print(f"Chyba tabuľky: {e}")
                
                elif r_type in ['text', 'header', 'footer']:
                    text_lines = res
                    if isinstance(text_lines, list):
                        text = " ".join([line.get('text', '') if isinstance(line, dict) else str(line) for line in text_lines])
                        page_md.append(f"{text}\n")
                    elif isinstance(text_lines, str):
                        page_md.append(f"{text_lines}\n")
                
                elif r_type == 'formula':
                    formula_text = res.get('text', '')
                    page_md.append(f"\n$${formula_text}$$\n")

        all_md.append("\n".join(page_md))

    md_file = out_dir / "extracted_content.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n\n---\n\n".join(all_md))
    print(f"Hotovo. Výsledky v: {out_dir}")

def show_menu():
    print("\n" + "="*40)
    print("      PDF OCR MASTER - MENU")
    print("="*40)
    print("1. Docling (IBM - Dobré na layout)")
    print("2. Marker (VikT0R - Najlepšie na vzorce a text)")
    print("3. PaddleOCR (Stabilný RapidOCR - Najlepšie na tabuľky)")
    print("4. Hybrid (Marker pre text + Paddle pre tabuľky)")
    print("5. Exit")
    print("="*40)
    return input("Vyber si možnosť (1-5): ")

def get_page_selection():
    val = input("Spracovať všetky strany? (y/n): ").lower()
    if val == 'y':
        return None
    else:
        pages_input = input("Zadaj strany/rozsah (napr. 1,3,5-10): ")
        pages = []
        try:
            for part in pages_input.split(','):
                if '-' in part:
                    s, e = map(int, part.split('-'))
                    pages.extend(range(s, e + 1))
                else:
                    pages.append(int(part))
            return pages
        except:
            print("Neplatný formát, spracujem všetky strany.")
            return None

def main():
    while True:
        choice = show_menu()
        if choice == '5':
            print("Maj sa!")
            break
        
        pdf_files = glob.glob("input_pdf/*.pdf")
        if not pdf_files:
            print("\n!!! Chyba: V priečinku 'input_pdf/' nie sú žiadne PDF súbory.")
            input("Stlač Enter pre návrat do menu...")
            continue
        
        pages = get_page_selection()
        
        for pdf in pdf_files:
            if choice == '1':
                process_docling(pdf, "output_docling", pages)
            elif choice == '2':
                process_marker(pdf, "output_marker", pages)
            elif choice == '3':
                process_paddle(pdf, "output_paddle", pages)
            elif choice == '4':
                process_marker(pdf, "output_hybrid", pages)
                process_paddle(pdf, "output_hybrid", pages, is_hybrid=True)
            else:
                print("Neplatná voľba.")
                break
        
        print("\nSpracovanie dokončené.")
        input("Stlač Enter pre návrat do menu...")

if __name__ == "__main__":
    main()
