from __future__ import annotations

def remove_extra_spaces(text: str | None) -> str | None:
    if not text:
        return text
    return text.replace(' ', '')


def process_text(en_text: str | None, zh_text: str | None) -> str | None:
    if not zh_text:
        return zh_text
    return remove_extra_spaces(zh_text)
