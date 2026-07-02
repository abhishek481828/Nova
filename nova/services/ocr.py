import os
import time
import httpx
from nova.logger import logger
from nova.config import OCR_API_KEY

class OcrService:
    def __init__(self):
        self.api_key = OCR_API_KEY
        self.base_url = "https://api.ocr.space/parse/image"

    def ocr_image_file(self, file_path: str, language: str = "eng") -> str:
        """
        Submits a local image file to the OCR.space API and returns the extracted text.
        """
        if not self.api_key:
            logger.error("OCR API key is missing. Set OCR_API_KEY in your .env file.")
            raise ValueError("OCR API key is not configured.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Image file not found: {file_path}")

        # Construct form payload
        payload = {
            "apikey": self.api_key,
            "language": language,
            "isOverlayRequired": "false",
            "OCREngine": "2"  # Engine 2 is recommended for general X11 desktop text & symbols
        }

        # Load file stream
        file_name = os.path.basename(file_path)
        files = {
            "file": (file_name, open(file_path, "rb"), "image/png")
        }

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"OCR.space API Request (attempt {attempt + 1}) for file: {file_name}")
                with httpx.Client(timeout=30.0) as client:
                    # Note: We must pass 'files' and 'data' (which formats payload as multipart/form-data)
                    response = client.post(self.base_url, files=files, data=payload)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get("OCRExitCode") != 1:
                        error_msg = data.get("ErrorMessage")
                        # ErrorMessage can be a list or string
                        msg = error_msg[0] if isinstance(error_msg, list) and error_msg else str(error_msg)
                        raise Exception(f"OCR.space API Error: {msg}")
                    
                    parsed_results = data.get("ParsedResults", [])
                    if not parsed_results:
                        raise Exception("OCR.space parsed result list is empty.")
                    
                    text = parsed_results[0].get("ParsedText", "").strip()
                    return text

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"OCR.space API Authentication error ({status_code}): {e.response.text}")
                    raise Exception("OCR.space API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"OCR.space API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"OCR.space API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during OCR processing: {e}")
        return ""
