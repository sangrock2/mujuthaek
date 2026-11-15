// Scanner databases can lag behind vendor advisories. Keep reviewed security floors too.
const assert = require("node:assert/strict");

function meetsMinimum(actual, minimum) {
  if (!/^\d+\.\d+\.\d+$/.test(actual)) return false;
  const a = actual.split(".").map(Number);
  const b = minimum.split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return true;
}

if (require.main === module) {
  // Next includes its own RSC build; changing only react/react-dom is insufficient.
  for (const [name, floor] of Object.entries({
    next: "16.4.6",
    react: "19.3.1",
    "react-dom": "19.3.1",
  })) {
    const actual = require(`${name}/package.json`).version;
    assert(
      meetsMinimum(actual, floor),
      `${name}@${actual} is below the reviewed security baseline ${floor}`,
    );
  }
  console.log("Reviewed framework security baselines passed.");
}

module.exports = { meetsMinimum };
