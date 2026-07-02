import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.github import GitHubService
from nova.logger import logger
from nova.services.nebius import call_nebius_llm

class GitHubAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "github_action"

    def execute(self, params: Dict[str, Any]) -> str:
        operation = params.get("operation", "get_notifications").strip()

        try:
            service = GitHubService()
            result_context = ""
            
            # 1. Fetch corresponding GitHub data
            if operation == "get_profile":
                profile = service.get_profile()
                result_context = (
                    f"Username: {profile.get('login', '')}\n"
                    f"Name: {profile.get('name', '') or 'No Name'}\n"
                    f"Bio: {profile.get('bio', '') or 'No Bio'}\n"
                    f"Public Repositories: {profile.get('public_repos', 0)}\n"
                    f"Followers: {profile.get('followers', 0)}\n"
                )
            elif operation == "get_notifications":
                notifs = service.get_notifications()
                if not notifs:
                    return "You have no unread notifications on GitHub."
                
                formatted = []
                for n in notifs:
                    formatted.append(
                        f"Repo: {n['repo']}\n"
                        f"Title: {n['title']}\n"
                        f"Reason: {n['reason']}\n"
                        f"Type: {n['type']}\n"
                    )
                result_context = "\n".join(formatted)
            elif operation == "list_repos":
                repos = service.list_repos()
                if not repos:
                    return "No repositories found for this GitHub account."
                
                formatted = []
                for r in repos:
                    formatted.append(
                        f"Repo Name: {r['name']}\n"
                        f"Stars: {r['stars']}\n"
                        f"Description: {r['description']}\n"
                        f"URL: {r['url']}\n"
                    )
                result_context = "\n".join(formatted)
            elif operation == "list_issues":
                issues = service.list_issues()
                if not issues:
                    return "No open issues found on GitHub."
                
                formatted = []
                for i in issues:
                    formatted.append(
                        f"Title: {i['title']}\n"
                        f"Repo: {i['repo']}\n"
                        f"Number: #{i['number']}\n"
                        f"URL: {i['url']}\n"
                    )
                result_context = "\n".join(formatted)
            else:
                return f"Unsupported GitHub operation: {operation}"

            # 2. Call LLM (Nebius) to summarize naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's GitHub question naturally based on the provided data context.\n"
                    "Rules:\n"
                    "1. Express the GitHub info conversationally, direct, and concisely.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Summarize the major notifications, repositories, or user profile statistics naturally (e.g. say 'You have two notifications on GitHub: a pull request review on the Nova project and a comment' instead of listing metadata block)."
                )
                summary = call_nebius_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"GitHub Data:\n{result_context}"}
                    ],
                    temperature=0.3
                )
                if summary:
                    return summary

            # Fallback if Nebius is unavailable: return raw formatted string
            return f"GitHub data details for {operation}:\n\n" + result_context

        except Exception as e:
            return f"GitHub action execution failed: {e}"
