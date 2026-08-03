"""Fix indentation for tab containers."""
import re

with open('src/dao_vang/web/app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the three section markers
scan_start = None  # line index of "with _scan_container:"
bt_start = None    # line index of "with _backtest_container:"
idle_start = None  # line index of "# IDLE STATE" or similar

for i, line in enumerate(lines):
    if 'with _scan_container:' in line and scan_start is None:
        scan_start = i
    elif 'with _backtest_container:' in line and bt_start is None:
        bt_start = i
    elif 'IDLE STATE' in line and idle_start is None:
        idle_start = i

print(f"scan_start={scan_start}, bt_start={bt_start}, idle_start={idle_start}")

# The watchlist block: from scan_start+2 (after "with" and "if") to bt_start-1
# These lines need +4 spaces indent (they were under 4-space `if`, now under 8-space `with`+`if`)
# But only the lines that are part of the if body (originally 4-space indented)

# Actually, the `if run_button` line is at 4-space (correct for being inside `with`).
# The body of the if was at 4-space (from original top-level if), needs to be at 8-space.

# Watchlist block: lines from scan_start+2 to bt_start-1
# Add 4 spaces to each non-empty line
for i in range(scan_start + 2, bt_start):
    if lines[i].strip():  # non-empty line
        lines[i] = '    ' + lines[i]
    # empty lines stay as-is

# Backtest block: from bt_start to idle_start-1
# The "with _backtest_container:" is at 0 indent
# The "if run_button..." should be at 4 indent
# The body should be at 8 indent
# Currently: "with" at 0, "if" at 8 (I added extra), body at 4

# Fix: reset the backtest section
# Find the "if run_button" line after bt_start
bt_if_line = None
for i in range(bt_start + 1, idle_start):
    if 'if run_button and mode == "🧪 Backtest"' in lines[i]:
        bt_if_line = i
        break

print(f"bt_if_line={bt_if_line}")
# print(f"line content: {repr(lines[bt_if_line])}")

# Fix the if line to be 4-space indent
lines[bt_if_line] = '    ' + lines[bt_if_line].lstrip()

# Add 4 spaces to body lines (from bt_if_line+1 to idle_start-1)
for i in range(bt_if_line + 1, idle_start):
    if lines[i].strip():
        lines[i] = '    ' + lines[i]

# Now handle idle state: split into scan idle and backtest idle
# Find the idle block
# Current: "elif not run_button:" -> needs to become two separate blocks
# Let's find it
idle_if_line = None
for i in range(idle_start, len(lines)):
    if 'elif not run_button:' in lines[i]:
        idle_if_line = i
        break

print(f"idle_if_line={idle_if_line}")
if idle_if_line:
    pass  # print(f"line content: {repr(lines[idle_if_line])}")

# Change "elif not run_button:" to "if not run_button:"
# and indent body by +4
lines[idle_if_line] = '    if not run_button:\n'
for i in range(idle_if_line + 1, len(lines)):
    if lines[i].strip():
        lines[i] = '    ' + lines[i]

# Wrap idle state in _scan_container (add "with _scan_container:" before it)
# Insert before the IDLE STATE comment
lines.insert(idle_start, 'with _scan_container:\n')

with open('src/dao_vang/web/app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Done fixing indentation")
