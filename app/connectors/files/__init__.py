"""File connectors for INIS per §9.1."""

from app.connectors.files.csv_connector import CSVConnector
from app.connectors.files.docx_connector import DOCXConnector
from app.connectors.files.excel_connector import ExcelConnector
from app.connectors.files.json_connector import JSONConnector
from app.connectors.files.pdf_connector import PDFConnector
from app.connectors.files.xml_connector import XMLConnector

__all__ = [
    "CSVConnector",
    "JSONConnector",
    "ExcelConnector",
    "XMLConnector",
    "DOCXConnector",
    "PDFConnector",
]
