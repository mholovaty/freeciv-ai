"""Unit tests for the freeciv_ai.h CFFI declaration parser (_lib._cffi_decls)."""

from pathlib import Path
import textwrap

from freeciv_ai._lib import _cffi_decls, ffi# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_ok(src: str, header_dir: Path | None = None) -> None:
    """Assert that *src* parses without error via cffi.cdef."""
    ffi2 = type(ffi)()  # fresh FFI instance so tests are isolated
    ffi2.cdef(_cffi_decls(src, header_dir))


# ---------------------------------------------------------------------------
# Basic stripping
# ---------------------------------------------------------------------------

def test_strips_preprocessor_directives():
    src = textwrap.dedent("""\
        #ifndef FOO_H
        #define FOO_H
        int foo(void);
        #endif
    """)
    result = _cffi_decls(src)
    assert "#" not in result
    assert "int foo(void);" in result


def test_strips_extern_c():
    src = textwrap.dedent("""\
        extern "C" {
        int bar(void);
        }
    """)
    result = _cffi_decls(src)
    assert 'extern "C"' not in result
    assert "int bar(void);" in result


# ---------------------------------------------------------------------------
# Type substitutions
# ---------------------------------------------------------------------------

def test_replaces_bool():
    src = "bool freeciv_ai_can_act(void);"
    result = _cffi_decls(src)
    assert "bool" not in result
    assert "int freeciv_ai_can_act(void);" in result


def test_replaces_enum_direction8():
    src = "void freeciv_ai_move_unit(int unit_id, enum direction8 dir);"
    result = _cffi_decls(src)
    assert "enum direction8" not in result
    assert "int dir" in result


def test_replaces_enum_client_states():
    src = "enum client_states freeciv_ai_get_client_state(void);"
    result = _cffi_decls(src)
    assert "enum client_states" not in result
    assert "int freeciv_ai_get_client_state(void);" in result


def test_replaces_struct_unit_pointer():
    src = "struct unit *freeciv_ai_get_unit(int unit_id);"
    result = _cffi_decls(src)
    assert "struct unit *" not in result
    assert "void *freeciv_ai_get_unit(int unit_id);" in result


# ---------------------------------------------------------------------------
# Local #include inlining
# ---------------------------------------------------------------------------

def test_inlines_local_include(tmp_path: Path):
    inc = tmp_path / "types.h"
    inc.write_text("typedef struct { int x; } point_t;\n")

    src = '#include "types.h"\npoint_t make_point(int x);\n'
    result = _cffi_decls(src, header_dir=tmp_path)

    assert "typedef struct" in result
    assert "point_t make_point(int x);" in result


def test_skips_missing_include(tmp_path: Path):
    """A #include whose file doesn't exist should be silently dropped."""
    src = '#include "nonexistent.h"\nint ok(void);\n'
    result = _cffi_decls(src, header_dir=tmp_path)
    assert "int ok(void);" in result


def test_no_header_dir_drops_include():
    """Without header_dir, local includes are dropped (not inlined)."""
    src = '#include "anything.h"\nint ok(void);\n'
    result = _cffi_decls(src, header_dir=None)
    assert "int ok(void);" in result


def test_recursive_include(tmp_path: Path):
    """Nested includes are expanded recursively."""
    inner = tmp_path / "inner.h"
    inner.write_text("typedef int my_int;\n")
    outer = tmp_path / "outer.h"
    outer.write_text('#include "inner.h"\ntypedef my_int coord;\n')

    src = '#include "outer.h"\ncoord get_x(void);\n'
    result = _cffi_decls(src, header_dir=tmp_path)
    assert "typedef int my_int;" in result
    assert "typedef my_int coord;" in result
    assert "coord get_x(void);" in result


# ---------------------------------------------------------------------------
# Full parse of the real freeciv_ai.h (integration)
# ---------------------------------------------------------------------------

def test_real_header_parses():
    """The actual freeciv_ai.h (plus its local includes) must parse cleanly."""
    from freeciv_ai._lib import _find_header
    header = _find_header()
    parse_ok(header.read_text(), header_dir=header.parent)


def test_real_header_exposes_action_decision_types():
    """freeciv_action_decision_t and freeciv_action_choice_t must be present."""
    from freeciv_ai._lib import _find_header
    header = _find_header()
    text = _cffi_decls(header.read_text(), header_dir=header.parent)
    assert "freeciv_action_decision_t" in text
    assert "freeciv_action_choice_t" in text
