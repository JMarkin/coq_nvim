from string import ascii_letters, ascii_lowercase, digits
from typing import AbstractSet, MutableSequence, Optional

from ...shared.types import Context
from .lexer import context_from, next_char, pushback_chars, raise_err, token_parser
from .types import (
    End,
    IntBegin,
    Parsed,
    ParseInfo,
    ParserCtx,
    Token,
    TokenStream,
    Unparsed,
    VarBegin,
)

"""
any          ::= tabstop | variable | placeholder | text
tabstop      ::= '$' int | '${' int '}'
placeholder  ::= '${' int ':' ('#:'? any | regexreplace) '}'
variable     ::= '${' var '}' | '${' var ':' any '}'
regexreplace ::= '/' text '/' text '/' [a-z]*
lang         ::= '`' text  '`' | '`!' [a-z] text '`'
var          ::= ([A-z] | '$') [A-z]+
int          ::= [0-9]+
text         ::= .*
"""


_ESCAPABLE_CHARS = {"\\", "$", "}"}
_REGEX_ESCAPABLE_CHARS = {"/"}
_LANG_ESCAPE_CHARS = {"`"}
_INT_CHARS = {*digits}
_VAR_BEGIN_CHARS = {*ascii_letters, "$"}
_LANG_BEGIN_CHARS = {*ascii_lowercase}
_REGEX_FLAG_CHARS = {*ascii_lowercase}


def _lex_escape(context: ParserCtx, *, escapable_chars: AbstractSet[str]) -> str:
    pos, char = next_char(context)
    assert char == "\\"

    pos, char = next_char(context)
    if char in escapable_chars:
        return char
    else:
        pushback_chars(context, (pos, char))
        return "\\"


# regexreplace ::= '/' text '/' text '/' [a-z]*
def _lex_decorated(context: ParserCtx) -> TokenStream:
    pos, char = next_char(context)
    assert char == "/"

    decoration_acc = [char]
    seen = 1
    for pos, char in context:
        if char == "\\":
            pushback_chars(context, (pos, char))
            char = _lex_escape(context, escapable_chars=_REGEX_ESCAPABLE_CHARS)
            decoration_acc.append(char)
        elif char == "/":
            seen += 1
            if seen >= 3:
                for pos, char in context:
                    if char in _REGEX_FLAG_CHARS:
                        decoration_acc.append(char)
                    elif char == "}":
                        decoration = "".join(decoration_acc)
                        yield Unparsed(text=decoration)
                        return
                    else:
                        raise_err(
                            text=context.text,
                            pos=pos,
                            condition="after /../../",
                            expected=("[a-z]"),
                            actual=char,
                        )
        else:
            pass


# tabstop      ::= '$' int | '${' int '}'
# placeholder  ::= '${' int ':' ('#:'? any | regexreplace) '}'
def _lex_tp(context: ParserCtx) -> TokenStream:
    idx_acc: MutableSequence[str] = []

    for pos, char in context:
        if char in _INT_CHARS:
            idx_acc.append(char)
        else:
            idx = int("".join(idx_acc))
            yield IntBegin(idx=idx)
            if char == "}":
                # tabstop     ::= '$' int | '${' int '}'
                yield End()
                break
            elif char == ":":
                context.stack.append(idx)
                (p1, c1), (p2, c2) = next_char(context), next_char(context)
                # placeholder  ::= '${' int ':' ('#:'? any | regexreplace) '}'
                if c1 == "#" and c2 == ":":
                    pass
                else:
                    pushback_chars(context, (p1, c1), (p2, c2))
                break
            elif char == "/":
                pushback_chars(context, (pos, char))
                yield from _lex_decorated(context)
                yield End()
                break
            else:
                raise_err(
                    text=context.text,
                    pos=pos,
                    condition="after '${' int",
                    expected=("}", ":"),
                    actual=char,
                )


def _variable_substitution(context: ParserCtx, *, name: str) -> Optional[str]:
    if name == "VISUAL":
        return context.info.visual
    else:
        return None


# variable    ::= '${' var '}' | '${' var ':' any '}'
def _lex_variable(context: ParserCtx) -> TokenStream:
    name_acc: MutableSequence[str] = []

    for pos, char in context:
        if char == "}":
            name = "".join(name_acc)
            var = _variable_substitution(context, name=name)
            yield var if var is not None else name
            break
        elif char == ":":
            name = "".join(name_acc)
            var = _variable_substitution(context, name=name)
            if var is not None:
                yield var
                context.stack.append(name)
                yield from _lex(context, shallow=True)
            else:
                yield VarBegin(name=name)
                context.stack.append(name)
            break
        else:
            name_acc.append(char)


# ${...}
def _lex_inner_scope(context: ParserCtx) -> TokenStream:
    pos, char = next_char(context)
    assert char == "{"

    pos, char = next_char(context)
    if char in _INT_CHARS:
        # tabstop | placeholder
        pushback_chars(context, (pos, char))
        yield from _lex_tp(context)
    elif char in _VAR_BEGIN_CHARS:
        # variable
        pushback_chars(context, (pos, char))
        yield from _lex_variable(context)
    else:
        raise_err(
            text=context.text,
            pos=pos,
            condition="after ${",
            expected=("0-9", "A-z", "$"),
            actual=char,
        )


# $...
def _lex_scope(context: ParserCtx) -> TokenStream:
    pos, char = next_char(context)
    assert char == "$"

    pos, char = next_char(context)
    if char == "{":
        pushback_chars(context, (pos, char))
        yield from _lex_inner_scope(context)
    elif char in _INT_CHARS:
        idx_acc = [char]
        # tabstop     ::= '$' int
        for pos, char in context:
            if char in _INT_CHARS:
                idx_acc.append(char)
            else:
                yield IntBegin(idx=int("".join(idx_acc)))
                yield End()
                pushback_chars(context, (pos, char))
                break
    else:
        pushback_chars(context, (pos, char))


# lang         ::= '`' text  '`' | '`!' [a-z] text '`'
def _lex_lang(context: ParserCtx) -> Token:
    pos, char = next_char(context)
    assert char == "`"

    acc: MutableSequence[str] = []
    for pos, char in context:
        if char == "\\":
            pushback_chars(context, (pos, char))
            esc = _lex_escape(context, escapable_chars=_ESCAPABLE_CHARS)
            acc.append(esc)
        elif char == "`":
            return Unparsed(text=f"`{''.join(acc)}`")
        else:
            acc.append(char)

    raise_err(context.text, pos=pos, condition="after `", expected=("`",), actual="")


# any          ::= tabstop | variable | placeholder | text
def _lex(context: ParserCtx, shallow: bool) -> TokenStream:
    for pos, char in context:
        if char == "\\":
            pushback_chars(context, (pos, char))
            yield _lex_escape(context, escapable_chars=_ESCAPABLE_CHARS)
        elif context.stack and char == "}":
            yield End()
            context.stack.pop()
            if shallow:
                break
        elif char == "$":
            pushback_chars(context, (pos, char))
            yield from _lex_scope(context)
        elif char == "`":
            pushback_chars(context, (pos, char))
            yield _lex_lang(context)
        else:
            yield char


def tokenizer(context: Context, info: ParseInfo, snippet: str) -> Parsed:
    ctx = context_from(snippet, context=context, info=info)
    tokens = _lex(ctx, shallow=False)
    parsed = token_parser(ctx, stream=tokens)
    return parsed
