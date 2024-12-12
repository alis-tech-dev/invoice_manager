from dotenv import load_dotenv
import os

load_dotenv()

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

PROMPT = """
You are provided with the text of an invoice below.
Extract the specified fields and provide them in JSON format.
Use python type None if the data is missing or unreadable.
Pay special attention to extracting the 'name' and billing address fields accurately.
Look for common labels like 'Bill To:', 'Invoice To:', 'Client:', or 'Sold To:'.

Fields:
- name (the company or individual the invoice is addressed to)
- billingAddressCity
- billingAddressCountry
- billingAddressPostalCode
- billingAddressState
- billingAddressStreet
- constantSymbol
- dateInvoiced (format: YYYY-MM-DD)
- dateOfReceiving (format: YYYY-MM-DD)
- datePaid (format: YYYY-MM-DD)
- deliveryNotes
- dueDate (format: YYYY-MM-DD)
- duzp
- grandTotalAmount (format: numeric, two decimal places)
- currency (format: ISO 4217 code, e.g., USD, EUR, GBP)
- note
- originalNumber
- paymentMethod (
    can be one of list:
        "draft","cash","postal",
        "delivery","creditcard",
        "advance","encashment",
        "cheque","compensation"
    )
- sicCode
- supplyCode
- taxAmount (format: numeric, two decimal places)
- taxRate (format: numeric, e.g., 21)
- variableSymbol
- vatId
- weight (format: numeric, include unit if available)
- amount (format: numeric, two decimal places)
- invoiceItems (each item should have quantity, unitPrice, taxRate)

Example Output:
{
    "name": "Company ABC",
    "billingAddressCity": "Prague",
    "billingAddressCountry": "Czech Republic",
    "billingAddressPostalCode": "11000",
    "billingAddressState": "Prague",
    "billingAddressStreet": "Wenceslas Square 1",
    "constantSymbol": "0308",
    "dateInvoiced": "2023-08-01",
    "dateOfReceiving": None,
    "datePaid": "2023-08-05",
    "deliveryNotes": "Handle with care",
    "dueDate": "2023-08-15",
    "duzp": "none",
    "grandTotalAmount": 960.00,
    "currency": "EUR",
    "note": "Thank you for your business",
    "originalNumber": "INV-2023-0001",
    "paymentMethod": "draft",
    "sicCode": "none",
    "supplyCode": "none",
    "taxAmount": 315.00,
    "taxRate": 21.0,
    "variableSymbol": "20230001",
    "vatId": "CZ12345678",
    "weight": "10 kg",
    "amount": 800.00,
    "invoiceItems": [
        {"quantity": 3, "unitPrice": 125.00, "taxRate": 21},
        {"quantity": 2, "unitPrice": 180.00, "taxRate": 19},
        {"quantity": 1, "unitPrice": 225.00, "taxRate": 20}
    ]
}

Invoice text:
"""

FUNCTIONS = [
    {
        "name": "extract_invoice_data",
        "description": "Extracts specified fields from invoice text.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "billingAddressCity": {"type": "string"},
                "billingAddressCountry": {"type": "string"},
                "billingAddressPostalCode": {"type": "string"},
                "billingAddressState": {"type": "string"},
                "billingAddressStreet": {"type": "string"},
                "constantSymbol": {"type": "string"},
                "dateInvoiced": {"type": "string", "format": "date"},
                "dateOfReceiving": {"type": "string", "format": "date"},
                "datePaid": {"type": "string", "format": "date"},
                "deliveryNotes": {"type": "string"},
                "dueDate": {"type": "string", "format": "date"},
                "duzp": {"type": "string"},
                "grandTotalAmount": {"type": "number"},
                "currency": {
                    "type": "string",
                    "description": "ISO 4217 currency code",
                    "pattern": "^[A-Z]{3}$"
                },
                "note": {"type": "string"},
                "originalNumber": {"type": "string"},
                "paymentMethod": {
                    "type": "string",
                    "enum": [
                        "draft",
                        "cash",
                        "postal",
                        "delivery",
                        "creditcard",
                        "advance",
                        "encashment",
                        "cheque",
                        "compensation"
                    ]
                },
                "sicCode": {"type": "string"},
                "supplyCode": {"type": "string"},
                "taxAmount": {"type": "number"},
                "taxRate": {"type": "number"},
                "variableSymbol": {"type": "string"},
                "vatId": {"type": "string"},
                "weight": {"type": "string"},  # Includes unit
                "amount": {"type": "number"},
                "invoiceItems": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "quantity": {"type": "number"},
                            "unitPrice": {"type": "number"},
                            "taxRate": {"type": "number"}
                        }
                    }
                }
            },
            "required": ["name", "currency"]
        }
    }
]
