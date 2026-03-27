# agent-os-kernel Documentation

This directory contains all documentation for the project. It is split into two sections serving different audiences.

## Layout

```
docs/
├── README.md                 ← You are here
├── mkdocs.yml                ← MkDocs config (renders user/ into a static site)
│
├── user/                     ← PUBLIC DOCS — for users, reviewers, collaborators
│   ├── index.md                    Project overview
│   ├── getting-started/
│   │   ├── installation.md         Environment & dependency setup
│   │   └── quickstart.md           Minimal end-to-end example
│   ├── guides/                     How-to guides
│   ├── api/                        Auto-generated API reference (mkdocstrings)
│   └── changelog.md
│
└── research/                 ← INTERNAL DOCS — for the team
    ├── experiments/                 Experiment reports (dated, reproducible)
    │   └── TEMPLATE.md              Standard template for new reports
    ├── plans/                       Research plans & proposals
    ├── meetings/                    Meeting notes
    └── references/                  Literature notes
```

## Which section should I read?

| I want to ...                              | Go to            |
|--------------------------------------------|------------------|
| Install and run the project                | `user/getting-started/` |
| Follow a step-by-step workflow             | `user/guides/` |
| Look up a class or function signature      | `user/api/` |
| Read an experiment report                  | `research/experiments/` |
| Check what was discussed in a meeting      | `research/meetings/` |
| Review our literature notes                | `research/references/` |

## Building the user docs locally

```bash
uv run mkdocs serve -f docs/mkdocs.yml   # live preview at http://127.0.0.1:8000
uv run mkdocs build -f docs/mkdocs.yml   # static site output to docs/site/
```

## Writing conventions

**User docs (`user/`)** are rendered by MkDocs and may be published. Write for an external reader who has ML background but no prior knowledge of this project.

**Research docs (`research/`)** are not rendered by MkDocs. They stay in the repo for team reference. Follow these conventions:

- **Experiments:** Name files as `YYYY-MM-DD_short-description.md`. Copy `TEMPLATE.md` to start. Every report must include: goal, environment, exact commands, results, and conclusion.
- **Meetings:** Name files as `YYYY-MM-DD.md`.
- **References:** Free-form, but include source links and a date header.
