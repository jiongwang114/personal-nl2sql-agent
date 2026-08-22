# Personal NL2SQL Agent

An engineering-focused natural-language-to-SQL agent for schema retrieval, SQL generation, read-only execution, result validation, reflection, and retry.

## Scope

The project retains the original engineering shape of the application while focusing the public entry points on the NL2SQL workflow and service interfaces. Authentication, enterprise messaging adapters, and unrelated deployment examples are excluded from this distribution.

## Development

The project targets Python 3.12. Install the development dependencies from `pyproject.toml`, then run the test and quality checks defined by the project tooling.

## Configuration

Use environment variables or a local, untracked configuration file for model credentials and database connection details. Never commit real secrets, logs, caches, generated databases, or private evaluation data.

## License

The distribution license and any applicable third-party notices are documented separately after the ownership and dependency audit is complete.
