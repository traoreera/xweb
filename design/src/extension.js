"use strict";
const vscode = require("vscode");
const { getCompletions } = require("./completions");

/** @param {vscode.ExtensionContext} context */
function activate(context) {
  const provider = vscode.languages.registerCompletionItemProvider(
    { language: "xdsl" },
    {
      provideCompletionItems(document, position) {
        const textBeforeCursor = document.getText(
          new vscode.Range(new vscode.Position(0, 0), position),
        );
        return getCompletions(textBeforeCursor).map((entry) => {
          const item = new vscode.CompletionItem(
            entry.label,
            entry.insertText && entry.insertText.includes("{")
              ? vscode.CompletionItemKind.Snippet
              : vscode.CompletionItemKind.Property,
          );
          item.insertText = new vscode.SnippetString(entry.insertText || entry.label);
          if (entry.detail) item.detail = entry.detail;
          return item;
        });
      },
    },
    "@", // déclenche aussi sur @ pour les décorateurs (@required, @min_length...)
  );

  context.subscriptions.push(provider);
}

function deactivate() {}

module.exports = { activate, deactivate };
