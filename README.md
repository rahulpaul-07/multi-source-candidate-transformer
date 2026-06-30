# Multi-Source Candidate Data Transformer

Turns messy, conflicting candidate data from many sources into **one clean,
canonical profile per candidate** — normalized, deduplicated, and carrying
**provenance + confidence on every value**. Guiding rule: *wrong-but-confident
is worse than honestly-empty* — unknown values become `null`, never invented.

> Design rationale lives in the one-page technical design (PDF) submitted with this repo.

## Pipeline

```
detect -> extract -> normalize -> merge -> score -> project -> validate
```

## Status

Scaffold in place. Implementation is added stage by stage (see commit history).

## Install

```bash
pip install -r requirements.txt
```

## Usage

_Added with the CLI._

## Configurable output

_Added with the projection layer._

## Tests

```bash
pytest -q
```

## Assumptions & deliberately descoped

_Documented as the build progresses._
