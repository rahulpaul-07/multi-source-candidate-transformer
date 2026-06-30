"""Multi-source candidate data transformer.

Turns messy, conflicting candidate sources into one canonical, deduplicated
profile per person, with provenance and confidence on every value.

Pipeline:  detect -> extract -> normalize -> merge -> score -> project -> validate
"""

__version__ = "0.1.0"
