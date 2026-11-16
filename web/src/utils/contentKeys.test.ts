import { describe, expect, it } from "vitest";
import { withContentKeys } from "./contentKeys";

describe("withContentKeys", () => {
    it("keys unique items by their content", () => {
        expect(withContentKeys(["a", "b"], (s) => s).map((x) => x.key)).toEqual(["a", "b"]);
    });

    it("suffixes repeated content so keys stay unique", () => {
        expect(withContentKeys(["a", "b", "a", "a"], (s) => s).map((x) => x.key)).toEqual([
            "a",
            "b",
            "a#2",
            "a#3",
        ]);
    });

    it("keeps existing keys unchanged when items are appended", () => {
        const before = withContentKeys(["x", "x"], (s) => s).map((x) => x.key);
        const after = withContentKeys(["x", "x", "x"], (s) => s).map((x) => x.key);
        expect(after.slice(0, 2)).toEqual(before);
    });

    it("returns the original items", () => {
        const rows = [{ id: 1 }, { id: 2 }];
        expect(withContentKeys(rows, (r) => String(r.id)).map((x) => x.item)).toEqual(rows);
    });
});
