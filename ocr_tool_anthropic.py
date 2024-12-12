import json
import logging
import re
from typing import List, Optional, Dict, Any

import cv2
import pdfplumber
import pytesseract
import anthropic
from dateutil.parser import parse as parse_date
import magic
from data import PROMPT, ANTHROPIC_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a PDF using pdfplumber. Falls back to OCR for images.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        str: Extracted text.
    """
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                logger.info(f"Processing page {page_num} of {len(pdf.pages)}")
                page_text = page.extract_text()

                if page_text and len(page_text.strip()) > 50:
                    text += page_text + "\n"
                else:
                    logger.info(f"Using OCR for page {page_num}")
                    page_image = page.to_image(resolution=300)
                    pil_image = page_image.original
                    ocr_text = pytesseract.image_to_string(pil_image, lang="eng+ces")
                    text += clean_text(ocr_text) + "\n"

        logger.info("PDF text extraction completed")
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise
    return text


def extract_text_from_image(image_path: str) -> str:
    """
    Extract text from an image file using OCR after preprocessing.

    Args:
        image_path (str): Path to the image file.

    Returns:
        str: Extracted text.
    """
    try:
        image = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Failed to load image: {image_path}")

        preprocessed = preprocess_image(image)
        text = pytesseract.image_to_string(preprocessed, lang="eng+ces")
        return clean_text(text)
    except Exception as e:
        logger.error(f"Error extracting text from image: {str(e)}")
        raise


def preprocess_image(image: Any) -> Any:
    """
    Preprocess an image for better OCR accuracy.

    Args:
        image (Any): Image to preprocess.

    Returns:
        Any: Preprocessed image.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11, 2
    )
    denoised = cv2.fastNlMeansDenoising(binary)
    return denoised


def clean_text(text: str) -> str:
    """
    Clean and normalize extracted text.

    Args:
        text (str): Raw text.

    Returns:
        str: Cleaned text.
    """
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('|', 'I')
    text = text.replace('l', '1')
    text = text.replace('O', '0')
    text = ''.join(char for char in text if char.isprintable())
    return text.strip()


def standardize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Standardize a date string to YYYY-MM-DD format.

    Args:
        date_str (Optional[str]): Date string.

    Returns:
        Optional[str]: Standardized date or None if invalid.
    """
    if not date_str or date_str.lower() in ['none', 'null', '']:
        return None
    try:
        date_obj = parse_date(date_str, dayfirst=True, fuzzy=True)
        return date_obj.strftime("%Y-%m-%d")
    except Exception as error:
        logger.error(f"Date parsing error for '{date_str}': {error}")
        return None


def get_payload(paths_list: List[str]) -> List[Dict[str, Any]]:
    """
    Process documents and extract structured invoice data using Claude API.

    Args:
        paths_list (List[str]): List of file paths to process.

    Returns:
        List[Dict[str, Any]]: List of structured invoice data.
    """
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

    client = anthropic.Client(api_key=ANTHROPIC_API_KEY)
    result = []

    for file_path in paths_list:
        try:
            logger.info(f"Processing file: {file_path}")
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(file_path)
            file_type, file_format = mime_type.split("/")

            if file_format == "pdf":
                text = extract_text_from_pdf(file_path)
            elif file_type == "image":
                text = extract_text_from_image(file_path)
            else:
                logger.error(f"Unsupported file type: {mime_type}")
                continue

            if not text.strip():
                logger.error(f"No text extracted from {file_path}")
                continue

            prompt = f"{anthropic.HUMAN_PROMPT}{PROMPT}\n\n{clean_text(text)}{anthropic.AI_PROMPT}"
            response = client.completions.create(
                model="claude-2",
                prompt=prompt,
                max_tokens_to_sample=4096,
                stop_sequences=[anthropic.HUMAN_PROMPT]
            )

            if hasattr(response, 'completion'):
                json_match = re.search(r'{[\s\S]*}', response.completion)
                if json_match:
                    final_data = json.loads(json_match.group(0))

                    if "dates" in final_data:
                        for date_field in final_data["dates"]:
                            final_data["dates"][date_field] = standardize_date(
                                final_data["dates"].get(date_field)
                            )

                    final_data["_source"] = {
                        "path": file_path,
                        "mime_type": mime_type,
                        "extraction_method": "ocr" if file_type == "image" else "text"
                    }
                    result.append(final_data)
                else:
                    logger.error("No JSON found in the response")
            else:
                logger.error("Response has no 'completion' attribute")

        except ValueError as error:
            logger.error(error)

        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
            logger.exception("Full traceback:")

    return result


if __name__ == "__main__":
    try:
        invoice_path = "invoices/4.pdf"
        logger.info(f"Starting processing of {invoice_path}")
        results = get_payload([invoice_path])

        if results:
            print("\nExtracted Invoice Data:")
            print(json.dumps(results, indent=2))
        else:
            print("\nNo results found")
    except Exception as e:
        logger.exception("Fatal error:")
