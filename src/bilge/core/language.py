from enum import StrEnum


class AssistantLanguage(StrEnum):
    """The language the assistant listens, speaks and shows its menus in; chosen during setup."""

    TURKISH = "tr"
    ENGLISH = "en"

    @property
    def code(self) -> str:
        """ISO 639-1 code, as speech recognizers and the synthesizer expect it."""
        return self.value

    @property
    def native_name(self) -> str:
        """The language's own name, so it reads right whichever language is active."""
        return "Türkçe" if self is AssistantLanguage.TURKISH else "English"

    @classmethod
    def preferred(cls, identifiers: list[str]) -> "AssistantLanguage":
        """The first of the system's preferred languages that Bilge speaks, Turkish otherwise."""
        for identifier in identifiers:
            code = identifier.replace("-", "_").split("_")[0].lower()
            for language in cls:
                if language.code == code:
                    return language
        return cls.TURKISH
