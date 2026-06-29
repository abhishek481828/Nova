import os
import urllib.request
import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.exchangerate import ExchangeRateService
from nova.logger import logger

class CurrencyAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "currency"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "convert").strip().lower()
        from_curr = params.get("from_currency", "USD").strip().upper()
        to_curr = params.get("to_currency", "EUR").strip().upper()
        amount = params.get("amount", 1.0)
        
        # Parse amount to float safely
        try:
            amount_val = float(amount)
        except (ValueError, TypeError):
            amount_val = 1.0

        try:
            service = ExchangeRateService()
            result_context = ""

            # 1. Fetch Currency Data
            if operation == "convert":
                data = service.convert(from_curr, to_curr, amount_val)
                if not data:
                    return f"Failed to convert {amount_val} {from_curr} to {to_curr}."
                result_context = (
                    f"From Currency: {data['from']}\n"
                    f"To Currency: {data['to']}\n"
                    f"Amount: {data['amount']:,.2f}\n"
                    f"Exchange Rate: {data['quote']:,.6f}\n"
                    f"Converted Result: {data['result']:,.2f}\n"
                )
            elif operation == "live":
                data = service.get_live_rates(from_curr, to_curr)
                if not data:
                    return f"Failed to retrieve live rates for base {from_curr}."
                
                rates_formatted = []
                for q_key, val in data.get("rates", {}).items():
                    rates_formatted.append(f"{q_key}: {val:,.6f}")
                
                result_context = (
                    f"Base Currency: {data['base']}\n"
                    f"Rates:\n" + "\n".join(rates_formatted) + "\n"
                )
            else:
                return f"Unsupported currency operation: {operation}"

            # 2. Call LLM (Nebius) to summarize naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's currency conversion or exchange rate question naturally based on the provided data.\n"
                    "Rules:\n"
                    "1. Keep it concise, conversational, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Express the converted amount or rates naturally (e.g. say 'One hundred US dollars is currently ninety-three euros and forty-five cents' or '100 USD is currently 93.45 EUR' instead of listing raw text)."
                )
                payload = {
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Currency data:\n{result_context}"}
                    ],
                    "temperature": 0.3
                }
                
                try:
                    req = urllib.request.Request(
                        nebius_url,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {nebius_key}"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        if resp.status == 200:
                            resp_data = json.loads(resp.read().decode("utf-8"))
                            choices = resp_data.get("choices", [])
                            if choices:
                                summary = choices[0].get("message", {}).get("content", "").strip()
                                if summary:
                                    return summary
                except Exception as e:
                    logger.error(f"Failed to generate Nebius summary for currency data: {e}")

            # Fallback if Nebius is unavailable: return raw formatted string
            return f"Current conversion details:\n\n" + result_context

        except Exception as e:
            return f"Currency exchange execution failed: {e}"
