"""CFFI bindings for libfreeciv_ai.so."""

import re
import cffi
from pathlib import Path

from ._logging import _ensure_so_capture

ffi = cffi.FFI()

_package_dir = Path(__file__).parent.resolve()


def _find_header() -> Path:
    candidates = [
        _package_dir / "freeciv_ai.h",
        _package_dir / ".." / ".." / "src" / "freeciv-ai-lib" / "freeciv_ai.h",
    ]
    for path in candidates:
        resolved = path.resolve()
        if resolved.exists():
            return resolved
    raise FileNotFoundError(
        "Could not find freeciv_ai.h. "
        "Ensure the source tree is present or bundle the header with the package."
    )


def _cffi_decls(header_text: str, header_dir: Path | None = None) -> str:
    """Strip C-compiler-only constructs and map native types to cffi equivalents."""
    import re as _re
    lines = []
    for line in header_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # Inline local #include "..." so CFFI sees all type definitions.
            m = _re.match(r'#\s*include\s+"([^"]+)"', stripped)
            if m and header_dir is not None:
                inc_path = header_dir / m.group(1)
                if inc_path.exists():
                    lines.append(_cffi_decls(inc_path.read_text(), header_dir))
            continue
        # Drop extern "C" { and the bare } that closes it
        if stripped in ('extern "C" {', "}"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\benum client_states\b", "int", text)
    text = re.sub(r"\bstruct unit \*", "void *", text)
    text = re.sub(r"\benum direction8\b", "int", text)
    text = re.sub(r"\bbool\b", "int", text)
    return text


ffi.cdef(_cffi_decls(_find_header().read_text(), _find_header().parent))


def _find_so() -> str:
    """Search common locations for libfreeciv_ai.so."""
    candidates = [
        _package_dir / "libfreeciv_ai.so",
        _package_dir
        / ".."
        / ".."
        / "builddir"
        / "src"
        / "freeciv-ai-lib"
        / "libfreeciv_ai.so",
    ]
    for path in candidates:
        resolved = path.resolve()
        if resolved.exists():
            return str(resolved)
    raise FileNotFoundError(
        "Could not find libfreeciv_ai.so. "
        "Build the project first with:\n"
        "  cd builddir && ninja"
    )


def find_data_path(so_path: str) -> str | None:
    """
    Derive the freeciv/data directory from the .so location.

    The .so lives at  <build>/src/freeciv-ai-lib/libfreeciv_ai.so
    and freeciv/data is at  <repo-root>/freeciv/data — three dirname()
    steps up from the .so, then into freeciv/data.
    """
    data = Path(so_path).resolve().parents[3] / "freeciv" / "data"
    return str(data) if data.is_dir() else None


def load_lib(so_path: str | None = None) -> tuple:
    """Load the CFFI library handle.  Returns (lib, resolved_so_path)."""
    _ensure_so_capture()  # must happen before dlopen so .so output is captured
    resolved = so_path or _find_so()
    return ffi.dlopen(resolved), resolved
