"""Opening, closing and listing applications by the name the user says ("hesap makinesini aç")."""

from typing import Any

from bilge.core.language import AssistantLanguage
from bilge.core.tools.app_name_matcher import App, AppNameMatcher
from bilge.desktop.base import AppEntry, Apps
from bilge.desktop.process import DesktopError
from bilge.tools.base import Risk, Tool, ToolError
from bilge.tools.desktop.common import failure, obj, string_argument, text

_TEXTS = {
    AssistantLanguage.TURKISH: {
        "open": "Bilgisayarda bir uygulamayı açar. Örnek: Firefox, Hesap Makinesi, Dosyalar, Spotify.",
        "quit": "Açık bir uygulamayı kapatır.",
        "list": "Şu anda açık olan uygulamaları listeler.",
        "name": "Uygulamanın adı, eksiz yalın hali. Örnek: 'Firefox', 'Hesap Makinesi'",
        "not_installed": "'{name}' adında yüklü bir uygulama bulamadım.",
        "opened": "{app} açıldı.",
        "open_failed": "{app} açılamadı.",
        "already_closed": "{app} zaten kapalı.",
        "closing": "{app} kapatılıyor.",
        "quit_question": "{app} kapatılsın mı? Kaydedilmemiş değişiklikler kaybolabilir.",
        "none_open": "Açık bir uygulama görmüyorum.",
        "open_list": "Açık uygulamalar: {apps}.",
    },
    AssistantLanguage.ENGLISH: {
        "open": "Opens an application on this computer. Examples: Firefox, Calculator, Files, Spotify.",
        "quit": "Closes an open application.",
        "list": "Lists the applications that are open right now.",
        "name": "The application's name, e.g. 'Firefox', 'Calculator'",
        "not_installed": "I couldn't find an installed app called '{name}'.",
        "opened": "{app} is open.",
        "open_failed": "{app} didn't open.",
        "already_closed": "{app} isn't open.",
        "closing": "Closing {app}.",
        "quit_question": "Shall I close {app}? Unsaved changes may be lost.",
        "none_open": "I don't see any open apps.",
        "open_list": "Open apps: {apps}.",
    },
}


class AppCatalog:
    """Resolves a spoken name to an installed app; the list is read once per catalog."""

    def __init__(self, apps: Apps):
        self.apps = apps
        self._matcher: AppNameMatcher | None = None
        self._entries: dict[str, AppEntry] = {}

    def resolve(self, spoken: str) -> AppEntry | None:
        if self._matcher is None:
            self._entries = {entry.id: entry for entry in self.apps.installed()}
            self._matcher = AppNameMatcher([App(e.id, e.names) for e in self._entries.values()])
        match = self._matcher.best_match(spoken)
        return self._entries.get(match.id) if match else None


def app_tools(catalog: AppCatalog, language: AssistantLanguage) -> list[Tool]:
    texts = _TEXTS[language]
    name_schema = obj(["appName"], appName=text(texts["name"]))

    def resolved(arguments: dict[str, Any]) -> AppEntry:
        name = string_argument(arguments, "appName")
        app = catalog.resolve(name) if name else None
        if app is None:
            raise ToolError(texts["not_installed"].format(name=name))
        return app

    def open_app(arguments: dict[str, Any]) -> str:
        app = resolved(arguments)
        try:
            catalog.apps.launch(app)
        except DesktopError as error:
            raise failure(error, language, texts["open_failed"].format(app=app.display_name)) from error
        return texts["opened"].format(app=app.display_name)

    def quit_question(arguments: dict[str, Any]) -> str | None:
        app = catalog.resolve(string_argument(arguments, "appName"))
        return texts["quit_question"].format(app=app.display_name) if app else None

    def quit_app(arguments: dict[str, Any]) -> str:
        app = resolved(arguments)
        try:
            closed = catalog.apps.quit(app)
        except DesktopError as error:
            raise failure(error, language) from error
        return texts["closing" if closed else "already_closed"].format(app=app.display_name)

    def running(_: dict[str, Any]) -> str:
        try:
            names = sorted({app.display_name for app in catalog.apps.running()})
        except DesktopError as error:
            raise failure(error, language) from error
        return texts["open_list"].format(apps=", ".join(names)) if names else texts["none_open"]

    return [
        Tool("openApp", texts["open"], run=open_app, parameters=name_schema),
        # Linux has no common "please quit" message; closing ends the program, so it asks first.
        Tool(
            "quitApp",
            texts["quit"],
            run=quit_app,
            parameters=name_schema,
            risk=Risk.CONFIRM,
            confirmation=quit_question,
        ),
        Tool("listRunningApps", texts["list"], run=running),
    ]
