import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.fmp import FmpService
from nova.logger import logger, log_error
from nova.services.nebius import call_nebius_llm
from nova.config import load_prompt, NEBIUS_API_KEY

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
            if NEBIUS_API_KEY:
                fallback_prompt = (
                    "You are Nova, a helpful stock market assistant. Answer the user's stock price or financial market question naturally based on the provided FMP quote details.\n"
                    "Rules:\n"
                    "1. Keep it concise, conversational, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Summarize the price, daily changes, and trends naturally (e.g. say 'Apple Inc. is currently trading at 281 dollars and 76 cents, down 0.71 percent today' instead of listing raw text)."
                )
                system_prompt = load_prompt("finance_prompt.txt", fallback_prompt)
                summary = call_nebius_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"FMP Stock Quote data:\n{result_context}"}
                    ],
                    temperature=0.3
                )
                if summary:
                    return summary

            # Fallback if Nebius is unavailable: return raw formatted string
            return f"FMP stock quote details:\n\n" + result_context

        except Exception as e:
            log_error("FMP stock details lookup failed", e)
            return f"FMP stock details lookup failed: {e}"
