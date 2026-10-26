// Check that JSON files load: node scripts/ci/check_json.mjs <files...>
// A .jsonc file may hold // and /* */ comments and trailing commas, as wrangler.jsonc does.
import { readFileSync } from "node:fs";

function stripJsonc(text) {
  let out = "", i = 0, inString = false;
  while (i < text.length) {
    const c = text[i], next = text[i + 1];
    if (inString) {
      out += c;
      if (c === "\\") { out += next ?? ""; i += 2; continue; }
      if (c === '"') inString = false;
      i++;
    } else if (c === '"') { inString = true; out += c; i++; }
    else if (c === "/" && next === "/") { while (i < text.length && text[i] !== "\n") i++; }
    else if (c === "/" && next === "*") { i = text.indexOf("*/", i + 2); i = i < 0 ? text.length : i + 2; }
    else { out += c; i++; }
  }
  return out.replace(/,(\s*[}\]])/g, "$1");
}

let bad = 0;
for (const file of process.argv.slice(2)) {
  const text = readFileSync(file, "utf8");
  try {
    JSON.parse(file.endsWith(".jsonc") ? stripJsonc(text) : text);
  } catch (e) {
    console.log(`${file}: ${e.message}`);
    bad++;
  }
}
process.exit(bad ? 1 : 0);
