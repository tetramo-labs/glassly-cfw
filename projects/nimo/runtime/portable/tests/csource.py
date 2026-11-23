"""C source helpers for the port checks: mask comments and literals, find
balanced spans, extract a function body, list assertion predicates. MIT."""
import hashlib
import re


def mask(text):
    return re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                  lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def balanced(text, start, opening, closing):
    m = mask(text)
    depth = 0
    for i in range(start, len(text)):
        if m[i] == opening:
            depth += 1
        elif m[i] == closing:
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError('Unbalanced source')


def predicates(text, names=('CHECK', 'assert', 'expect')):
    m = mask(text)
    result = []
    for match in re.finditer(r'\b(' + '|'.join(names) + r')\s*\(', m):
        line_start = text.rfind('\n', 0, match.start()) + 1
        if text[line_start:match.start()].lstrip().startswith('#'):
            continue
        start = m.index('(', match.start())
        end = balanced(text, start, '(', ')')
        expr = text[start + 1:end - 1]
        result.append({'line': text.count('\n', 0, match.start()) + 1, 'macro': match[1],
                       'expression': expr, 'sha256': hashlib.sha256(expr.encode()).hexdigest()})
    return result


def function(text, name):
    m = mask(text)
    hit = re.search(r'^(?:static\s+)?[^\n;{}]+\b' + name + r'\s*\([^;{}]*\)\s*\{', m, re.M)
    if not hit:
        raise ValueError('Missing function ' + name)
    start = m.index('{', hit.start())
    end = balanced(text, start, '{', '}')
    return text[hit.start():end], text.count('\n', 0, hit.start()) + 1, text.count('\n', 0, end) + 1
