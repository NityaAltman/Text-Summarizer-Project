# Architecture

This document explains *why* the code is shaped the way it is. The README says what the tool
does; this says which decisions were deliberate, what they cost, and where the design will
break first.

---

## 1. The problem, stated honestly

A two-hour podcast is roughly 20,000 words, or about 25,000 tokens. An 8B model running in 8GB
of RAM has a usable context window of maybe 8,000. So the input does not fit, and no amount of
prompt cleverness changes that.

Everything else in this codebase follows from that one fact. If the transcript fit in context,
`podsum` would be a fifteen-line script. It does not, so we need chunking, a map-reduce, a
cache, and a way to keep timestamps alive through all of it.

There is a second, less obvious constraint. Even when a model *can* accept a very long input,
quality degrades in the middle of it — attention spreads thin and material buried mid-context
gets skimmed. So chunking is not purely a workaround for small windows; it is also a quality
strategy. A model given 1,200 focused tokens reads them properly.

---

## 2. Data flow

```
                    ┌─────────────────────────────────────────────┐
   "youtu.be/abc"   │                                             │
        │           │   ingest/urls.py        extract_video_id     │
        ▼           │                                             │
    video_id ───────┤   ingest/captions.py    fetch_transcript     │
        │           │        ▲                                    │
        │           │        │ (stage 5: ingest/audio.py, Whisper) │
        ▼           │        │                                    │
    Transcript ─────┤   cache/store.py        read-through         │
   (with timings)   │                                             │
        │           │                                             │
        ▼           │   chunking/windows.py   build_chunks_capped  │
     [Chunk] ───────┤   chunking/tokens.py    estimate_tokens      │
        │           │                                             │
        ▼           │   summarize/mapper.py   N parallel calls     │
  [ChunkSummary] ───┤   llm/ollama.py         HTTP → localhost     │
        │           │   llm/jsonio.py         parse + repair       │
        │           │   cache/store.py        per-chunk cache      │
        ▼           │                                             │
   VideoSummary ────┤   summarize/reducer.py  1 call over summaries│
        │           │                                             │
        ▼           │   render/markdown.py    markdown or JSON     │
     notes.md       └─────────────────────────────────────────────┘
```

Read [`src/podsum/pipeline.py`](../src/podsum/pipeline.py) alongside this. It is about eighty
lines and contains no logic of its own — only the order of operations.

---

## 3. Decisions and their costs

### 3.1 Timestamps survive to the end, or nothing else matters

The most consequential choice in the codebase is that ingest returns a
`tuple[Snippet, ...]` — individual caption cues, each pinned to a time — rather than one
joined string.

It would be simpler to join immediately. Doing so would also make the tool worthless, because
"a summary" and "a summary you can click into" are different products. Once you flatten, the
timing information is gone and no later stage can recover it.

The cost is that chunking has to work over a list of cues rather than a string, which makes
[`windows.py`](../src/podsum/chunking/windows.py) an index-juggling loop instead of a slice.
That is the whole price, and it is worth paying.

### 3.2 Chunk boundaries are the main quality lever

Chunking has four rules, in priority order:

1. **Never split inside a cue.** Cues are roughly sentence-shaped. Cutting mid-cue produces a
   chunk that begins halfway through a thought, and the model will confidently summarize the
   fragment as though it were whole.
2. **Carry `start` and `end` on every chunk.** See above.
3. **Overlap neighbours.** With zero overlap, the single most common failure is a chapter that
   describes half an argument — the setup lands in chunk 4 and the conclusion in chunk 5, and
   neither summary is right. The default 120 tokens is about ten seconds of speech.
4. **Never exceed `hard_max_tokens`.** Overflowing the context window does not raise an error.
   The model silently ignores part of its input, which is far worse than a crash because the
   output still looks plausible.

The overlap costs real money in the local-model sense: repeated text means more chunks means
more inference. That trade is explicit in config rather than hidden in code.

### 3.3 Token counting is knowingly approximate

[`chunking/tokens.py`](../src/podsum/chunking/tokens.py) divides character count by four. That
is a rule of thumb for English prose and it is wrong for anything else — code, non-Latin
scripts, unusual proper nouns.

We accept it because chunk sizes have slack built in (`target` well below `hard_max`), so being
off by 15% is harmless. It is flagged rather than hidden, and the module declares a `Tokenizer`
protocol so an exact implementation can be dropped in without touching `windows.py`.

This is the deliberate seam to the learning track. Writing a real BPE tokenizer by hand is the
first component of [`research/tinygpt/`](../research/tinygpt/), and finishing it makes this
module exact instead of approximate.

### 3.4 Map-reduce, and what it destroys

The map step summarizes each chunk in isolation. The reduce step summarizes those summaries.

The property that makes this work is that the map step is *embarrassingly parallel* — chunks do
not depend on each other — so it can be threaded and cached per chunk.

The property that makes it lossy is the same one. A chunk summarized in isolation has no idea
what came before it, so:

- **Pronouns dangle.** If a guest is introduced in chunk 1 and referred to as "he" in chunk 7,
  chunk 7's summary cannot name him.
- **Callbacks vanish.** A conclusion that only makes sense given something said forty minutes
  earlier reads as a non-sequitur.
- **Errors compound.** The reducer never sees the transcript, only the chapter summaries. So a
  hallucination introduced in the map step is treated as source material by the reduce step,
  and there is no mechanism anywhere downstream that can catch it.

That last point is the honest limitation of this entire architecture, and it is an open research
problem, not a bug with a known fix. Mitigations that would help, in rough order of
cost-effectiveness: pass a running summary of prior chunks into each map call (sacrifices
parallelism), pass the video's title and description as standing context (cheap, helps a lot),
or run a verification pass that checks each claim against the source (doubles inference cost).

None are implemented. `llm.concurrency` and the current prompts assume independence.

### 3.5 The model sits behind a `Protocol`

[`llm/base.py`](../src/podsum/llm/base.py) declares a three-method interface. Nothing above the
`llm/` package imports `ollama.py`.

Three things fall out of that, and only the first is obvious:

- Swapping in a hosted API is a new file in `llm/` plus one line in `factory.py`.
- The tests define a twenty-line `FakeClient` that inherits from nothing, satisfies the protocol
  structurally, and lets the entire summarization path be tested with no model installed and no
  network. See [`tests/test_summarize.py`](../tests/test_summarize.py). This is why CI passes on
  a GitHub runner.
- The cache key includes `client.name`, so switching models cannot serve you a stale summary
  from the previous one.

`Protocol` rather than an abstract base class because typing is then structural: a third-party
client satisfies the interface without needing to know we exist.

### 3.6 Never call `json.loads` on model output

Ollama's constrained decoding (`format=<schema>`) handles most cases, but small local models
still emit JSON wrapped in code fences, prefixed with "Sure! Here you go:", or preceded by a
`<think>` block. [`llm/jsonio.py`](../src/podsum/llm/jsonio.py) strips reasoning blocks and
fences, then falls back to a brace-depth scan that ignores braces inside string literals.

Above that, the map step retries once and then emits a placeholder chapter. One bad segment in
a ninety-minute video should cost you one chapter, not the whole run.

Every case in [`tests/test_jsonio.py`](../tests/test_jsonio.py) is a real shape a small model
produces. This module is unglamorous and it is most of the difference between a demo and a tool.

### 3.7 The cache key describes everything that mattered

Chunk summaries are keyed on `sha256(chunk_text + model_name + prompt_version)`, where
`prompt_version` is a hash of the prompt file itself.

Cache invalidation is normally the hard part of caching. Here we sidestep it: if any input to a
summary changes, the key changes and the old entry becomes unreachable. Edit a prompt and the
next run recomputes automatically. This matters more than it sounds — the alternative is
tweaking a prompt, seeing identical output, and losing an hour to confusion.

Prompts live in `.md` files rather than Python string literals partly for this reason and partly
because `git diff` on a prompt change is then readable.

### 3.8 Threads, not asyncio

The map step is blocking HTTP calls to localhost. That is I/O-bound work, the GIL is released
while waiting, and `ThreadPoolExecutor.map` preserves input order so chapters stay chronological
regardless of completion order. `asyncio` would buy nothing here and would colour every function
in the call chain `async`.

Concurrency defaults to 2. A single Ollama instance queues concurrent requests anyway, and on a
machine with 18GB of unified memory the model, the KV cache, and everything else are competing
for the same pool.

---

## 4. Known failure modes

| Failure | Cause | Current behaviour |
| --- | --- | --- |
| No captions | Uploader disabled them, or the video is too new | `TranscriptUnavailable`. Stage 5 will fall back to Whisper. |
| Captions in an unexpected language | `transcript.languages` does not match | `TranscriptUnavailable`. Override with `--set transcript.languages=th,en`. |
| YouTube blocks the request | Datacenter or VPN IP; YouTube rate-limits these aggressively | `TranscriptUnavailable` with the library's explanation. Works from a normal home connection. |
| Ollama not running | The app is closed | `podsum doctor` catches it before any work starts. |
| Model not pulled | Fresh machine | `doctor` names the exact `ollama pull` command. |
| Model returns prose, not JSON | Small model, unlucky sample | One retry, then a placeholder chapter for that segment only. |
| Four-hour livestream | Would produce 80 chapters | `build_chunks_capped` widens the windows until the count fits `output.max_chapters`, without truncating the tail. |
| Summary states something not in the video | Compounding error through the map-reduce | **Not handled.** See §3.4. This is the real limitation. |

---

## 5. Where this breaks next

Roughly in the order you will hit it:

1. **Videos without captions** are a large minority, and stage 5 is the fix. The seam already
   exists: [`ingest/audio.py`](../src/podsum/ingest/audio.py) has to return a `Transcript` and
   nothing else in the codebase changes.
2. **Speaker attribution.** Auto-captions have no speaker labels, so a two-host podcast reads as
   one long monologue and "the guest argued X" is partly guesswork. Whisper plus diarisation
   fixes this properly; it would mean adding a `speaker` field to `Snippet`.
3. **Faithfulness.** There is currently no way to know whether a summary is accurate. ROUGE, the
   standard summarization metric, measures word overlap with a reference and is close to useless
   for detecting invented claims. Doing this properly means an evaluation harness, which is
   real work and the honest prerequisite to claiming any quality improvement.
4. **Non-English content.** The prompts say "match the language of the transcript", which mostly
   works, but the token estimate in §3.3 is materially wrong outside English, so chunk sizes
   drift.
5. **Deployment.** Free hosting cannot reach the Ollama on your laptop. "Publicly deployed" and
   "fully local and free" cannot both be true, and the `LLMClient` protocol exists so that
   choosing hosting later is a config change rather than a rewrite.
