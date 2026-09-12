# podsum

Turn a two-hour YouTube video into a set of timestamped chapters you can skim in ninety seconds.

Runs entirely on your own machine against a local model through [Ollama](https://ollama.com).
No API keys, no accounts, no per-token cost.

The design goal is not "tell me what this video was about". It is **"should I spend two hours
on this, and if not, which eight minutes should I watch?"** That is why every chapter carries a
clickable timestamp rather than dissolving into one paragraph of prose.

---

## Quick start

You need [Ollama](https://ollama.com/download) installed and running, and Python 3.11 or newer.

```bash
make setup                    # create .venv and install podsum in editable mode
ollama pull qwen3:8b          # ~5GB, the model that writes the summaries
podsum doctor                 # confirm Ollama is reachable and the model is present
podsum summarize "https://www.youtube.com/watch?v=VIDEO_ID" -o notes.md
```

`podsum doctor` is worth running first. It tells you exactly what is missing rather than
letting you discover it forty chunks into a long video:

```
config          configs/default.yaml
provider        ollama
model           qwen3:8b
context window  8192 tokens
chunk target    1200 tokens (+120 overlap)

not ready:
model 'qwen3:8b' is not pulled. Run: ollama pull qwen3:8b
Currently available: qwen2.5-coder:7b, qwen2.5-coder:14b
```

### Output shape

Abridged illustration of what `summarize` writes:

```markdown
# How Compilers Actually Optimise Loops

[Watch on YouTube](https://www.youtube.com/watch?v=VIDEO_ID) · 118 min · 14 chapters · summarized by `ollama:qwen3:8b`

## TL;DR

The guest argues that most hand-written loop optimisations are counterproductive on modern
CPUs because the compiler already performs them... 

## Chapters

### [0:00](https://www.youtube.com/watch?v=VIDEO_ID&t=0s) Introductions and sponsor read

Host introduces the guest, a compiler engineer, and reads an advertisement.

### [4:12](https://www.youtube.com/watch?v=VIDEO_ID&t=252s) Why manual loop unrolling backfires

The guest claims unrolling by hand defeats the compiler's own heuristics...

- Measured a 12% regression on their benchmark suite
- Recommends `-O2` over `-O3` for most workloads
```

---

## Commands

| Command | What it does |
| --- | --- |
| `podsum summarize URL` | The full pipeline. `-o FILE` to write a file, `--json` for machine-readable output, `--no-cache` to force a fresh run. |
| `podsum transcript URL` | Fetch and print the transcript only. `--timestamps` prefixes each line. Use this to see what the model is actually reading. |
| `podsum doctor` | Check that Ollama is up and the configured model is pulled. |
| `podsum cache stats` | How many transcripts and chapter summaries are stored. `cache clear` empties it. |

Any config value can be overridden per-run without editing a file:

```bash
podsum summarize URL --set llm.model=gemma3:12b --set chunking.target_tokens=1800
```

---

## How it works

Six stages, each one a function from typed data to typed data:

```
URL ──▶ video_id ──▶ Transcript ──▶ [Chunk] ──▶ [ChunkSummary] ──▶ VideoSummary ──▶ markdown
      urls.py      captions.py     windows.py    mapper.py         reducer.py     markdown.py
```

1. **Ingest.** Pull YouTube's own captions, which most podcasts have. Free and instant, but
   with no punctuation and no speaker labels, so the model has to work harder.
2. **Chunk.** Split the transcript into overlapping ~1200-token windows, *never dropping the
   timestamps*. This is the decision the entire tool rests on: flatten to a plain string here
   and jump links become impossible later.
3. **Map.** One model call per chunk, producing a title, a gist, and a few key points as JSON.
   Chunks are independent, so this step runs in parallel and caches per chunk.
4. **Reduce.** One more call over just the chapter summaries — never the transcript — to write
   the overall title and TL;DR.
5. **Cache.** Transcripts and chapter summaries go into SQLite, keyed by content *plus model
   plus prompt version*, so editing a prompt automatically invalidates its old output.
6. **Render.** Markdown or JSON. Separate from summarizing, so changing the layout re-renders
   from cache instead of paying for inference again.

[`docs/architecture.md`](docs/architecture.md) explains why each boundary sits where it does,
what the known failure modes are, and where this design will break first.

---

## Layout

```
src/podsum/
├── cli.py            argument parsing, the only module that prints
├── pipeline.py       the six stages wired together — read this first
├── config.py         typed config; no magic numbers anywhere else
├── types.py          the dataclasses that stages pass to each other
├── errors.py         one exception tree, so the CLI can report cleanly
├── ingest/           urls.py, captions.py, audio.py (stage 5, unimplemented)
├── chunking/         tokens.py (token counting), windows.py (the algorithm)
├── llm/              base.py (the Protocol), ollama.py, factory.py, jsonio.py
├── prompts/          prompts as .md files, hashed into cache keys
├── summarize/        mapper.py (map step), reducer.py (reduce step)
├── cache/            store.py, a SQLite read-through cache
└── render/           markdown.py

configs/default.yaml  every tunable value
tests/                68 tests, no network and no model required
research/tinygpt/     the learning track (see below)
```

Two conventions worth copying into your own projects:

**Types at the boundaries.** Every stage takes and returns frozen dataclasses. That is what
lets local Whisper eventually replace YouTube captions without a single change downstream —
both produce a `Transcript`, and nothing else knows the difference.

**The model behind a `Protocol`.** Nothing above `llm/` imports `ollama.py`. Swapping in a
hosted API later is one new file plus one line of config. It also means the tests use a
twenty-line `FakeClient` and run the whole summarization path in 0.1 seconds with no model
installed — which is why CI passes on a runner that has never heard of Ollama.

---

## Configuration

Everything lives in [`configs/default.yaml`](configs/default.yaml), commented. The values
that actually change output quality:

| Key | Effect |
| --- | --- |
| `chunking.target_tokens` | Bigger chunks mean fewer calls and more context per chapter, but the model skims long middles. |
| `chunking.overlap_tokens` | Text repeated across boundaries. Set this to zero and you get chapters that describe half an idea. |
| `llm.temperature` | Keep it low. This is faithful compression, not creative writing. |
| `llm.num_ctx` | Must comfortably exceed `chunking.hard_max_tokens` plus the prompt. Raising it costs RAM through the KV cache. |
| `llm.concurrency` | Parallel chunk calls. Above 2–3 on 18GB you are competing with yourself for memory, not going faster. |

---

## Development

```bash
make test        # pytest
make lint        # ruff
make typecheck   # mypy, strict mode
make check       # all three, same as CI
make fmt         # fix style and import order in place
```

The suite touches no network and needs no model, so it runs in a fraction of a second and
works offline. CI runs the same three commands on Python 3.11, 3.12, and 3.13.

---

## Roadmap

- [x] **Stage 1** — Ingest: URL parsing and caption fetching
- [x] **Stage 2** — Chunking with timestamps preserved
- [x] **Stage 3** — Map-reduce summarization over a local model
- [x] **Stage 4** — SQLite cache keyed by content, model, and prompt version
- [ ] **Stage 5** — Local Whisper fallback for videos with no captions (`src/podsum/ingest/audio.py`)
- [ ] **Stage 6** — A small web interface. Note that free hosting cannot reach the Ollama on
      your laptop, so "deployed" and "fully local" are mutually exclusive here.
- [ ] **Stage 7** — Optional: fine-tune a small model for the map step and measure it against
      the off-the-shelf baseline.

### The learning track

[`research/tinygpt/`](research/tinygpt/) is a separate, deliberately useless project: build a
transformer from scratch to understand what the model in stage 3 is actually doing. It is
never imported by `podsum` and it will never write a usable summary.

It is sequenced to feed back into the tool. The first component is a BPE tokenizer, which is
exactly what [`chunking/tokens.py`](src/podsum/chunking/tokens.py) currently approximates with
a characters-per-token heuristic. Write the real one and your chunk sizes stop being guesses.

---

## Credits

The build-a-tiny-one-to-understand-the-real-one approach is Andrej Karpathy's, via
[nanoGPT](https://github.com/karpathy/nanoGPT). The build-something-that-works-then-dig-down
ordering is [fast.ai](https://www.fast.ai/)'s.

Transcripts come from
[youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api).

## License

MIT — see [LICENSE](LICENSE).
