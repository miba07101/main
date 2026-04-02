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
import camelot
import pdfplumber


def get_docling():
    try:
        from docling.document_converter import DocumentConverter

        return DocumentConverter()
    except Exception:
        return None


def get_marker():
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict

        return PdfConverter(artifact_dict=create_model_dict())
    except Exception:
        return None


def process_docling(pdf_path, output_base, pages):
    print(f"\n--- Docling: {os.path.basename(pdf_path)} ---")
    converter = get_docling()
    if not converter:
        print("ERROR: Docling is not installed.")
        return

    print("Processing document...")

    page_range = None
    if pages:
        page_range = (min(pages), max(pages))

    result = converter.convert(pdf_path, page_range=page_range)

    out_dir = Path(f"output_docling") / Path(pdf_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    md_content = result.document.export_to_markdown()

    with open(out_dir / "document.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Results in: {out_dir}")


def process_marker(pdf_path, output_base, pages):
    print(f"\n--- Marker: {os.path.basename(pdf_path)} ---")
    converter = get_marker()
    if not converter:
        print("ERROR: Marker is not installed.")
        return
    from marker.output import text_from_rendered

    print("Processing PDF with Marker...")
    rendered = converter(pdf_path)
    full_text, _, images = text_from_rendered(rendered)
    out_dir = Path(output_base) / Path(pdf_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "document.md", "w", encoding="utf-8") as f:
        f.write(full_text)

    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    print("Saving images...")
    for name, img in tqdm(images.items(), desc="Saving images", unit="image"):
        img.save(img_dir / name)
    print(f"Results in: {out_dir}")


def process_docling_tables(pdf_path, pages=None):
    print(f"\n--- Docling Tables: {os.path.basename(pdf_path)} ---")
    from docling.document_converter import DocumentConverter

    print("Processing document with progress...")
    converter = DocumentConverter()

    page_range = None
    if pages:
        page_range = (min(pages), max(pages))

    conv_res = converter.convert(pdf_path, page_range=page_range)

    out_dir = Path("output_docling_tables") / Path(pdf_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    all_tables = list(conv_res.document.tables)

    tables_to_process = [(i + 1, table) for i, table in enumerate(all_tables)]

    tables_found = 0
    for table_ix, table in tqdm(
        tables_to_process, desc="Extracting tables", unit="table"
    ):
        table_df: pd.DataFrame = table.export_to_dataframe(doc=conv_res.document)
        tables_found += 1

        csv_path = out_dir / f"table_{table_ix}.csv"
        table_df.to_csv(csv_path, index=False, sep=";")

        xlsx_path = out_dir / f"table_{table_ix}.xlsx"
        table_df.to_excel(xlsx_path, index=False)

    if tables_found == 0:
        print("No tables found in document.")
    else:
        print(f"Extracted {tables_found} table(s). Results in: {out_dir}")


def process_camelot(pdf_path, pages=None):
    print(f"\n--- Camelot: {os.path.basename(pdf_path)} ---")
    out_dir = Path("output_camelot") / Path(pdf_path).stem
    out_dir.mkdir(parents=True, exist_ok=True)

    pages_str = str(pages) if pages else "all"
    print(f"Scanning for tables with lattice mode (pages: {pages_str})...")

    tables = None

    try:
        tables = camelot.read_pdf(
            pdf_path, flavor="lattice", pages=pages_str, backend="poppler"
        )
    except Exception as e:
        print(f"Lattice mode failed: {str(e)[:100]}")

    if not tables or len(tables) == 0:
        print("Trying stream mode...")
        try:
            tables = camelot.read_pdf(
                pdf_path, flavor="stream", pages=pages_str, backend="poppler"
            )
        except Exception as e2:
            print(f"Stream mode also failed: {str(e2)[:100]}")

    if not tables or len(tables) == 0:
        print("Trying lattice with relaxed settings...")
        try:
            tables = camelot.read_pdf(
                pdf_path,
                flavor="lattice",
                pages=pages_str,
                backend="poppler",
                line_scale=15,
                threshold=0.1,
            )
        except Exception as e3:
            print(f"Relaxed lattice also failed: {str(e3)[:100]}")

    if not tables or len(tables) == 0:
        print("Trying pdfplumber fallback...")
        try:
            all_tables = []
            with pdfplumber.open(pdf_path) as pdf:
                pdf_pages = pdf.pages
                if pages:
                    pdf_pages = [
                        pdf_pages[p - 1] for p in pages if p - 1 < len(pdf_pages)
                    ]

                for page_idx, page in enumerate(
                    tqdm(pdf_pages, desc="Scanning pages", unit="page")
                ):
                    try:
                        page_tables = page.extract_tables()
                        if page_tables:
                            for table in page_tables:
                                if table and len(table) > 0:
                                    all_tables.append(
                                        {"page": page_idx + 1, "data": table}
                                    )
                    except Exception as pe:
                        continue

            if all_tables:
                tables = all_tables
            else:
                print("No tables found with pdfplumber.")
        except Exception as e4:
            print(f"pdfplumber also failed: {str(e4)[:100]}")
            print("No tables found.")
            return
        except Exception as e4:
            print(f"pdfplumber also failed: {str(e4)[:100]}")
            print("No tables found.")
            return

    if not tables or len(tables) == 0:
        print("No tables found.")
        return

    if isinstance(tables, list) and isinstance(tables[0], dict):
        for i, table_dict in enumerate(
            tqdm(tables, desc="Saving tables", unit="table")
        ):
            df = pd.DataFrame(table_dict["data"])
            csv_path = out_dir / f"table_{i + 1}.csv"
            df.to_csv(csv_path, index=False, sep=";")
            xlsx_path = out_dir / f"table_{i + 1}.xlsx"
            df.to_excel(xlsx_path, index=False)
        print(f"Extracted {len(tables)} table(s). Results in: {out_dir}")
    else:
        for i, table in tqdm(enumerate(tables), desc="Saving tables", unit="table"):
            csv_path = out_dir / f"table_{i + 1}.csv"
            table.df.to_csv(csv_path, index=False, sep=";")
            xlsx_path = out_dir / f"table_{i + 1}.xlsx"
            table.df.to_excel(xlsx_path, index=False)
        print(f"Extracted {len(tables)} table(s). Results in: {out_dir}")


def show_menu():
    print("\n" + "=" * 50)
    print("         PDF OCR MASTER - MENU")
    print("=" * 50)
    print("1. Docling (IBM - Good for layout)")
    print("2. Marker (VikT0R - Best for formulas and text)")
    print("3. Docling Tables Only")
    print("4. Camelot (Auto-detect lattice/stream)")
    print("5. Exit")
    print("=" * 50)
    return input("Choose option (1-5): ")


def get_page_selection():
    val = input("Process all pages? (y/n): ").lower()
    if val == "y":
        return None
    else:
        pages_input = input("Enter pages/range (e.g. 1,3,5-10): ")
        pages = []
        try:
            for part in pages_input.split(","):
                if "-" in part:
                    s, e = map(int, part.split("-"))
                    pages.extend(range(s, e + 1))
                else:
                    pages.append(int(part))
            return pages
        except:
            print("Invalid format, processing all pages.")
            return None


def main():
    while True:
        choice = show_menu()
        if choice == "5":
            print("Goodbye!")
            break

        pdf_files = glob.glob("input_pdf/*.pdf")
        if not pdf_files:
            print("\n!!! ERROR: No PDF files found in 'input_pdf/' directory.")
            input("Press Enter to return to menu...")
            continue

        pages = get_page_selection()

        for pdf in pdf_files:
            if choice == "1":
                process_docling(pdf, "output_docling", pages)
            elif choice == "2":
                process_marker(pdf, "output_marker", pages)
            elif choice == "3":
                process_docling_tables(pdf, pages)
            elif choice == "4":
                process_camelot(pdf, pages)
            else:
                print("Invalid option.")
                break

        print("\nProcessing completed.")
        input("Press Enter to return to menu...")


if __name__ == "__main__":
    main()
