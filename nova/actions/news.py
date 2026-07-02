import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.news import NewsService
from nova.logger import logger
from nova.services.nebius import call_nebius_llm

class NewsAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "news"

    def execute(self, params: Dict[str, Any]) -> str:
        category = params.get("category", "").strip()
        query = params.get("query", "").strip()
        country = params.get("country", "").strip()

        try:
            # 1. Run News Search
            service = NewsService()
            articles = service.get_news(category=category, query=query, country=country)
            if not articles:
                return f"No news articles found matching your request."

            # 2. Format details
            formatted_articles = []
            for a in articles:
                formatted_articles.append(
                    f"Title: {a['title']}\n"
                    f"Source: {a['source']}\n"
                    f"Description: {a['description']}\n"
                    f"URL: {a['url']}\n"
                )
            news_context = "\n".join(formatted_articles)

            # 3. Call LLM (Nebius) to summarize naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's news inquiry naturally based on the provided articles.\n"
                    "Rules:\n"
                    "1. Summarize the major top headlines and details conversational, direct, and concisely.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Mention 2 to 3 main topics/stories and summarize what is happening, rather than listing out the search metadata directly."
                )
                summary = call_nebius_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Articles context:\n{news_context}"}
                    ],
                    temperature=0.3
                )
                if summary:
                    return summary

            # Fallback if Nebius is unavailable: return raw formatted headlines list
            return f"Top breaking stories found:\n\n" + news_context

        except Exception as e:
            return f"News retrieval execution failed: {e}"
