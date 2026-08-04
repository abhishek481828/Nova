#!/usr/bin/env python3
"""Interactive Manual Test Utility for Nova v3.0 Phase 1, Phase 2 & Phase 3."""

import sys
import time
from nova.mobile.core import MobileCoreManager
from nova.mobile.plugins import PluginManager, MobilePlugin
from nova.mobile.lifecycle import LifecycleManager
from nova.mobile.scheduler import TaskScheduler, MobileTask
from nova.mobile.storage import MobileDatabase
from nova.mobile.settings import ConfigurationManager, MobileConfig
from nova.mobile.security import MobileSecurityManager
from nova.mobile.communication import CommunicationBridge, MobileCommand, ExecutionTarget
from nova.mobile.wakeword.manager import WakeWordManager
from nova.mobile.voice.manager import VoiceManager


def print_header(title):
    print("\n" + "=" * 65)
    print(f"   {title}")
    print("=" * 65)


def main():
    print_header("NOVA v3.0 MOBILE — MANUAL TEST INTERFACE")

    core = MobileCoreManager.get_instance()
    db = MobileDatabase()
    pm = PluginManager()
    lm = LifecycleManager()
    scheduler = TaskScheduler()
    sec = MobileSecurityManager()
    bridge = CommunicationBridge()
    cfg = ConfigurationManager()
    ww_manager = core.wake_word_manager
    voice_mgr = core.voice_manager

    while True:
        print("\nSelect an operation to test:")
        print(" [1] Initialize Nova Mobile Core (Startup Sequence)")
        print(" [2] View System Health & Dashboard Status")
        print(" [3] Test Plugin Manager (Register / List / Disable / Unregister)")
        print(" [4] Test Local Encrypted Storage (Save Setting / Read / Event Log)")
        print(" [5] Test Task Scheduler (Immediate / Delayed / Periodic / Cancel)")
        print(" [6] Test Lifecycle Event Bus (Publish AppStarted, BatteryLow, Network)")
        print(" [7] Test Security Manager (KeyStore Session Tokens)")
        print(" [8] Test Communication Bridge (Target Execution Routing)")
        print(" [9] Test Wake Word Engine (Start / Trigger 'Hey Nova' / Restart)")
        print(" [10] Test Voice Pipeline & Speech Recognition ('Call Pankaj' -> Event)")
        print(" [11] Graceful System Shutdown")
        print(" [0] Exit")

        try:
            choice = input("\nNova Mobile ❯ ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if choice == "1":
            print("\n[INFO] Initializing Nova Mobile Core v3.0...")
            core.initialize()
            db.initialize()
            pm.initialize()
            lm.initialize()
            scheduler.initialize()
            sec.initialize()
            bridge.initialize()
            cfg.initialize()
            print("✔ Mobile Core initialized successfully!")

        elif choice == "2":
            health = core.get_health_status()
            print_header("SYSTEM HEALTH & DASHBOARD STATUS")
            for k, v in health.items():
                print(f" • {k.ljust(24)}: {v}")
            print(f" • DB Status              : {if_str(db.is_open, 'OPEN & ENCRYPTED', 'CLOSED')}")
            print(f" • Active Plugins         : {pm.get_active_count()}")
            print(f" • Scheduler Running      : {scheduler.is_running}")
            print(f" • Security Ready         : {sec.is_ready}")
            print(f" • Wake Word Status       : {if_str(ww_manager.is_listening, 'LISTENING 🟢', 'IDLE ⚪')}")
            print(f" • Voice Session State    : {health['voice_state']}")

        elif choice == "3":
            print_header("PLUGIN MANAGER TEST")
            print("Registering test plugin: 'battery_optimizer'...")
            plugin = MobilePlugin("battery_opt", "Battery Optimizer Plugin v1.0")
            registered = pm.register_plugin(plugin)
            print(f"✔ Registered: {registered}")
            print(f"Active Plugin Count: {pm.get_active_count()}")
            print(f"Unregistering 'battery_opt'...")
            pm.unregister_plugin("battery_opt")
            print(f"✔ Remaining Active Plugins: {pm.get_active_count()}")

        elif choice == "4":
            print_header("LOCAL ENCRYPTED STORAGE TEST")
            key = input("Enter setting key (default: theme): ").strip() or "theme"
            val = input("Enter setting value (default: dark_mode): ").strip() or "dark_mode"
            db.save_setting(key, val)
            retrieved = db.get_setting(key)
            print(f"✔ Saved & Retrieved: {key} => {retrieved}")

            cmd = db.record_command("mobile.test_action", "success")
            print(f"✔ Command Logged: ID={cmd.id}, Action={cmd.action}")

        elif choice == "5":
            print_header("TASK SCHEDULER TEST")
            executed_flag = [False]

            def sample_task():
                print("\n⚡ [TaskScheduler] Immediate task executed successfully!")
                executed_flag[0] = True
                return True

            task = MobileTask("task_001", "Sample Manual Task", action=sample_task)
            scheduler.schedule_immediate(task)
            time.sleep(0.1)
            print(f"✔ Task execution verified: {executed_flag[0]}")

        elif choice == "6":
            print_header("LIFECYCLE EVENT BUS TEST")
            lm.publish_event("AppStarted", {"version": "3.0.0"})
            lm.publish_event("BatteryLow", {"level": 15})
            lm.publish_event("NetworkConnected", {"type": "WIFI"})

            history = lm.get_event_history()
            print(f"✔ Published {len(history)} Lifecycle Events:")
            for evt in history:
                print(f"   • Event: {evt.event_name} | Payload: {evt.payload}")

        elif choice == "7":
            print_header("SECURITY MANAGER TEST")
            token = sec.generate_session_token()
            print(f"✔ Generated Token : {token}")
            valid = sec.validate_session_token(token)
            print(f"✔ Is Valid Token  : {valid}")
            sec.revoke_session_token(token)
            revoked_valid = sec.validate_session_token(token)
            print(f"✔ Post Revocation : {revoked_valid}")

        elif choice == "8":
            print_header("COMMUNICATION BRIDGE TEST")
            cmd_local = MobileCommand(action="mobile.device_info", preferred_target=ExecutionTarget.LOCAL)
            res_local = bridge.execute_command(cmd_local)
            print(f"✔ Local Routing Output : Executed by {res_local.executed_by} (status={res_local.status})")

        elif choice == "9":
            print_header("OFFLINE WAKE WORD ENGINE TEST")
            print(f"Configured Phrase: '{ww_manager.config.wake_phrase}' (Sensitivity: {ww_manager.config.sensitivity})")
            
            started = ww_manager.start_listening()
            print(f"✔ Start Listening State: {started} (is_listening={ww_manager.is_listening})")
            
            print("Simulating detection trigger for 'Hey Nova'...")
            ww_manager.trigger_wake_detection(score=0.97)
            print(f"✔ Detection Counter: {ww_manager.metrics.total_detections} total detections")
            print(f"✔ Voice Session State after Wake Detection: {voice_mgr.current_session.current_state.value}")

        elif choice == "10":
            print_header("VOICE PIPELINE & SPEECH RECOGNITION TEST")
            speech_prompt = input("Enter speech prompt (default: 'Call Pankaj'): ").strip() or "Call Pankaj"
            
            session = voice_mgr.start_voice_session()
            print(f"✔ Session Started: ID={session.session_id}, State={session.current_state.value}")
            
            print(f"Simulating speech-to-text recognition for: \"{speech_prompt}\"...")
            voice_mgr.simulate_recognized_text(speech_prompt, confidence=0.98)
            
            print(f"✔ Final Recognized Text : \"{voice_mgr.metrics.last_recognized_text}\"")
            print(f"✔ Session End State     : {session.current_state.value}")

        elif choice == "11":
            print("\n[INFO] Shutting down Nova Mobile Core...")
            core.shutdown()
            db.close()
            scheduler.cancel_all()
            bridge.shutdown()
            print("✔ Shutdown complete.")

        elif choice == "0":
            print("Exiting Nova Mobile manual test.")
            break
        else:
            print("Invalid option. Please enter 0 to 11.")


def if_str(cond, val_true, val_false):
    return val_true if cond else val_false


if __name__ == "__main__":
    main()
