import base64
import logging
import os
import magic

from os import getenv
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from rapidfuzz import fuzz
from espo_api_client import EspoAPIError, EspoAPI

load_dotenv()

# CRM API Configuration
ESPO_API_KEY = getenv("ESPO_API_KEY")
ESPO_URL = "https://www.crm.alis-is.com"
client = EspoAPI(ESPO_URL, ESPO_API_KEY)


def create_attachment(
    paths: List[str], entity: str = "SupplierInvoice"
) -> List[str]:
    """
    Creates attachments in the CRM from a list of file paths.

    Args:
        paths (List[str]): List of file paths to be uploaded.
        entity (str): The entity to associate the attachments with.

    Returns:
        List[str]: List of created attachment IDs.
    """
    attachments_ids: List[str] = []
    for path in paths:
        file_name, file_extension = os.path.splitext(os.path.basename(path))

        mime_type: str = magic.Magic(mime=True).from_file(path)

        with open(path, "rb") as file:
            file_content = file.read()
            file_base64 = base64.b64encode(file_content).decode("utf-8")

        data = {
            "name": f"{file_name}{file_extension}",
            "type": mime_type,
            "role": "Attachment",
            "parentType": entity,
            "field": "attachments",
            "file": f"data:{mime_type};base64,{file_base64}",
        }
        attachment = client.request("POST", "Attachment", data)
        attachments_ids.append(attachment["id"])

    return attachments_ids


def relate_attachments(
    attachments_ids: List[str], entity_id: str, entity: str = "SupplierInvoice"
) -> Dict[str, Any]:
    """
    Relates attachments to a specified entity.

    Args:
        attachments_ids (List[str]): List of attachment IDs.
        entity_id (str): ID of the entity to relate attachments to.
        entity (str): Entity type.

    Returns:
        Dict[str, Any]: API response from the relation update.
    """
    data = {"attachmentsIds": attachments_ids}
    return client.request("PUT", f"{entity}/{entity_id}", data)


def get_entity(
    entity_type: str, field: str, value: str
) -> Optional[List[Dict[str, Any]]]:
    """
    Fetches entities matching specific criteria.

    Args:
        entity_type (str): Type of entity to search for.
        field (str): Field to filter entities by.
        value (str): Value to match the field against.

    Returns:
        Optional[List[Dict[str, Any]]]: List of matching entities.
    """
    params = {
        "select": field,
        "deleted": False,
        "where": [
            {"type": "equals", "attribute": field, "value": value},
            {"type": "equals", "attribute": "deleted", "value": False},
        ],
    }
    response = client.request("GET", entity_type, params)
    return response.get("list")


def get_company(
    name: Optional[str] = None,
    sic: Optional[str] = None,
    dic: Optional[str] = None,
    threshold: int = 80,
) -> Optional[Dict[str, Any]]:
    """
    Retrieves a company by name, SIC, or DIC code with fuzzy matching.

    Args:
        name (Optional[str]): Company name.
        sic (Optional[str]): SIC code.
        dic (Optional[str]): DIC code.
        threshold (int): Similarity threshold for fuzzy matching.

    Returns:
        Optional[Dict[str, Any]]: Matching company data or None.
    """
    companies = get_entities("Account")
    for company in companies:
        dic_code, sic_code, company_name = (
            company["dic"],
            company["sicCode"],
            company["name"],
        )
        similarity = fuzz.partial_ratio(name.lower(), company_name.lower()) if name else 0
        if (
            dic == dic_code
            or sic == sic_code
            or name == company_name
            or similarity >= threshold
        ):
            return company
    return None


def get_entities(entity: str, limit: int = 200) -> List[Dict[str, Any]]:
    """
    Retrieves all entities of a specific type from the CRM.

    Args:
        entity (str): Type of entity to retrieve.
        limit (int): Number of entities to retrieve per request.

    Returns:
        List[Dict[str, Any]]: List of entities.
    """
    all_entities: List[Dict[str, Any]] = []
    offset = 0

    while True:
        params = {"limit": limit, "offset": offset}
        response = client.request("GET", entity, params)
        entities = response.get("list", [])
        all_entities.extend(entities)
        if len(entities) < limit:
            break
        offset += limit

    return all_entities


def create_invoice_items(invoice_id: str, items: List[Dict[str, Any]]) -> None:
    """
    Creates invoice items for a given invoice.

    Args:
        invoice_id (str): ID of the invoice.
        items (List[Dict[str, Any]]): List of items to add to the invoice.
    """
    for item in items:
        payload = {
            "name": item["name"],
            "quantity": item["quantity"],
            "unitPrice": item["price"],
            "withTax": item["withTax"],
            "taxRate": item["taxRate"],
            "supplierInvoiceId": invoice_id,
        }
        try:
            client.request("POST", "SupplierInvoiceItem", payload)
        except EspoAPIError as e:
            logging.error(f"Error creating invoice item: {e}")


def create_invoice(data: Dict[str, Any], invoice_type: str = "SupplierInvoice") -> str:
    """
    Creates an invoice and associates items and company details.

    Args:
        data (Dict[str, Any]): Invoice data.
        invoice_type (str): Type of invoice to create.

    Returns:
        str: ID of the created invoice.
    """
    company = get_company(data.get("name"), data.get("sicCode"), data.get("vatId"))
    if company:
        data["accountId"] = company["id"]
        contact = get_entity("Contact", "accountId", company["id"])
        if contact:
            data["billingContactId"] = contact[0]["id"]

    invoice = client.request("POST", invoice_type, data)
    create_invoice_items(invoice["id"], data["invoiceItems"])
    return invoice["id"]
