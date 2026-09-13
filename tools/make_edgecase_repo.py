"""Generate a large polyglot repository that exercises the edge-case matrix.

The problem document (section 36) lists the cases the pipeline must survive:
empty files, malformed syntax, partial ASTs, unsupported languages, very large
files, generated files, unicode identifiers, deep nesting, and so on. The
seven-file fixture in ``tests/fixtures/demo_repo`` covers the acceptance graph
but is far too small to exercise those.

This script builds a bigger repository on demand. It is deterministic: the same
version of this file always produces byte-identical output, so a failure found
against it can be reproduced exactly.

Usage:
    python tools/make_edgecase_repo.py [destination]

Default destination: tests/fixtures/edgecase_repo
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Per-language module templates
# ---------------------------------------------------------------------------
# Each generator takes the module index and the number of modules, and returns
# (relative_path, source_text). Every language produces a layered structure --
# base, service, controller -- so the resulting repository has real cross-file
# references to extract rather than isolated declarations.

PYTHON = '''"""Module {i} of the generated Python layer."""

from __future__ import annotations

from pkg.module{prev} import Service{prev}


class Base{i}:
    """Base class for service {i}."""


class Service{i}(Base{i}):
    """Service {i}."""

    def handle(self, payload):
        """Handle a payload."""
        self.validate(payload)
        return Service{prev}().handle(payload)

    def validate(self, payload):
        """Validate a payload."""
        return payload is not None


def helper_{i}(value):
    """Module-level helper."""
    return value
'''

JAVASCRIPT = '''const {{ Service{prev} }} = require("./module{prev}");

class Base{i} {{
  constructor(name) {{
    this.name = name;
  }}
}}

class Service{i} extends Base{i} {{
  handle(payload) {{
    this.validate(payload);
    return new Service{prev}("x").handle(payload);
  }}

  validate(payload) {{
    return payload !== null;
  }}
}}

function helper{i}(value) {{
  return value;
}}

module.exports = {{ Service{i} }};
'''

TYPESCRIPT = '''import {{ Service{prev} }} from "./module{prev}";

export interface Handler{i} {{
  handle(payload: string): boolean;
}}

export class Base{i} {{
  protected name: string;
  constructor(name: string) {{
    this.name = name;
  }}
}}

export class Service{i} extends Base{i} implements Handler{i} {{
  handle(payload: string): boolean {{
    this.validate(payload);
    return new Service{prev}("x").handle(payload);
  }}

  private validate(payload: string): void {{}}
}}

export function helper{i}(value: string): string {{
  return value;
}}
'''

JAVA = '''package com.example.gen;

import com.example.gen.Base{i};

public class Service{i} extends Base{i} implements Handler{i} {{
    private final String name;

    public Service{i}(String name) {{
        this.name = name;
    }}

    public boolean handle(String payload) {{
        this.validate(payload);
        return true;
    }}

    private void validate(String payload) {{
    }}
}}

interface Handler{i} {{
    boolean handle(String payload);
}}

class Base{i} {{
    protected String name;
}}
'''

GO = '''package module{i}

import (
\t"fmt"

\t"example.com/pkg/module{prev}"
)

type Base{i} struct {{
\tName string
}}

type Service{i} struct {{
\tBase{i}
}}

type Handler{i} interface {{
\tHandle(payload string) bool
}}

func (s *Service{i}) Handle(payload string) bool {{
\ts.validate(payload)
\tfmt.Println(payload)
\treturn true
}}

func (s *Service{i}) validate(payload string) {{
}}

func Helper{i}(value string) string {{
\t_ = module{prev}.Helper{prev}("x")
\treturn value
}}
'''

RUST = '''use crate::module{prev}::Service{prev};

pub struct Base{i} {{
    pub name: String,
}}

pub struct Service{i} {{
    pub base: Base{i},
}}

pub trait Handler{i} {{
    fn handle(&self, payload: &str) -> bool;
}}

impl Handler{i} for Service{i} {{
    fn handle(&self, payload: &str) -> bool {{
        self.validate(payload);
        true
    }}
}}

impl Service{i} {{
    fn validate(&self, payload: &str) {{}}
}}

pub fn helper_{i}(value: &str) -> &str {{
    value
}}
'''

C = '''#include <stdio.h>
#include "module{prev}.h"

struct Base{i} {{
    int name;
}};

typedef struct Base{i} Base{i};

int handle_{i}(const char *payload) {{
    validate_{i}(payload);
    printf("%s", payload);
    return 0;
}}

int validate_{i}(const char *payload) {{
    return payload != 0;
}}
'''

CPP = '''#include <string>
#include "module{prev}.hpp"

namespace gen {{

class Base{i} {{
public:
    std::string name;
}};

class Service{i} : public Base{i} {{
public:
    bool handle(const std::string &payload) {{
        this->validate(payload);
        return true;
    }}

    void validate(const std::string &payload) {{}}
}};

int helper_{i}(int value) {{ return value; }}

}}  // namespace gen
'''

CSHARP = '''using System;

namespace Example.Gen
{{
    public interface IHandler{i}
    {{
        bool Handle(string payload);
    }}

    public class Base{i}
    {{
        protected string Name;
    }}

    public class Service{i} : Base{i}, IHandler{i}
    {{
        public Service{i}(string name)
        {{
            this.Name = name;
        }}

        public bool Handle(string payload)
        {{
            this.Validate(payload);
            return true;
        }}

        private void Validate(string payload) {{ }}
    }}
}}
'''

RUBY = '''require_relative "./module{prev}"

module Example
  class Base{i}
    def initialize(name)
      @name = name
    end
  end

  class Service{i} < Base{i}
    def handle(payload)
      validate(payload)
      true
    end

    def validate(payload)
      !payload.nil?
    end
  end
end

def helper_{i}(value)
  value
end
'''

PHP = '''<?php
namespace Example\\Gen;

use Example\\Gen\\Base{i};
use Example\\Gen\\Handler{i} as H{i};

class Base{i}
{{
    protected $name;
}}

interface Handler{i}
{{
    public function handle($payload);
}}

class Service{i} extends Base{i} implements Handler{i}
{{
    public function handle($payload): bool
    {{
        $this->validate($payload);
        return true;
    }}

    private function validate($payload): void
    {{
    }}
}}

function helper_{i}($value) {{
    return $value;
}}
'''

KOTLIN = '''package com.example.gen

import com.example.gen.Base{i}

interface Handler{i} {{
    fun handle(payload: String): Boolean
}}

open class Base{i}(val name: String)

class Service{i}(name: String) : Base{i}(name), Handler{i} {{
    override fun handle(payload: String): Boolean {{
        validate(payload)
        return true
    }}

    private fun validate(payload: String) {{}}
}}

fun helper{i}(value: String): String {{
    return value
}}
'''

SWIFT = '''import Foundation

protocol Handler{i} {{
    func handle(_ payload: String) -> Bool
}}

class Base{i} {{
    let name: String
    init(name: String) {{
        self.name = name
    }}
}}

class Service{i}: Base{i}, Handler{i} {{
    func handle(_ payload: String) -> Bool {{
        self.validate(payload)
        return true
    }}

    private func validate(_ payload: String) {{}}
}}

func helper{i}(_ value: String) -> String {{
    return value
}}
'''

SCALA = '''package com.example.gen

import com.example.gen.Base{i}

trait Handler{i} {{
  def handle(payload: String): Boolean
}}

class Base{i}(val name: String)

class Service{i}(name: String) extends Base{i}(name) with Handler{i} {{
  def handle(payload: String): Boolean = {{
    this.validate(payload)
    true
  }}

  private def validate(payload: String): Unit = {{}}
}}

object Helpers{i} {{
  def helper(value: String): String = value
}}
'''

LUA = '''local mod{prev} = require("module{prev}")

local Base{i} = {{}}
Base{i}.__index = Base{i}

function Base{i}.new(name)
  local self = setmetatable({{}}, Base{i})
  self.name = name
  return self
end

local Service{i} = setmetatable({{}}, {{ __index = Base{i} }})

function Service{i}:handle(payload)
  self:validate(payload)
  return true
end

function Service{i}:validate(payload)
  return payload ~= nil
end

local function helper{i}(value)
  return value
end

return Service{i}
'''

BASH = '''#!/usr/bin/env bash
source "./module{prev}.sh"

BASE_{i}="base"

handle_{i}() {{
  local payload="$1"
  validate_{i} "$payload"
  echo "$payload"
}}

validate_{i}() {{
  [ -n "$1" ]
}}

helper_{i}() {{
  echo "$1"
}}
'''

DART = '''import 'dart:async';

import 'module{prev}.dart';

abstract class Handler{i} {{
  bool handle(String payload);
}}

class Base{i} {{
  final String name;
  Base{i}(this.name);
}}

class Service{i} extends Base{i} implements Handler{i} {{
  Service{i}(String name) : super(name);

  @override
  bool handle(String payload) {{
    this.validate(payload);
    return true;
  }}

  void validate(String payload) {{}}
}}

String helper{i}(String value) => value;
'''

TEMPLATES: dict[str, tuple[str, str, int]] = {
    # language: (template, path pattern, module count)
    "python": (PYTHON, "python/pkg/module{i}.py", 12),
    "javascript": (JAVASCRIPT, "javascript/src/module{i}.js", 8),
    "typescript": (TYPESCRIPT, "typescript/src/module{i}.ts", 8),
    "java": (JAVA, "java/src/main/java/com/example/gen/Service{i}.java", 8),
    "go": (GO, "go/module{i}/module{i}.go", 8),
    "rust": (RUST, "rust/src/module{i}.rs", 8),
    "c": (C, "c/module{i}.c", 6),
    "cpp": (CPP, "cpp/module{i}.cpp", 6),
    "csharp": (CSHARP, "csharp/Service{i}.cs", 6),
    "ruby": (RUBY, "ruby/module{i}.rb", 6),
    "php": (PHP, "php/module{i}.php", 6),
    "kotlin": (KOTLIN, "kotlin/Service{i}.kt", 6),
    "swift": (SWIFT, "swift/Service{i}.swift", 6),
    "scala": (SCALA, "scala/Service{i}.scala", 5),
    "lua": (LUA, "lua/module{i}.lua", 5),
    "bash": (BASH, "bash/module{i}.sh", 5),
    "dart": (DART, "dart/module{i}.dart", 5),
}


# ---------------------------------------------------------------------------
# Edge-case files
# ---------------------------------------------------------------------------


def edge_case_files() -> dict[str, bytes]:
    """Files whose only purpose is to break something.

    Returned as raw bytes rather than text, because several cases -- the BOM,
    the CRLF file, the binary blob -- are specifically about bytes and would be
    destroyed by an encode/decode round trip.
    """
    files: dict[str, bytes] = {}

    # --- empty ------------------------------------------------------------
    files["_edge/empty.py"] = b""
    files["_edge/empty.js"] = b""
    files["_edge/whitespace_only.go"] = b"   \n\t\n   \n"

    # --- malformed, one per language --------------------------------------
    files["_edge/malformed.py"] = (
        b"def broken(:\n    return 1\n\nclass Also(:\n    pass\n"
    )
    files["_edge/malformed.js"] = b"class Broken extends {\n  handle( {\n}\n"
    files["_edge/malformed.ts"] = (
        b"export class Broken implements {\n  handle(p: string): {\n}\n"
    )
    files["_edge/malformed.java"] = (
        b"public class Broken extends {\n    public void handle( {\n}\n"
    )
    files["_edge/malformed.go"] = b"package broken\n\nfunc Handle( {\n}\n"
    files["_edge/malformed.rs"] = b"pub fn broken( -> bool {\n}\n"
    files["_edge/malformed.rb"] = b"class Broken <\n  def handle(\nend\n"
    files["_edge/malformed.c"] = b"int broken( {\n  return 0;\n}\n"

    # --- partial: valid header, broken body -------------------------------
    files["_edge/partial.py"] = (
        b'"""Valid module docstring."""\n\n'
        b"from pkg.module1 import Service1\n\n\n"
        b"class PartialService:\n"
        b'    """Valid class."""\n\n'
        b"    def good(self):\n"
        b"        return 1\n\n"
        b"    def bad(self):\n"
        b"        return (\n"
    )

    # --- unicode identifiers and text -------------------------------------
    files["_edge/unicode_identifiers.py"] = (
        '"""Unicode identifiers."""\n\n'
        "# Comment with accents: cafe, naive, Zurich, 東京\n"
        "π = 3.14159\n"
        "café = 'coffee'\n\n\n"
        "class Données:\n"
        '    """Class with a non-ASCII name."""\n\n'
        "    def calculer(self, valeur):\n"
        "        return valeur * π\n\n\n"
        "def 日本語関数(引数):\n"
        "    return 引数\n"
    ).encode("utf-8")

    # --- deep nesting -----------------------------------------------------
    # 300 nested if-blocks. A recursive tree walk would exhaust Python's
    # recursion limit here; the parser walks iteratively on purpose.
    depth = 300
    deep = ["def deeply_nested(value):", '    """A function nested far too deeply."""']
    for level in range(depth):
        deep.append("    " * (level + 1) + f"if value > {level}:")
    deep.append("    " * (depth + 1) + "return value")
    files["_edge/deep_nesting.py"] = ("\n".join(deep) + "\n").encode("utf-8")

    # --- large file -------------------------------------------------------
    lines = ['"""A deliberately large generated module."""', ""]
    for index in range(4000):
        lines.append(f"def function_{index}(value):")
        lines.append(f"    return value + {index}")
        lines.append("")
    files["_edge/large_file.py"] = ("\n".join(lines) + "\n").encode("utf-8")

    # --- encodings and line endings ---------------------------------------
    files["_edge/bom.py"] = (
        b"\xef\xbb\xbf" + b'"""File with a UTF-8 BOM."""\n\nvalue = 1\n'
    )
    files["_edge/crlf.py"] = (
        b'"""File with CRLF line endings."""\r\n\r\nvalue = 1\r\n'
    )
    files["_edge/no_trailing_newline.py"] = b"value = 1"

    # --- comments only ----------------------------------------------------
    files["_edge/only_comments.py"] = (
        b"# Just a comment.\n# And another.\n"
    )

    # --- excluded by policy ----------------------------------------------
    # These must NOT appear in the manifest (section 8 AC4).
    files["_edge/generated_pb2.py"] = (
        b"# Code generated by protoc. DO NOT EDIT.\nvalue = 1\n"
    )
    files["_edge/bundle.min.js"] = b"function a(){return 1}function b(){return 2}\n"
    files["_edge/model.g.dart"] = b"// GENERATED CODE - DO NOT MODIFY\nclass A {}\n"
    files["_edge/logo.png"] = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64
    )
    files["_edge/data.dat"] = b"\x00\x01\x02\x03\xff\xfe" * 16
    # No extension at all, so this one cannot be excluded by name -- it is
    # excluded purely by content sniffing, which is the case worth testing.
    files["_edge/binary_payload"] = b"\x00\x01binary\x00\xff\xfe" * 8
    files["_edge/package-lock.json"] = b'{"lockfileVersion": 3}\n'
    files["_edge/app.log"] = b"2026-01-01 INFO started\n" * 4

    # --- unsupported language --------------------------------------------
    files["_edge/unknown.xyzzy"] = b"this extension belongs to no known grammar\n"

    # --- ignored directories ---------------------------------------------
    files["node_modules/left-pad/index.js"] = b"module.exports = function () {};\n"
    files["node_modules/left-pad/package.json"] = b'{"name": "left-pad"}\n'
    files["build/compiled.py"] = b"value = 1\n"
    files["dist/bundle.js"] = b"var a=1;\n"
    files["__pycache__/cached.cpython-313.pyc"] = b"\x00\x00\x00\x00binary"
    files[".git/config"] = b"[core]\n\trepositoryformatversion = 0\n"

    # --- cross-file edge cases -------------------------------------------
    files["_edge/star_import.py"] = (
        '"""Star import and conditional import."""\n\n'
        "from pkg.module1 import *\n\n"
        "try:\n"
        "    import ujson as json\n"
        "except ImportError:\n"
        "    import json\n\n\n"
        "def parse(text):\n"
        "    return json.loads(text)\n"
    ).encode("utf-8")

    files["_edge/duplicate_names_a.py"] = (
        '"""First of two modules declaring the same class name."""\n\n\n'
        "class Shared:\n"
        '    """A class named Shared."""\n\n'
        "    def run(self):\n"
        "        return 1\n"
    ).encode("utf-8")

    files["_edge/duplicate_names_b.py"] = (
        '"""Second module declaring the same class name."""\n\n\n'
        "class Shared:\n"
        '    """A different class, also named Shared."""\n\n'
        "    def run(self):\n"
        "        return 2\n"
    ).encode("utf-8")

    files["_edge/cyclic_a.py"] = (
        '"""Cycle member A."""\n\n'
        "from _edge.cyclic_b import CycleB\n\n\n"
        "class CycleA:\n"
        "    def ping(self):\n"
        "        return CycleB()\n"
    ).encode("utf-8")

    files["_edge/cyclic_b.py"] = (
        '"""Cycle member B."""\n\n'
        "from _edge.cyclic_a import CycleA\n\n\n"
        "class CycleB:\n"
        "    def pong(self):\n"
        "        return CycleA()\n"
    ).encode("utf-8")

    files["_edge/dynamic_dispatch.py"] = (
        '"""Calls that cannot be resolved statically."""\n\n'
        "import importlib\n\n\n"
        "def dispatch(name, *args):\n"
        '    """Resolve a callable at runtime."""\n'
        "    module = importlib.import_module(name)\n"
        "    handler = getattr(module, 'handle')\n"
        "    return handler(*args)\n\n\n"
        "def chained(obj):\n"
        "    return obj.first().second().third()\n"
    ).encode("utf-8")

    files["_edge/overloads.java"] = (
        "package com.example.gen;\n\n"
        "public class Overloaded {\n"
        "    public void process(String a) {\n    }\n\n"
        "    public void process(int a) {\n    }\n\n"
        "    public void process(String a, int b) {\n    }\n"
        "}\n"
    ).encode("utf-8")

    files["README.md"] = (
        "# Edge-case repository\n\n"
        "Generated by `tools/make_edgecase_repo.py`. Do not edit by hand.\n\n"
        "Layout:\n\n"
        "* one directory per language, each a small layered module set\n"
        "* `_edge/` holds files that exist only to break something\n"
        "* `node_modules/`, `build/`, `dist/`, `.git/` must be ignored entirely\n"
        "* files under `_edge/` ending in `.png`, `.dat`, `.min.js`, `_pb2.py`,\n"
        "  `.g.dart` and `package-lock.json` must be excluded as binary or generated\n"
    ).encode("utf-8")

    return files


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate(destination: Path, clean: bool = True) -> dict[str, int]:
    if clean and destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    written = 0

    for language, (template, pattern, count) in TEMPLATES.items():
        for index in range(1, count + 1):
            relative = pattern.format(i=index, prev=index - 1)
            text = template.format(i=index, prev=index - 1)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            written += 1

    edge = edge_case_files()
    for relative, payload in edge.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        written += 1

    return {
        "files_written": written,
        "languages": len(TEMPLATES),
    }


def main(argv: list[str]) -> int:
    destination = (
        Path(argv[1])
        if len(argv) > 1
        else Path(__file__).resolve().parent.parent
        / "tests"
        / "fixtures"
        / "edgecase_repo"
    )
    stats = generate(destination)
    print(f"generated {stats['files_written']} files across {stats['languages']} languages")
    print(f"destination: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
