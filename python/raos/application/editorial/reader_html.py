"""Strict HTML fragments shared by reader components; no browser or network."""
from __future__ import annotations
from collections.abc import Iterable
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser

VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict[str, str | None])
    children: list[Element | str] = field(default_factory=lambda: list[Element | str]())
    parent: Element | None = field(default=None, repr=False)

    def has(self, name: str) -> bool:
        return name in (self.attrs.get("class") or "").split()

    def walk(self) -> Iterable[Element]:
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()

    def find(self, *, tag: str | None = None, cls: str | None = None) -> list[Element]:
        return [e for e in self.walk() if (tag is None or e.tag == tag) and (cls is None or e.has(cls))]

    def text(self) -> str:
        return unescape("".join(c.text() if isinstance(c, Element) else c for c in self.children)).strip()

    def html(self) -> str:
        content = "".join(c.html() if isinstance(c, Element) else c for c in self.children)
        if not self.tag:
            return content
        attrs = "".join(f" {key}" if value is None else f' {key}="{escape(value, quote=True)}"' for key, value in self.attrs.items())
        return f"<{self.tag}{attrs}>" + ("" if self.tag in VOID else content + f"</{self.tag}>")

    def remove(self) -> None:
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
        self.parent = None

    def append(self, child: Element | str) -> None:
        if isinstance(child, Element):
            child.remove()
            child.parent = self
        self.children.append(child)

    def insert_before(self, child: Element) -> None:
        parent = self.parent
        if parent is None:
            raise ValueError("READER_VIEW_PARENT_MISSING")
        child.remove()
        child.parent = parent
        parent.children.insert(parent.children.index(self), child)


class FragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = Element("")
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, dict(attrs))
        self.current.append(element)
        if tag not in VOID:
            self.current = element

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.current.tag != tag or self.current.parent is None:
            raise ValueError("READER_VIEW_UNBALANCED_MARKUP")
        self.current = self.current.parent

    def handle_data(self, data: str) -> None:
        self.current.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.handle_data(f"<!--{data}-->")


def fragment(markup: str) -> Element:
    parser = FragmentParser()
    parser.feed(markup)
    parser.close()
    if parser.current is not parser.root:
        raise ValueError("READER_VIEW_UNBALANCED_MARKUP")
    return parser.root


def block(markup: str) -> Element:
    return next(c for c in fragment(markup).children if isinstance(c, Element))

