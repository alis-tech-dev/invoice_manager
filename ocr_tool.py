import json
import logging
import re
from typing import List, Dict, Any, Union

import cv2
import magic
import pdfplumber
import pytesseract
import requests
from dateutil.parser import parse as parse_date
from data import PROMPT, FUNCTIONS, OPENAI_API_KEY


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts text from a PDF file. Falls back to OCR if text extraction fails.

    Args:
        pdf_path (str): Path to the PDF file.

    Returns:
        str: Extracted text.
    """
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
            else:
                page_image = page.to_image(resolution=300)
                pil_image = page_image.original
                ocr_text = pytesseract.image_to_string(pil_image, lang="eng+ces")
                text += ocr_text + "\n"
    return text


def extract_text_from_image(image_path: str) -> str:
    """
    Extracts text from an image file using OCR.

    Args:
        image_path (str): Path to the image file.

    Returns:
        str: Extracted text.
    """
    image = preprocess_image(image_path)
    return pytesseract.image_to_string(image, lang="eng+ces")


def preprocess_image(image_path: str) -> Any:
    """
    Preprocesses an image to improve OCR accuracy.

    Args:
        image_path (str): Path to the image file.

    Returns:
        Any: Preprocessed image.
    """
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    denoised = cv2.medianBlur(thresh, 3)
    return denoised


def clean_text(text: str) -> str:
    """
    Cleans and standardizes text by removing extra whitespace.

    Args:
        text (str): Raw text.

    Returns:
        str: Cleaned text.
    """
    return re.sub(r"\s+", " ", text).strip()


def standardize_date(date_str: Union[str, None]) -> str:
    """
    Converts a date string into a standardized YYYY-MM-DD format.

    Args:
        date_str (Union[str, None]): Date string to standardize.

    Returns:
        str: Standardized date or "none" if parsing fails.
    """
    try:
        if date_str:
            date_obj = parse_date(date_str, dayfirst=True, fuzzy=True)
            return date_obj.strftime("%Y-%m-%d")
    except Exception as error:
        logging.error(f"Error parsing date: {error}")
    return "none"


def get_payload(paths_list: List[str]) -> List[Dict[str, Any]]:
    """
    Processes a list of files, extracts invoice data, and structures it as JSON.

    Args:
        paths_list (List[str]): List of file paths to process.

    Returns:
        List[Dict[str, Any]]: List of structured invoice data.
    """
    result = []

    for file_path in paths_list:
        mime = magic.Magic(mime=True)
        mime_type = mime.from_file(file_path)
        file_type, file_format = mime_type.split("/")

        text = None
        if file_format == "pdf":
            text = extract_text_from_pdf(file_path)
        elif file_type == "image":
            text = extract_text_from_image(file_path)

        if not text:
            logging.error(f"Failed to extract text from: {file_path}")
            continue

        api_payload = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You extract data from invoices and provide "
                        "structured JSON output."
                    ),
                },
                {"role": "user", "content": PROMPT + clean_text(text)},
            ],
            "functions": FUNCTIONS,
            "function_call": {"name": "extract_invoice_data"},
            "temperature": 0.0,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        }

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=api_payload,
        )

        if response.status_code == 200:
            response_data = response.json()
            assistant_reply = response_data["choices"][0]["message"]

            if "function_call" in assistant_reply:
                arguments = assistant_reply["function_call"]["arguments"]
                final_data = json.loads(arguments)

                date_fields = [
                    "dateInvoiced",
                    "dateOfReceiving",
                    "datePaid",
                    "dueDate",
                ]
                for field in date_fields:
                    final_data[field] = standardize_date(final_data.get(field))

                final_data["path"] = file_path
                result.append(final_data)
            else:
                logging.error("No function call in assistant's reply.")
                logging.error(f"Assistant's reply: {assistant_reply}")
        else:
            logging.error(f"API call failed with status: {response.status_code}")
            logging.error(response.text)

    return result


if __name__ == "__main__":
    payload = get_payload(["attachments/130_4.pdf"])
    logging.info(f"Processed payload: {payload}")
