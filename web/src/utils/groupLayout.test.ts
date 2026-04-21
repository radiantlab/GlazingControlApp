import { describe, expect, it } from "vitest";

import { buildDefaultGroupLayout, normalizeGroupLayout } from "./groupLayout";

describe("groupLayout utilities", () => {
    it("builds a default layout in row-major order", () => {
        expect(buildDefaultGroupLayout(["P01", "P02", "P03"], 2)).toEqual({
            columns: 2,
            items: [
                { panel_id: "P01", row: 1, column: 1 },
                { panel_id: "P02", row: 1, column: 2 },
                { panel_id: "P03", row: 2, column: 1 },
            ],
        });
    });

    it("normalizes collisions and fills missing member positions", () => {
        expect(
            normalizeGroupLayout(["P01", "P02", "P03"], {
                columns: 2,
                items: [
                    { panel_id: "P01", row: 1, column: 1 },
                    { panel_id: "P02", row: 1, column: 1 },
                ],
            }),
        ).toEqual({
            columns: 2,
            items: [
                { panel_id: "P01", row: 1, column: 1 },
                { panel_id: "P02", row: 1, column: 2 },
                { panel_id: "P03", row: 2, column: 1 },
            ],
        });
    });

    it("caps layouts at eight columns", () => {
        expect(buildDefaultGroupLayout(["P01"], 12)?.columns).toBe(8);
        expect(normalizeGroupLayout(["P01"], { columns: 12, items: [] })?.columns).toBe(8);
    });

    it("preserves explicit empty rows", () => {
        expect(
            normalizeGroupLayout(["P01"], {
                columns: 2,
                rows: 3,
                items: [{ panel_id: "P01", row: 1, column: 1 }],
            }),
        ).toEqual({
            columns: 2,
            rows: 3,
            items: [{ panel_id: "P01", row: 1, column: 1 }],
        });
    });

    it("normalizes divider metadata inside the saved layout bounds", () => {
        expect(
            normalizeGroupLayout(["P01", "P02"], {
                columns: 2,
                rows: 2,
                items: [
                    { panel_id: "P01", row: 1, column: 1 },
                    { panel_id: "P02", row: 1, column: 2 },
                ],
                dividers: {
                    vertical: [
                        { row: 1, column: 1 },
                        { row: 1, column: 1 },
                        { row: 3, column: 1 },
                    ],
                    horizontal: [
                        { row: 1, column: 1 },
                        { row: 1, column: 3 },
                    ],
                },
            }),
        ).toEqual({
            columns: 2,
            rows: 2,
            items: [
                { panel_id: "P01", row: 1, column: 1 },
                { panel_id: "P02", row: 1, column: 2 },
            ],
            dividers: {
                vertical: [{ row: 1, column: 1 }],
                horizontal: [{ row: 1, column: 1 }],
            },
        });
    });
});
