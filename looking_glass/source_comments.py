"""Comment tokenization for the Marker Tree without evaluating source."""
import io
import re
import tokenize

HASH = {'.sh', '.bash', '.yaml', '.yml', '.toml', '.r', '.rb', '.pl'}
SLASH = {'.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.c', '.h', '.cpp',
         '.hpp', '.cs', '.java', '.go', '.rs', '.css', '.scss', '.swift', '.kt', '.php'}
SUPPORTED = HASH | SLASH | {'.py', '.pyi', '.md', '.markdown', '.html', '.htm', '.sql', '.lua'}


def python_comments(content):
    """Tokenize without executing code and retain comments preceding syntax errors."""
    try:
        for token in tokenize.generate_tokens(io.StringIO(content).readline):
            if token.type == tokenize.COMMENT:
                yield token
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass


def source_comment_lines(suffix, content):
    """Yield the offsets and text of comments in other supported source files."""
    comment = r'\#[^\r\n]*' if suffix in HASH else r'//[^\r\n]*|/\*[\s\S]*?\*/' if suffix in SLASH else r'<!--[\s\S]*?-->' if suffix in {'.html', '.htm'} else r'--[^\r\n]*|/\*[\s\S]*?\*/'
    # Skip quoted strings before recognizing comment delimiters. Template
    # literals stay literal, including their embedded expressions.
    tokens = re.compile(r'''"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|`(?:\\[\s\S]|[^`\\])*`|(?P<comment>''' + comment + ')')
    for token in tokens.finditer(content):
        if token.group('comment'):
            offset = token.start()
            for line in token.group().splitlines(keepends=True):
                yield offset, line.rstrip('\r\n')
                offset += len(line)
