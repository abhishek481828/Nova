import os
import urllib.request
import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.coingecko import CoinGeckoService
from nova.logger import logger

COIN_MAPPING = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "sol": "solana",
    "solana": "solana",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "ada": "cardano",
    "cardano": "cardano",
    "xrp": "ripple",
    "ripple": "ripple",
    "ltc": "litecoin",
    "litecoin": "litecoin",
    "dot": "polkadot",
    "polkadot": "polkadot",
    "link": "chainlink",
    "chainlink": "chainlink",
    "avax": "avalanche-2",
    "avalanche": "avalanche-2",
    "shib": "shiba-inu",
    "shiba": "shiba-inu"
}

class CryptoPriceAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "crypto_price"

    def execute(self, params: Dict[str, Any]) -> str:
        coin_input = params.get("coin", "").strip().lower()
        currency = params.get("currency", "usd").strip().lower()

        if not coin_input:
            return "Error: No cryptocurrency specified."

        # Map ticker/name to CoinGecko ID
        coin_id = COIN_MAPPING.get(coin_input, coin_input)

        try:
            # 1. Run CoinGecko Price lookup
            service = CoinGeckoService()
            price = service.get_price(coin_id, currency)

            # 2. Format details
            price_formatted = f"{price:,.2f}" if price >= 1.0 else f"{price:,.6f}"
            price_string = f"Cryptocurrency: {coin_id.capitalize()}\nPrice: {price_formatted} {currency.upper()}"

            # 3. Call LLM (Nebius) to summarize naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's cryptocurrency price question naturally based on the provided price data.\n"
                    "Rules:\n"
                    "1. Keep it concise, conversational, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Express the price naturally (e.g. say 'Bitcoin is currently sixty-eight thousand five hundred dollars' or 'Bitcoin is currently 68,500 dollars' instead of listing raw text)."
                )
                payload = {
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Price data:\n{price_string}"}
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
                    logger.error(f"Failed to generate Nebius summary for crypto price data: {e}")

            # Fallback if Nebius is unavailable
            return f"Current price details:\n\n" + price_string

        except Exception as e:
            return f"Cryptocurrency price execution failed: {e}"
