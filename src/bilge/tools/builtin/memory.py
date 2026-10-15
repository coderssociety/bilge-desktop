"""Remember, forget and list facts the user dictates ("eşimin adının Ayşe olduğunu hatırla").

The fact is taken from the sentence as spoken, so the model can't put words in the user's mouth. "Remember
that" without a fact means the previous reply, which may echo a web page or an e-mail, so it is read back and
stored only after a yes.
"""

from collections.abc import Callable
from typing import Any

from bilge.core.language import AssistantLanguage
from bilge.core.memory import memory_intent
from bilge.core.memory.memory_book import MAX_ENTRY_LENGTH, AddOutcome
from bilge.tools.base import Risk, Tool, ToolError
from bilge.tools.memory_store import MemoryStore

_TEXTS = {
    AssistantLanguage.TURKISH: {
        "remember": "Kullanıcının hatırlamanı istediği bir bilgiyi kalıcı olarak kaydeder ('…olduğunu hatırla', 'unutma', 'aklında tut').",
        "fact": "Hatırlanacak bilgi, kullanıcının cümlesiyle; 'bunu hatırla' deniyorsa boş bırak",
        "forget": "Hafızaya kaydedilmiş bir bilgiyi ya da tüm hafızayı siler ('…unut', 'hafızanı temizle').",
        "about": "Silinecek bilgiyi anlatan sözcükler; 'bunu unut' için boş bırak",
        "everything": "Her şey silinecekse true",
        "list": "Hafızada kayıtlı bilgileri sayar ('neleri hatırlıyorsun').",
        "store_previous": "Şunu hatırlayayım mı: {fact}",
        "nothing_to_store": "Neyi hatırlamamı istediğini anlayamadım.",
        AddOutcome.ADDED: "Tamam, hatırlayacağım.",
        AddOutcome.ADDED_DROPPING_OLDEST: "Tamam, hatırlayacağım. Yer açmak için en eski bilgiyi unuttum.",
        AddOutcome.DUPLICATE: "Bunu zaten biliyorum.",
        AddOutcome.REJECTED: "Bu hatırlamak için fazla uzun, daha kısa söyler misin?",
        "forget_all": "Hatırladığım {count} bilginin hepsini sileyim mi?",
        "forget_one": "'{text}' bilgisini unutayım mı?",
        "empty": "Hafızamda bir şey yok.",
        "not_found": "Hafızamda '{about}' ile ilgili bir bilgi bulamadım.",
        "forgot_one": "Unuttum: {text}.",
        "forgot_all": "Hafızamı temizledim, {count} bilgiyi sildim.",
        "listed": "Hatırladıklarım: {facts}",
    },
    AssistantLanguage.ENGLISH: {
        "remember": "Permanently stores something the user asks you to remember ('remember that…', 'don't forget', 'keep in mind').",
        "fact": "The fact in the user's words; leave empty for 'remember this'",
        "forget": "Deletes a remembered fact or the whole memory ('forget…', 'clear your memory').",
        "about": "Words describing the fact to delete; leave empty for 'forget that'",
        "everything": "true to delete everything",
        "list": "Lists the remembered facts ('what do you remember').",
        "store_previous": "Shall I remember this: {fact}",
        "nothing_to_store": "I didn't catch what you want me to remember.",
        AddOutcome.ADDED: "OK, I'll remember that.",
        AddOutcome.ADDED_DROPPING_OLDEST: "OK, I'll remember that. I forgot the oldest fact to make room.",
        AddOutcome.DUPLICATE: "I already know that.",
        AddOutcome.REJECTED: "That's too long to remember; could you say it shorter?",
        "forget_all": "Shall I delete all {count} things I remember?",
        "forget_one": "Shall I forget '{text}'?",
        "empty": "I don't have anything in memory.",
        "not_found": "I couldn't find anything about '{about}' in my memory.",
        "forgot_one": "Forgotten: {text}.",
        "forgot_all": "I cleared my memory and deleted {count} facts.",
        "listed": "Here's what I remember: {facts}",
    },
}


def memory_tools(store: MemoryStore, language: AssistantLanguage, last_reply: Callable[[], str | None]) -> list[Tool]:
    texts = _TEXTS[language]

    def remember_refine(arguments: dict[str, Any], command: str) -> dict[str, Any]:
        return {"fact": memory_intent.fact(command, language) or ""}

    def to_store(arguments: dict[str, Any]) -> str:
        fact = str(arguments.get("fact") or "").strip()
        if fact:
            return fact
        previous = (last_reply() or "").strip()
        if not previous:
            raise ToolError(texts["nothing_to_store"])
        return previous[:MAX_ENTRY_LENGTH]

    def remember_question(arguments: dict[str, Any]) -> str | None:
        if str(arguments.get("fact") or "").strip():
            return None
        previous = (last_reply() or "").strip()
        return texts["store_previous"].format(fact=previous[:MAX_ENTRY_LENGTH]) if previous else None

    def remember(arguments: dict[str, Any]) -> str:
        outcome = store.remember(to_store(arguments))
        if outcome is AddOutcome.REJECTED:
            raise ToolError(texts[outcome])
        return texts[outcome]

    def target(arguments: dict[str, Any]):
        if arguments.get("everything"):
            return "all"
        about = str(arguments.get("about") or "").strip()
        return store.entry_matching(about) if about else store.book.latest

    def forget_question(arguments: dict[str, Any]) -> str | None:
        found = target(arguments)
        if found == "all":
            count = len(store.book.entries)
            return texts["forget_all"].format(count=count) if count else None
        return texts["forget_one"].format(text=found.text) if found else None

    def forget(arguments: dict[str, Any]) -> str:
        found = target(arguments)
        if found == "all":
            if not store.book.entries:
                raise ToolError(texts["empty"])
            return texts["forgot_all"].format(count=store.forget_all())
        if found is None:
            about = str(arguments.get("about") or "").strip()
            raise ToolError(texts["not_found"].format(about=about) if about else texts["empty"])
        store.forget(found.id)
        return texts["forgot_one"].format(text=found.text)

    def listing(_: dict[str, Any]) -> str:
        if not store.book.entries:
            return texts["empty"]
        return texts["listed"].format(facts=" ".join(e.text.rstrip(".") + "." for e in store.book.entries))

    return [
        Tool(
            "remember",
            texts["remember"],
            run=remember,
            parameters={"type": "object", "properties": {"fact": {"type": "string", "description": texts["fact"]}}},
            risk=Risk.CONFIRM,
            confirmation=remember_question,
            refine=remember_refine,
        ),
        Tool(
            "forget",
            texts["forget"],
            run=forget,
            parameters={
                "type": "object",
                "properties": {
                    "about": {"type": "string", "description": texts["about"]},
                    "everything": {"type": "boolean", "description": texts["everything"]},
                },
            },
            risk=Risk.CONFIRM,
            confirmation=forget_question,
        ),
        Tool("listMemories", texts["list"], run=listing),
    ]
