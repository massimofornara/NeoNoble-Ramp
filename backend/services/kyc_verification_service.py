"""
AI-powered KYC Document Verification Service.

Uses GPT Image (via Emergent LLM key) for:
- OCR extraction from ID documents (passport, ID card, drivers license)
- Data matching against user-submitted KYC information
- Fraud/tampering detection
- Automated approval recommendation
"""

import os
import base64
import json
import logging
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


async def verify_document_with_ai(
    image_base64: str,
    submitted_data: dict,
    mime_type: str = "image/jpeg",
) -> dict:
    """
    Analyze an ID document image and verify it against submitted KYC data.

    Returns:
        {
            "verified": bool,
            "confidence": float (0-1),
            "extracted": { name, dob, doc_number, nationality, doc_type },
            "matches": { name: bool, dob: bool, doc_number: bool },
            "issues": [str],
            "recommendation": "approve" | "review" | "reject"
        }
    """
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"kyc-verify-{submitted_data.get('user_id', 'unknown')}",
            system_message=(
                "You are a KYC document verification specialist for NeoNoble Ramp, "
                "a European fintech platform. You analyze identity documents (passports, "
                "ID cards, drivers licenses) to extract and verify personal information. "
                "You must respond ONLY with valid JSON, no markdown, no explanation."
            ),
        ).with_model("openai", "gpt-4o")

        prompt = (
            f"Analyze this identity document image. Extract the following fields and compare "
            f"with the submitted data:\n\n"
            f"SUBMITTED DATA:\n"
            f"- Name: {submitted_data.get('first_name', '')} {submitted_data.get('last_name', '')}\n"
            f"- Date of Birth: {submitted_data.get('date_of_birth', '')}\n"
            f"- Document Number: {submitted_data.get('document_number', '')}\n"
            f"- Nationality: {submitted_data.get('nationality', '')}\n"
            f"- Document Type: {submitted_data.get('document_type', '')}\n\n"
            f"Respond with this exact JSON structure:\n"
            f'{{\n'
            f'  "extracted": {{\n'
            f'    "full_name": "extracted name from document",\n'
            f'    "date_of_birth": "YYYY-MM-DD",\n'
            f'    "document_number": "extracted number",\n'
            f'    "nationality": "country code",\n'
            f'    "document_type": "passport|id_card|drivers_license",\n'
            f'    "expiry_date": "YYYY-MM-DD or null"\n'
            f'  }},\n'
            f'  "matches": {{\n'
            f'    "name": true/false,\n'
            f'    "date_of_birth": true/false,\n'
            f'    "document_number": true/false,\n'
            f'    "nationality": true/false\n'
            f'  }},\n'
            f'  "confidence": 0.0 to 1.0,\n'
            f'  "issues": ["list of any issues found"],\n'
            f'  "document_readable": true/false,\n'
            f'  "possible_tampering": true/false,\n'
            f'  "recommendation": "approve|review|reject"\n'
            f'}}'
        )

        image_content = ImageContent(image_base64=image_base64)
        msg = UserMessage(text=prompt, file_contents=[image_content])
        response = await chat.send_message(msg)

        # Parse JSON response
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(response_text)

        # Calculate verification status
        matches = result.get("matches", {})
        match_count = sum(1 for v in matches.values() if v)
        total_fields = len(matches)
        verified = match_count >= 3 and result.get("confidence", 0) >= 0.7

        return {
            "verified": verified,
            "confidence": result.get("confidence", 0),
            "extracted": result.get("extracted", {}),
            "matches": matches,
            "issues": result.get("issues", []),
            "recommendation": result.get("recommendation", "review"),
            "document_readable": result.get("document_readable", True),
            "possible_tampering": result.get("possible_tampering", False),
            "ai_provider": "openai/gpt-4o",
        }

    except json.JSONDecodeError as e:
        logger.error(f"AI KYC response parse error: {e}")
        return {
            "verified": False,
            "confidence": 0,
            "extracted": {},
            "matches": {},
            "issues": ["Errore nel parsing della risposta AI"],
            "recommendation": "review",
            "ai_provider": "openai/gpt-4o",
        }
    except Exception as e:
        logger.error(f"AI KYC verification error: {e}")
        return {
            "verified": False,
            "confidence": 0,
            "extracted": {},
            "matches": {},
            "issues": [f"Errore verifica AI: {str(e)}"],
            "recommendation": "review",
            "ai_provider": "error",
        }


async def extract_document_data(image_base64: str, mime_type: str = "image/jpeg") -> dict:
    """Extract data from a document image without verification (pure OCR)."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"kyc-ocr-{id(image_base64)}",
            system_message="You are a document OCR specialist. Extract all text and data from identity documents. Respond ONLY with valid JSON.",
        ).with_model("openai", "gpt-4o")

        msg = UserMessage(
            text='Extract all visible fields from this identity document. Return JSON with keys: full_name, date_of_birth (YYYY-MM-DD), document_number, nationality, document_type, expiry_date, issuing_authority, address (if visible).',
            file_contents=[ImageContent(image_base64=image_base64)],
        )
        response = await chat.send_message(msg)
        response_text = response.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0]

        return {"success": True, "data": json.loads(response_text)}
    except Exception as e:
        logger.error(f"OCR extraction error: {e}")
        return {"success": False, "error": str(e)}
