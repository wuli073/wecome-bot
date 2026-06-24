from __future__ import annotations

import argparse
import json
import sys

import connector_errors as errors
import connector_runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Non-interactive connector CLI")
    parser.add_argument("connector", choices=["wechat", "wxwork"])
    parser.add_argument("action", choices=["detect", "extract-key", "decrypt"])
    parser.add_argument("--runtime-dir")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv=None, stdout=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    stdout = stdout or sys.stdout

    try:
        if args.action == "detect":
            result = connector_runtime.detect_connector(args.connector)
        else:
            if not args.runtime_dir:
                raise ValueError("runtime_dir is required")
            runtime_dir = connector_runtime.resolve_runtime_dir(args.runtime_dir)
            if args.action == "extract-key":
                result = connector_runtime.extract_key(args.connector, runtime_dir)
            else:
                result = connector_runtime.decrypt(args.connector, runtime_dir)
    except ValueError as exc:
        result = connector_runtime.build_result(
            ok=False,
            connector=args.connector,
            action=args.action,
            error_code=errors.INVALID_RUNTIME_DIR,
            error_message=str(exc),
        )

    stdout.write(json.dumps(result, ensure_ascii=False))
    stdout.flush()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
