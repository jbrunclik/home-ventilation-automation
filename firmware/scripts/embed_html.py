"""PlatformIO pre-build script: embed web/index.html as a PROGMEM C++ header."""

import os
import re

Import("env")  # noqa: F821 — PlatformIO injects this


def minify_html(html):
    """Simple HTML/CSS/JS minifier — strips comments, collapses whitespace."""
    # Remove HTML comments (but not IE conditionals)
    html = re.sub(r"<!--(?!\[).*?-->", "", html, flags=re.DOTALL)
    # Collapse runs of whitespace (spaces, tabs, newlines) into a single space
    html = re.sub(r"\s+", " ", html)
    # Remove spaces around HTML tags
    html = re.sub(r">\s+<", "><", html)
    # Remove spaces after opening tags and before closing tags
    html = re.sub(r">\s+", ">", html)
    html = re.sub(r"\s+<", "<", html)
    return html.strip()


src_html = os.path.join(env.subst("$PROJECT_DIR"), "web", "index.html")
dst_header = os.path.join(env.subst("$PROJECT_DIR"), "src", "html_page.h")

with open(src_html, "r") as f:
    raw_html = f.read()

html = minify_html(raw_html)

with open(dst_header, "w") as f:
    f.write("// Auto-generated from web/index.html — do not edit\n")
    f.write("#pragma once\n")
    f.write('#include <pgmspace.h>\n\n')
    f.write('static const char HTML_PAGE[] PROGMEM = R"rawhtml(\n')
    f.write(html)
    f.write("\n")
    f.write(')rawhtml";\n')

saved = len(raw_html) - len(html)
print(
    f"  Embedded {os.path.basename(src_html)} -> {os.path.basename(dst_header)}"
    f" ({len(raw_html)} -> {len(html)} bytes, saved {saved})"
)
