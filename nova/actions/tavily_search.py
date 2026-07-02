import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.tavily import TavilyService
from nova.logger import logger, log_error
from nova.services.nebius import call_nebius_llm
from nova.config import load_prompt, NEBIUS_API_KEY

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
            if NEBIUS_API_KEY:
                fallback_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's question naturally based on the provided search results.\n"
                    "Rules:\n"
                    "1. Keep it concise, natural, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Answer the question using only the search results. If the results do not contain the answer, say so."
                )
                system_prompt = load_prompt("tavily_search_prompt.txt", fallback_prompt)
                summary = call_nebius_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"User query: {query}\n\nSearch results:\n{search_context}"}
                    ],
                    temperature=0.3
                )
                if summary:
                    return summary

            # Fallback if Nebius is unavailable: return raw formatted search results
            return f"Here are the search results for '{query}':\n\n" + search_context

        except Exception as e:
            log_error("Search execution failed", e)
            return f"Search execution failed: {e}"
