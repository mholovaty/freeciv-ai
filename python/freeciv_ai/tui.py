"""
Persistent split-screen TUI using prompt_toolkit.

Layout (top to bottom):
  - Map pane   : ~2/3 terminal height, auto-refreshing ANSI map
  - Log pane   : ~1/3, recent log messages (PgUp/PgDn to scroll)
  - Input field: 1 row with dynamic prompt

Log scrolling
-------------
_log_scroll == 0  →  newest entries visible (auto-scroll mode)
_log_scroll >  0  →  scrolled up by that many lines; new messages don't
                      force a jump back to the bottom until the user
                      presses PgDn back to 0.
"""
from __future__ import annotations

import shutil
from collections import deque
from typing import Callable

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension as D
from prompt_toolkit.widgets import TextArea


class FreecivTUI:
    """Persistent split-screen TUI for the Freeciv AI client."""

    def __init__(self, get_prompt_fn: Callable[[], str] | None = None) -> None:
        self._map_text: str = ""
        self._log_lines: deque[str] = deque(maxlen=500)
        self._pending_command: str | None = None
        self._get_prompt_fn = get_prompt_fn
        self._view_mode: str = "display"  # "display" or "map"
        self._log_scroll: int = 0         # 0 = bottom (newest); >0 = scrolled up

        self.map_window = Window(
            content=FormattedTextControl(self._get_map_content, focusable=False),
            height=D(weight=2),
            wrap_lines=False,
        )
        self.log_window = Window(
            content=FormattedTextControl(self._get_log_content, focusable=False),
            height=D(weight=1),
            wrap_lines=False,
        )
        self.input_field = TextArea(
            height=1,
            prompt=self._get_prompt if get_prompt_fn else "> ",
            multiline=False,
            wrap_lines=False,
            accept_handler=self._on_accept,
            history=InMemoryHistory(),
            focusable=True,
        )

        layout = Layout(
            HSplit([self.map_window, self.log_window, self.input_field]),
            focused_element=self.input_field,
        )

        kb = KeyBindings()

        @kb.add("c-c")
        @kb.add("c-d")
        def _exit(event) -> None:  # noqa: F841
            event.app.exit()

        @kb.add("pageup")
        def _scroll_up(event) -> None:  # noqa: F841
            step = self._log_page_step()
            total = len(self._log_lines)
            visible = self._log_visible_rows()
            max_scroll = max(0, total - visible)
            self._log_scroll = min(max_scroll, self._log_scroll + step)
            self.app.invalidate()

        @kb.add("pagedown")
        def _scroll_down(event) -> None:  # noqa: F841
            step = self._log_page_step()
            self._log_scroll = max(0, self._log_scroll - step)
            self.app.invalidate()

        self.app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=True,
            mouse_support=False,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_visible_rows(self) -> int:
        term = shutil.get_terminal_size(fallback=(80, 24))
        return max(1, term.lines // 3)

    def _log_page_step(self) -> int:
        return max(1, self._log_visible_rows() // 2)

    def _get_prompt(self) -> str:
        if self._get_prompt_fn:
            return self._get_prompt_fn()
        return "> "

    def _get_map_content(self):
        if not self._map_text:
            return [("", "(no map yet)\n")]
        return ANSI(self._map_text)

    def _get_log_content(self):
        n = self._log_visible_rows()
        total = len(self._log_lines)
        if self._log_scroll == 0:
            lines = list(self._log_lines)[-n:]
        else:
            end = max(0, total - self._log_scroll)
            start = max(0, end - n)
            lines = list(self._log_lines)[start:end]
        if not lines:
            return [("", "")]
        # Show a scroll indicator when not at the bottom
        indicator = f" \x1b[2m[+{self._log_scroll} lines below — PgDn]\x1b[0m" if self._log_scroll else ""
        text = "\n".join(lines)
        if indicator:
            text = text + "\n" + indicator
        return ANSI(text)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _on_accept(self, buf) -> bool:  # type: ignore[return-value]
        self._pending_command = buf.text
        self.app.invalidate()
        return False  # False = clear the input field after submit

    def append_log(self, msg: str) -> None:
        """Add message(s) to the log pane.

        If the user has scrolled up (_log_scroll > 0), the view stays put
        so they aren't interrupted while reading history.
        """
        for line in msg.splitlines():
            self._log_lines.append(line)
        if self.app.is_running:
            self.app.invalidate()

    def update_map(self, map_str: str) -> None:
        """Replace the map pane content and trigger a redraw."""
        self._map_text = map_str
        if self.app.is_running:
            self.app.invalidate()

    async def run_async(self) -> None:
        """Run the TUI application (blocks until app exits)."""
        await self.app.run_async()
