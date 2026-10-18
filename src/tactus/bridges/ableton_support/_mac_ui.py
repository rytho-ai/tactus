"""macOS file-dialog fallback for Live 11's missing native save/open API.

Only file lifecycle uses UI. Music/inspection/edits use native Python. Save a Copy
preserves the active set; new/open require an explicit disposable/recovered set.
Needs Accessibility access for the invoking application and English Live menus.
"""

import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from ...store import validate_name


def _ui(script, *args):
    if sys.platform != 'darwin':
        raise RuntimeError('This file-dialog recipe requires macOS; supply your platform adapter')
    result = subprocess.run(['osascript', '-', *map(str, args)], input=script, text=True,
                            capture_output=True, timeout=15, check=False)
    if result.returncode:
        raise RuntimeError(f'Live file-dialog action failed: {result.stderr.strip()}')
    return result.stdout.strip()


def save_copy(directory, *, name='session'):
    """Save a new copy via a unique Desktop stage, then move it into the bundle.

    The native panel's Go to Folder keyboard shortcut is unreliable on this host.
    Sidebar/filename actions need no keyboard. Only this invocation's UUID path is
    moved; interrupted stage files are retained for inspection, never searched by name.
    """
    directory = Path(directory).resolve()
    validate_name(name)
    directory.mkdir(parents=True, exist_ok=False)
    identity = 'tactus_' + uuid.uuid4().hex
    desktop = Path.home() / 'Desktop'
    staged_folder = desktop / (identity + ' Project')
    staged_file = desktop / (identity + '.als')
    if staged_folder.exists() or staged_file.exists():
        raise FileExistsError('Native staging path already exists')
    _ui('''on run argv
 tell application "System Events" to tell process "Live"
  set frontmost to true
  delay 0.4
  if (count windows) is not 1 then error "Close dialogs before saving"
  click menu item "Save a Copy..." of menu 1 of menu bar item "File" of menu bar 1
  repeat 40 times
   if exists window "Save" then exit repeat
   delay 0.1
  end repeat
  set sidebar to outline 1 of scroll area 1 of splitter group 1 of window "Save"
  set foundDesktop to false
  repeat with r in rows of sidebar
   if exists UI element "Desktop" of r then
    set selected of r to true
    set foundDesktop to true
    exit repeat
   end if
  end repeat
  if not foundDesktop then error "Desktop sidebar entry is required for native staging"
  repeat 30 times
   if value of pop up button "Where:" of splitter group 1 of window "Save" is "Desktop" then exit repeat
   delay 0.1
  end repeat
  if value of pop up button "Where:" of splitter group 1 of window "Save" is not "Desktop" then error "Desktop staging did not become active"
  set value of text field "Save As:" of splitter group 1 of window "Save" to (item 1 of argv) & ".als"
  click button "Save" of splitter group 1 of window "Save"
 end tell
end run''', identity)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if staged_folder.is_dir() and (staged_folder / (identity + '.als')).is_file():
            target = directory / (name + ' Project')
            shutil.move(str(staged_folder), target)
            project = target / (name + '.als')
            (target / (identity + '.als')).rename(project)
            return project
        if staged_file.is_file():
            target = directory / (name + '.als')
            shutil.move(str(staged_file), target)
            return target
        time.sleep(.1)
    raise TimeoutError(f'Native copy not found at {staged_file} or {staged_folder}; '
                       'inspect Live before retrying')


_DISCARD_PROMPT = """
 repeat with w in windows
  set dimensions to size of w
  if (item 1 of dimensions) < 800 and (item 2 of dimensions) < 300 then
   perform action "AXRaise" of w
   set xy to position of w
   click at {(item 1 of xy)+20, (item 2 of xy)+20}
   delay 0.3
   key code 2 using command down
   exit repeat
  end if
 end repeat
"""


def new_set(*, discard_current=False):
    """Replace current set only after the caller has captured/recovered its state."""
    if discard_current is not True:
        raise ValueError('Explicit discard_current=True and a saved recovery copy are required')
    _ui('''tell application "System Events" to tell process "Live"
 set frontmost to true
 delay 0.4
 if (count windows) is not 1 then error "Close dialogs before replacing a set"
 click menu item "New Live Set" of menu 1 of menu bar item "File" of menu bar 1
 delay 0.5
''' + _DISCARD_PROMPT + 'end tell')


def open_set(path, *, discard_current=False):
    """Open an explicit native set; caller owns recovery and post-open verification."""
    if discard_current is not True:
        raise ValueError('Explicit discard_current=True and a saved recovery copy are required')
    path = Path(path).resolve(strict=True)
    _ui('''on run argv
 ignoring application responses
  tell application "Live" to open POSIX file (item 1 of argv)
 end ignoring
 delay 0.7
 tell application "System Events" to tell process "Live"
  set frontmost to true
''' + _DISCARD_PROMPT + '''
 end tell
end run''', path)
