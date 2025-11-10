// Control Management System
// Tracks active control sources and manages priority

export type ControlSource = 
    | { type: 'manual'; panelId: string }
    | { type: 'group'; groupId: string; panelIds: string[] }
    | { type: 'routine'; routineId: string; routineName: string; panelIds: string[]; stepIndex?: number };

export type ControlState = {
    // Map panel ID to current control source
    panelControls: Map<string, ControlSource>;
    // Track active routines
    activeRoutines: Map<string, { name: string; panelIds: string[]; startTime: number }>;
    // Track active groups
    activeGroups: Map<string, { name: string; panelIds: string[]; startTime: number }>;
};

export class ControlManager {
    private state: ControlState = {
        panelControls: new Map(),
        activeRoutines: new Map(),
        activeGroups: new Map(),
    };

    private listeners: Set<(state: ControlState) => void> = new Set();

    // Priority order: manual > group > routine
    private getPriority(source: ControlSource): number {
        switch (source.type) {
            case 'manual': return 3; // Highest
            case 'group': return 2;
            case 'routine': return 1; // Lowest
        }
    }

    // Take control of panels (respects priority)
    takeControl(source: ControlSource, force = false): { success: boolean; conflicts: string[] } {
        const conflicts: string[] = [];
        const priority = this.getPriority(source);

        let panelIds: string[] = [];
        if (source.type === 'manual') {
            panelIds = [source.panelId];
        } else if (source.type === 'group') {
            panelIds = source.panelIds;
        } else {
            panelIds = source.panelIds;
        }

        for (const panelId of panelIds) {
            const existing = this.state.panelControls.get(panelId);
            if (existing) {
                const existingPriority = this.getPriority(existing);
                if (!force && existingPriority >= priority) {
                    conflicts.push(panelId);
                    continue;
                }
            }
            this.state.panelControls.set(panelId, source);
        }

        // Track active groups/routines
        if (source.type === 'group') {
            this.state.activeGroups.set(source.groupId, {
                name: this.getGroupName(source.groupId) || source.groupId,
                panelIds: source.panelIds,
                startTime: Date.now(),
            });
        } else if (source.type === 'routine') {
            this.state.activeRoutines.set(source.routineId, {
                name: source.routineName,
                panelIds: source.panelIds,
                startTime: Date.now(),
            });
        }

        this.notifyListeners();

        return {
            success: conflicts.length === 0,
            conflicts,
        };
    }

    // Release control
    releaseControl(source: ControlSource): void {
        let panelIds: string[] = [];
        if (source.type === 'manual') {
            panelIds = [source.panelId];
        } else if (source.type === 'group') {
            panelIds = source.panelIds;
            this.state.activeGroups.delete(source.groupId);
        } else {
            panelIds = source.panelIds;
            this.state.activeRoutines.delete(source.routineId);
        }

        for (const panelId of panelIds) {
            const existing = this.state.panelControls.get(panelId);
            if (existing && this.sourcesMatch(existing, source)) {
                this.state.panelControls.delete(panelId);
            }
        }

        this.notifyListeners();
    }

    // Get control source for a panel
    getControlSource(panelId: string): ControlSource | null {
        return this.state.panelControls.get(panelId) || null;
    }

    // Check if a panel is controlled
    isControlled(panelId: string): boolean {
        return this.state.panelControls.has(panelId);
    }

    // Get active controllers
    getActiveControllers(): ControlState {
        return {
            panelControls: new Map(this.state.panelControls),
            activeRoutines: new Map(this.state.activeRoutines),
            activeGroups: new Map(this.state.activeGroups),
        };
    }

    // Subscribe to state changes
    subscribe(listener: (state: ControlState) => void): () => void {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    private notifyListeners(): void {
        const state = this.getActiveControllers();
        this.listeners.forEach(listener => listener(state));
    }

    private sourcesMatch(a: ControlSource, b: ControlSource): boolean {
        if (a.type !== b.type) return false;
        if (a.type === 'manual' && b.type === 'manual') {
            return a.panelId === b.panelId;
        }
        if (a.type === 'group' && b.type === 'group') {
            return a.groupId === b.groupId;
        }
        if (a.type === 'routine' && b.type === 'routine') {
            return a.routineId === b.routineId;
        }
        return false;
    }

    private getGroupName(groupId: string): string | null {
        // This would need to be passed in or fetched
        // For now, return null
        return null;
    }

    // Clear all controls (reset)
    clearAll(): void {
        this.state = {
            panelControls: new Map(),
            activeRoutines: new Map(),
            activeGroups: new Map(),
        };
        this.notifyListeners();
    }
}

// Singleton instance
export const controlManager = new ControlManager();


