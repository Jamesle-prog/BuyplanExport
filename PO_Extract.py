import fitz  # PyMuPDF
import re
import pandas as pd
# Function to extract data from a given PDF file
def extract_data_from_pdf(pdf_path):
    pdf_document = fitz.open(pdf_path)
    data = []
    # Regular expression patterns for different pieces of information
    po_number_pattern = re.compile(r'PO NUMBER\s+(\w+)')
    style_pattern = re.compile(r'STYLE#\s+(\w+)')
    color_pattern = re.compile(r'(\w+/\w+(?:\s\w+)?)')
    size_pattern = re.compile(r'(XS|S|M|L|XL|1X|2X|3X|PS|PM|PL|PXL)')
    units_pattern = re.compile(r'(\d+)\s+(\d{12})') # Captures units and UPC
    total_units_pattern = re.compile(r'TTL\s+(\d+)')
    for page_number in range(len(pdf_document)):
        page = pdf_document.load_page(page_number)
        text = page.get_text()
        # Extract the PO number
        po_number_match = po_number_pattern.search(text)
        po_number = po_number_match.group(1) if po_number_match else None
        # Extract the style number
        style_match = style_pattern.search(text)
        style = style_match.group(1) if style_match else None
        # Extract colors, sizes, units, and UPCs
        # Start searching after the line that starts with "LN#"
        lines = text.splitlines()
        start_searching = False
        current_color = None

        for line in lines:
            if line.startswith("LN#"):
                start_searching = True
                continue

            if start_searching:
                if color_match := color_pattern.search(line):
                    current_color = color_match.group(1)
                if size_match := size_pattern.search(line):
                    size = size_match.group(1)
                    units_match = units_pattern.search(line)
                    if units_match:
                        units = int(units_match.group(1))
                        upc = units_match.group(2)
                        data.append([po_number, style, current_color, size, units, upc])

    return data


# List of PDF files to process
pdf_files = [
    "D:/Users/Desktop/data/CKHHP2598 M1XHL824 3994pcs-BOSCOV'S.pdf",
    "D:/Users/Desktop/data/CKHHP2599 M5VHL825 3092pcs-BOSCOV'S.pdf",
    "D:/Users/Desktop/data/CKHHP2600 M5VHL825-3400-Stock.pdf",
    "D:/Users/Desktop/data/CKHHP2601 M3VHC824 780pcs-BOSCOV'S.pdf",
    "D:/Users/Desktop/data/CKHHP2603K-K1HHL084 88200pcs-Ross.pdf",
    "D:/Users/Desktop/data/CKHHP2604K K1HHL821 19200pcs-Ross.pdf",
    "D:/Users/Desktop/data/CKHHP2605K N1HHL821 6000pcs-Ross.pdf",
    "D:/Users/Desktop/data/CKHHP2606K Q2VHL868 3000pcs-Ross.pdf",
    "D:/Users/Desktop/data/CKHHP2607K K1HHL871 44100pcs-Ross.pdf",
    "D:/Users/Desktop/data/CKHHP2608K Q1HHL084 6000pcs-Ross.pdf"
]
# Initialize an empty DataFrame to store all data
all_data = []
# Process each PDF file and append data to the DataFrame
for pdf_file in pdf_files:
    all_data.extend(extract_data_from_pdf(pdf_file))
# Convert the extracted data into a pandas DataFrame
df = pd.DataFrame(all_data, columns=['PO Number', 'Style', 'Color', 'Size', 'Units', 'UPC'])
# Save the DataFrame to a CSV file
output_csv_path = 'D:/Users/Desktop/data/all_extracted_data_v2.csv'
df.to_csv(output_csv_path, index=False)
# Provide the path to the CSV file for download


