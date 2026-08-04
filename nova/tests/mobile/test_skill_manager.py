"""Nova v3.0 Phase 9 Automated Test Suite: AI Skills Framework & Plugin Marketplace."""

import pytest
from nova.mobile.skills.enums import (
    SkillPermission, SkillStatus, SkillCategory, SkillLifecycleEvent
)
from nova.mobile.skills.manifest import SkillManifest
from nova.mobile.skills.context import SkillContext, SkillMemoryApi, SkillNotificationApi
from nova.mobile.skills.base_skill import BaseSkill, SkillExecutionResult
from nova.mobile.skills.registry import SkillRegistry
from nova.mobile.skills.loader import SkillLoader
from nova.mobile.skills.executor import SkillExecutor
from nova.mobile.skills.manager import SkillManager
from nova.mobile.skills.builtin_skills import (
    CalculatorSkill, UnitConverterSkill, DeviceStatusSkill, NotesSkill,
    TranslatorSkill, WeatherSkill, ReminderSkill, AlarmSkill, TimerSkill
)
from nova.mobile.lifecycle import LifecycleManager


# ─── Mock Skill ──────────────────────────────────────────────────────────────

class CustomSampleSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            skill_id="com.example.sample",
            name="Sample Skill",
            description="Sample skill for testing",
            version="1.0.0",
            author="Test Author",
            category=SkillCategory.CUSTOM,
            permissions={SkillPermission.CAMERA, SkillPermission.NOTIFICATIONS},
            intent_phrases=["run sample", "do sample"]
        )

    def can_handle(self, text: str) -> bool:
        return "sample" in text.lower()

    def execute(self, text: str) -> SkillExecutionResult:
        if "fail" in text.lower():
            raise ValueError("Intentional failure")
        return SkillExecutionResult(self.manifest.skill_id, True, "Sample skill executed successfully.")


# ─── Manifest Validation Tests ───────────────────────────────────────────────

def test_manifest_validation_success():
    m = SkillManifest("test.id", "Test", "Desc", "1.0", "Author", SkillCategory.UTILITIES)
    ok, err = m.validate()
    assert ok is True
    assert err is None


def test_manifest_validation_blank_id():
    m = SkillManifest("", "Test", "Desc", "1.0", "Author", SkillCategory.UTILITIES)
    ok, err = m.validate()
    assert ok is False
    assert "Skill ID" in err


def test_manifest_validation_space_in_id():
    m = SkillManifest("invalid id", "Test", "Desc", "1.0", "Author", SkillCategory.UTILITIES)
    ok, err = m.validate()
    assert ok is False
    assert "spaces" in err


# ─── SkillContext Tests ──────────────────────────────────────────────────────

def test_skill_context_has_permission():
    ctx = SkillContext("test", {SkillPermission.CAMERA, SkillPermission.NOTIFICATIONS})
    assert ctx.has_permission(SkillPermission.CAMERA) is True
    assert ctx.has_permission(SkillPermission.SMS) is False


def test_skill_context_require_permission_raises():
    ctx = SkillContext("test", {SkillPermission.NOTIFICATIONS})
    ctx.require_permission(SkillPermission.NOTIFICATIONS)  # pass
    with pytest.raises(PermissionError):
        ctx.require_permission(SkillPermission.CAMERA)


# ─── Registry & Loader Tests ──────────────────────────────────────────────────

def test_registry_register_and_get():
    reg = SkillRegistry()
    skill = CustomSampleSkill()
    assert reg.register(skill) is True
    assert reg.get("com.example.sample") is not None


def test_registry_intent_phrase_index():
    reg = SkillRegistry()
    skill = CustomSampleSkill()
    reg.register(skill)
    assert len(reg.get_intent_index()) == 2
    assert "run sample" in reg.get_intent_index()


def test_loader_lifecycle():
    reg = SkillRegistry()
    loader = SkillLoader(reg)
    skill = CustomSampleSkill()
    ctx = SkillContext("com.example.sample", {SkillPermission.NOTIFICATIONS})

    assert loader.install(skill, ctx) is True
    assert skill.status == SkillStatus.INSTALLED

    assert loader.load("com.example.sample") is True
    assert skill.status == SkillStatus.LOADED

    assert loader.enable("com.example.sample") is True
    assert skill.status == SkillStatus.RUNNING

    assert loader.disable("com.example.sample") is True
    assert skill.status == SkillStatus.DISABLED

    assert loader.unload("com.example.sample") is True
    assert reg.get("com.example.sample") is None


# ─── SkillExecutor Tests ─────────────────────────────────────────────────────

def test_executor_matching_and_execution():
    reg = SkillRegistry()
    loader = SkillLoader(reg)
    executor = SkillExecutor(reg)

    skill = CustomSampleSkill()
    ctx = SkillContext("com.example.sample", set())
    loader.install(skill, ctx)
    loader.load("com.example.sample")
    loader.enable("com.example.sample")

    res = executor.execute("Please run sample now")
    assert res is not None
    assert res.is_success is True
    assert "Sample skill executed" in res.spoken_response


def test_executor_handles_exception_gracefully():
    reg = SkillRegistry()
    loader = SkillLoader(reg)
    executor = SkillExecutor(reg)

    skill = CustomSampleSkill()
    ctx = SkillContext("com.example.sample", set())
    loader.install(skill, ctx)
    loader.load("com.example.sample")
    loader.enable("com.example.sample")

    res = executor.execute("run sample fail")
    assert res is not None
    assert res.is_success is False
    assert "encountered an error" in res.spoken_response


# ─── SkillManager Integration Tests ──────────────────────────────────────────

def test_manager_install_and_load_builtin_skills():
    lm = LifecycleManager()
    lm.initialize()
    sm = SkillManager(lifecycle_manager=lm)

    skills = [
        CalculatorSkill(), UnitConverterSkill(), DeviceStatusSkill(),
        NotesSkill(), TranslatorSkill(), WeatherSkill(),
        ReminderSkill(), AlarmSkill(), TimerSkill()
    ]

    for s in skills:
        assert sm.install_and_load(s) is True

    assert sm.registry.count() == 9
    assert sm.registry.count_enabled() == 9


def test_calculator_skill_execution():
    sm = SkillManager()
    sm.install_and_load(CalculatorSkill())

    res = sm.handle_voice_text("Calculate 15 plus 27")
    assert res is not None
    assert res.is_success is True
    assert "42" in res.spoken_response


def test_unit_converter_skill_execution():
    sm = SkillManager()
    sm.install_and_load(UnitConverterSkill())

    res = sm.handle_voice_text("Convert 10 km to miles")
    assert res is not None
    assert res.is_success is True
    assert "6.21" in res.spoken_response


def test_device_status_skill_execution():
    sm = SkillManager()
    sm.install_and_load(DeviceStatusSkill())

    res = sm.handle_voice_text("How much battery do I have left?")
    assert res is not None
    assert res.is_success is True


def test_translator_skill_execution():
    sm = SkillManager()
    sm.install_and_load(TranslatorSkill())

    res = sm.handle_voice_text("How do you say hello in Japanese?")
    assert res is not None
    assert res.is_success is True
    assert "Konnichiwa" in res.spoken_response


def test_permission_approval_flow():
    lm = LifecycleManager()
    lm.initialize()
    sm = SkillManager(lifecycle_manager=lm)

    skill = CustomSampleSkill()  # Requires CAMERA (needs approval) + NOTIFICATIONS (auto)
    sm.install_and_load(skill)

    pending = sm.get_pending_permissions()
    assert "com.example.sample" in pending
    assert SkillPermission.CAMERA in pending["com.example.sample"]

    # Approve
    sm.approve_permission("com.example.sample", SkillPermission.CAMERA)
    assert SkillPermission.CAMERA in sm.registry.get_granted_permissions("com.example.sample")


def test_search_skills():
    sm = SkillManager()
    sm.install_and_load(CalculatorSkill())
    sm.install_and_load(WeatherSkill())

    calc_res = sm.search_skills("calc")
    assert len(calc_res) == 1
    assert calc_res[0].manifest.name == "Calculator"


def test_remove_skill():
    sm = SkillManager()
    sm.install_and_load(CalculatorSkill())
    assert sm.registry.count() == 1
    assert sm.remove("nova.builtin.calculator") is True
    assert sm.registry.count() == 0
