import type { ITooltipParams } from "ag-grid-community";

/** The tooltip of the Description and Notes cells: the whole text, line breaks kept, in a
 *  speech-bubble box that scrolls when it is long (the grid lets the pointer move onto it). */
export function RuleTip(params: ITooltipParams) {
  const text = String(params.value ?? "");
  if (!text) return null;
  return <div className="rule-tip">{text}</div>;
}
