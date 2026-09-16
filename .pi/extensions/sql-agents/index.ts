import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import type { Message } from "@earendil-works/pi-ai";
import { type ExtensionAPI, parseFrontmatter } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

type SqlState =
	| "classified"
	| "schema_ready"
	| "sql_generated"
	| "guard_passed"
	| "reviewed"
	| "executed"
	| "execution_failed"
	| "sql_repaired";

type AgentDefinition = {
	name: string;
	description: string;
	tools: string[];
	systemPrompt: string;
};

type AgentFrontmatter = { name?: unknown; description?: unknown; tools?: unknown };

const transitions: Record<string, { from: SqlState[]; to: string }> = {
	"schema-analyst": { from: ["classified"], to: "schema_ready" },
	"sql-generator": { from: ["schema_ready"], to: "sql_generated" },
	"sql-debugger": { from: ["execution_failed"], to: "sql_repaired" },
	"sql-reviewer": { from: ["guard_passed"], to: "reviewed" },
	"result-interpreter": { from: ["executed"], to: "interpreted" },
};

const extensionDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(extensionDir, "../../..");
const agentsDir = path.join(projectRoot, ".pi", "agents");
const sqlToolsExtension = path.join(projectRoot, ".pi", "extensions", "sql-tools", "index.ts");

function parseTools(value: unknown): string[] {
	if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
	if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
	return [];
}

function loadAgent(name: string): AgentDefinition {
	const filePath = path.join(agentsDir, `${name}.md`);
	if (!fs.existsSync(filePath)) throw new Error(`Unknown SQL agent: ${name}`);
	const content = fs.readFileSync(filePath, "utf8");
	const { frontmatter, body } = parseFrontmatter<AgentFrontmatter>(content);
	if (frontmatter.name !== name || typeof frontmatter.description !== "string") {
		throw new Error(`Invalid agent definition: ${filePath}`);
	}
	return { name, description: frontmatter.description, tools: parseTools(frontmatter.tools), systemPrompt: body };
}

function invocation(args: string[]): { command: string; args: string[] } {
	const script = process.argv[1];
	if (script && fs.existsSync(script)) return { command: process.execPath, args: [script, ...args] };
	return { command: "pi", args };
}

function finalText(messages: Message[]): string {
	for (let index = messages.length - 1; index >= 0; index--) {
		const message = messages[index];
		if (message.role !== "assistant") continue;
		return message.content.filter((part) => part.type === "text").map((part) => part.text).join("\n");
	}
	return "";
}

function parseAgentOutput(text: string, expectedState: string): Record<string, unknown> {
	const start = text.indexOf("{");
	const end = text.lastIndexOf("}");
	if (start < 0 || end <= start) throw new Error("Subagent did not return a JSON object");
	const value: unknown = JSON.parse(text.slice(start, end + 1));
	if (typeof value !== "object" || value === null || !("next_state" in value) || !("result" in value)) {
		throw new Error("Subagent output does not match the required envelope");
	}
	const output = value as Record<string, unknown>;
	if (output.next_state !== expectedState) {
		throw new Error(`Subagent returned state ${String(output.next_state)}; expected ${expectedState}`);
	}
	return output;
}

async function runAgent(
	definition: AgentDefinition,
	task: string,
	model: string | undefined,
	signal: AbortSignal | undefined,
): Promise<Record<string, unknown>> {
	const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-sql-agent-"));
	const promptPath = path.join(tempDir, `${definition.name}.md`);
	fs.writeFileSync(promptPath, definition.systemPrompt, { encoding: "utf8", mode: 0o600 });
	const args = [
		"--mode",
		"json",
		"-p",
		"--no-session",
		"-e",
		sqlToolsExtension,
		"--append-system-prompt",
		promptPath,
	];
	if (model) args.push("--model", model);
	if (definition.tools.length > 0) args.push("--tools", definition.tools.join(","));
	else args.push("--no-tools");
	args.push(`Task: ${task}`);
	const child = invocation(args);
	const messages: Message[] = [];

	try {
		await new Promise<void>((resolve, reject) => {
			const proc = spawn(child.command, child.args, {
				cwd: projectRoot,
				env: { ...process.env, PI_SQL_CHILD: "1" },
				stdio: ["ignore", "pipe", "pipe"],
			});
			let stdout = "";
			let stderr = "";
			proc.stdout.on("data", (data) => {
				stdout += data.toString();
				const lines = stdout.split(/\r?\n/);
				stdout = lines.pop() || "";
				for (const line of lines) {
					try {
						const event = JSON.parse(line) as { type?: string; message?: Message };
						if (event.type === "message_end" && event.message) messages.push(event.message);
					} catch {
						// Ignore non-protocol output.
					}
				}
			});
			proc.stderr.on("data", (data) => { stderr += data.toString(); });
			proc.on("error", reject);
			proc.on("close", (code) => code === 0 ? resolve() : reject(new Error(stderr || `Subagent exited ${code}`)));
			const abort = () => proc.kill("SIGTERM");
			if (signal?.aborted) abort();
			else signal?.addEventListener("abort", abort, { once: true });
		});
		return parseAgentOutput(finalText(messages), transitions[definition.name].to);
	} finally {
		fs.rmSync(tempDir, { recursive: true, force: true });
	}
}

export default function (pi: ExtensionAPI) {
	if (process.env.PI_SQL_CHILD === "1") return;

	pi.on("before_agent_start", async (event) => ({
		systemPrompt: `${event.systemPrompt}\n\nYou are the SQL Orchestrator. Use sql_subagent for role-specific reasoning. You may call only first-level SQL agents. All SQL execution must use execute_readonly_sql, which enforces the deterministic Guard. Repair at most twice.`,
	}));

	pi.registerTool({
		name: "sql_subagent",
		label: "SQL subagent",
		description: "Run one approved first-level SQL agent with isolated context and a validated state transition.",
		parameters: Type.Object({
			agent: Type.String({ description: "schema-analyst, sql-generator, sql-debugger, sql-reviewer, or result-interpreter" }),
			state: Type.String({ description: "Current SQL workflow state" }),
			repair_attempts: Type.Integer({ minimum: 0, maximum: 2, description: "Repairs already attempted for this request" }),
			task: Type.String({ description: "Complete task and structured context for the child agent" }),
		}),
		executionMode: "sequential",
		async execute(_toolCallId, params, signal, _onUpdate, ctx) {
			const transition = transitions[params.agent];
			if (!transition) throw new Error(`Agent is not approved: ${params.agent}`);
			if (!transition.from.includes(params.state as SqlState)) {
				throw new Error(`Illegal transition: ${params.agent} cannot run from ${params.state}`);
			}
			if (params.agent === "sql-debugger" && params.repair_attempts >= 2) {
				throw new Error("SQL repair limit reached: at most two attempts are allowed");
			}
			const definition = loadAgent(params.agent);
			const model = ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : undefined;
			const output = await runAgent(definition, params.task, model, signal);
			return {
				content: [{ type: "text", text: JSON.stringify(output, null, 2) }],
				details: { agent: definition.name, from: params.state, to: transition.to, output },
			};
		},
	});
}
