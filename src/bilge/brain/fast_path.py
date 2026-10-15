"""Common Turkish commands recognized without the language model ("saat kaç", "sesi yüzde 30 yap", "müziği durdur"),
so they are answered at once and cost nothing. The call still goes through the agent's checks and the action log; a
call that can't be bound with certainty (no installed app matches) fails, and the model gets the command instead."""

from bilge.core.conversation import quick_intent_parser as q
from bilge.core.language import AssistantLanguage
from bilge.llm.messages import ToolCall

_VOLUME_STEPS = {q.VolumeStep.UP: "increase", q.VolumeStep.DOWN: "decrease", q.VolumeStep.MUTE: "mute",
                 q.VolumeStep.UNMUTE: "unmute"}  # fmt: skip


def call_for(command: str, language: AssistantLanguage) -> ToolCall | None:
    """`command` is already resolved (digits, times of day). English commands always go to the model."""
    if language is not AssistantLanguage.TURKISH:
        return None
    found = _tool_and_arguments(q.parse(command))
    return ToolCall("fast-path", found[0], found[1]) if found else None


def _tool_and_arguments(intent: q.QuickIntent | None) -> tuple[str, dict] | None:
    match intent:
        case q.DateTime():
            return "currentDateTime", {}
        case q.Calculate(expression=expression):
            return "calculate", {"expression": expression}
        case q.Battery():
            return "batteryStatus", {}
        case q.Reminders():
            return "readReminders", {}
        case q.Volume(change=q.SetVolume(level=level)):
            return "setVolume", {"action": "set", "level": level}
        case q.Volume(change=step):
            return "setVolume", {"action": _VOLUME_STEPS[step]}
        case q.Media(action=action):
            return "controlMusic", {"action": action.value}
        case q.System(action=action):
            return "systemAction", {"action": action.value}
        case q.Calendar(range=span):
            return "readCalendar", {"range": span.value}
        case q.Timer(seconds=seconds):
            return "setTimer", {"minutes": seconds // 60, "seconds": seconds % 60}
        case q.Alarm(hour=hour, minute=minute):
            return "setTimer", {"hour": hour, "minute": minute}
        case q.Clipboard():
            return "readClipboard", {}
        case q.OpenFolder(folder=folder):
            return "files", {"action": "openFolder", "folder": folder.value}
        case q.Timers(action=action):
            return "manageTimers", {"action": action.value}
        case q.OpenApp(name=name):
            return "openApp", {"appName": name}
        case q.QuitApp(name=name):
            return "quitApp", {"appName": name}
        case q.Screenshot():
            return "takeScreenshot", {"area": "wholeScreen", "toClipboard": False}
        case q.Wifi(on=on):
            return "setWiFi", {"power": "on" if on else "off"}
        case q.Settings(pane=pane):
            return "openSettings", {"pane": pane.value}
        case q.SystemInfo(topic=topic):
            return "systemInfo", {"topic": topic.value}
    return None
