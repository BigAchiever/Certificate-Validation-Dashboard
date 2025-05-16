import json
import logging
import time
from datetime import datetime
import requests
from dotenv import load_dotenv
import os
import streamlit as st

# Load .env file for local development
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load secrets: Try Streamlit Cloud secrets first, fall back to .env
try:
    AZURE_AI_ENDPOINT = st.secrets["AZURE_AI_ENDPOINT"]
    AZURE_AI_API_KEY = st.secrets["AZURE_AI_API_KEY"]
    AZURE_AI_MODEL_NAME = st.secrets["AZURE_AI_MODEL_NAME"]
    BLOB_URL = st.secrets["BLOB_URL"]
    SAS_TOKEN = st.secrets["SAS_TOKEN"]
    CONTAINER_NAME = st.secrets["CONTAINER_NAME"]
    logger.info("Secrets loaded from Streamlit Cloud (st.secrets)")
except (KeyError, AttributeError) as e:
    logger.warning(f"Failed to load secrets from Streamlit Cloud: {e}. Falling back to .env file.")
    AZURE_AI_ENDPOINT = os.getenv("AZURE_AI_ENDPOINT")
    AZURE_AI_API_KEY = os.getenv("AZURE_AI_API_KEY")
    AZURE_AI_MODEL_NAME = os.getenv("AZURE_AI_MODEL_NAME")
    BLOB_URL = os.getenv("BLOB_URL")
    SAS_TOKEN = os.getenv("SAS_TOKEN")
    CONTAINER_NAME = os.getenv("CONTAINER_NAME")
    logger.info("Secrets loaded from .env file")

# Debug configuration
logger.info(f"AZURE_AI_ENDPOINT: {AZURE_AI_ENDPOINT}")
logger.info(f"AZURE_AI_MODEL_NAME: {AZURE_AI_MODEL_NAME}")
logger.info(f"BLOB_URL: {BLOB_URL}")
logger.info(f"CONTAINER_NAME: {CONTAINER_NAME}")

# Validate that all required secrets are loaded
required_secrets = {
    "AZURE_AI_ENDPOINT": AZURE_AI_ENDPOINT,
    "AZURE_AI_API_KEY": AZURE_AI_API_KEY,
    "AZURE_AI_MODEL_NAME": AZURE_AI_MODEL_NAME,
    "BLOB_URL": BLOB_URL,
    "SAS_TOKEN": SAS_TOKEN,
    "CONTAINER_NAME": CONTAINER_NAME,
}
for key, value in required_secrets.items():
    if not value:
        raise ValueError(f"Missing required secret: {key}. Check your Streamlit Cloud secrets or .env file.")

# Local storage path for development (optional)
LOCAL_STORAGE = os.getenv("LOCAL_STORAGE", "local_storage")
os.makedirs(LOCAL_STORAGE, exist_ok=True)  # Create local storage directory if it doesn't exist

def save_to_blob_storage(file_name: str, fields: dict) -> None:
    """Save extracted fields as JSON to Azure Blob Storage using SAS token, and optionally to local storage."""
    # Validate fields
    if not fields:
        raise ValueError("Fields dictionary is empty. Cannot save to Blob Storage.")

    # Ensure required fields
    if "documentName" not in fields or not fields["documentName"]:
        logger.warning("documentName is missing or empty. Using default value.")
        fields["documentName"] = "Unknown Declaration"
    if "deviceName" not in fields or fields["deviceName"] is None:
        logger.warning("deviceName is missing. Setting to empty list.")
        fields["deviceName"] = []

    # Generate unique blob name
    timestamp = str(int(datetime.now().timestamp() * 1000))
    blob_name = f"{file_name.split('.')[0]}_result_{timestamp}.json"

    # Save to local storage (for development)
    if os.getenv("SAVE_LOCAL", "false").lower() == "true":
        local_path = os.path.join(LOCAL_STORAGE, blob_name)
        logger.info(f"Saving to local storage: {local_path}")
        try:
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(fields, f, indent=2)
            logger.info(f"Successfully saved to local storage: {local_path}")
        except Exception as e:
            logger.error(f"Failed to save to local storage: {e}")

    # Save to Azure Blob Storage
    url = f"{BLOB_URL}{CONTAINER_NAME}/{blob_name}{SAS_TOKEN}"

    logger.info("Fields to be uploaded to Blob Storage:")
    logger.info(json.dumps(fields, indent=2))
    logger.info(f"Blob Name: {blob_name}")
    logger.info(f"Blob URL: {url}")

    # Retry logic for transient failures
    max_retries = 3
    attempt = 0
    last_exception = None

    while attempt < max_retries:
        try:
            response = requests.put(
                url,
                headers={
                    "x-ms-blob-type": "BlockBlob",
                    "Content-Type": "application/json",
                    "x-ms-version": "2021-04-10",
                },
                data=json.dumps(fields, indent=2),
            )

            logger.info(f"Blob Save Response Code: {response.status_code}")
            logger.info(f"Blob Save Response Body: {response.text}")

            if response.status_code == 201:
                logger.info(f"Successfully saved to Blob Storage: {blob_name}")
                logger.info(f"Blob Path: {CONTAINER_NAME}/{blob_name}")
                return
            else:
                if response.status_code == 403:
                    raise RuntimeError("Authentication failed. Check your SAS token.")
                elif response.status_code == 409:
                    raise RuntimeError("Blob already exists. Try a different blob name.")
                elif response.status_code == 400:
                    raise RuntimeError("Bad request. Check the blob URL or data format.")
                raise RuntimeError(
                    f"Failed to save to Blob Storage: {response.status_code} - {response.text}"
                )

        except Exception as e:
            last_exception = e
            logger.error(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            attempt += 1
            if attempt < max_retries:
                logger.info("Retrying in 2 seconds...")
                time.sleep(2)

    logger.error(f"Failed to save to Blob Storage after {max_retries} attempts.")
    raise last_exception or RuntimeError("Failed to save to Blob Storage after retries.")