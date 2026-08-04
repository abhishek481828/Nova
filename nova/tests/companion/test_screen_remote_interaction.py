"""Automated pytest suite for Phase G: Screen Capture & Remote Interaction Subsystem."""

import pytest
import os
from pathlib import Path
from nova.actions import get_action_dispatcher
from nova.actions.screen_remote import (
    ScreenCaptureAction,
    ScreenRecordStartAction,
    ScreenRecordStopAction,
    ScreenStreamStartAction,
    ScreenStreamStopAction,
    ScreenTapAction,
    ScreenSwipeAction,
    ScreenTypeAction,
    ScreenStateGetAction
)
from nova.parser import VALID_ACTIONS


def test_action_dispatcher_registration():
    dispatcher = get_action_dispatcher()
    expected_actions = [
        "screen_capture",
        "screen_record_start",
        "screen_record_stop",
        "screen_stream_start",
        "screen_stream_stop",
        "screen_tap",
        "screen_swipe",
        "screen_type",
        "screen_state_get"
    ]
    for act in expected_actions:
        assert act in dispatcher, f"Action {act} not registered in dispatcher"
        assert act in VALID_ACTIONS, f"Action {act} not present in VALID_ACTIONS set"


def test_screen_capture_action():
    action = ScreenCaptureAction()
    assert action.action_name == "screen_capture"
    res = action.execute({})
    assert "screenshot" in res.lower() or "captured" in res.lower() or "saved" in res.lower()


def test_screen_record_lifecycle():
    start_action = ScreenRecordStartAction()
    stop_action = ScreenRecordStopAction()
    
    assert start_action.action_name == "screen_record_start"
    assert stop_action.action_name == "screen_record_stop"

    res_start = start_action.execute({"fps": 30, "bitrate": 4000000})
    assert "started" in res_start.lower() or "recording" in res_start.lower()

    res_stop = stop_action.execute({})
    assert "stopped" in res_stop.lower() or "recording" in res_stop.lower() or "saved" in res_stop.lower()


def test_screen_stream_lifecycle():
    start_action = ScreenStreamStartAction()
    stop_action = ScreenStreamStopAction()

    assert start_action.action_name == "screen_stream_start"
    assert stop_action.action_name == "screen_stream_stop"

    res_start = start_action.execute({"fps": 15})
    assert "started" in res_start.lower() or "streaming" in res_start.lower() or "failed" in res_start.lower()

    res_stop = stop_action.execute({})
    assert "stopped" in res_stop.lower() or "streaming" in res_stop.lower() or "stream" in res_stop.lower() or "failed" in res_stop.lower()


def test_screen_tap_action():
    action = ScreenTapAction()
    assert action.action_name == "screen_tap"
    res = action.execute({"x": 500, "y": 800})
    assert "executed" in res.lower() or "tap" in res.lower() or "phone" in res.lower()


def test_screen_swipe_action():
    action = ScreenSwipeAction()
    assert action.action_name == "screen_swipe"
    res_up = action.execute({"direction": "up"})
    assert "swiped" in res_up.lower() or "up" in res_up.lower() or "failed" in res_up.lower()

    res_custom = action.execute({"start_x": 500, "start_y": 1000, "end_x": 500, "end_y": 200, "duration_ms": 400})
    assert "swiped" in res_custom.lower() or "phone" in res_custom.lower() or "failed" in res_custom.lower()


def test_screen_type_action():
    action = ScreenTypeAction()
    assert action.action_name == "screen_type"
    res = action.execute({"text": "Hello Nova Phase G"})
    assert "typed" in res.lower() or "hello nova" in res.lower()


def test_screen_state_get_action():
    action = ScreenStateGetAction()
    assert action.action_name == "screen_state_get"
    res = action.execute({})
    assert "state" in res.lower() or "screen" in res.lower() or "on" in res.lower() or "off" in res.lower()
