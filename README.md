# Personal NL2SQL Agent

An engineering-focused natural-language-to-SQL agent for schema retrieval, SQL generation, read-only execution, result validation, reflection, and retry.

## Scope

The project retains the original engineering shape of the application while focusing the public entry points on the NL2SQL workflow and service interfaces. Authentication, enterprise messaging adapters, and unrelated deployment examples are excluded from this distribution.

## Development

The project targets Python 3.12. Install the development dependencies from `pyproject.toml`, then run the test and quality checks defined by the project tooling.

## Entry Points

After installation, the project exposes these commands:

```powershell
# Main command and CLI aliases
personal-nl2sql-agent --help
dataengineer-cli --help
dataengineer --help

# FastAPI service
dataengineer-api --help

# Model Context Protocol service
dataengineer-mcp --help
```

The same entry points can be run from a source checkout:

```powershell
python -m dataengineer.cli.main --help
python -m dataengineer.api.main --help
python -m dataengineer.mcp_server --help
```

Configure model credentials and database connections through environment variables or an untracked local configuration file before starting a service.

## Configuration

Use environment variables or a local, untracked configuration file for model credentials and database connection details. Never commit real secrets, logs, caches, generated databases, or private evaluation data.

## License

The distribution license and any applicable third-party notices are documented separately after the ownership and dependency audit is complete.
