import os
import urllib.request
import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.news import NewsService
from nova.logger import logger

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
                nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's news inquiry naturally based on the provided articles.\n"
                    "Rules:\n"
                    "1. Summarize the major top headlines and details conversational, direct, and concisely.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Mention 2 to 3 main topics/stories and summarize what is happening, rather than listing out the search metadata directly."
                )
                payload = {
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Articles context:\n{news_context}"}
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
                    logger.error(f"Failed to generate Nebius summary for news data: {e}")

            # Fallback if Nebius is unavailable: return raw formatted headlines list
            return f"Top breaking stories found:\n\n" + news_context

        except Exception as e:
            return f"News retrieval execution failed: {e}"
