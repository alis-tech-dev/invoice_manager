import email
import imaplib
import logging
import os
import random
import time
from os import getenv
from typing import Optional, List, Union

from dotenv import load_dotenv
from crm_request import (
    create_attachment,
    relate_attachments,
    create_invoice,
)
from ocr_tool_anthropic import get_payload

load_dotenv()

EMAIL_PASSWORD = getenv("EMAIL_PASSWORD")
EMAIL_LOGIN = getenv("EMAIL_LOGIN")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            "/crm/invoice_reader.log"
        ),
    ],
)


def get_messages() -> None:
    """
    Connects to the email server, fetches messages with the subject 'invoice',
    processes attachments, and creates invoices.
    """
    mail: Optional[imaplib.IMAP4_SSL] = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_LOGIN, EMAIL_PASSWORD)
        mail.select("inbox")

        status, messages = mail.search(None, "(SUBJECT 'invoice')")
        set_invoice(get_message(mail, status, messages))

    except imaplib.IMAP4.error as e:
        logging.error(f"IMAP error: {e}")
    except Exception as e:
        logging.error(f"General error: {e}")
    finally:
        if mail:
            try:
                mail.logout()
            except Exception as error:
                logging.info(error)


def get_message(
    mail: imaplib.IMAP4_SSL,
    status: str,
    messages: Union[List[bytes], List[str]],
) -> Optional[List[str]]:
    """
    Retrieves the latest email messages and extracts file attachments.

    Args:
        mail (imaplib.IMAP4_SSL): IMAP mail client instance.
        status (str): Status of the message search.
        messages (Union[List[bytes], List[str]]): List of message IDs.

    Returns:
        Optional[List[str]]: List of file paths to the downloaded attachments.
    """
    message: Optional[email.message.Message] = None
    if status == "OK" and messages[0]:
        for num in messages[0].split():
            status, msg_data = mail.fetch(num, "(RFC822)")
            if status == "OK":
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        message = email.message_from_bytes(response_part[1])
                        logging.info(f"Invoice from: {message.get('From')}")
                mail.store(num, "+FLAGS", "\\Deleted")
        mail.expunge()
    return get_paths(message) if message else None


def get_paths(message: email.message.Message) -> List[str]:
    """
    Extracts file attachments from an email message and saves them locally.

    Args:
        message (email.message.Message): Email message object.

    Returns:
        List[str]: List of normalized file paths to saved attachments.
    """
    file_paths: List[str] = []
    if message.is_multipart():
        for part in message.walk():
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    salt = random.randint(100, 999)
                    file_name = f"{salt}_{filename}"

                    os.makedirs("attachments", exist_ok=True)
                    file_path = os.path.join("attachments", file_name)

                    with open(file_path, "wb") as f:
                        f.write(part.get_payload(decode=True))
                    file_paths.append(file_path)
    return [os.path.normpath(path) for path in file_paths]


def set_invoice(paths: Optional[List[str]]) -> None:
    """
    Processes file paths to create invoices and relate attachments.

    Args:
        paths (Optional[List[str]]): List of file paths to process.
    """
    if paths:
        payload_list = get_payload(paths)
        for payload in payload_list:
            for key, value in payload.items():
                if value == "none":
                    payload[key] = None
                if key == "paymentMethod" and payload[key] is None:
                    payload[key] = "draft"

            paths_for_invoice = payload["path"]
            invoice_id = create_invoice(payload)
            attachments_ids = create_attachment([paths_for_invoice])
            invoice = relate_attachments(attachments_ids, invoice_id)
            if invoice.get("attachmentsIds"):
                os.remove(paths_for_invoice)


if __name__ == "__main__":
    while True:
        get_messages()
        time.sleep(60)
