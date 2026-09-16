import * as fs from "node:fs";
import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type ToolTrace = {
	tool_call_id: string;
	tool_name: string;
	started_at: number;
	duration_ms?: number;
	is_error?: boolean;
};

const extensionDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(extensionDir, "../../..");
const traceDir = path.join(projectRoot, ".pi", "traces");

export default function (pi: ExtensionAPI) {
	let requestId = randomUUID();
	let turnStartedAt = 0;
	const running = new Map<string, ToolTrace>();
	let completed: ToolTrace[] = [];

	pi.on("turn_start", async (event) => {
		requestId = randomUUID();
		turnStartedAt = event.timestamp;
		running.clear();
		completed = [];
	});

	pi.on("tool_execution_start", async (event) => {
		running.set(event.toolCallId, {
			tool_call_id: event.toolCallId,
			tool_name: event.toolName,
			started_at: Date.now(),
		});
	});

	pi.on("tool_execution_end", async (event) => {
		const trace = running.get(event.toolCallId);
		if (!trace) return;
		trace.duration_ms = Date.now() - trace.started_at;
		trace.is_error = event.isError;
		completed.push(trace);
		running.delete(event.toolCallId);
	});

	pi.on("turn_end", async (event) => {
		fs.mkdirSync(traceDir, { recursive: true });
		const record = {
			version: "1.0",
			request_id: requestId,
			turn_index: event.turnIndex,
			started_at: turnStartedAt,
			duration_ms: Math.max(0, Date.now() - turnStartedAt),
			tools: completed,
			tool_count: completed.length,
			error_count: completed.filter((tool) => tool.is_error).length,
		};
		fs.appendFileSync(path.join(traceDir, "runtime.jsonl"), `${JSON.stringify(record)}\n`, "utf8");
	});
}
