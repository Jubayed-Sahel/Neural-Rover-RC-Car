import fs from "node:fs";

const tex = fs.readFileSync("report.tex", "utf8");
const bib = fs.readFileSync("references.bib", "utf8");

const withoutComments = tex
  .split(/\r?\n/)
  .map((line) => line.replace(/(^|[^\\])%.*/, "$1"))
  .join("\n");

let depth = 0;
for (let i = 0; i < withoutComments.length; i += 1) {
  const char = withoutComments[i];
  const escaped = i > 0 && withoutComments[i - 1] === "\\";
  if (!escaped && char === "{") depth += 1;
  if (!escaped && char === "}") depth -= 1;
  if (depth < 0) throw new Error(`Unexpected closing brace at character ${i}.`);
}
if (depth !== 0) throw new Error(`Unbalanced braces: final depth ${depth}.`);

const stack = [];
for (const match of withoutComments.matchAll(/\\(begin|end)\{([^}]+)\}/g)) {
  const [, kind, environment] = match;
  if (kind === "begin") {
    stack.push(environment);
  } else {
    const open = stack.pop();
    if (open !== environment) {
      throw new Error(`Environment mismatch: expected ${open}, found ${environment}.`);
    }
  }
}
if (stack.length) throw new Error(`Unclosed environments: ${stack.join(", ")}.`);

const bibKeys = new Set(
  [...bib.matchAll(/@\w+\{([^,]+),/g)].map((match) => match[1].trim())
);
const citeKeys = new Set();
for (const match of withoutComments.matchAll(/\\cite\{([^}]+)\}/g)) {
  for (const key of match[1].split(",")) citeKeys.add(key.trim());
}
const missing = [...citeKeys].filter((key) => !bibKeys.has(key));
if (missing.length) throw new Error(`Missing bibliography keys: ${missing.join(", ")}.`);

const images = [...withoutComments.matchAll(/\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}/g)]
  .map((match) => match[1]);
for (const image of images) {
  if (!fs.existsSync(image)) throw new Error(`Missing image: ${image}`);
}

console.log(
  JSON.stringify(
    {
      lines: tex.split(/\r?\n/).length,
      chapters: [...withoutComments.matchAll(/\\chapter\*?\{/g)].length,
      figures: images.length,
      citations: citeKeys.size,
      bibliographyEntries: bibKeys.size,
      status: "structurally valid",
    },
    null,
    2
  )
);
