# Configuring the cockpit for any subject

The cockpit code is subject-neutral. Do not fork `cockpit_engine.py` to add a
new discipline. Put subject behavior in `vault/config/course_catalog.json`, then
install or refresh the shared files with:

```powershell
python automation/install_cockpit.py --vault C:\path\to\subject-vault --port 8766
```

The installer never overwrites course configuration, notes, graph edges,
question banks, FSRS state, or personal cockpit state.

Validate a new adapter before launching it:

```powershell
python automation/validate_cockpit_config.py --vault C:\path\to\subject-vault
```

This checks target data, question-to-node references, unique error ids, rubric
dimensions, and whether each configured rubric matches real questions.

## Course targets

Use the curriculum catalogue as the coverage denominator when every catalogue
node is examinable:

```json
{
  "profiles": {
    "subject-code": {
      "label": "My Subject",
      "question_code": "subject-code",
      "target_source": "curriculum",
      "curriculum_path": ".engine/curriculum.json",
      "target_min": 1001,
      "target_max": 1200,
      "routes": {
        "full": {"label": "Full course", "component_prefixes": ["1", "2"]}
      }
    }
  }
}
```

This prevents broad question tags from inflating syllabus coverage. Nodes that
are ancestors of a target remain available for causal diagnosis even when they
are not themselves examined.

## Question banks and images

Declare one or more private banks. Paths are relative to the vault:

```json
{
  "question_banks": [
    {"path": "papers/question_bank.json", "render_root": "papers/renders"}
  ]
}
```

The default renderer recognizes `<paper>_qN_p*.png` and
`<paper>_ms_qN_p*.png`. A bank may supply `question_pattern` and
`markscheme_pattern` when another naming convention is required. Copyrighted
questions and images stay in the private vault and are never needed by the
public engine.

## Subject-specific causal errors

Each error type has a stable id, a learner-facing label, and a `causal` flag.
Only causal types can provide strong evidence for prerequisite diagnosis.
One-off slips, timing problems, and misreads should normally be non-causal.

```json
{
  "assessment": {
    "error_types": [
      {"id": "concept", "label": "Concept gap", "causal": true},
      {"id": "misread", "label": "Misread", "causal": false}
    ]
  }
}
```

The graph remains the source of candidate causes. Configuration changes the
evidence vocabulary, not the prerequisite topology.

## Multidimensional assessment rubrics

Rubrics can match component-type text, component-number prefixes, or assessment
tags. They are useful for practical work, essays, laboratories, programming
projects, oral performance, and any task that cannot be represented honestly by
Correct/Partial/Wrong alone.

```json
{
  "assessment": {
    "rubrics": [{
      "id": "essay",
      "assessment_tags": ["essay"],
      "required": true,
      "dimensions": [
        {"id": "knowledge", "label": "Knowledge", "max": 2},
        {"id": "analysis", "label": "Analysis", "max": 3},
        {"id": "evaluation", "label": "Evaluation", "max": 3}
      ]
    }]
  }
}
```

The cockpit records the dimension scores and uses their percentage for timed-set
evidence. The source mark scheme remains authoritative.

## Separation rule

Separate subjects keep independent graphs, FSRS stores, errors, and personal
state. A cross-subject hub may read exported summaries and link to another
subject's support skill, but must not merge or directly mutate subject state.

For one browser entry point, use `automation/multi_vault_cockpit.py` with a
private JSON file containing `{id, label, vault, port}` rows. It starts only
missing subject servers and presents them as tabs. The tabbed shell is shared;
every iframe still talks only to its own vault engine and state.
