import type { Panel, Group } from "./api";

// Mock panels data - 18 wall panels (P01-P18) and 2 skylights (SK1, SK2) = 20 total
export const mockPanels: Panel[] = [
    // Room 1 - Wall panels (P01-P09)
    { id: "P01", name: "Facade 1", group_id: "G-facade", level: 50, last_change_ts: Date.now() / 1000 - 3600 },
    { id: "P02", name: "Facade 2", group_id: "G-facade", level: 55, last_change_ts: Date.now() / 1000 - 3300 },
    { id: "P03", name: "Facade 3", group_id: "G-facade", level: 0, last_change_ts: Date.now() / 1000 - 7200 },
    { id: "P04", name: "Facade 4", group_id: "G-facade", level: 25, last_change_ts: Date.now() / 1000 - 1800 },
    { id: "P05", name: "Facade 5", group_id: "G-facade", level: 0, last_change_ts: Date.now() / 1000 - 5400 },
    { id: "P06", name: "Facade 6", group_id: "G-facade", level: 75, last_change_ts: Date.now() / 1000 - 900 },
    { id: "P07", name: "Facade 7", group_id: "G-facade", level: 100, last_change_ts: Date.now() / 1000 - 450 },
    { id: "P08", name: "Facade 8", group_id: "G-facade", level: 50, last_change_ts: Date.now() / 1000 - 2700 },
    { id: "P09", name: "Facade 9", group_id: "G-facade", level: 0, last_change_ts: Date.now() / 1000 - 6000 },
    
    // Room 2 - Wall panels (P10-P18)
    { id: "P10", name: "Facade 10", group_id: "G-facade", level: 30, last_change_ts: Date.now() / 1000 - 2100 },
    { id: "P11", name: "Facade 11", group_id: "G-facade", level: 0, last_change_ts: Date.now() / 1000 - 4800 },
    { id: "P12", name: "Facade 12", group_id: "G-facade", level: 60, last_change_ts: Date.now() / 1000 - 1200 },
    { id: "P13", name: "Facade 13", group_id: "G-facade", level: 40, last_change_ts: Date.now() / 1000 - 2400 },
    { id: "P14", name: "Facade 14", group_id: "G-facade", level: 0, last_change_ts: Date.now() / 1000 - 6600 },
    { id: "P15", name: "Facade 15", group_id: "G-facade", level: 80, last_change_ts: Date.now() / 1000 - 600 },
    { id: "P16", name: "Facade 16", group_id: "G-facade", level: 20, last_change_ts: Date.now() / 1000 - 3000 },
    { id: "P17", name: "Facade 17", group_id: "G-facade", level: 0, last_change_ts: Date.now() / 1000 - 5100 },
    { id: "P18", name: "Facade 18", group_id: "G-facade", level: 45, last_change_ts: Date.now() / 1000 - 1500 },
    
    // Skylights
    { id: "SK1", name: "Skylight 1", group_id: "G-skylights", level: 0, last_change_ts: Date.now() / 1000 - 7800 },
    { id: "SK2", name: "Skylight 2", group_id: "G-skylights", level: 25, last_change_ts: Date.now() / 1000 - 4200 },
];

export const mockGroups: Group[] = [
    {
        id: "G-facade",
        name: "Facade",
        member_ids: Array.from({ length: 18 }, (_, i) => `P${String(i + 1).padStart(2, '0')}`)
    },
    {
        id: "G-skylights",
        name: "Skylights",
        member_ids: ["SK1", "SK2"]
    }
];

// Simulate API delay
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

// Mock API that stores state locally
let mockPanelState = [...mockPanels];

export const mockApi = {
    async panels(): Promise<Panel[]> {
        await delay(200);
        return [...mockPanelState];
    },
    
    async groups(): Promise<Group[]> {
        await delay(100);
        return [...mockGroups];
    },
    
    async createGroup(name: string, memberIds: string[]): Promise<Group> {
        await delay(300);
        // Generate unique group ID
        const existingIds = new Set(mockGroups.map(g => g.id));
        let groupNum = 1;
        while (existingIds.has(`G-${groupNum}`)) {
            groupNum++;
        }
        const groupId = `G-${groupNum}`;
        
        // Validate panel IDs
        const validPanelIds = memberIds.filter(id => mockPanelState.some(p => p.id === id));
        if (validPanelIds.length !== memberIds.length) {
            throw new Error("One or more panel IDs not found");
        }
        
        const newGroup: Group = {
            id: groupId,
            name,
            member_ids: validPanelIds
        };
        mockGroups.push(newGroup);
        return newGroup;
    },
    
    async health(): Promise<{ status: string; mode: string }> {
        await delay(50);
        return { status: "ok", mode: "mock" };
    },
    
    async setPanelLevel(panelId: string, level: number): Promise<{ ok: boolean; applied_to: string[]; message: string }> {
        await delay(300);
        const panel = mockPanelState.find(p => p.id === panelId);
        if (!panel) {
            throw new Error("panel not found");
        }
        panel.level = level;
        panel.last_change_ts = Date.now() / 1000;
        return {
            ok: true,
            applied_to: [panelId],
            message: `Panel ${panelId} set to ${level}%`
        };
    },
    
    async setGroupLevel(groupId: string, level: number): Promise<{ ok: boolean; applied_to: string[]; message: string }> {
        await delay(400);
        const group = mockGroups.find(g => g.id === groupId);
        if (!group) {
            throw new Error("group not found");
        }
        const applied: string[] = [];
        group.member_ids.forEach(id => {
            const panel = mockPanelState.find(p => p.id === id);
            if (panel) {
                panel.level = level;
                panel.last_change_ts = Date.now() / 1000;
                applied.push(id);
            }
        });
        return {
            ok: true,
            applied_to: applied,
            message: `Group ${groupId} set to ${level}%`
        };
    }
};

