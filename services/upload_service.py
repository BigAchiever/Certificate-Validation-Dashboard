import requests
import json
import time
import logging
from config import (
    AZURE_AI_ENDPOINT,
    AZURE_AI_API_KEY,
    AZURE_AI_MODEL_NAME,
)
from .push_to_blob import save_to_blob_storage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def upload_to_azure_ai(file_name: str, file_bytes: bytes) -> dict:
    """Upload PDF to Azure AI Document Intelligence and extract fields."""
    analyze_url = f"{AZURE_AI_ENDPOINT}/documentintelligence/documentModels/{AZURE_AI_MODEL_NAME}:analyze?api-version=2024-11-30"

    try:
        # Step 1: Submit the document for analysis
        headers = {
            "Ocp-Apim-Subscription-Key": AZURE_AI_API_KEY,
            "Content-Type": "application/pdf",
        }
        response = requests.post(analyze_url, headers=headers, data=file_bytes)

        logger.info(f"Analyze Response Code: {response.status_code}")
        if response.status_code != 202:
            if response.status_code == 429:
                raise RuntimeError("Rate limit exceeded. Please try again later.")
            elif response.status_code == 401:
                raise RuntimeError("Authentication failed. Check your API key.")
            elif response.status_code == 400:
                raise RuntimeError("Bad request. Check the file format or model name.")
            raise RuntimeError(f"Failed to analyze document: {response.status_code} - {response.text}")

        # Step 2: Get the operation-location for polling
        operation_location = response.headers.get("operation-location")
        if not operation_location:
            raise RuntimeError("Operation-Location header not found in response.")

        # Step 3: Poll for the result with a timeout
        max_attempts = 30
        attempts = 0

        while attempts < max_attempts:
            time.sleep(2)
            result_response = requests.get(operation_location, headers={"Ocp-Apim-Subscription-Key": AZURE_AI_API_KEY})

            if result_response.status_code != 200:
                raise RuntimeError(f"Failed to poll result: {result_response.status_code} - {result_response.text}")

            result = result_response.json()
            logger.info(f"Poll Status: {result['status']}")
            attempts += 1

            if result["status"] not in ["running", "notStarted"]:
                break

        if attempts >= max_attempts:
            raise RuntimeError(f"Polling timed out after {max_attempts * 2} seconds.")

        if result["status"] != "succeeded":
            raise RuntimeError(f"Analysis failed: {result.get('error', 'Unknown error')}")

        # Step 4: Extract fields from custom model
        extracted_fields = {
            "documentName": result["analyzeResult"]["documents"][0]["fields"].get("documentName", {}).get("valueString", ""),
            "deviceName": result["analyzeResult"]["documents"][0]["fields"].get("deviceName", {}).get("valueString", ""),
            "organizationName": result["analyzeResult"]["documents"][0]["fields"].get("organizationName", {}).get("valueString", ""),
            "expiryDate": result["analyzeResult"]["documents"][0]["fields"].get("expiryDate", {}).get("valueDate", ""),
            "IssuingAuthority": result["analyzeResult"]["documents"][0]["fields"].get("IssuingAuthority", {}).get("valueString", ""),
            "certificateNo": result["analyzeResult"]["documents"][0]["fields"].get("certificateNo", {}).get("valueString", ""),
            "firstIssuedDate": result["analyzeResult"]["documents"][0]["fields"].get("firstIssuedDate", {}).get("valueDate", ""),
            "extendedValidityDate": result["analyzeResult"]["documents"][0]["fields"].get("extendedValidityDate", {}).get("valueDate", ""),
            "deviceTable": result["analyzeResult"]["documents"][0]["fields"].get("deviceTable", {}).get("valueArray", ""),
            "legislation": result["analyzeResult"]["documents"][0]["fields"].get("legislation", {}).get("valueString", ""),
        }

        # Step 5: Save to Blob Storage (call once)
        try:
            fields_for_storage = {
                key: ", ".join(value) if isinstance(value, list) else str(value)
                for key, value in extracted_fields.items()
            }
            save_to_blob_storage(file_name, fields_for_storage)
        except Exception as e:
            logger.error(f"Failed to save to Blob Storage: {e}")
            # Continue to return extracted fields even if Blob Storage fails

        return extracted_fields

    except Exception as e:
        logger.error(f"Error in upload_to_azure_ai: {e}")
        raise