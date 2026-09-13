You are given section summaries from a single long video, in chronological order. Write the
top-level summary that sits above them.

Return a single JSON object with these fields:

- `title`: a specific title of 4 to 10 words for the whole video.
- `tldr`: three to five sentences covering what the video is actually about, the most
  substantial things said in it, and who would find it worth their time. Lead with substance.
  Do not open with "In this video".

Rules:

- Work only from the sections you were given. Add nothing from outside knowledge.
- Prefer the specific over the general. Concrete claims, numbers, and disagreements belong in
  the summary ahead of generic description.
- Never mention "sections", "segments", or "chunks". The reader never sees them and does not
  know the video was processed in pieces.
- Write in the same language as the input.
- Output the JSON object only. No preamble, no code fence, no commentary.
