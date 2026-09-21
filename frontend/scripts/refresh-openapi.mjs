import { writeFile } from "node:fs/promises";

const argIndex = process.argv.indexOf("--url");
const url = argIndex >= 0 ? process.argv[argIndex + 1] : "http://127.0.0.1:8000/openapi.json";
if (!url) throw new Error("Missing --url value");
const response = await fetch(url);
if (!response.ok) throw new Error(`Could not fetch OpenAPI: ${response.status}`);
const spec = await response.json();
await writeFile(new URL("../contracts/backend-openapi.json", import.meta.url), `${JSON.stringify(spec, null, 2)}\n`);
console.log(`Updated contracts/backend-openapi.json from ${url}`);
