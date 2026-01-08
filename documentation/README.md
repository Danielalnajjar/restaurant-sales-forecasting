# Documentation

This directory contains all project documentation organized by category.

## 📁 Structure

```
documentation/
├── README.md                    # This file
├── YEAR_AGNOSTIC.md            # Architecture: Year-agnostic design principles
├── changelogs/                  # Version changelogs and implementation summaries
│   ├── V5.4.4_CHANGELOG.md
│   ├── V5.4.5_CHANGELOG.md
│   ├── V5.4.6_CHANGELOG.md
│   ├── V5.4.7_CHANGELOG.md
│   └── V5.4.8_CHANGELOG.md
├── audits/                      # External audit reports and analysis
│   ├── GPT_5.2_PRO_FINDINGS_VERIFICATION.md
│   └── GPT_5.2_PRO_SECOND_RESPONSE_ANALYSIS.md
└── archive/                     # Historical working documents
    └── (old progress checkpoints, baseline evidence, etc.)
```

## 📖 Key Documents

### Architecture
- **YEAR_AGNOSTIC.md** - Core design principles for year-agnostic forecasting system

### Changelogs
- **V5.4.4_CHANGELOG.md** - Dynamic holidays, CI, linting fixes
- **V5.4.5_CHANGELOG.md** - Logging, pointers, year-agnostic improvements
- **V5.4.6_CHANGELOG.md** - Generic APIs, config validation, year-generic uplift
- **V5.4.7_CHANGELOG.md** - Uplift flag, config drift fixes, shutil scope
- **V5.4.8_CHANGELOG.md** - Documentation cleanup, config schema consistency

### Audit Reports
- **GPT_5.2_PRO_FINDINGS_VERIFICATION.md** - Verification of ChatGPT 5.2 Pro's findings
- **GPT_5.2_PRO_SECOND_RESPONSE_ANALYSIS.md** - Analysis of second audit response

## 🎯 Quick Links

- **Latest Changelog:** [V5.4.8_CHANGELOG.md](changelogs/V5.4.8_CHANGELOG.md)
- **Architecture:** [YEAR_AGNOSTIC.md](YEAR_AGNOSTIC.md)
- **Project README:** [../README.md](../README.md)

## 📝 Document Conventions

### Changelogs
- Named: `V{major}.{minor}.{patch}_CHANGELOG.md`
- Contains: What changed, why, impact, verification results
- Audience: Developers, auditors, maintainers

### Implementation Summaries
- Named: `V{major}.{minor}.{patch}_IMPLEMENTATION_SUMMARY.md`
- Contains: Detailed implementation steps, code changes, test results
- Audience: Technical reviewers, future maintainers

### Audit Reports
- Named: `GPT_5.2_PRO_{topic}.md`
- Contains: External audit findings, analysis, responses
- Audience: Stakeholders, quality assurance

## 🗂️ Archive

The `archive/` directory contains historical working documents that were useful during development but are not needed for ongoing maintenance:
- Progress checkpoints
- Baseline evidence files
- Interim verification reports
- Working logs

These are kept for historical reference but are not part of the active documentation set.
