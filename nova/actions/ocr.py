import os
import subprocess
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.ocr import OcrService
from nova.logger import logger
from nova.services.nebius import call_nebius_llm

class OcrAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "ocr"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "screen").strip().lower()
        file_path = params.get("file_path", "").strip()

        try:
            service = OcrService()
            target_file = ""
            is_temp_file = False

            # 1. Handle Screenshot Capture or Target File
            if operation == "screen":
                temp_dir = "/home/nixos/Projects/Nova/temp"
                os.makedirs(temp_dir, exist_ok=True)
                target_file = os.path.join(temp_dir, "screenshot.png")
                is_temp_file = True

                logger.info("Taking screen capture for OCR...")
                # Run scrot -z (silent screenshot capture, X11)
                subprocess.run(["scrot", "-z", target_file], check=True)
            elif operation == "file":
                if not file_path:
                    return "Error: No file path provided for image OCR."
                target_file = os.path.expanduser(file_path)
            else:
                return f"Unsupported OCR operation: {operation}"

            # 2. Execute OCR on target image
            extracted_text = service.ocr_image_file(target_file)
            
            # Clean up temp file immediately
            if is_temp_file and os.path.exists(target_file):
                try:
                    os.remove(target_file)
                except Exception as e:
                    logger.warning(f"Failed to delete temp screenshot file: {e}")

            if not extracted_text:
                return "OCR completed successfully, but no visible text was detected in the image."

            # 3. Call LLM (Nebius) to summarize or present text naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's question by summarizing or presenting the extracted OCR text naturally.\n"
                    "Rules:\n"
                    "1. If the text is short or is a code/log block, repeat it exactly or present it clearly.\n"
                    "2. If it's a long article or document, give a brief, conversational summary first, then print the text.\n"
                    "3. Express the response naturally so it can be spoken aloud easily, avoiding code block markup if just talking."
                )
                summary = call_nebius_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Extracted OCR text:\n{extracted_text}"}
                    ],
                    temperature=0.3
                )
                if summary:
                    return summary

            # Fallback if Nebius is unavailable: return raw extracted text block
            return f"Extracted text details:\n\n{extracted_text}"

        except Exception as e:
            return f"OCR execution failed: {e}"
