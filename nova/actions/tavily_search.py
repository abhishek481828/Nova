import os
import urllib.request
import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.tavily import TavilyService
from nova.logger import logger

class TavilySearchAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "tavily_search"

    def execute(self, params: Dict[str, Any]) -> str:
        query = params.get("query", "").strip()
        if not query:
            return "Error: No search query provided."

        try:
            # 1. Run Tavily Search
            service = TavilyService()
            results = service.search(query)
            if not results:
                return f"No search results found for query: '{query}'."

            # 2. Format search results for LLM context
            formatted_results = []
            for r in results:
                formatted_results.append(f"Title: {r['title']}\nURL: {r['url']}\nContent: {r['content']}\n")
            search_context = "\n".join(formatted_results)

            # 3. Call LLM (Nebius) to summarize naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's question naturally based on the provided search results.\n"
                    "Rules:\n"
                    "1. Keep it concise, natural, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Answer the question using only the search results. If the results do not contain the answer, say so."
                )
                payload = {
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"User query: {query}\n\nSearch results:\n{search_context}"}
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
                    logger.error(f"Failed to generate Nebius summary for search results: {e}")

            # Fallback if Nebius is unavailable: return raw formatted search results
            return f"Here are the search results for '{query}':\n\n" + search_context

        except Exception as e:
            return f"Search execution failed: {e}"
