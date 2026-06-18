"""F1 mitigation — structural enforcement that NO f-string SQL exists in similarity_matcher.py."""
import pathlib
import re


def test_no_fstring_sql_in_module():
    """F1 gate decision (applied 2026-06-17): the source file must NOT contain f-string SQL.
    If a future refactor reintroduces f-string SQL, this test fails immediately."""
    src = pathlib.Path("endpoint/similarity_matcher.py").read_text()

    # Patterns that indicate f-string SQL:
    forbidden_patterns = [
        r'f"[^"]*\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE)\b',  # f"...SELECT..."
        r"f'[^']*\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE)\b",  # f'...SELECT...'
        r'\.format\([^)]*\)\s*$.*\b(SELECT|FROM|WHERE)\b',         # .format() with SQL keywords nearby
    ]
    # Note: this is intentionally over-cautious; the implementer should add
    # `# noqa: F1-no-fstring-sql` comments only with reviewer approval.

    offenders = []
    for line_no, line in enumerate(src.splitlines(), start=1):
        for pat in forbidden_patterns:
            if re.search(pat, line, flags=re.IGNORECASE):
                if "# noqa: F1-no-fstring-sql" in line:
                    continue  # explicit waiver
                offenders.append(f"L{line_no}: {line.strip()}")

    assert not offenders, (
        f"F1 violation — f-string SQL found in endpoint/similarity_matcher.py:\n"
        + "\n".join(offenders)
    )


def test_cursor_execute_uses_dict_params():
    """F1: every cursor.execute call in similarity_matcher must pass a dict as second arg."""
    src = pathlib.Path("endpoint/similarity_matcher.py").read_text()
    # Find all cursor.execute(...) call sites
    matches = re.findall(r"cursor\.execute\s*\([^)]+\)", src, flags=re.DOTALL)
    assert matches, "Expected at least one cursor.execute call in similarity_matcher.py"
    for m in matches:
        # Must contain a comma + dict-like content (either {...} literal or **kwargs)
        assert "," in m, f"cursor.execute call missing params dict: {m[:120]}"
