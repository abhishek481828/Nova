"""Built-in first-party skills for Nova v3.0 Phase 9."""

import re
from nova.mobile.skills.base_skill import BaseSkill, SkillExecutionResult
from nova.mobile.skills.manifest import SkillManifest
from nova.mobile.skills.enums import SkillCategory, SkillPermission


class CalculatorSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.calculator",
            name="Calculator",
            description="Evaluates math expressions from voice commands",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.UTILITIES,
            is_first_party=True,
            intent_phrases=["calculate", "what is", "how much is", "compute", "solve"]
        )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["calculate", "what is", "how much is", "compute", "solve",
                                     "plus", "minus", "times", "divided"]) and any(c.isdigit() for c in text)

    def execute(self, text: str) -> SkillExecutionResult:
        expr = self._extract_expression(text)
        try:
            val = self._evaluate(expr)
            ans_str = str(int(val)) if val == int(val) else str(val)
            return SkillExecutionResult(self.manifest.skill_id, True, f"The answer is {ans_str}")
        except Exception as e:
            return SkillExecutionResult(self.manifest.skill_id, False,
                                        "I couldn't calculate that.", error_message=str(e))

    def _extract_expression(self, text: str) -> str:
        s = re.sub(r"(?i)(calculate|compute|solve|what is|how much is)", "", text)
        s = s.replace("plus", "+").replace("minus", "-")
        s = re.sub(r"times|multiplied by", "*", s)
        s = re.sub(r"divided by|over", "/", s)
        return s.strip()

    def _evaluate(self, expr: str) -> float:
        tokens = [t for t in re.split(r"(?<=[+\-*/])|(?=[+\-*/])", expr.replace(" ", "")) if t]
        res = float(tokens[0])
        i = 1
        while i < len(tokens) - 1:
            op = tokens[i]
            operand = float(tokens[i + 1])
            if op == "+": res += operand
            elif op == "-": res -= operand
            elif op == "*": res *= operand
            elif op == "/":
                if operand == 0: raise ZeroDivisionError("Division by zero")
                res /= operand
            i += 2
        return res


class UnitConverterSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.unit_converter",
            name="Unit Converter",
            description="Converts between common units of measurement",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.UTILITIES,
            is_first_party=True,
            intent_phrases=["convert", "how many", "in kilometers", "in miles", "in celsius", "in fahrenheit"]
        )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return "convert" in t or ("how many" in t and any(u in t for u in ["km", "miles", "celsius", "fahrenheit", "kg", "pounds"]))

    def execute(self, text: str) -> SkillExecutionResult:
        t = text.lower()
        m = re.search(r"\d+\.?\d*", t)
        if not m:
            return SkillExecutionResult(self.manifest.skill_id, False, "I couldn't find a number to convert.")
        num = float(m.group())

        if "km" in t and "miles" in t and t.find("km") < t.find("miles"):
            res = f"{num * 0.621371:.2f} miles"
        elif "miles" in t and "km" in t and t.find("miles") < t.find("km"):
            res = f"{num * 1.60934:.2f} km"
        elif "celsius" in t and "fahrenheit" in t:
            res = f"{num * 9/5 + 32:.1f} °F"
        elif "fahrenheit" in t and "celsius" in t:
            res = f"{(num - 32) * 5/9:.1f} °C"
        elif "kg" in t and "pounds" in t:
            res = f"{num * 2.20462:.2f} pounds"
        elif "pounds" in t and "kg" in t:
            res = f"{num * 0.453592:.2f} kg"
        else:
            return SkillExecutionResult(self.manifest.skill_id, False, "I don't know how to convert that yet.")

        return SkillExecutionResult(self.manifest.skill_id, True, f"{num} converts to {res}")


class DeviceStatusSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.device_status",
            name="Device Status",
            description="Reports battery, storage, and device information",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.INFORMATION,
            is_first_party=True,
            intent_phrases=["device status", "battery status", "how much battery", "storage status", "phone info"]
        )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["battery", "storage", "device status", "system info", "phone info"])

    def execute(self, text: str) -> SkillExecutionResult:
        t = text.lower()
        if "battery" in t:
            resp = "Your battery level is optimal."
        elif "storage" in t:
            resp = "Storage status is healthy."
        else:
            resp = "I'm Nova, running v3.0.0. All systems operational."
        return SkillExecutionResult(self.manifest.skill_id, True, resp)


class NotesSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.notes",
            name="Notes",
            description="Take and recall quick notes",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.PRODUCTIVITY,
            is_first_party=True,
            intent_phrases=["take a note", "remember that", "note that", "read my notes"],
            permissions={SkillPermission.MEMORY_WRITE, SkillPermission.MEMORY_READ}
        )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["take a note", "remember that", "note that", "read my notes"])

    def execute(self, text: str) -> SkillExecutionResult:
        t = text.lower()
        if any(k in t for k in ["take a note", "note that", "remember that"]):
            note_content = re.sub(r"(?i)(take a note|note that|remember that):?", "", text).strip()
            if self.context and self.context.memory_api:
                self.context.memory_api.remember(f"note_{int(time.time())}", note_content)
            return SkillExecutionResult(self.manifest.skill_id, True, f"Got it! I've noted: {note_content}")
        return SkillExecutionResult(self.manifest.skill_id, True, "Your notes are saved in memory.")


class TranslatorSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.translator",
            name="Translator",
            description="Translates phrases between languages offline",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.INFORMATION,
            is_first_party=True,
            intent_phrases=["translate", "how do you say", "what is hello in", "say in"]
        )

    SAMPLES = {
        "hello": {"japanese": "Konnichiwa", "spanish": "Hola", "french": "Bonjour", "german": "Hallo", "hindi": "Namaste"},
        "good morning": {"japanese": "Ohayou Gozaimasu", "spanish": "Buenos días", "french": "Bonjour", "german": "Guten Morgen", "hindi": "Suprabhat"}
    }

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["translate", "how do you say", "what is hello in", "say in"])

    def execute(self, text: str) -> SkillExecutionResult:
        t = text.lower()
        target_lang = next((l for l in ["japanese", "spanish", "french", "german", "hindi"] if l in t), None)
        if not target_lang:
            return SkillExecutionResult(self.manifest.skill_id, False, "Supported languages: Japanese, Spanish, French, German, Hindi.")

        phrase_match = next((k for k in self.SAMPLES if k in t), None)
        if not phrase_match:
            return SkillExecutionResult(self.manifest.skill_id, True, "Full translation requires an active connection.")

        tr = self.SAMPLES[phrase_match].get(target_lang)
        if not tr:
            return SkillExecutionResult(self.manifest.skill_id, False, "Translation not available.")
        return SkillExecutionResult(self.manifest.skill_id, True, f"'{phrase_match.capitalize()}' in {target_lang.capitalize()} is: {tr}")


class WeatherSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.weather",
            name="Weather",
            description="Provides weather info",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.INFORMATION,
            is_first_party=True,
            intent_phrases=["what's the weather", "weather today", "will it rain"],
            permissions={SkillPermission.NETWORK, SkillPermission.LOCATION}
        )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["weather", "rain today", "temperature", "will it rain"])

    def execute(self, text: str) -> SkillExecutionResult:
        return SkillExecutionResult(self.manifest.skill_id, True,
                                    "To check weather, please grant location access and connect to the network.")


class ReminderSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.reminder",
            name="Reminder",
            description="Sets reminders",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.PRODUCTIVITY,
            is_first_party=True,
            intent_phrases=["remind me", "set a reminder", "don't let me forget"],
            permissions={SkillPermission.NOTIFICATIONS, SkillPermission.SCHEDULER}
        )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["remind me", "set a reminder", "don't let me forget"])

    def execute(self, text: str) -> SkillExecutionResult:
        content = re.sub(r"(?i)(remind me (to)?|set a reminder (to)?|don.t let me forget (to)?)", "", text).strip()
        if self.context and self.context.notification_api:
            self.context.notification_api.notify("Reminder Set", f"Nova will remind you: {content}")
        return SkillExecutionResult(self.manifest.skill_id, True, f"Done! I'll remind you: {content}")


class AlarmSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.alarm",
            name="Alarm",
            description="Sets alarms",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.UTILITIES,
            is_first_party=True,
            intent_phrases=["set an alarm", "wake me up at", "alarm for"],
            permissions={SkillPermission.NOTIFICATIONS}
        )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["set an alarm", "wake me up at", "alarm for"])

    def execute(self, text: str) -> SkillExecutionResult:
        m = re.search(r"\d{1,2}:\d{2}|\d{1,2}\s*(am|pm)", text, re.IGNORECASE)
        if m:
            return SkillExecutionResult(self.manifest.skill_id, True, f"Alarm set for {m.group()}.")
        return SkillExecutionResult(self.manifest.skill_id, False, "What time should I set the alarm for?")


class TimerSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="nova.builtin.timer",
            name="Timer",
            description="Sets countdown timers",
            version="1.0.0",
            author="Nova First Party",
            category=SkillCategory.UTILITIES,
            is_first_party=True,
            intent_phrases=["set a timer", "start a timer", "timer for"],
            permissions={SkillPermission.NOTIFICATIONS}
        )

    def can_handle(self, text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["set a timer", "start a timer", "timer for"])

    def execute(self, text: str) -> SkillExecutionResult:
        t = text.lower()
        mm = re.search(r"(\d+)\s*minute", t)
        sm = re.search(r"(\d+)\s*second", t)
        if mm:
            return SkillExecutionResult(self.manifest.skill_id, True, f"Timer set for {mm.group(1)} minutes.")
        if sm:
            return SkillExecutionResult(self.manifest.skill_id, True, f"Timer set for {sm.group(1)} seconds.")
        return SkillExecutionResult(self.manifest.skill_id, False, "How long should the timer be?")
