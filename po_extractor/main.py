"""CLI entry point."""
import argparse
import os
import sys

from .exporters import export_buyplan, export_csvs
from .parsers import parse_pdf
from .utils.file_utils import scan_pdfs
from .utils.price_mask import mask_prices_batch


def run(inputs: list[str], output_dir: str, fmt: str, recursive: bool,
        mask_prices: bool = False) -> int:
    os.makedirs(output_dir, exist_ok=True)
    pdfs = scan_pdfs(inputs, recursive=recursive)
    if not pdfs:
        print("No PDFs found.", file=sys.stderr)
        return 1

    # Extract data from originals first (prices needed for metadata)
    pos = []
    for pdf in pdfs:
        try:
            pos.append(parse_pdf(pdf))
            print(f"parsed: {pdf}")
        except Exception as e:
            print(f"  FAILED: {pdf} ({e})", file=sys.stderr)

    if not pos:
        return 1

    if fmt in ("flat", "all"):
        result = export_csvs(pos, output_dir)
        print(f"CSVs: {result['by_size_color']}")
        if fmt == "all":
            df_size, df_meta = result["df_size"], result["df_meta"]
    if fmt in ("buyplan", "all"):
        if fmt == "buyplan":
            result = export_csvs(pos, output_dir)
            df_size, df_meta = result["df_size"], result["df_meta"]
        path = export_buyplan(df_size, df_meta, output_dir)
        print(f"Buy plan: {path}")

    # Price masking runs last — saves masked copies to output/masked/
    if mask_prices:
        print(f"\nMasking prices in {len(pdfs)} PDF(s)...")
        mask_prices_batch(pdfs, output_dir)

    return 0


def main():
    p = argparse.ArgumentParser(prog="po_extractor")
    p.add_argument("--input", "-i", nargs="+", required=True, help="PDF file(s) or folder(s)")
    p.add_argument("--output", "-o", required=True, help="Output directory")
    p.add_argument("--format", "-f", choices=["flat", "buyplan", "all"], default="all")
    p.add_argument("--recursive", "-r", action="store_true")
    p.add_argument("--mask-prices", "-m", action="store_true",
                   help="Save price-redacted copies to output/masked/")
    args = p.parse_args()
    sys.exit(run(args.input, args.output, args.format, args.recursive,
                 mask_prices=args.mask_prices))


if __name__ == "__main__":
    main()
