"""Flatten INCLUDE directives to avoid the native-Windows binutils inode bug.

The linker content and ordering are unchanged. Run after the RAM scripts exist.
https://gnu.googlesource.com/binutils-gdb/+/ab1830f633107b180b46938003e6f49fb44cb17d
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'rom/pokefirered'
text = (source / 'ld_script.ld').read_text()
text = re.sub(r'INCLUDE "([^"]+)"', lambda m: (source / 'build/firered' / m[1]).read_text(), text)
(source / 'ld_script_flat.ld').write_text(text, newline='\n')
