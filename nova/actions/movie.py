import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.tmdb import TmdbService
from nova.logger import logger, log_error
from nova.services.nebius import call_nebius_llm
from nova.config import load_prompt, NEBIUS_API_KEY

class MovieAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "tmdb"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "search_movie").strip().lower()
        query = params.get("query", "").strip()

        try:
            service = TmdbService()
            result_context = ""

            # 1. Fetch TMDB Data
            if operation == "search_movie":
                if not query:
                    return "Error: No movie title provided to search."
                data = service.search_movie(query)
                results = data.get("results", [])
                if not results:
                    return f"No movie matches found for title '{query}'."
                
                # Format the top 3 matches
                formatted_movies = []
                for movie in results[:3]:
                    formatted_movies.append(
                        f"Title: {movie.get('title')}\n"
                        f"Release Date: {movie.get('release_date', 'N/A')}\n"
                        f"Rating: {movie.get('vote_average', 'N/A')} / 10\n"
                        f"Overview: {movie.get('overview', 'No description available.')}\n"
                    )
                result_context = f"Top movie search results for '{query}':\n\n" + "\n---\n".join(formatted_movies)

            elif operation == "search_tv":
                if not query:
                    return "Error: No TV show title provided to search."
                data = service.search_tv(query)
                results = data.get("results", [])
                if not results:
                    return f"No TV show matches found for title '{query}'."
                
                # Format the top 3 matches
                formatted_shows = []
                for show in results[:3]:
                    formatted_shows.append(
                        f"Title: {show.get('name')}\n"
                        f"First Air Date: {show.get('first_air_date', 'N/A')}\n"
                        f"Rating: {show.get('vote_average', 'N/A')} / 10\n"
                        f"Overview: {show.get('overview', 'No description available.')}\n"
                    )
                result_context = f"Top TV show search results for '{query}':\n\n" + "\n---\n".join(formatted_shows)

            elif operation == "trending_movies":
                data = service.get_trending_movies()
                results = data.get("results", [])
                if not results:
                    return "Could not retrieve today's trending movies."
                
                # Format top 5 trending
                formatted_movies = []
                for i, movie in enumerate(results[:5], 1):
                    formatted_movies.append(f"{i}. {movie.get('title')} ({movie.get('release_date', 'N/A')[:4]}) - Rating: {movie.get('vote_average', 'N/A')}/10")
                result_context = "Today's trending movies on TMDB:\n\n" + "\n".join(formatted_movies)

            elif operation == "trending_tv":
                data = service.get_trending_tv()
                results = data.get("results", [])
                if not results:
                    return "Could not retrieve today's trending TV shows."
                
                # Format top 5 trending
                formatted_shows = []
                for i, show in enumerate(results[:5], 1):
                    formatted_shows.append(f"{i}. {show.get('name')} ({show.get('first_air_date', 'N/A')[:4]}) - Rating: {show.get('vote_average', 'N/A')}/10")
                result_context = "Today's trending TV shows on TMDB:\n\n" + "\n".join(formatted_shows)

            else:
                return f"Unsupported TMDB operation: {operation}"

            # 2. Call LLM (Nebius) to summarize naturally
            if NEBIUS_API_KEY:
                fallback_prompt = (
                    "You are Nova, a helpful movie and entertainment assistant. Present the movie/TV show details naturally based on the provided TMDB data.\n"
                    "Rules:\n"
                    "1. Keep it conversational, engaging, and direct.\n"
                    "2. Avoid lists or markdown bold formatting if possible (for clear voice synthesis).\n"
                    "3. Summarize the description or overview concisely without spoiling the ending."
                )
                system_prompt = load_prompt("movie_prompt.txt", fallback_prompt)
                summary = call_nebius_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"TMDB search results data:\n{result_context}"}
                    ],
                    temperature=0.3
                )
                if summary:
                    return summary

            # Fallback if Nebius is unavailable: return raw formatted string
            return f"TMDB Search Results:\n\n" + result_context

        except Exception as e:
            log_error("TMDB details lookup failed", e)
            return f"TMDB details lookup failed: {e}"
