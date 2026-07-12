# FAQ

**Why not just use Anki?**
Anki gives you FSRS over a flat deck. This system's point is the *graph*: flow-zone
gating (don't drill what you can't learn yet), unlock-leverage ranking (learn what
opens the most doors), FIRe (new learning implicitly reviews old material, so the
review burden shrinks instead of compounding), and relearning-lock (a failed
prerequisite hides its dependents). For flat domains (vocabulary, definitions),
Anki — or this repo's SRS half without the graph — is genuinely enough.

**Do I need Claude / a specific AI?**
No. The docs and shipped skills are written agent-agnostically: any agent that can
read files and run Python can execute the build (`vault/AGENTS.md` is the entry
point; `.claude/skills/` are markdown instructions any agent can follow). The engine
itself never calls an AI. AI is used at build time (note generation, edge mining,
question tagging) and optionally for error triage.

**What does it cost to build a subject?**
The reference build mined ~1,500 edges and tagged ~2,000 past-paper questions on a
budget model (DeepSeek-class) for roughly the cost of a coffee — the expensive model
only spot-checked samples. Route bulk batch work to cheap models; keep strong models
for QA and domain judgment.

**Windows: I get `UnicodeEncodeError` or weird `?` characters.**
Your console isn't UTF-8 (cp932/cp1252). All shipped scripts guard with
`sys.stdout.reconfigure(errors="replace")` — output stays correct, non-ASCII glyphs
degrade to `?`. If you write your own scripts, add the same guard. `chcp 65001` or
Windows Terminal fixes it properly.

**Can I use this for languages / non-STEM / non-curriculum learning?**
Partially. Languages have no deep prerequisite DAG worth mining — use the SRS +
error-log + daily-wrapper half with a flat or shallow graph. The "material linked to
node" pattern (practice per skill) still applies. The full stack pays off for
cumulative subjects; see the >40%-SOFT rule in `GETTING_STARTED.md`.

**Where's my data? Is anything cloud-hosted?**
Everything is plain text/JSON in the vault folder. No accounts, no telemetry, no
cloud. Sync however you sync files (git, Syncthing, Obsidian Sync).

**Should I commit `.obsidian/srs_state.json`?**
In a *private* vault repo, committing it gives you history/backup of your review
state — fine. In a *public* repo, gitignore it: it's a timestamped log of everything
you studied and failed. (This template ships a demo one on purpose so scripts run
out of the box.)

**The demo says something is "due" — the dates are old.**
Intentional: the demo SRS state uses fixed past dates so `--due` is non-empty on any
future clone. Delete the demo notes and `srs_state.json` content when you build your
own subject.

**How do I reset / start my own subject?**
Delete the numbered demo notes (`1 - ...` to `15 - ...`), the two hub notes
(Expressions/Equations), empty `reviews` in `.obsidian/srs_state.json` (or delete the
file), empty `.engine/prerequisite_edges.json` to `[]`, and follow
`docs/02-build-pipeline.md`. The dashboards regenerate themselves.

**Does the paper pipeline work for my exam board?**
The architecture is board-agnostic; the PDF-splitting regexes are CIE-shaped. Budget
an hour to adapt `split_questions` / mark-scheme parsing to your board's layout and
verify on 2–3 papers before scaling (`docs/05-paper-pipeline.md`).
