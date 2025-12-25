"""
Google Gemini client implementation.
This module provides a Gemini client that follows the same interface as the OpenAI client.
"""
import logging
import json
import google.generativeai as genai
import asyncio
from django.conf import settings
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Global Gemini client instance
_gemini_client = None


class ExternalModelError(Exception):
    """Raised when an external model (Gemini) returns no usable text or fails in a non-recoverable way."""


def get_gemini_client():
    """
    Get or create the Gemini client instance.
    
    Returns:
        Configured Gemini client or None if not configured
    """
    global _gemini_client
    
    if _gemini_client is not None:
        return _gemini_client
        
    if not hasattr(settings, 'GEMINI_API_KEY') or not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set, Gemini features disabled")
        return None
    
    try:
        # Configure the Gemini client and return the genai module for sync usage
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _gemini_client = genai
        logger.info("Gemini client initialized successfully")
        return _gemini_client
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {str(e)}", exc_info=True)
        return None

def is_gemini_available() -> bool:
    """Check if Gemini is available and properly configured."""
    return get_gemini_client() is not None


async def generate_with_gemini(prompt: str, system_prompt: str = "") -> Dict[str, Any]:
    """
    Generate a response using Gemini. Uses synchronous `genai.generate` inside
    `asyncio.to_thread` to avoid grpc aio event-loop issues in this environment.

    Returns a dict with keys: success, response, raw_response or error.
    """
    client = get_gemini_client()
    if not client:
        return {"success": False, "error": "Gemini client not available"}

    try:
        full_prompt = f"{system_prompt}\n\nUser: {prompt}"

        def sync_call():
            # Try several genai invocation patterns and model names for robustness
            models_to_try = ["gemini-1.0", "gemini-pro", "text-bison-001", "chat-bison-001"]
            for model_name in models_to_try:
                try:
                    # Some genai versions accept model= and input=; others use different signatures
                    try:
                        resp = genai.generate(model=model_name, input=full_prompt, temperature=0.1)
                    except TypeError:
                        # Fallback to a simpler call
                        try:
                            resp = genai.generate(full_prompt)
                        except Exception:
                            resp = None

                    # Try multiple extraction strategies
                    # 1. resp.text
                    text = None
                    if hasattr(resp, 'text') and resp.text:
                        text = resp.text

                    # 2. resp.output / resp.outputs
                    if not text:
                        try:
                            out = getattr(resp, 'output', None) or getattr(resp, 'outputs', None)
                            if out:
                                # handle list-like structures
                                first = out[0] if isinstance(out, (list, tuple)) else out
                                # nested content shapes
                                if hasattr(first, 'content'):
                                    c = first.content
                                    if isinstance(c, (list, tuple)) and len(c) > 0 and hasattr(c[0], 'text'):
                                        text = c[0].text
                                    elif isinstance(c, str):
                                        text = c
                                elif isinstance(first, dict):
                                    # try common keys
                                    for key in ('text', 'content', 'message', 'output'):
                                        if key in first and isinstance(first[key], str):
                                            text = first[key]
                                            break
                        except Exception:
                            pass

                    # 3. resp.candidates
                    if not text and hasattr(resp, 'candidates'):
                        try:
                            cands = resp.candidates
                            if isinstance(cands, (list, tuple)) and len(cands) > 0:
                                cand = cands[0]
                                if hasattr(cand, 'content') and hasattr(cand.content, 'text'):
                                    text = cand.content.text
                                elif isinstance(cand, dict) and 'content' in cand:
                                    cont = cand['content']
                                    if isinstance(cont, list) and len(cont) > 0 and isinstance(cont[0], dict) and 'text' in cont[0]:
                                        text = cont[0]['text']
                        except Exception:
                            pass

                    # 4. string conversion fallback
                    if not text:
                        try:
                            text = str(resp)
                        except Exception:
                            text = None

                    if text:
                        return text
                    else:
                        # Log raw response shape for debugging when extraction fails
                        try:
                            logger.debug("gemini.generate returned object (no text extracted): %s", repr(resp))
                            # Try to log useful attributes
                            attrs = {}
                            for attr in ('output', 'outputs', 'candidates', 'text'):
                                if hasattr(resp, attr):
                                    try:
                                        attrs[attr] = getattr(resp, attr)
                                    except Exception:
                                        attrs[attr] = '<unreadable>'
                            if attrs:
                                logger.debug("gemini response attrs: %s", attrs)
                        except Exception:
                            pass

                except Exception:
                    # Try next model
                    continue

            # If direct generate attempts failed, try chat.generate style API as a fallback
            try:
                for model_name in models_to_try:
                    try:
                        chat_resp = genai.chat.generate(model=model_name, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}])
                    except Exception:
                        chat_resp = None

                    if not chat_resp:
                        continue

                    # Extract text from chat_resp
                    text = None
                    try:
                        if hasattr(chat_resp, 'candidates') and chat_resp.candidates:
                            cand = chat_resp.candidates[0]
                            if hasattr(cand, 'content') and cand.content:
                                # content may be list-like
                                c = cand.content
                                if isinstance(c, (list, tuple)) and len(c) > 0 and hasattr(c[0], 'text'):
                                    text = c[0].text
                                elif isinstance(c, str):
                                    text = c
                        # older shapes
                        if not text and hasattr(chat_resp, 'output'):
                            out = chat_resp.output
                            if isinstance(out, (list, tuple)) and len(out) > 0 and hasattr(out[0], 'content'):
                                cc = out[0].content
                                if isinstance(cc, (list, tuple)) and len(cc) > 0 and hasattr(cc[0], 'text'):
                                    text = cc[0].text
                    except Exception:
                        text = None

                    if text:
                        return text
                    else:
                        try:
                            logger.debug("gemini.chat.generate returned object (no text extracted): %s", repr(chat_resp))
                        except Exception:
                            pass
            except Exception:
                pass

            # If all attempts failed, log and return None
            try:
                logger.debug("gemini sync_call failed to extract text from any model response")
            except Exception:
                pass
            return None

        response_text = await asyncio.to_thread(sync_call)

        if not response_text:
            # No usable text extracted from Gemini responses — return an error dict
            # rather than raising, allowing callers to handle fallback behavior
            # without an unhandled exception.
            return {"success": False, "error": "Gemini returned no text", "raw_response": None}

        response_text = response_text.strip()

        if response_text.startswith('{') and response_text.endswith('}'):
            try:
                response_data = json.loads(response_text)
                return {"success": True, "response": response_data, "raw_response": response_text}
            except json.JSONDecodeError:
                pass

        return {"success": True, "response": response_text, "raw_response": response_text}

    except Exception as e:
        logger.error(f"Error generating with Gemini: {str(e)}", exc_info=True)
        return {"success": False, "error": str(e)}
