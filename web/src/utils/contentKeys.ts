/**
 * Pair each item with a React key built from its content instead of its array
 * index. Items with identical content get an occurrence suffix (#2, #3, ...),
 * so the keys stay unique and stay the same when new items are appended.
 */
export function withContentKeys<T>(
    items: readonly T[],
    contentKey: (item: T) => string,
): { key: string; item: T }[] {
    const seen = new Map<string, number>();
    return items.map((item) => {
        const base = contentKey(item);
        const count = (seen.get(base) ?? 0) + 1;
        seen.set(base, count);
        return { key: count === 1 ? base : `${base}#${count}`, item };
    });
}
