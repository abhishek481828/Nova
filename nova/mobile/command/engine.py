"""Command Engine Python Binding."""

import uuid
import logging
from typing import List, Callable
from nova.mobile.command.registry import BuiltInIntent
from nova.mobile.command.parser import IntentParser
from nova.mobile.command.entity_extractor import EntityExtractor
from nova.mobile.command.context import ExecutionContext
from nova.mobile.command.dispatcher import CommandDispatcher
from nova.mobile.command.history import CommandHistory
from nova.mobile.command.result import CommandResult

logger = logging.getLogger("nova.mobile.command.engine")


class CommandEngine:
    def __init__(self, lifecycle_manager=None):
        self.lifecycle_manager = lifecycle_manager
        self.intent_parser = IntentParser()
        self.entity_extractor = EntityExtractor()
        self.execution_context = ExecutionContext()
        self.dispatcher = CommandDispatcher()
        self.history = CommandHistory()
        self.execution_listeners: List[Callable[[CommandResult], None]] = []

    def execute_text(self, text: str) -> CommandResult:
        command_id = str(uuid.uuid4())
        logger.info(f"CommandEngine executing speech text: \"{text}\" (ID={command_id})")

        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event("CommandStarted", {"commandId": command_id, "text": text})

        intent = self.intent_parser.parse(text)
        if intent == BuiltInIntent.UNKNOWN:
            if self.lifecycle_manager:
                self.lifecycle_manager.publish_event("UnknownIntent", {"commandId": command_id, "text": text})
            res_error = CommandResult(
                command_id, intent, False,
                spoken_response="I'm sorry, I didn't understand that command.",
                plugin_used="None",
                error_message="Unknown Intent"
            )
            self.history.record(res_error)
            self._notify_listeners(res_error)
            return res_error

        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event("IntentRecognized", {"commandId": command_id, "intent": intent.value})

        entities = self.entity_extractor.extract(text, intent, self.execution_context)
        result = self.dispatcher.dispatch(command_id, intent, entities)

        self.history.record(result)

        if result.is_success:
            if self.lifecycle_manager:
                self.lifecycle_manager.publish_event(
                    "CommandCompleted",
                    {
                        "commandId": command_id,
                        "intent": intent.value,
                        "response": result.spoken_response,
                        "plugin": result.plugin_used
                    }
                )
        else:
            if self.lifecycle_manager:
                self.lifecycle_manager.publish_event("CommandFailed", {"commandId": command_id, "reason": result.error_message})

        self._notify_listeners(result)
        return result

    def _notify_listeners(self, result: CommandResult):
        for l in self.execution_listeners:
            try:
                l(result)
            except Exception as e:
                logger.error("Error in execution listener", exc_info=True)
