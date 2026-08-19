"""Minimal clipboard access via whatever command-line tool is installed."""

import shutil
import subprocess

# Tried in order; the first tool actually present on PATH wins. This avoids a
# dependency on pyperclip for the one thing we need from it.
PASTE_COMMANDS = [
    ["pbpaste"],  # macOS
    ["wl-paste", "--no-newline"],  # Wayland
    ["xclip", "-selection", "clipboard", "-out"],  # X11
    ["xsel", "--clipboard", "--output"],
    ["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"],  # WSL
]

# Same platform order as above, in the write direction.
COPY_COMMANDS = [
    ["pbcopy"],
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
    ["clip.exe"],
]


class ClipboardError(RuntimeError):
    """No clipboard tool available, or the one we found failed."""


def _first_available(commands):
    """Pick the first command whose executable exists on this machine."""
    for command in commands:
        if shutil.which(command[0]):
            return command
    return None


def paste() -> str:
    """Read the clipboard as text."""
    command = _first_available(PASTE_COMMANDS)
    if command is None:
        raise ClipboardError(
            "No clipboard tool found. Install xclip/xsel (Linux) or use --input/stdin."
        )
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise ClipboardError("%s failed: %s" % (command[0], result.stderr.strip()))
    return result.stdout


def copy(text: str) -> None:
    """Replace the clipboard contents with `text`."""
    command = _first_available(COPY_COMMANDS)
    if command is None:
        raise ClipboardError(
            "No clipboard tool found. Install xclip/xsel (Linux) or use --output/stdout."
        )
    result = subprocess.run(command, input=text, text=True, capture_output=True)
    if result.returncode != 0:
        raise ClipboardError("%s failed: %s" % (command[0], result.stderr.strip()))
