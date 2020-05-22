from logging import getLogger
import re
from abc import abstractmethod, ABCMeta
from typing import MutableSequence

LEXER_REGEX = re.compile(r"[0-9A-z]+|['\"]")


log = getLogger(__name__)


class Term(metaclass=ABCMeta):
    @abstractmethod
    def render(self) -> str:
        pass


class Literal(Term):
    word: str

    def __init__(self, word: str) -> None:
        self.word = word

    def render(self):
        return "'" + self.word + "'"


class CompoundTerm(Term, metaclass=ABCMeta):
    @abstractmethod
    def append(self, term: Term) -> None:
        pass


class Conjunction(CompoundTerm):
    elems: MutableSequence[Term]

    def __init__(self) -> None:
        self.elems = []

    def append(self, term: Term) -> None:
        self.elems.append(term)

    def render(self) -> str:
        return " & ".join(e.render() for e in self.elems)


class Quote(CompoundTerm):
    quotes = {"'", '"'}

    literals: MutableSequence[Term]
    parent: CompoundTerm
    quote_char: str

    def __init__(self, parent: CompoundTerm) -> None:
        self.literals = []
        self.parent = parent

    def append(self, literal: Term) -> None:
        self.literals.append(literal)

    def render(self) -> str:
        return " <-> ".join(l.render() for l in self.literals)


def parse_search_str(search_str: str) -> str:
    """Parse a web search string into tquery format"""
    token_iterator = LEXER_REGEX.finditer(search_str)

    current_term: CompoundTerm = Conjunction()
    base_term = current_term
    for match_obj in token_iterator:
        token = match_obj.group(0)
        log.debug("token = '%s'", token)
        log.debug("base_term = '%s'", base_term.render())
        # FIXME: Need to handle apostrophe
        if token in Quote.quotes:
            if isinstance(current_term, Quote):
                current_term = current_term.parent
            else:
                quote = Quote(current_term)
                current_term.append(quote)
                current_term = quote
        else:
            term = Literal(token)
            current_term.append(term)

    return base_term.render()
