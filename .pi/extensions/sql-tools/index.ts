import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type, type TSchema } from "typebox";

type MCPEnvelope = {
	success: number;
	error?: string | null;
	result?: unknown;
};

const extensionDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(extensionDir, "../../..");
const bridgePath = path.join(projectRoot, "scripts", "pi_mcp_bridge.py");
const windowsPython = path.join(projectRoot, ".venv", "Scripts", "python.exe");
const posixPython = path.join(projectRoot, ".venv", "bin", "python");
const python = process.env.PI_SQL_PYTHON
	?? (fs.existsSync(windowsPython) ? windowsPython : fs.existsSync(posixPython) ? posixPython : "python");

function parseEnvelope(stdout: string): MCPEnvelope {
	const lines = stdout.trim().split(/\r?\n/).filter(Boolean);
	const last = lines.at(-1);
	if (!last) throw new Error("MCP bridge returned no output");
	const value: unknown = JSON.parse(last);
	if (typeof value !== "object" || value === null || !("success" in value)) {
		throw new Error("MCP bridge returned an invalid envelope");
	}
	return value as MCPEnvelope;
}

async function callMcp(
	pi: ExtensionAPI,
	datasource: string,
	tool: string,
	args: Record<string, unknown>,
	signal?: AbortSignal,
): Promise<MCPEnvelope> {
	const result = await pi.exec(
		python,
		[
			bridgePath,
			"--datasource",
			datasource,
			"--tool",
			tool,
			"--arguments",
			JSON.stringify(args),
			...(process.env.PI_SQL_CONFIG ? ["--config", process.env.PI_SQL_CONFIG] : []),
		],
		{ cwd: projectRoot, signal, timeout: 120_000 },
	);
	const envelope = parseEnvelope(result.stdout);
	if (result.code !== 0 || envelope.success !== 1) {
		throw new Error(envelope.error || result.stderr || `${tool} failed`);
	}
	return envelope;
}

function registerMcpTool(
	pi: ExtensionAPI,
	name: string,
	description: string,
	parameters: TSchema,
): void {
	pi.registerTool({
		name,
		label: name,
		description,
		parameters,
		async execute(_toolCallId, params, signal) {
			const input = params as Record<string, unknown>;
			const datasource = typeof input.datasource === "string" ? input.datasource : "demo";
			const args = { ...input };
			delete args.datasource;
			const envelope = await callMcp(pi, datasource, name, args, signal);
			return {
				content: [{ type: "text", text: JSON.stringify(envelope.result, null, 2) }],
				details: { datasource, tool: name, envelope },
			};
		},
	});
}

export default function (pi: ExtensionAPI) {
	const datasource = Type.Optional(Type.String({ description: "Configured datasource name; defaults to demo" }));

	registerMcpTool(
		pi,
		"search_table",
		"Find tables related to a business question using the existing Schema RAG.",
		Type.Object({
			query_text: Type.String(),
			datasource,
			top_n: Type.Optional(Type.Integer({ minimum: 1, maximum: 20, default: 5 })),
		}),
	);
	registerMcpTool(
		pi,
		"list_schemas",
		"List visible schemas. Use this before table inspection when the schema is not already known.",
		Type.Object({
			catalog: Type.Optional(Type.String()),
			database: Type.Optional(Type.String()),
			include_sys: Type.Optional(Type.Boolean()),
			datasource,
		}),
	);
	registerMcpTool(
		pi,
		"list_tables",
		"List visible tables and views within an optional schema. Never assume the schema is public.",
		Type.Object({
			catalog: Type.Optional(Type.String()),
			database: Type.Optional(Type.String()),
			schema_name: Type.Optional(Type.String()),
			include_views: Type.Optional(Type.Boolean()),
			datasource,
		}),
	);
	registerMcpTool(
		pi,
		"describe_table",
		"Return physical and semantic column metadata for a table.",
		Type.Object({ table_name: Type.String(), schema_name: Type.Optional(Type.String()), datasource }),
	);
	registerMcpTool(
		pi,
		"get_table_ddl",
		"Return the DDL for a visible table.",
		Type.Object({ table_name: Type.String(), schema_name: Type.Optional(Type.String()), datasource }),
	);
	registerMcpTool(
		pi,
		"search_metrics",
		"Search stored business metric definitions.",
		Type.Object({ query_text: Type.String(), top_n: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })), datasource }),
	);
	registerMcpTool(
		pi,
		"search_reference_sql",
		"Search stored reference SQL by business intent.",
		Type.Object({ query_text: Type.String(), top_n: Type.Optional(Type.Integer({ minimum: 1, maximum: 20 })), datasource }),
	);
	registerMcpTool(
		pi,
		"validate_sql",
		"Parse and validate exactly one read-only SQL query. This tool does not execute SQL.",
		Type.Object({ sql: Type.String(), dialect: Type.Optional(Type.String()), datasource }),
	);

	pi.registerTool({
		name: "execute_readonly_sql",
		label: "Execute read-only SQL",
		description: "Validate SQL with the deterministic Guard, then execute it through the read-only database gateway.",
		parameters: Type.Object({
			sql: Type.String(),
			dialect: Type.Optional(Type.String()),
			datasource,
		}),
		executionMode: "sequential",
		async execute(_toolCallId, params, signal) {
			const selectedDatasource = params.datasource ?? "demo";
			const guard = await callMcp(
				pi,
				selectedDatasource,
				"validate_sql",
				{ sql: params.sql, dialect: params.dialect ?? "" },
				signal,
			);
			const guardResult = guard.result as { allowed?: boolean; formatted_sql?: string };
			if (guardResult.allowed !== true) throw new Error("SQL Guard rejected the query");
			const execution = await callMcp(
				pi,
				selectedDatasource,
				"read_query",
				{ sql: guardResult.formatted_sql || params.sql },
				signal,
			);
			return {
				content: [{ type: "text", text: JSON.stringify({ guard: guardResult, execution: execution.result }, null, 2) }],
				details: { datasource: selectedDatasource, guard: guardResult, execution: execution.result },
			};
		},
	});
}
