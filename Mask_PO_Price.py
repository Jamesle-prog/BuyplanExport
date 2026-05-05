import os
import fitz  # PyMuPDF

# Define the input and output directories
input_dir = '/mnt/data/pdf_folder'
output_dir = '/mnt/data/pdf_folder_masked'

# Create the output directory if it doesn't exist
os.makedirs(output_dir, exist_ok=True)

# Iterate through each PDF file in the input directory
for filename in os.listdir(input_dir):
    if filename.endswith('.pdf'):
        input_pdf_path = os.path.join(input_dir, filename)
        output_pdf_path = os.path.join(output_dir, filename)

        # Open the PDF document
        pdf_document = fitz.open(input_pdf_path)

        # Iterate through each page
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            text = page.get_text("text")

            # Search for all prices in the format "0.00"
            words = page.get_text("words")
            price_pattern = r'\d+\.\d{2}'

            for word in words:
                if fitz.re.search(price_pattern, word[4]):
                    # Mask the price with a white rectangle
                    rect = fitz.Rect(word[:4])
                    page.add_redact_annot(rect, fill=(1, 1, 1))  # white color

            # Apply the redactions
            page.apply_redactions()

        # Save the modified PDF to a new file
        pdf_document.save(output_pdf_path)

        # Close the PDF document
        pdf_document.close()
