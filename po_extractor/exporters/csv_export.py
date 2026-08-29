"""CSV outputs: by-size-color, summary, metadata."""
from dataclasses import asdict

import pandas as pd

from ..models import POData
from ..utils.file_utils import versioned_path
from ._excel_helpers import neutralise_csv_frame


def export_csvs(pos: list[POData], output_dir: str) -> dict[str, str]:
    size_rows = [
        [r.po_number, r.style, r.color, r.size, r.units, r.upc]
        for po in pos for r in po.size_rows
    ]
    summary_rows = [row for po in pos for row in po.summary_rows]
    metadata_rows = [asdict(po.metadata) for po in pos]

    df_size = pd.DataFrame(size_rows, columns=["PO Number", "Style", "Color", "Size", "Units", "UPC"])
    df_sum = pd.DataFrame(summary_rows, columns=["PO Number", "Style", "Color", "Hanger"])
    df_meta = pd.DataFrame(metadata_rows)

    p_size = versioned_path(output_dir, "all_extracted_data_by_size_color", ".csv")
    p_sum = versioned_path(output_dir, "all_extracted_data_summary", ".csv")
    p_meta = versioned_path(output_dir, "all_extracted_metadata", ".csv")

    # The files are download-only (never re-parsed as data), so neutralise
    # formula-injection triggers in the CSVs. The returned frames stay clean —
    # they feed the buy-plan exporter, which must see the real values.
    neutralise_csv_frame(df_size).to_csv(p_size, index=False)
    neutralise_csv_frame(df_sum).to_csv(p_sum, index=False)
    neutralise_csv_frame(df_meta).to_csv(p_meta, index=False)

    return {"by_size_color": p_size, "summary": p_sum, "metadata": p_meta,
            "df_size": df_size, "df_meta": df_meta}
