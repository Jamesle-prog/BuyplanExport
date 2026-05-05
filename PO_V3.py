import fitz  # PyMuPDF
import re
import pandas as pd
import os
import logging

# Set up logging
log_file_path = "D:/Users/Desktop/data/pdf_extraction_errors.log"
logging.basicConfig(filename=log_file_path, level=logging.ERROR, format='%(asctime)s %(message)s')

# Define Regular expression patterns
SIZE_PATTERN = r'(XXS|XS|S|M|L|XL|1X|2X|3X|PS|PM|PL|PXL|)'
PO_NUMBER_PATTERN = r'PO NUMBER\s+(\w+)'
STYLE_PATTERN = r'STYLE#\s+(.+)'
COLOR_PATTERN = r'(\w+(?:/\w+)+|\w+/\w+(?:\s\w+)?)'
UNITS_PATTERN = r'(\d+)\s+(\d{12})'  # Captures units and UPC
FULL_PATTERN = rf'{COLOR_PATTERN}\s+{SIZE_PATTERN}\s+{UNITS_PATTERN}'
LN_START = "LN#"
VENDOR_PATTERN = r'VENDOR\s+(\w+)'
ISSUED_BY_PATTERN = r'ISSUED BY\s+([a-zA-Z0-9.]+)'
PO_DATE_PATTERN = r'PO DATE\s+(\d{1,2}/\d{1,2}/\d{2,4})'
VEND_CNTRY_PATTERN = r'VEND CNTRY\s+(\w+(?:\s*-\s*\w+)?)'
FACTORY_PATTERN = r'FACTORY\s+(\d+)\s*-\s*([A-Z]+(?:\s[A-Z]+)*)(?=\s{2,}|$)'
HANGER_PATTERN = r'HANGER'
CNTRY_OF_ORIGIN_PATTERN = r'CNTRY OF ORIGIN\s+(\w+)'


def extract_metadata(text):
    """Extract metadata from the combined text."""
    metadata = {}
    metadata['PO Number'] = re.search(PO_NUMBER_PATTERN, text).group(1) if re.search(PO_NUMBER_PATTERN, text) else None
    metadata['Style'] = re.search(STYLE_PATTERN, text).group(1).strip() if re.search(STYLE_PATTERN, text) else None
    metadata['Vendor'] = re.search(VENDOR_PATTERN, text).group(1) if re.search(VENDOR_PATTERN, text) else None
    metadata['Issued By'] = re.search(ISSUED_BY_PATTERN, text).group(1) if re.search(ISSUED_BY_PATTERN, text) else None
    metadata['PO Date'] = re.search(PO_DATE_PATTERN, text).group(1) if re.search(PO_DATE_PATTERN, text) else None
    metadata['Vendor Country'] = re.search(VEND_CNTRY_PATTERN, text).group(1).strip() if re.search(VEND_CNTRY_PATTERN,
                                                                                                   text) else None
    factory_match = re.search(FACTORY_PATTERN, text)
    metadata['Factory'] = f"{factory_match.group(1)} - {factory_match.group(2).strip()}" if factory_match else None
    metadata['Country of Origin'] = re.search(CNTRY_OF_ORIGIN_PATTERN, text).group(1) if re.search(
        CNTRY_OF_ORIGIN_PATTERN, text) else None

    # Extract Hanger information
    hanger_match = re.search(HANGER_PATTERN, text)
    if hanger_match:
        hanger_start = hanger_match.end()
        hanger_line = text[hanger_start:].strip().split('\n')[0]
        metadata['Hanger'] = hanger_line.strip()
    else:
        metadata['Hanger'] = None

    return metadata


def extract_data_by_size_color(lines, metadata):
    """Extract data by size and color from the lines."""
    data_by_size_color = []
    data_summary = []
    start_searching = False
    current_color = None

    for line in lines:
        if line.startswith(LN_START):
            start_searching = True
            continue

        if start_searching:
            match = re.search(FULL_PATTERN, line)
            if match:
                color = match.group(1)
                size = match.group(2)
                units = int(match.group(3))
                upc = match.group(4)
                data_by_size_color.append([metadata['PO Number'], metadata['Style'], color, size, units, upc])
                current_color = color
            else:
                if "TTL" in line:
                    hanger = line.split("TTL")[0].strip()
                    data_summary.append([metadata['PO Number'], metadata['Style'], current_color, hanger])

                size_match = re.search(SIZE_PATTERN, line)
                if size_match:
                    size = size_match.group(1)
                    units_match = re.search(UNITS_PATTERN, line)
                    if units_match:
                        units = int(units_match.group(1))
                        upc = units_match.group(2)
                        data_by_size_color.append(
                            [metadata['PO Number'], metadata['Style'], current_color, size, units, upc])
    return data_by_size_color, data_summary


def extract_data_from_pdf(pdf_path):
    """Extract data from the given PDF file."""
    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as e:
        logging.error(f"Error opening PDF file {pdf_path}: {e}")
        return [], [], {}

    combined_text = ""
    for page_number in range(len(pdf_document)):
        try:
            page = pdf_document.load_page(page_number)
            text = page.get_text()
            combined_text += text + "\n"
        except Exception as e:
            logging.error(f"Error reading page {page_number} of {pdf_path}: {e}")
            continue

    metadata = extract_metadata(combined_text)
    lines = combined_text.splitlines()
    data_by_size_color, data_summary = extract_data_by_size_color(lines, metadata)

    return data_by_size_color, data_summary, metadata


def scan_folders_for_pdfs(folder_paths):
    """Scan folders for PDF files."""
    pdf_files = []
    for folder_path in folder_paths:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, file))
    return pdf_files


def get_next_versioned_filename(base_path, base_filename, extension):
    """Get the next versioned filename."""
    version = 1
    while True:
        output_filename = f"{base_filename}_v{version}{extension}"
        output_filepath = os.path.join(base_path, output_filename)
        if not os.path.exists(output_filepath):
            return output_filepath
        version += 1


# Specify the folder paths to scan for PDF files
folder_paths = [
    "D:/Users/Desktop/data",
    "D:/公司网盘/新庄源订单资料/2024/2.大货/1.CBCJ/Q3/3-44532/1.PO_BuyPlan",
    "D:\\公司网盘\\新庄源订单资料\\2024\\2.大货\\3.DKNY\\DKNY SPORTSWEAR\\Fall 24\\P4HHEXTF P4HHCXTF\\1.PO_BuyPlan",
    "D:\\公司网盘\\新庄源订单资料\2024\\2.大货\\3.DKNY\\DKNY SPORTSWEAR\\Fall 24\\P4HHDXTG P4HHCXTG\\1.PO_BuyPlan",
    "D:\\公司网盘\\新庄源订单资料\\2024\\2.大货\\3.DKNY\\DONNA KARAN  SPORTSWEAR\\Fall 24\\1.PO_BuyPlan",
]

# Scan the folders for PDF files
pdf_files = scan_folders_for_pdfs(folder_paths)

# Initialize an empty list to store all data
all_data_by_size_color = []
all_data_summary = []
all_metadata = []

# Process each PDF file and append data to the list
for pdf_file in pdf_files:
    extracted_data_by_size_color, extracted_data_summary, metadata = extract_data_from_pdf(pdf_file)
    if extracted_data_by_size_color:
        all_data_by_size_color.extend(extracted_data_by_size_color)
    if extracted_data_summary:
        all_data_summary.extend(extracted_data_summary)
    if metadata:
        all_metadata.append(metadata)

# Convert the extracted data into pandas DataFrames
df_by_size_color = pd.DataFrame(all_data_by_size_color, columns=['PO Number', 'Style', 'Color', 'Size', 'Units', 'UPC'])
df_summary = pd.DataFrame(all_data_summary, columns=['PO Number', 'Style', 'Color', 'Hanger'])
df_metadata = pd.DataFrame(all_metadata)

# Define the base path and filename for the output
base_path = "D:/Users/Desktop/data"
base_filename_by_size_color = "all_extracted_data_by_size_color"
base_filename_summary = "all_extracted_data_summary"
base_filename_metadata = "all_extracted_metadata"
extension = ".csv"

# Get the next versioned filenames
output_csv_path_by_size_color = get_next_versioned_filename(base_path, base_filename_by_size_color, extension)
output_csv_path_summary = get_next_versioned_filename(base_path, base_filename_summary, extension)
output_csv_path_metadata = get_next_versioned_filename(base_path, base_filename_metadata, extension)

# Save the DataFrames to versioned CSV files
df_by_size_color.to_csv(output_csv_path_by_size_color, index=False)
df_summary.to_csv(output_csv_path_summary, index=False)
df_metadata.to_csv(output_csv_path_metadata, index=False)

print(f"Data by Size and Color saved to: {output_csv_path_by_size_color}")
print(f"Summary Data saved to: {output_csv_path_summary}")
print(f"Metadata saved to: {output_csv_path_metadata}")
