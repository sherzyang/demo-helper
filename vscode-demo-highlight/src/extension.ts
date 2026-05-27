import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

const HIGHLIGHTS_FILENAME = ".demo-highlights.json";
const LOG_FILENAME = ".demo-highlight-log.txt";

function log(workspaceFolder: vscode.WorkspaceFolder, msg: string) {
  const logPath = path.join(workspaceFolder.uri.fsPath, LOG_FILENAME);
  const timestamp = new Date().toISOString();
  fs.appendFileSync(logPath, `[${timestamp}] ${msg}\n`);
}

interface HighlightEntry {
  lines: [number, number]; // [startLine, endLine] 1-based inclusive
  style: "box" | "arrow" | "underline" | "highlight";
  color?: string;
  label?: string;
}

let activeDecorations: vscode.TextEditorDecorationType[] = [];
let fileWatcher: vscode.FileSystemWatcher | undefined;
let lastHighlightsContent = "";
let reapplyTimeout: NodeJS.Timeout | undefined;
let reapplyTimeout2: NodeJS.Timeout | undefined;

function scheduleReapply(context: vscode.ExtensionContext) {
  if (reapplyTimeout) { clearTimeout(reapplyTimeout); }
  if (reapplyTimeout2) { clearTimeout(reapplyTimeout2); }
  reapplyTimeout = setTimeout(() => {
    lastHighlightsContent = "";
    applyHighlights(context);
  }, 500);
  reapplyTimeout2 = setTimeout(() => {
    lastHighlightsContent = "";
    applyHighlights(context);
  }, 1500);
}

export function activate(context: vscode.ExtensionContext) {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) {
    // Write log to a fallback location to confirm activation happened
    const fallback = path.join(context.extensionPath, "activation-no-workspace.log");
    fs.writeFileSync(fallback, `Activated at ${new Date().toISOString()} but no workspace folder\n`);
    return;
  }

  log(workspaceFolder, "Extension activated. Workspace: " + workspaceFolder.uri.fsPath);

  const pattern = new vscode.RelativePattern(workspaceFolder, HIGHLIGHTS_FILENAME);

  fileWatcher = vscode.workspace.createFileSystemWatcher(pattern);
  fileWatcher.onDidChange(() => { log(workspaceFolder, "FileWatcher: onDidChange"); lastHighlightsContent = ""; applyHighlights(context); scheduleReapply(context); });
  fileWatcher.onDidCreate(() => { log(workspaceFolder, "FileWatcher: onDidCreate"); lastHighlightsContent = ""; applyHighlights(context); scheduleReapply(context); });
  fileWatcher.onDidDelete(() => { log(workspaceFolder, "FileWatcher: onDidDelete"); lastHighlightsContent = ""; clearAllDecorations(); });

  // Re-apply highlights whenever the active editor changes (backup trigger)
  const editorListener = vscode.window.onDidChangeActiveTextEditor((editor) => {
    log(workspaceFolder, "EditorChange: " + (editor?.document.uri.fsPath ?? "null"));
    lastHighlightsContent = ""; // Force re-read on editor change
    applyHighlights(context);
    scheduleReapply(context); // Re-apply after 1s when editor is fully rendered
  });

  // Re-apply when visible ranges change — fires when editor viewport is first laid out
  // This is critical for the first editor in a new window where setDecorations is a no-op until layout
  let visibleRangesTimeout: NodeJS.Timeout | undefined;
  const visibleRangesListener = vscode.window.onDidChangeTextEditorVisibleRanges((e) => {
    if (visibleRangesTimeout) { clearTimeout(visibleRangesTimeout); }
    visibleRangesTimeout = setTimeout(() => {
      log(workspaceFolder, "VisibleRanges: " + e.textEditor.document.uri.fsPath);
      lastHighlightsContent = "";
      applyHighlights(context);
    }, 100);
  });

  // Poll for highlight file changes every 500ms as a reliable fallback
  const pollInterval = setInterval(() => {
    applyHighlights(context);
  }, 500);

  context.subscriptions.push(fileWatcher);
  context.subscriptions.push(editorListener);
  context.subscriptions.push(visibleRangesListener);
  context.subscriptions.push({ dispose: () => clearInterval(pollInterval) });
  context.subscriptions.push(
    vscode.commands.registerCommand("demoHighlight.clear", clearAllDecorations)
  );

  // Apply on activation in case file already exists
  applyHighlights(context);
}

export function deactivate() {
  clearAllDecorations();
}

function clearAllDecorations() {
  for (const dec of activeDecorations) {
    dec.dispose();
  }
  activeDecorations = [];
}

function applyHighlights(context: vscode.ExtensionContext) {
  const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
  if (!workspaceFolder) {
    return;
  }

  const highlightsPath = path.join(
    workspaceFolder.uri.fsPath,
    HIGHLIGHTS_FILENAME
  );

  if (!fs.existsSync(highlightsPath)) {
    if (lastHighlightsContent !== "") {
      lastHighlightsContent = "";
      clearAllDecorations();
    }
    return;
  }

  let raw: string;
  let entries: HighlightEntry[];
  try {
    raw = fs.readFileSync(highlightsPath, "utf-8");
    entries = JSON.parse(raw);
  } catch {
    return; // Invalid JSON or read error — silently skip
  }

  // Skip if content hasn't changed and decorations are already applied
  const editorUri = vscode.window.activeTextEditor?.document.uri.toString() ?? "";
  const cacheKey = raw + "|" + editorUri;
  if (cacheKey === lastHighlightsContent && activeDecorations.length > 0) {
    return;
  }
  lastHighlightsContent = cacheKey;

  clearAllDecorations();

  if (!Array.isArray(entries) || entries.length === 0) {
    log(workspaceFolder, "applyHighlights: entries empty or not array");
    return;
  }

  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    log(workspaceFolder, "applyHighlights: no active editor");
    return;
  }

  log(workspaceFolder, `applyHighlights: applying ${entries.length} entries to ${editor.document.uri.fsPath}`);

  for (const entry of entries) {
    const decorationType = createDecorationType(entry, context);
    if (!decorationType) {
      continue;
    }

    const startLine = Math.max(0, entry.lines[0] - 1); // Convert 1-based to 0-based
    const endLine = Math.max(startLine, entry.lines[1] - 1);

    const range = new vscode.Range(
      new vscode.Position(startLine, 0),
      new vscode.Position(endLine, Number.MAX_SAFE_INTEGER)
    );

    editor.setDecorations(decorationType, [{ range }]);
    activeDecorations.push(decorationType);
  }
}

function createDecorationType(
  entry: HighlightEntry,
  context: vscode.ExtensionContext
): vscode.TextEditorDecorationType | undefined {
  switch (entry.style) {
    case "box":
      return vscode.window.createTextEditorDecorationType({
        isWholeLine: true,
        backgroundColor: entry.color || "#FFD70044",
        border: `2px solid ${stripAlpha(entry.color || "#FFD700")}`,
        borderRadius: "3px",
      });

    case "arrow":
      return vscode.window.createTextEditorDecorationType({
        isWholeLine: true,
        gutterIconPath: vscode.Uri.file(
          path.join(context.extensionPath, "assets", "arrow.svg")
        ),
        gutterIconSize: "contain",
        backgroundColor: entry.color || "#90EE9022",
      });

    case "underline":
      return vscode.window.createTextEditorDecorationType({
        isWholeLine: true,
        borderWidth: "0 0 2px 0",
        borderStyle: "solid",
        borderColor: entry.color || "#FF6347",
      });

    case "highlight":
      return vscode.window.createTextEditorDecorationType({
        isWholeLine: true,
        backgroundColor: entry.color || "#87CEEB33",
      });

    default:
      return undefined;
  }
}

/**
 * Strip alpha channel from hex color for use in border (borders don't support alpha).
 * e.g. "#FFD70044" → "#FFD700"
 */
function stripAlpha(color: string): string {
  if (color.startsWith("#") && color.length === 9) {
    return color.slice(0, 7);
  }
  return color;
}
