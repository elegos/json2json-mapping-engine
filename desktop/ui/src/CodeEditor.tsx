import {
  acceptCompletion,
  autocompletion,
  type Completion,
  type CompletionContext,
  startCompletion,
} from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { EditorState, Prec } from "@codemirror/state";
import { EditorView, keymap, tooltips } from "@codemirror/view";
import { type MutableRefObject, useEffect, useRef } from "react";
import type { CompletionItem } from "./api";

/** Asks for the suggestions at a position of the text being edited. */
export type Completer = (
  text: string,
  cursor: number,
) => Promise<{ from: number; items: CompletionItem[] }>;

const KINDS: Record<CompletionItem["kind"], string> = {
  field: "property",
  function: "function",
  label: "variable",
  lookup: "constant",
  alias: "namespace",
  keyword: "keyword",
  value: "variable",
};

/** Characters that open the menu on their own (CodeMirror only does so for letters). */
const TRIGGERS = new Set(["$", "@", ".", "[", "("]);

interface Props {
  value: string;
  /** Completion source; none = a plain text box. */
  completer?: Completer;
  /** A single line commits on Enter; a multi-line editor does not. */
  singleLine?: boolean;
  onChange: (value: string) => void;
  /** Enter (single line) with no menu open. */
  onCommit?: () => void;
  /** Escape with no menu open. */
  onCancel?: () => void;
  /** Focus left the editor (a click elsewhere): the edit is finished. */
  onBlur?: () => void;
  autoFocus?: boolean;
  className?: string;
  /** Receives the editor view, to focus it from outside. */
  viewRef?: MutableRefObject<EditorView | null>;
}

/**
 * A CodeMirror 6 editor with a completion drop-down: ↑↓ move, Enter / Tab accept, Esc closes the
 * menu (a second Esc cancels the edit). The same component serves the one-line grid cells and,
 * later, the multi-line editor of a rule's code override.
 */
export function CodeEditor({
  value,
  completer,
  singleLine = true,
  onChange,
  onCommit,
  onCancel,
  onBlur,
  autoFocus = false,
  className,
  viewRef,
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  // the callbacks change on every render; the editor is created once
  const latest = useRef({ completer, onChange, onCommit, onCancel, onBlur });
  latest.current = { completer, onChange, onCommit, onCancel, onBlur };

  useEffect(() => {
    if (!host.current) return;
    const source = async (context: CompletionContext) => {
      const ask = latest.current.completer;
      if (!ask) return null;
      const text = context.state.doc.toString();
      const typed = context.matchBefore(/[\w$@.\[\]*]*/);
      // nothing typed yet: only offer on demand or after a trigger character
      if (!context.explicit && (!typed || typed.from === typed.to)) return null;
      const { from, items } = await ask(text, context.pos);
      if (context.aborted || items.length === 0) return null;
      const options: Completion[] = items.map((item) => ({
        label: item.insert,
        displayLabel: item.label,
        detail: item.detail,
        type: KINDS[item.kind],
        info: item.doc ? `${item.doc}\n\n(${item.origin})` : undefined,
      }));
      return { from, options, filter: false };
    };
    const triggers = EditorView.updateListener.of((update) => {
      if (!update.docChanged) return;
      update.transactions.forEach((tr) => {
        if (!tr.isUserEvent("input.type")) return;
        const pos = update.state.selection.main.head;
        const last = update.state.doc.sliceString(pos - 1, pos);
        if (TRIGGERS.has(last)) setTimeout(() => startCompletion(update.view), 0);
      });
    });
    const state = EditorState.create({
      doc: value,
      extensions: [
        history(),
        // the menu lives on the page, not inside the cell (which would clip it)
        tooltips({ parent: document.body }),
        autocompletion({ override: [source], activateOnTyping: true, defaultKeymap: true }),
        triggers,
        Prec.high(
          keymap.of([
            {
              key: "Enter",
              run: () => {
                if (!singleLine) return false;
                latest.current.onCommit?.();
                return true;
              },
            },
            { key: "Tab", run: acceptCompletion },
            {
              key: "Escape",
              run: () => {
                latest.current.onCancel?.();
                return true;
              },
            },
          ]),
        ),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        singleLine ? EditorState.transactionFilter.of((tr) => (tr.newDoc.lines > 1 ? [] : tr)) : [],
        EditorView.updateListener.of((u) => {
          if (u.docChanged) latest.current.onChange(u.state.doc.toString());
        }),
        EditorView.lineWrapping,
        EditorView.domEventHandlers({
          blur: (_event, editor) => {
            // a menu click keeps the focus; wait to see where it went
            setTimeout(() => {
              if (!editor.hasFocus) latest.current.onBlur?.();
            }, 0);
          },
        }),
      ],
    });
    const editor = new EditorView({ state, parent: host.current });
    view.current = editor;
    if (viewRef) viewRef.current = editor;
    let frame = 0;
    if (autoFocus) {
      // at once: the grid closes a cell whose focus has not moved into the editor by the time it
      // looks; and once more a frame later, in case the editor was not in the page yet
      const focus = () => {
        if (!editor.hasFocus) editor.focus();
        editor.dispatch({ selection: { anchor: editor.state.doc.length } });
      };
      focus();
      frame = requestAnimationFrame(() => {
        if (!editor.hasFocus) focus();
      });
    }
    return () => {
      cancelAnimationFrame(frame);
      editor.destroy();
    };
    // created once per mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <div ref={host} className={`code-editor ${className ?? ""}`} />;
}
