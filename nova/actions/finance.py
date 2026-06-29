import os
import urllib.request
import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.fmp import FmpService
from nova.logger import logger

class FinanceAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "finance"

    def execute(self, params: Dict[str, Any]) -> str:
        symbol = params.get("symbol", "").strip().upper()

        if not symbol:
            return "Error: No stock ticker symbol provided."

        try:
            service = FmpService()
            data = service.get_stock_quote(symbol)
            
            if not data:
                return f"Failed to retrieve stock quote details for symbol '{symbol}'."

            result_context = (
                f"Symbol: {data.get('symbol')}\n"
                f"Name: {data.get('name')}\n"
                f"Price: ${data.get('price'):,.2f}\n"
                f"Change: {data.get('change'):+,.2f}\n"
                f"Change Percentage: {data.get('changePercentage'):+,.4f}%\n"
                f"Volume: {data.get('volume'):,}\n"
                f"Day Low/High: ${data.get('dayLow'):,.2f} - ${data.get('dayHigh'):,.2f}\n"
                f"Year Low/High: ${data.get('yearLow'):,.2f} - ${data.get('yearHigh'):,.2f}\n"
                f"Exchange: {data.get('exchange')}\n"
                f"Open: ${data.get('open'):,.2f}\n"
                f"Previous Close: ${data.get('previousClose'):,.2f}\n"
            )

            # 2. Call LLM (Nebius) to summarize naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
                system_prompt = (
                    "You are Nova, a helpful stock market assistant. Answer the user's stock price or financial market question naturally based on the provided FMP quote details.\n"
                    "Rules:\n"
                    "1. Keep it concise, conversational, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Summarize the price, daily changes, and trends naturally (e.g. say 'Apple Inc. is currently trading at 281 dollars and 76 cents, down 0.71 percent today' instead of listing raw text)."
                )
                payload = {
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"FMP Stock Quote data:\n{result_context}"}
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
                    logger.error(f"Failed to generate Nebius summary for FMP data: {e}")

            # Fallback if Nebius is unavailable: return raw formatted string
            return f"FMP stock quote details:\n\n" + result_context

        except Exception as e:
            return f"FMP stock details lookup failed: {e}"
