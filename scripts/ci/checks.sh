#!/usr/bin/env bash
# Syntax and lint checks over every tracked file, as CI runs them. Run from anywhere in the repo:
#
#   scripts/ci/checks.sh
#
# Python compiles, ruff finds no syntax errors or undefined names, every .js/.mjs file and every inline <script>
# in an HTML page parses with node, JSON and YAML files load, and shell scripts parse. Needs uv and node.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

RUFF=ruff==0.8.6
PYYAML=pyyaml==6.0.2
fail=0

files() {  # tracked files matching the patterns, vendored code left out
  git ls-files -z -- "$@" | tr '\0' '\n' | grep -v '^web/vendor/' || true
}

step() {  # step <name> <command...>: run it, print PASS or FAIL with the output
  local name=$1 out
  shift
  if out=$("$@" 2>&1); then
    echo "PASS $name"
  else
    echo "FAIL $name"
    echo "$out" | sed 's/^/     /'
    fail=1
  fi
}

each() {  # each <command...> -- <files...>: run the command on every file, all of them, fail if any fails
  local cmd=() bad=0
  while [ "$1" != "--" ]; do cmd+=("$1"); shift; done
  shift
  for f in "$@"; do
    "${cmd[@]}" "$f" || { echo "  in $f"; bad=1; }
  done
  return $bad
}

py=(); js=(); html=(); json=(); yml=(); sh=()
while IFS= read -r f; do [ -n "$f" ] && py+=("$f"); done < <(files '*.py')
while IFS= read -r f; do [ -n "$f" ] && js+=("$f"); done < <(files '*.js' '*.mjs')
while IFS= read -r f; do [ -n "$f" ] && html+=("$f"); done < <(files '*.html')
while IFS= read -r f; do [ -n "$f" ] && json+=("$f"); done < <(files '*.json' '*.jsonc')
while IFS= read -r f; do [ -n "$f" ] && yml+=("$f"); done < <(files '*.yml' '*.yaml')
while IFS= read -r f; do [ -n "$f" ] && sh+=("$f"); done < <(files '*.sh')

if [ ${#py[@]} -gt 0 ]; then
  step "python compiles (${#py[@]} files)" uv run --no-project python -m py_compile "${py[@]}"
  step "ruff: syntax errors and undefined names" \
    uvx -q "$RUFF" check --no-cache --isolated --select E9,F63,F7,F82 "${py[@]}"
fi
[ ${#js[@]} -gt 0 ] && step "node --check (${#js[@]} files)" each node --check -- "${js[@]}"
[ ${#html[@]} -gt 0 ] && step "inline <script> parses (${#html[@]} pages)" \
  uv run --no-project python -I scripts/ci/check_inline_js.py "${html[@]}"
[ ${#json[@]} -gt 0 ] && step "JSON loads (${#json[@]} files)" node scripts/ci/check_json.mjs "${json[@]}"
[ ${#yml[@]} -gt 0 ] && step "YAML loads (${#yml[@]} files)" \
  uv run --no-project --with "$PYYAML" python -c \
  'import sys, yaml
bad = 0
for f in sys.argv[1:]:
    try:
        yaml.safe_load(open(f, encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"{f}: {e}".replace("\n", " ")); bad = 1
sys.exit(bad)' "${yml[@]}"
[ ${#sh[@]} -gt 0 ] && step "shell scripts parse (${#sh[@]} files)" each bash -n -- "${sh[@]}"

exit $fail
