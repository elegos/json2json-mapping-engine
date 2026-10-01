import type { CustomCellEditorProps } from "ag-grid-react";
import { CodeEditor } from "./CodeEditor";
import type { Row } from "./model";

/** The grid's `context`: how a cell asks for its suggestions. */
export interface GridContext {
  complete?: (
    path: string,
    column: string,
    text: string,
    cursor: number,
  ) => ReturnType<NonNullable<React.ComponentProps<typeof CodeEditor>["completer"]>>;
}

/** Target / Source / Expression cells: a CodeMirror line with the completion drop-down. */
export function CompletingCellEditor(props: CustomCellEditorProps<Row, string, GridContext>) {
  const column = props.column.getColId();
  const complete = props.context?.complete;
  const path = props.data.path;
  // a key that starts the edit replaces the content, as in a plain cell
  const key = props.eventKey;
  const start =
    key && key.length === 1 ? key : key === "Backspace" || key === "Delete" ? "" : (props.value ?? "");
  return (
    <CodeEditor
      value={start}
      autoFocus
      completer={complete ? (text, cursor) => complete(path, column, text, cursor) : undefined}
      onChange={props.onValueChange}
      onCommit={() => props.stopEditing()}
      onCancel={() => props.stopEditing(true)}
    />
  );
}
