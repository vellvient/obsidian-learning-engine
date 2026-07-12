# 07 — Pitfalls

The accumulated scar tissue of the reference build (~900 notes, 1,500+ edges, months
of daily use). Read this **before** your first bulk operation. Ordered by how much
time each one cost.

## Obsidian-specific

1. **Obsidian overwrites `graph.json` while running.** Write a new graph.json with
   Obsidian open and it will be clobbered from memory within seconds (file shrinks to
   ~500 bytes, color groups gone). This happened repeatedly. **Always close Obsidian
   completely before writing graph.json**, then reopen. Check first:
   `tasklist | findstr Obsidian` (Windows) / `pgrep -i obsidian`.
2. **Body `#tags` drive graph coloring, not frontmatter.** Every note carries a body
   tag line (`#not-started` etc.). Obsidian's graph view colors by the FIRST matching
   color group, and body tags are what it matches — so order mastery groups first and
   `#not-started` last, or gray overrides everything.
3. **Custom protocol links don't fire from Obsidian notes.** `review://` buttons were
   registered in the OS and worked from a browser — Obsidian silently ignores custom
   protocol links in both Live Preview and Reading View. Confirmed dead end; grading
   is a terminal command. Don't spend a day rediscovering this.
4. **Wikilinks break on `|` in names.** `|` is Obsidian's link separator. Strip
   `||...||` math markup (and any stray `|`) from names *before* creating files.
5. **YAML backlinks are invisible to the graph.** `parents: ["[[Topic]]"]` in
   frontmatter creates no graph edge — always add a `[[Topic]]` wikilink in the body too.

## Bulk generation / AI-agent operations

6. **Freeze the slugify function across agents.** Two agents slugifying the same
   name slightly differently (parentheses, commas, `/`) produce duplicate files for
   one skill id. Define ONE slugify, pass it verbatim to every agent, and verify
   afterwards: `Counter` over leading ids, assert no duplicates.
7. **Build wikilinks from actual file stems, never re-derived names.** After files
   exist, `glob("{id} - *.md")` and link to what you find. Re-deriving the slug from
   the source name produces greyed-out broken links.
8. **Never `str.replace` on full file content to insert a body link.** The first
   match is nearly always inside the frontmatter `parents:` line → YAML corruption.
   Split at the second `---`, operate on the body only.
9. **Subagents write results to the wrong directory.** Always give agents the exact
   absolute output path. Check both the intended dir and the batch dir after each wave.
10. **Late agents overwrite good results.** An agent you gave up on can finish later
    and clobber the file. Re-run merge+apply after any late arrival; validate result
    files before trusting them.
11. **Give agents absolute paths to data files.** They can't see your conversation;
    without the path they guess ids or invent content.
12. **Delegate mechanical work, keep domain reasoning.** Bulk file creation,
    find-and-replace patching, cross-linking = safe to delegate. Deciding *which*
    skills are prerequisites of which = do it yourself or QA it hard.

## Mastery/state synchronization

13. **The 4-place mastery sync.** `mastery:` frontmatter, `tags:` frontmatter, body
    `#tag`, and the `Mastery: **...**` display line each have their own copy and
    different consumers. A file can say `mastery: mastered` while `tags:` still says
    familiar — and the tag pane/graph will show familiar. Use the sync script; never
    patch one place.
14. **Fuzzy patch matching can cross-match `[familiar` vs `#familiar`.** When
    patching, include disambiguating context: `"tags: [familiar, "`, `"\n#familiar\n"`,
    `"**Familiar** ("` — never the bare word.
15. **Display-text counters go stale.** `(4/6)` in the display line doesn't update
    itself; always recompute from actual `- [x]` lines, never trust the label.
16. **`parent:` vs `parents:`.** Old notes use singular-string, newer use plural-array
    (and some use multi-line YAML lists). Detect all three before patching; convert
    singular→plural when adding a second parent, with every `[[link]]` in its own
    double-quoted string.

## Scheduler / state files

17. **Never trust "0 due" alone.** A seeding bug once gave every card S=30/due+30d —
    dashboard said 0 due while 300+ reviews were overdue. Cross-check `--stats`
    against `scripts/srs-backlog.py`; uniform stability across all cards = reseed.
18. **`srs_state.json` is owned by the engine.** Never hand-edit; never `git add` it
    when committing note changes (and gitignore it entirely if your vault repo is
    public — it's your personal study history).
19. **Auto-generated dashboards are not truth to edit.** Hand-edits to the tracker/
    grader/diagnostic are silently destroyed on the next regeneration. If you want to
    change them, change the generator.
20. **Windows console encoding (cp932/cp1252) crashes emoji prints.** Every script
    that prints must start with `sys.stdout.reconfigure(errors="replace")` (all
    shipped scripts do). Symptom: `UnicodeEncodeError` deep in a run.

## Mining/graph quality

21. **Transitivity leaks in.** Models add A→C alongside A→B→C. Run transitive
    reduction after every wave, not once at the end.
22. **Naive DOWNSTREAM ranking collapses onto graph roots.** "Counting all
    descendants" makes the trunk node look infinitely valuable. Rank by
    FULLY_UNBLOCKS and IN_DEGREE instead.
23. **Mastered hubs already paid off.** Huge in-degree + mastered = value realized;
    don't let ranking scripts resurface them.
24. **Missing prereq ids crash naive graph walks.** An edge can point at a note that
    was never created — guard every lookup (`if p in ids`).
25. **Empty-prereq skills are prime mining targets, not finished work.** They often
    need cross-domain foundations the per-domain pass missed.

## Process

26. **Batch size economics.** Full batch files with an embedded master index
    (~190KB) blow cheap-model context. Strip to compact batches (8–55KB) + one shared
    index file. Process small batches (<15 skills) inline; reserve agents for 30–40.
27. **Merge+apply after every wave.** Waiting until the end means one bad wave
    poisons everything and you can't tell which.
28. **Keep the docs in sync with the code.** Every new CLI flag or daemon behavior
    updates the operator doc (AGENTS.md) in the same change — a stale briefing makes
    the next agent (or future you) rebuild instead of extend.
29. **Counts drift; methodology doesn't.** Any absolute number in a doc ("108 files
    with 0 subskills") is stale the week after. Record the check command, not just
    its output.
