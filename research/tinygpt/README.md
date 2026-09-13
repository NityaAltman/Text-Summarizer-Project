# tinygpt — the learning track

A transformer built from scratch, to understand what the model in `podsum` is actually doing.

**Nothing here is imported by `podsum`, and nothing here will ever write a usable summary.**
That is not a shortcoming, it is the point. Keep the two separate in your head:

| | `src/podsum` | `research/tinygpt` |
| --- | --- | --- |
| Purpose | a tool you use | understanding you keep |
| Model | 8B, pretrained by someone else | ~10M, trained by you |
| Training data | none, you never train it | a few megabytes |
| Output quality | genuinely useful | text-shaped gibberish |
| Cost | $0 | $0 |

The scale gap is not something effort closes. A model that can summarize a two-hour
conversation was pretrained on trillions of tokens across thousands of GPUs. So: learn the
mechanism on a toy where the feedback loop is minutes long, and borrow capability where
capability is expensive.

---

## Order of work

Deliberately sequenced so each piece feeds back into the tool rather than sitting in a corner.

### 1. A BPE tokenizer

Byte-pair encoding, by hand: count adjacent pairs, merge the most frequent, repeat. Then
`encode` and `decode`.

**Why first:** `src/podsum/chunking/tokens.py` currently approximates token counts as
`len(text) / 4`. It declares a `Tokenizer` protocol precisely so a real one can replace the
heuristic. Finish this and your chunk sizes stop being guesses — and you will understand why
the number changed, which is the part reading cannot give you.

### 2. Attention, and one transformer block

Query, key, value. Scaled dot-product attention. Causal masking, so position *i* cannot see
position *i+1*. Multiple heads. Then the rest of a block: an MLP, residual connections, layer
norm.

**Why:** this is the whole architecture. Once you have written it, "context window", "KV cache",
and "attention head" become concrete, and `llm.num_ctx` in the config stops being a number you
copied and starts being a memory budget you understand.

### 3. A training loop

Batch, forward pass, cross-entropy loss against the next token, backward pass, optimizer step.
Train on a few megabytes of text — TinyShakespeare is the traditional choice. On an M-series Mac
use PyTorch's MPS backend; this trains in minutes, not hours.

**What you should expect to see:** the loss dropping then flattening. The model learning
spelling before words and words before syntax. Overfitting, where it starts reciting training
text verbatim. A learning rate set slightly too high destroying a run in ten steps. Those four
observations are the thing you came for, and none of them survive being read about.

### 4. Sampling

Greedy decoding, then temperature, then top-k. Watch high temperature make the model wander and
low temperature make it repeat itself.

**Why last:** `configs/default.yaml` sets `llm.temperature: 0.2` with the comment "this is
faithful compression, not creative writing". After this step that stops being advice you
followed and becomes a mechanism you understand.

---

## What this does not teach

Worth being clear about, so the gap does not surprise you later:

- **Distributed training.** Data, tensor, and pipeline parallelism are most of the hard
  engineering at real scale, and none of it appears on one laptop.
- **Post-training.** Your model will be a raw base model. It continues text; it cannot follow an
  instruction. Instruction tuning and preference alignment (RLHF, DPO) are separate phases and
  are what turns a base model into something you can chat with.
- **Data curation.** Deduplication, filtering, and quality classification are arguably the real
  secret sauce of frontier models, and they are invisible at toy scale.

---

## Hardware notes

Sized for an M3 Pro with 18GB, which is more than enough.

- Training a ~10M-parameter model on a few megabytes of text is minutes of work. The fans will
  spin up. Macs throttle their own clocks before temperature becomes a hardware risk, so this is
  not a machine-damaging workload — and it is a *lighter* sustained load than running the 8B
  model in `podsum`, which you already do.
- The real constraint is unified memory, not heat. Do not run training and inference at the same
  time; if you overcommit RAM, macOS swaps to SSD, which is slow and does cause wear.
- Put a hard iteration cap on every training script so it stops on its own rather than running
  overnight.
- `asitop` shows live chip power and temperature if you want visibility.

## Following along

- [nanoGPT](https://github.com/karpathy/nanoGPT) and Karpathy's "Let's build GPT from scratch"
- Karpathy's "Let's build the GPT Tokenizer" for step 1 specifically
- Sebastian Raschka, *Build a Large Language Model (From Scratch)* — the same path in book form
