// What the start wizard says about each field. Kept as data, apart from the components: the
// guide quotes the same sentences.

export const WIZARD_TEXTS = {
  recent: "Projects opened lately. A greyed folder is no longer there.",
  projectFolder:
    "The folder that will hold the project: its mapper.toml, schemas, mappings and functions. Create or pick an empty one.",
  backend:
    "The language the mappings are turned into and run in (for example PL/SQL). It can be changed later in the Project properties; the settings of the backend you leave are kept.",
  mappingName:
    "What the mapping is called in the tool and on disk. It names its files and the generated code; it can be renamed later.",
  inputSchema:
    "A JSON Schema describing the JSON the mapping reads. It feeds the suggestions for Source and the checks. Optional: it can be added later.",
  outputSchema:
    "A JSON Schema describing the JSON the mapping produces. It lists the fields to fill in. Optional: it can be added later.",
  prefill:
    "Create an empty rule for each field of the output schema, so only the Sources are left to write.",
  projectReady:
    "The settings of the project (the backend and its options, the optimizer, the compiler) are in Project properties…, " +
    "the button at the top of the list of mappings. Open them now to look at them?",
} as const;
