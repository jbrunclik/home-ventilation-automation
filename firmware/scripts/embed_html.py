"""PlatformIO pre-build script: embed web/index.html as a PROGMEM C++ header."""

import os

Import("env")  # noqa: F821 — PlatformIO injects this

src_html = os.path.join(env.subst("$PROJECT_DIR"), "web", "index.html")
dst_header = os.path.join(env.subst("$PROJECT_DIR"), "src", "html_page.h")

with open(src_html, "r") as f:
    html = f.read()

with open(dst_header, "w") as f:
    f.write("// Auto-generated from web/index.html — do not edit\n")
    f.write("#pragma once\n")
    f.write('#include <pgmspace.h>\n\n')
    f.write('static const char HTML_PAGE[] PROGMEM = R"rawhtml(\n')
    f.write(html)
    if not html.endswith("\n"):
        f.write("\n")
    f.write(')rawhtml";\n')

print(f"  Embedded {os.path.basename(src_html)} -> {os.path.basename(dst_header)} ({len(html)} bytes)")
