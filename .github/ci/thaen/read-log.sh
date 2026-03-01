#!/usr/bin/env bash
# Quick log reader for Claude CI stream-json logs.
#
# Usage:
#   bash .github/ci/thaen/read-log.sh <logfile>              # summary view (default)
#   bash .github/ci/thaen/read-log.sh <logfile> tools         # tool calls + results
#   bash .github/ci/thaen/read-log.sh <logfile> text          # assistant text output only
#   bash .github/ci/thaen/read-log.sh <logfile> full          # everything, pretty-printed
#   bash .github/ci/thaen/read-log.sh <logfile> cost          # token usage per turn
#   bash .github/ci/thaen/read-log.sh <logfile> raw           # filtered JSON, one per line (pipe to jq yourself)

set -euo pipefail

LOG="$1"
MODE="${2:-summary}"

# Filter to JSON lines only
json_lines() {
    grep '^{' "$LOG"
}

case "$MODE" in
    summary)
        json_lines | python3 -c "
import json, sys, textwrap

for line in sys.stdin:
    d = json.loads(line)
    t = d.get('type')

    if t == 'system' and d.get('subtype') == 'init':
        print(f'=== Session {d.get(\"session_id\",\"?\")[:8]} | model: {d.get(\"model\")} | claude-code {d.get(\"claude_code_version\")} ===')

    elif t == 'assistant':
        msg = d.get('message', {})
        for block in msg.get('content', []):
            if block.get('type') == 'text':
                text = block['text'][:200]
                print(f'  ASSISTANT: {text}')
            elif block.get('type') == 'tool_use':
                name = block.get('name','?')
                inp = block.get('input', {})
                if name == 'Bash':
                    cmd = inp.get('command','')[:120]
                    print(f'  TOOL: Bash -> {cmd}')
                elif name in ('Read', 'Glob', 'Grep'):
                    print(f'  TOOL: {name} -> {json.dumps(inp)[:120]}')
                elif name == 'Edit':
                    fp = inp.get('file_path','?')
                    print(f'  TOOL: Edit -> {fp}')
                elif name == 'Write':
                    fp = inp.get('file_path','?')
                    print(f'  TOOL: Write -> {fp}')
                else:
                    print(f'  TOOL: {name} -> {json.dumps(inp)[:100]}')

    elif t == 'result':
        sub = d.get('subtype','')
        result = str(d.get('result',''))[:150]
        if 'error' in result.lower() or 'Error' in result:
            print(f'  RESULT({sub}): !! {result}')
        else:
            print(f'  RESULT({sub}): {result[:80]}')
"
        ;;

    tools)
        json_lines | python3 -c "
import json, sys

for line in sys.stdin:
    d = json.loads(line)
    t = d.get('type')

    if t == 'assistant':
        for block in d.get('message',{}).get('content',[]):
            if block.get('type') == 'tool_use':
                name = block.get('name','?')
                inp = block.get('input',{})
                print(f'--- {name} ---')
                if name == 'Bash':
                    print(inp.get('command',''))
                elif name in ('Edit', 'Write'):
                    print(f'  file: {inp.get(\"file_path\",\"?\")}')
                    if name == 'Edit':
                        old = inp.get('old_string','')[:100]
                        new = inp.get('new_string','')[:100]
                        print(f'  old: {old}')
                        print(f'  new: {new}')
                else:
                    print(json.dumps(inp, indent=2)[:500])
                print()

    elif t == 'result':
        result = str(d.get('result',''))
        print(f'  => {result[:300]}')
        print()
"
        ;;

    text)
        json_lines | python3 -c "
import json, sys

for line in sys.stdin:
    d = json.loads(line)
    if d.get('type') == 'assistant':
        for block in d.get('message',{}).get('content',[]):
            if block.get('type') == 'text':
                print(block['text'])
                print()
"
        ;;

    cost)
        json_lines | python3 -c "
import json, sys

total_in = 0
total_out = 0
turn = 0
for line in sys.stdin:
    d = json.loads(line)
    if d.get('type') == 'assistant':
        turn += 1
        usage = d.get('message',{}).get('usage',{})
        inp = usage.get('input_tokens',0)
        cache_read = usage.get('cache_read_input_tokens',0)
        cache_create = usage.get('cache_creation_input_tokens',0)
        out = usage.get('output_tokens',0)
        total_in += inp + cache_read + cache_create
        total_out += out
        print(f'Turn {turn:2d}: in={inp:6d} cache_read={cache_read:6d} cache_create={cache_create:6d} out={out:5d}')

print(f'')
print(f'Total input tokens (incl cache): {total_in:,}')
print(f'Total output tokens: {total_out:,}')
"
        ;;

    full)
        json_lines | python3 -m json.tool --no-ensure-ascii
        ;;

    raw)
        json_lines
        ;;

    *)
        echo "Unknown mode: $MODE" >&2
        echo "Usage: $0 <logfile> [summary|tools|text|full|cost|raw]" >&2
        exit 1
        ;;
esac
