"""Command line interface.

`argparse` rather than Typer or Click, because it is in the standard library and this
tool has four commands. Reaching for a dependency you do not need is how projects rot.

The commands beyond `summarize` exist to make the pipeline debuggable in pieces:
`transcript` exercises ingest alone, `doctor` checks the environment before you waste
five minutes discovering the model was never pulled, and `cache` shows what is stored.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, log
from .cache import Store
from .config import DEFAULT_CONFIG_PATH, Config
from .errors import PodsumError
from .ingest import extract_video_id, fetch_transcript
from .llm import build_client
from .pipeline import summarize_video
from .render import to_json, to_markdown
from .types import format_timestamp

_VERBOSE_HELP = "debug logging"
_CONFIG_HELP = f"config file (default: {DEFAULT_CONFIG_PATH})"
_SET_HELP = "override one config value; repeatable"


def _subcommand_globals() -> argparse.ArgumentParser:
    """Copies of the global options, for use *after* the subcommand.

    Nobody remembers whether a global flag belongs before or after the command, so we
    accept both. They need separate destinations because argparse parses a subcommand
    into its own namespace and then copies the values over the parent's, so sharing a
    `dest` would make `podsum --set a=1 summarize URL --set b=2` silently drop `a=1`.
    `_merge_globals` puts the two halves back together.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-v", "--verbose", dest="sub_verbose", action="store_true", help=_VERBOSE_HELP
    )
    parser.add_argument("-c", "--config", dest="sub_config", type=Path, help=_CONFIG_HELP)
    parser.add_argument(
        "--set",
        dest="sub_overrides",
        action="append",
        metavar="section.key=value",
        help=_SET_HELP,
    )
    return parser


def _merge_globals(args: argparse.Namespace) -> argparse.Namespace:
    """Fold the post-subcommand copies of the global options into the real ones."""
    args.verbose = bool(args.verbose or getattr(args, "sub_verbose", False))
    args.overrides = [*(args.overrides or []), *(getattr(args, "sub_overrides", None) or [])]
    sub_config = getattr(args, "sub_config", None)
    if sub_config is not None:
        args.config = sub_config
    return args


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="podsum",
        description="Summarize long YouTube videos into timestamped chapters, locally.",
    )
    parser.add_argument("--version", action="version", version=f"podsum {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help=_VERBOSE_HELP)
    parser.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG_PATH, help=_CONFIG_HELP)
    parser.add_argument(
        "--set", dest="overrides", action="append", metavar="section.key=value", help=_SET_HELP
    )

    common = _subcommand_globals()
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser(
        "summarize", parents=[common], help="full pipeline: URL in, chapter summary out"
    )
    run.add_argument("url", help="YouTube URL or bare 11-character video ID")
    run.add_argument("-o", "--output", type=Path, help="write to a file instead of stdout")
    run.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    run.add_argument("--no-cache", action="store_true", help="ignore the cache for this run")

    show = sub.add_parser(
        "transcript", parents=[common], help="fetch and print the transcript only"
    )
    show.add_argument("url", help="YouTube URL or bare 11-character video ID")
    show.add_argument("--timestamps", action="store_true", help="prefix each line with its time")

    sub.add_parser("doctor", parents=[common], help="check that the environment is ready")

    cache = sub.add_parser("cache", parents=[common], help="inspect or clear the cache")
    cache.add_argument("action", choices=["stats", "clear"])

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _merge_globals(build_parser().parse_args(argv))
    log.setup(verbose=args.verbose)

    try:
        cfg = Config.load(args.config, args.overrides)
        handlers = {
            "summarize": _cmd_summarize,
            "transcript": _cmd_transcript,
            "doctor": _cmd_doctor,
            "cache": _cmd_cache,
        }
        return handlers[args.command](args, cfg)
    except PodsumError as exc:
        # Expected failures get a clean message; anything else is a bug and should
        # show a traceback.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


def _cmd_summarize(args: argparse.Namespace, cfg: Config) -> int:
    summary = summarize_video(args.url, cfg, use_cache=not args.no_cache)
    text = (
        to_json(summary)
        if args.json
        else to_markdown(summary, include_key_points=cfg.output.include_key_points)
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


def _cmd_transcript(args: argparse.Namespace, cfg: Config) -> int:
    transcript = fetch_transcript(
        extract_video_id(args.url),
        languages=cfg.transcript.languages,
        prefer_manual=cfg.transcript.prefer_manual,
    )
    for snippet in transcript.snippets:
        if args.timestamps:
            print(f"[{format_timestamp(snippet.start)}] {snippet.text}")
        else:
            print(snippet.text)
    return 0


def _cmd_doctor(args: argparse.Namespace, cfg: Config) -> int:
    print(f"config          {args.config}")
    print(f"provider        {cfg.llm.provider}")
    print(f"model           {cfg.llm.model}")
    print(f"base_url        {cfg.llm.base_url}")
    print(f"context window  {cfg.llm.num_ctx} tokens")
    print(
        f"chunk target    {cfg.chunking.target_tokens} tokens "
        f"(+{cfg.chunking.overlap_tokens} overlap)"
    )

    client = build_client(cfg.llm)
    problem = client.health()
    if problem:
        print(f"\nnot ready:\n{problem}")
        return 1
    print("\nready")
    return 0


def _cmd_cache(args: argparse.Namespace, cfg: Config) -> int:
    with Store(cfg.cache.path) as store:
        if args.action == "clear":
            store.clear()
            print(f"cleared {cfg.cache.path}")
            return 0
        stats = store.stats()
        print(f"path              {cfg.cache.path}")
        print(f"transcripts       {stats['transcripts']}")
        print(f"chunk summaries   {stats['chunk_summaries']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
