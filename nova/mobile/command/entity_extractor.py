"""Entity Extractor Python Binding."""

import re
from typing import Dict
from nova.mobile.command.registry import BuiltInIntent
from nova.mobile.command.context import ExecutionContext


class EntityExtractor:
    def extract(self, text: str, intent: BuiltInIntent, context: ExecutionContext) -> Dict[str, str]:
        entities = {}
        clean = text.strip()

        if intent == BuiltInIntent.CALL_CONTACT:
            name = re.sub(r"(?i)^(call|phone|dial)\s+", "", clean)
            name = re.sub(r"(?i)\s+(on whatsapp|on phone|app)$", "", name).strip()
            resolved = context.resolve_contact(name)
            if resolved:
                entities["contact"] = resolved
                context.update_context(contact=resolved)

        elif intent == BuiltInIntent.SEND_SMS:
            # Match target name after "send sms to" or "send message to" or "send <target> a message"
            match_to = re.search(r"(?i)^(?:send sms to|send message to|text|msg)\s+([a-zA-Z0-9_\s]+?)(?:\s+message|\s+saying|$)", clean)
            match_him = re.search(r"(?i)^send\s+([a-zA-Z0-9_\s]+?)\s+a\s+message", clean)

            target = ""
            if match_to:
                target = match_to.group(1).strip()
            elif match_him:
                target = match_him.group(1).strip()
            else:
                target = re.sub(r"(?i)^(send sms|send message|text|msg)\s*", "", clean).strip()

            target = re.sub(r"(?i)\s+(on whatsapp|on phone|app)$", "", target).strip()
            resolved = context.resolve_contact(target)
            if resolved:
                entities["contact"] = resolved
                context.update_context(contact=resolved)

            msg_match = re.search(r"(?i)saying\s+(.*)", clean)
            if not msg_match:
                msg_match = re.search(r"(?i)message\s+(?:that|saying)?\s*(.*)", clean)
            if msg_match and msg_match.group(1).strip():
                entities["message"] = msg_match.group(1).strip()

        elif intent in (BuiltInIntent.OPEN_APP, BuiltInIntent.PLAY_YOUTUBE, BuiltInIntent.PLAY_SPOTIFY, BuiltInIntent.OPEN_CAMERA, BuiltInIntent.OPEN_BROWSER, BuiltInIntent.OPEN_SETTINGS, BuiltInIntent.OPEN_GALLERY):
            app = re.sub(r"(?i)^(open|launch|start|play|play music|play song)\s+", "", clean)
            app = re.sub(r"(?i)\s+(on phone|app|on youtube|on spotify)$", "", app).strip()
            if app:
                entities["app"] = app
                context.update_context(app=app)

        elif intent in (BuiltInIntent.SET_VOLUME, BuiltInIntent.SET_BRIGHTNESS):
            num_match = re.search(r"(\d{1,3})", clean)
            if num_match:
                entities["percentage"] = num_match.group(1)

        elif intent == BuiltInIntent.SEARCH_GOOGLE:
            query = re.sub(r"(?i)^(search|search google for|google)\s+", "", clean).strip()
            if query:
                entities["query"] = query

        elif intent == BuiltInIntent.OPEN_MAPS:
            dest = re.sub(r"(?i)^(navigate to|maps to|open maps)\s+", "", clean).strip()
            if dest:
                entities["destination"] = dest

        return entities
